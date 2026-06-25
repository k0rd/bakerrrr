import json
import math
import random
from collections import Counter
from pathlib import Path

from engine.sites import site_gameplay_profile
from game.content_warnings import warn_content_fallback
from game.npc_names import CATALOG as NPC_NAME_CATALOG, DEFAULT_NAME_CATALOG
from game.property_access import FINANCE_SERVICE_FALLBACKS, default_site_services_for_archetype


BUSINESS_NAME_DATA_PATH = Path(__file__).resolve().parent.parent / "game" / "business_names.json"


def normalize_building_levels(archetype, floors, basement_levels):
    archetype = str(archetype or "").strip().lower()
    try:
        floors = int(floors)
    except (TypeError, ValueError):
        floors = 1
    try:
        basement_levels = int(basement_levels)
    except (TypeError, ValueError):
        basement_levels = 0
    floors = max(1, floors)
    basement_levels = max(0, basement_levels)

    # Transit exchanges work better as true station stacks than as office-like
    # towers with a token basement. Keep them street-level with a deeper platform.
    if archetype == "metro_exchange":
        floors = 1
        basement_levels = max(2, basement_levels)

    return floors, basement_levels


class World:
    RUNTIME_ONLY_STATE_KEYS = {
        "business_name_data",
        "buildings_by_district",
        "building_archetypes",
        "career_pool",
        "custom_world_profiles",
        "_overworld_region_cache",
    }

    AREA_TYPES = (
        "city",
        "frontier",
        "wilderness",
        "coastal",
    )

    DISTRICT_TYPES = (
        "industrial",
        "residential",
        "downtown",
        "slums",
        "corporate",
        "military",
        "entertainment",
    )

    OVERWORLD_REGION_SIZE = 18
    OVERWORLD_REGION_MARGIN = 3
    OVERWORLD_URBAN_NOISE_SCALE = 2.2
    OVERWORLD_RIDGE_NOISE_SCALE = 1.7
    OVERWORLD_COAST_NOISE_SCALE = 2.8
    OVERWORLD_WILD_NOISE_SCALE = 2.6
    OVERWORLD_CITY_CORE_THRESHOLD = 0.88
    OVERWORLD_CITY_CORE_WILD_CAP = 0.48
    OVERWORLD_CITY_EDGE_THRESHOLD = 0.82
    OVERWORLD_CITY_EDGE_RIDGE_THRESHOLD = 0.64
    OVERWORLD_CITY_EDGE_WILD_CAP = 0.52
    OVERWORLD_COAST_CORE_THRESHOLD = 0.80
    OVERWORLD_COAST_EDGE_THRESHOLD = 0.72
    OVERWORLD_WILDERNESS_THRESHOLD = 0.58
    OVERWORLD_FRONTIER_URBAN_THRESHOLD = 0.68
    OVERWORLD_DISTRICT_CELL_SIZE = 3
    OVERWORLD_TERRAIN_DEFAULT = {
        "city": "urban",
        "frontier": "scrub",
        "wilderness": "plains",
        "coastal": "shore",
    }
    OVERWORLD_TERRAIN_VARIANTS = {
        "city": ("urban", "urban", "park", "industrial_waste"),
        "frontier": ("scrub", "plains", "badlands", "hills"),
        "wilderness": ("forest", "forest", "hills", "marsh", "plains", "lake", "waterway"),
        "coastal": ("shore", "shoals", "dunes", "cliffs", "salt_flats", "island", "ocean"),
    }
    OVERWORLD_LANDMARK_TEMPLATES = (
        {
            "id": "ancient_grove",
            "name": "Ancient Grove",
            "glyph": "G",
            "terrain": "forest",
            "color": "insect",
            "radius_min": 5,
            "radius_max": 9,
        },
        {
            "id": "stone_spine",
            "name": "Stone Spine",
            "glyph": "A",
            "terrain": "hills",
            "color": "guard",
            "radius_min": 5,
            "radius_max": 8,
        },
        {
            "id": "crater_lake",
            "name": "Crater Lake",
            "glyph": "L",
            "terrain": "lake",
            "color": "avian",
            "radius_min": 4,
            "radius_max": 7,
        },
        {
            "id": "shatter_ruins",
            "name": "Shatter Ruins",
            "glyph": "U",
            "terrain": "ruins",
            "color": "cat_purple",
            "radius_min": 4,
            "radius_max": 7,
        },
        {
            "id": "red_dunes",
            "name": "Red Dunes",
            "glyph": "D",
            "terrain": "dunes",
            "color": "cat_orange",
            "radius_min": 5,
            "radius_max": 8,
        },
        {
            "id": "glass_marsh",
            "name": "Glass Marsh",
            "glyph": "M",
            "terrain": "marsh",
            "color": "insect",
            "radius_min": 5,
            "radius_max": 8,
        },
        {
            "id": "radio_spire",
            "name": "Radio Spire",
            "glyph": "R",
            "terrain": "hills",
            "color": "player",
            "radius_min": 4,
            "radius_max": 7,
        },
        {
            "id": "sunken_drydock",
            "name": "Sunken Drydock",
            "glyph": "K",
            "terrain": "ruins",
            "color": "item_tool",
            "radius_min": 4,
            "radius_max": 7,
        },
        {
            "id": "white_quarry",
            "name": "White Quarry",
            "glyph": "Q",
            "terrain": "salt_flats",
            "color": "human",
            "radius_min": 5,
            "radius_max": 8,
        },
        {
            "id": "storm_break",
            "name": "Storm Break",
            "glyph": "S",
            "terrain": "shore",
            "color": "objective",
            "radius_min": 5,
            "radius_max": 8,
        },
    )
    OVERWORLD_REGION_PREFIXES = (
        "Ash", "Black", "Blue", "Broken", "Cinder", "Copper", "Drift", "East",
        "Ember", "First", "Grand", "Gray", "High", "Iron", "Lower", "North",
        "Old", "Outer", "Red", "River", "Rust", "Salt", "Silver", "South",
        "Stone", "Sun", "Upper", "West", "White", "Wild",
    )
    OVERWORLD_REGION_SUFFIX_BY_AREA = {
        "city": ("Basin", "Belt", "District", "Grid", "Quarter", "Span"),
        "frontier": ("March", "Range", "Reach", "Scrub", "Steppe", "Tract"),
        "wilderness": ("Deep", "Expanse", "Hinterland", "Wilds", "Wood"),
        "coastal": ("Coast", "Inlet", "Shore", "Sound", "Tidelands"),
    }
    SETTLEMENT_PREFIXES = (
        "Amber", "Bridge", "Copper", "Crown", "Dock", "Grand", "Gray", "Harbor",
        "Iron", "Lake", "Metro", "New", "North", "Old", "Port", "River",
        "South", "Stone", "Union", "West",
    )
    SETTLEMENT_ROOTS = (
        "Anchor", "Arc", "Bay", "Bridge", "Cross", "Field", "Gate", "Grove",
        "Haven", "Hill", "Junction", "Market", "Moor", "Point", "Reach", "Spire",
        "Station", "Vale", "Vista", "Yard",
    )
    SETTLEMENT_SUFFIXES = (
        "City", "Crossing", "Heights", "Landing", "Point", "Springs", "Station", "Ward",
    )

    NON_CITY_SITE_POOLS = {
        "frontier": (
            "relay_post",
            "roadhouse",
            "butcher_shop",
            "outfitter",
            "surplus_store",
            "salvage_camp",
            "pump_house",
            "work_shed",
            "truck_stop",
            "breaker_yard",
        ),
        "wilderness": (
            "field_camp",
            "survey_post",
            "ranger_hut",
            "butcher_shop",
            "outfitter",
            "ruin_shelter",
            "lookout_post",
        ),
        "coastal": (
            "dock_shack",
            "ferry_post",
            "tide_station",
            "net_house",
            "beacon_house",
            "bait_shop",
            "butcher_shop",
            "drydock_yard",
            "coast_watch",
        ),
    }

    NON_CITY_SITE_LABELS = {
        "relay_post": "Relay Post",
        "roadhouse": "Roadhouse",
        "outfitter": "Outfitter",
        "surplus_store": "Surplus Store",
        "truck_stop": "Truck Stop",
        "inspection_shed": "Inspection Shed",
        "breaker_yard": "Breaker Yard",
        "butcher_shop": "Butcher Shop",
        "salvage_camp": "Salvage Camp",
        "pump_house": "Pump House",
        "work_shed": "Work Shed",
        "field_camp": "Field Camp",
        "survey_post": "Survey Post",
        "ranger_hut": "Ranger Hut",
        "ruin_shelter": "Ruin Shelter",
        "lookout_post": "Lookout Post",
        "firewatch_tower": "Firewatch Tower",
        "weather_station": "Weather Station",
        "herbalist_camp": "Herbalist Camp",
        "flea_market": "Flea Market",
        "dock_shack": "Dock Shack",
        "ferry_post": "Ferry Post",
        "tide_station": "Tide Station",
        "net_house": "Net House",
        "beacon_house": "Beacon House",
        "bait_shop": "Bait Shop",
        "drydock_yard": "Drydock Yard",
        "coast_watch": "Coast Watch",
    }

    NON_CITY_SITE_GLYPHS = {
        "relay_post": "R",
        "roadhouse": "H",
        "outfitter": "O",
        "surplus_store": "S",
        "truck_stop": "T",
        "inspection_shed": "I",
        "breaker_yard": "B",
        "butcher_shop": "B",
        "salvage_camp": "S",
        "pump_house": "P",
        "work_shed": "W",
        "field_camp": "C",
        "survey_post": "Y",
        "ranger_hut": "H",
        "ruin_shelter": "U",
        "lookout_post": "L",
        "firewatch_tower": "F",
        "weather_station": "W",
        "herbalist_camp": "H",
        "flea_market": "M",
        "dock_shack": "D",
        "ferry_post": "F",
        "tide_station": "T",
        "net_house": "N",
        "beacon_house": "B",
        "bait_shop": "B",
        "drydock_yard": "Y",
        "coast_watch": "C",
    }

    NON_CITY_SITE_COLORS = {
        "relay_post": "player",
        "roadhouse": "cat_orange",
        "outfitter": "cat_orange",
        "surplus_store": "item_tool",
        "truck_stop": "cat_orange",
        "inspection_shed": "guard",
        "breaker_yard": "item_tool",
        "butcher_shop": "cat_orange",
        "salvage_camp": "item_tool",
        "pump_house": "guard",
        "work_shed": "human",
        "field_camp": "insect",
        "survey_post": "player",
        "ranger_hut": "insect",
        "ruin_shelter": "cat_purple",
        "lookout_post": "guard",
        "firewatch_tower": "player",
        "weather_station": "player",
        "herbalist_camp": "insect",
        "flea_market": "cat_orange",
        "dock_shack": "avian",
        "ferry_post": "objective",
        "tide_station": "avian",
        "net_house": "human",
        "beacon_house": "objective",
        "bait_shop": "avian",
        "drydock_yard": "item_tool",
        "coast_watch": "guard",
    }

    PUBLIC_NON_CITY_SITE_KINDS = {
        "relay_post",
        "roadhouse",
        "outfitter",
        "surplus_store",
        "truck_stop",
        "inspection_shed",
        "ranger_hut",
        "dock_shack",
        "ferry_post",
        "tide_station",
        "firewatch_tower",
        "weather_station",
        "herbalist_camp",
        "flea_market",
        "breaker_yard",
        "butcher_shop",
        "drydock_yard",
        "salvage_camp",
        "net_house",
        "bait_shop",
        "coast_watch",
    }
    VERTICAL_MIXED_USE_CHANCE_BY_DISTRICT = {
        "residential": 0.018,
        "downtown": 0.055,
        "slums": 0.045,
        "corporate": 0.052,
        "entertainment": 0.05,
    }
    INDOOR_CITY_MARKET_CHANCE_BY_DISTRICT = {
        "downtown": 0.14,
        "slums": 0.16,
        "entertainment": 0.15,
        "industrial": 0.08,
        "residential": 0.05,
    }
    NON_CITY_COMPOUND_MARKET_CHANCE_BY_AREA = {
        "frontier": 0.18,
        "wilderness": 0.12,
        "coastal": 0.16,
    }
    VERTICAL_MIXED_USE_PARENT_ARCHETYPES = {
        "apartment",
        "bank",
        "brokerage",
        "co_working_hub",
        "hotel",
        "office",
        "tenement",
        "tower",
    }
    VERTICAL_MIXED_USE_TENANT_WEIGHTS = (
        "office",
        "office",
        "pharmacy",
        "backroom_clinic",
        "hair_studio",
        "makeup_counter",
        "top_shop",
        "shoe_shop",
        "clothing_superstore",
        "jewelry_shop",
        "bookshop",
        "hardware_store",
        "employment_agency",
        "pawn_shop",
        "restaurant",
        "tavern",
        "co_working_hub",
        "brokerage",
    )
    VERTICAL_MIXED_USE_HOUSING_WEIGHTS = (
        "apartment",
        "tenement",
        "flophouse",
        "hotel",
    )
    VERTICAL_MIXED_USE_SPAN_SUFFIXES = (
        "Arcade",
        "Building",
        "Center",
        "Chambers",
        "City",
        "Court",
        "Exchange",
        "Flats",
        "Galleria",
        "Gardens",
        "Hall",
        "House",
        "Landing",
        "Lofts",
        "Plaza",
        "Square",
        "Terrace",
        "Tower",
        "Walk",
    )
    INDOOR_CITY_MARKET_SPAN_SUFFIXES = (
        "Arcade",
        "Bazaar",
        "Exchange",
        "Food Hall",
        "Galleria",
        "Market",
        "Market Hall",
        "Public Market",
        "Swap Hall",
    )
    INDOOR_CITY_MARKET_TENANT_WEIGHTS = (
        "restaurant",
        "street_kitchen",
        "top_shop",
        "bottom_shop",
        "shoe_shop",
        "outerwear_shop",
        "headwear_shop",
        "clothing_superstore",
        "accessory_shop",
        "jewelry_shop",
        "makeup_counter",
        "hair_studio",
        "tattoo_parlor",
        "pawn_shop",
        "thrift_store",
        "outfitter",
        "hardware_store",
        "tool_depot",
        "pharmacy",
        "backroom_clinic",
        "arcade",
        "bookshop",
        "tavern",
        "courier_office",
        "employment_agency",
        "bank",
    )
    NON_CITY_COMPOUND_MARKET_TENANT_WEIGHTS = (
        "restaurant",
        "tavern",
        "corner_store",
        "outerwear_shop",
        "shoe_shop",
        "accessory_shop",
        "clothing_superstore",
        "hair_studio",
        "tattoo_parlor",
        "hardware_store",
        "tool_depot",
        "pawn_shop",
        "outfitter",
        "surplus_store",
        "pharmacy",
        "service_station",
        "auto_garage",
        "courier_office",
        "employment_agency",
        "bounty_office",
        "bank",
    )
    SPAN_SERVICE_ANCHOR_ARCHETYPES = {
        "backroom_clinic",
        "bank",
        "brokerage",
        "flophouse",
        "hotel",
        "office",
        "pawn_shop",
        "service_station",
        "tavern",
        "courier_office",
        "employment_agency",
        "bounty_office",
    }
    NON_CITY_OUTSIDER_SITE_CHANCE_BY_AREA = {
        "frontier": 0.032,
        "wilderness": 0.028,
        "coastal": 0.04,
    }
    NON_CITY_DENSE_SITE_CHANCE_BY_AREA = {
        "frontier": 0.05,
        "wilderness": 0.035,
        "coastal": 0.05,
    }
    NON_CITY_COMPOUND_SERVICE_CHANCE_BY_AREA = {
        "frontier": 0.62,
        "wilderness": 0.42,
        "coastal": 0.56,
    }
    NON_CITY_RURAL_COUNTERPART_ARCHETYPES = {
        "accessory_shop",
        "auto_garage",
        "bar",
        "bookshop",
        "bottom_shop",
        "corner_store",
        "hair_studio",
        "headwear_shop",
        "flophouse",
        "hardware_store",
        "hotel",
        "outerwear_shop",
        "outfitter",
        "pawn_shop",
        "pharmacy",
        "restaurant",
        "service_station",
        "shoe_shop",
        "surplus_store",
        "tattoo_parlor",
        "tavern",
        "tool_depot",
        "top_shop",
    }
    NON_CITY_RURAL_COUNTERPART_WEIGHTS = (
        "restaurant",
        "restaurant",
        "tavern",
        "tavern",
        "service_station",
        "service_station",
        "hardware_store",
        "pharmacy",
        "corner_store",
        "outfitter",
        "surplus_store",
        "outerwear_shop",
        "shoe_shop",
        "accessory_shop",
        "hair_studio",
        "tattoo_parlor",
        "auto_garage",
        "tool_depot",
        "pawn_shop",
        "hotel",
        "bar",
        "bookshop",
        "flophouse",
    )
    NON_CITY_COMPOUND_SERVICE_WEIGHTS = (
        "service_station",
        "service_station",
        "restaurant",
        "restaurant",
        "tavern",
        "hardware_store",
        "pawn_shop",
        "bank",
        "bank",
        "brokerage",
        "casino",
        "casino",
        "gaming_hall",
        "hotel",
        "pharmacy",
        "auto_garage",
        "courier_office",
        "employment_agency",
        "bounty_office",
        "contractor_office",
    )

    OVERWORLD_TRAVEL_BASE = {
        "city": {"energy": 0, "safety": 0, "social": 0, "risk": 0},
        "frontier": {"energy": 1, "safety": 0, "social": 0, "risk": 1},
        "wilderness": {"energy": 2, "safety": 1, "social": 1, "risk": 2},
        "coastal": {"energy": 1, "safety": 1, "social": 0, "risk": 2},
    }

    OVERWORLD_TERRAIN_TRAVEL_MODS = {
        "badlands": {"energy": 1, "safety": 1, "risk": 1},
        "cliffs": {"energy": 1, "risk": 1},
        "dunes": {"energy": 1, "risk": 1},
        "forest": {"energy": 1},
        "hills": {"energy": 1},
        "industrial_waste": {"safety": 1, "risk": 1},
        "marsh": {"energy": 1, "safety": 1, "risk": 1},
        "ruins": {"safety": 1, "risk": 1},
        "salt_flats": {"energy": 1},
        "shoals": {"safety": 1, "risk": 1},
    }

    OVERWORLD_PATH_TRAVEL_MODS = {
        "freeway": {"energy": -2, "safety": -1, "social": -1, "risk": -1},
        "road": {"energy": -1, "safety": -1, "social": -1, "risk": -1},
        "trail": {"energy": -1, "social": -1, "risk": -1},
    }

    CITY_TRAVEL_SUPPORT = {
        "industrial": ("trade",),
        "residential": ("shelter",),
        "downtown": ("services", "trade"),
        "slums": ("supplies",),
        "corporate": ("services",),
        "military": ("security",),
        "entertainment": ("social", "trade"),
    }

    NON_CITY_SITE_TRAVEL_OPPORTUNITIES = {
        "salvage_camp": ("salvage",),
        "breaker_yard": ("salvage", "tools"),
        "pump_house": ("water",),
        "work_shed": ("tools",),
        "outfitter": ("supplies", "tools"),
        "surplus_store": ("supplies", "tools"),
        "truck_stop": ("supplies",),
        "net_house": ("supplies",),
        "bait_shop": ("supplies",),
        "drydock_yard": ("salvage",),
    }

    OVERWORLD_DISCOVERY_PROFILES = {
        "salvage": {
            "label": "salvage",
            "credits_min": 8,
            "credits_max": 18,
        },
        "water": {
            "label": "fresh water",
            "energy_gain": 5,
            "safety_gain": 4,
        },
        "supplies": {
            "label": "supply cache",
            "item_pool": ("street_ration", "med_gel", "spark_brew", "energy_bar", "bottled_water", "meal_voucher"),
        },
        "tools": {
            "label": "tool salvage",
            "credits_min": 6,
            "credits_max": 14,
            "item_pool": ("city_pass_token", "battery_pack", "scrap_circuit", "pocket_multitool"),
        },
        "landmark": {
            "label": "vantage",
            "intel_radius": 1,
        },
    }
    NON_CITY_SITE_SERVICE_SUPPORTS = {
        "bus_transit": ("services",),
        "business_management": ("services",),
        "coach_transit": ("services",),
        "butcher_prepare": ("services", "supplies"),
        "ferry_transit": ("services",),
        "fuel": ("services",),
        "herbal_care": ("services", "supplies"),
        "herbal_prepare": ("services", "supplies"),
        "herbal_recipe_sales": ("services", "supplies"),
        "intel": ("intel",),
        "repair": ("services",),
        "rest": ("services", "shelter"),
        "shelter": ("services", "shelter"),
        "shuttle_transit": ("services",),
    }
    NON_CITY_SPECIALTY_ALIASES = {
        "broken reach": "field_refuge",
        "deep green": "field_refuge",
        "drydock reach": "parts_yard",
        "ferry chain": "route_hub",
        "marsh belt": "field_refuge",
        "relay corridor": "route_hub",
        "ridge watch": "watch_network",
        "ruin tract": "field_refuge",
        "salvage belt": "parts_yard",
        "storm watch": "watch_network",
        "watch strip": "watch_network",
        "working shore": "route_hub",
    }
    NON_CITY_SPECIALTY_PROFILES = {
        "route_hub": {
            "minimum_focus_sites": 2,
            "bonus_site_kinds_by_identity": {
                "ferry chain": ("ferry_post", "tide_station", "dock_shack"),
                "relay corridor": ("relay_post", "truck_stop", "roadhouse"),
                "working shore": ("dock_shack", "bait_shop"),
            },
            "site_services_by_kind": {
                "bait_shop": ("shelter",),
                "dock_shack": ("shelter",),
                "ferry_post": ("shelter",),
                "relay_post": ("intel",),
                "roadhouse": ("rest",),
                "tide_station": ("shelter",),
                "truck_stop": ("rest",),
            },
            "opportunity_tags_by_kind": {
                "bait_shop": ("supplies",),
                "dock_shack": ("supplies",),
                "ferry_post": ("supplies",),
                "relay_post": ("supplies",),
                "roadhouse": ("supplies",),
                "tide_station": ("supplies",),
                "truck_stop": ("supplies",),
            },
            "discovery_overrides": {
                "supplies": {
                    "label": "route stash",
                    "item_pool": ("city_pass_token", "transit_daypass", "meal_voucher", "bottled_water"),
                },
            },
        },
        "parts_yard": {
            "minimum_focus_sites": 2,
            "bonus_site_kinds_by_identity": {
                "drydock reach": ("drydock_yard", "dock_shack"),
                "salvage belt": ("breaker_yard", "salvage_camp", "work_shed"),
            },
            "site_services_by_kind": {
                "breaker_yard": ("repair",),
                "dock_shack": ("repair",),
                "drydock_yard": ("repair",),
                "roadhouse": ("repair",),
                "salvage_camp": ("repair",),
                "truck_stop": ("repair",),
                "work_shed": ("repair",),
            },
            "opportunity_tags_by_kind": {
                "breaker_yard": ("salvage", "tools"),
                "dock_shack": ("tools",),
                "drydock_yard": ("salvage", "tools"),
                "roadhouse": ("tools",),
                "salvage_camp": ("salvage", "tools"),
                "truck_stop": ("tools",),
                "work_shed": ("tools",),
            },
            "discovery_overrides": {
                "salvage": {
                    "label": "salvage haul",
                    "credits_min": 12,
                    "credits_max": 24,
                },
                "tools": {
                    "label": "parts cache",
                    "credits_min": 8,
                    "credits_max": 18,
                    "item_pool": ("battery_pack", "lockpick_kit", "pocket_multitool", "prybar", "scrap_circuit", "signal_jammer"),
                },
            },
        },
        "watch_network": {
            "minimum_focus_sites": 2,
            "bonus_site_kinds_by_identity": {
                "ridge watch": ("lookout_post", "firewatch_tower", "weather_station", "survey_post"),
                "storm watch": ("coast_watch", "beacon_house", "weather_station"),
                "watch strip": ("inspection_shed", "weather_station", "lookout_post"),
            },
            "site_services_by_kind": {
                "beacon_house": ("intel",),
                "coast_watch": ("intel",),
                "firewatch_tower": ("intel",),
                "inspection_shed": ("intel",),
                "lookout_post": ("intel",),
                "relay_post": ("intel",),
                "survey_post": ("intel",),
                "weather_station": ("intel",),
            },
            "opportunity_tags_by_kind": {
                "beacon_house": ("landmark",),
                "coast_watch": ("landmark",),
                "firewatch_tower": ("landmark",),
                "inspection_shed": ("landmark",),
                "lookout_post": ("landmark",),
                "relay_post": ("landmark",),
                "survey_post": ("landmark",),
                "weather_station": ("landmark",),
            },
            "discovery_overrides": {
                "landmark": {
                    "label": "watch vantage",
                    "intel_radius": 3,
                },
            },
        },
        "field_refuge": {
            "minimum_focus_sites": 2,
            "bonus_site_kinds_by_identity": {
                "broken reach": ("ruin_shelter",),
                "deep green": ("field_camp", "ranger_hut"),
                "marsh belt": ("herbalist_camp", "field_camp"),
                "ruin tract": ("ruin_shelter", "field_camp"),
            },
            "site_services_by_kind": {
                "field_camp": ("shelter",),
                "herbalist_camp": ("rest",),
                "ranger_hut": ("rest",),
                "ruin_shelter": ("rest",),
            },
            "opportunity_tags_by_kind": {
                "field_camp": ("water", "supplies"),
                "herbalist_camp": ("water", "supplies"),
                "ranger_hut": ("water",),
                "ruin_shelter": ("supplies",),
            },
            "discovery_overrides": {
                "supplies": {
                    "label": "remedy cache",
                    "item_pool": ("med_gel", "hydration_salts", "bottled_water", "street_ration"),
                },
                "water": {
                    "label": "field spring",
                    "energy_gain": 6,
                    "safety_gain": 5,
                },
            },
        },
    }

    CITY_TRAVEL_LABELS = {
        "industrial": "freight yards",
        "residential": "housing blocks",
        "downtown": "commercial core",
        "slums": "scrap market sprawl",
        "corporate": "tower campus",
        "military": "checkpoint zone",
        "entertainment": "venue strip",
    }
    OVERWORLD_SUPPORT_READS = {
        "services": "service access",
        "trade": "trade pull",
        "shelter": "shelter cover",
        "intel": "intel support",
        "security": "checkpoint cover",
        "social": "social cover",
        "supplies": "supply access",
    }
    OVERWORLD_OPPORTUNITY_READS = {
        "landmark": "vantage reads",
        "salvage": "salvage chances",
        "water": "water access",
        "tools": "tool salvage",
        "supplies": "supply finds",
    }

    FACTIONS = (
        "civilians",
        "coppers",
        "dock_union",
        "neon_gang",
        "syndicate",
        "corpsec",
    )

    CORE_BUILDINGS_BY_DISTRICT = {
        "industrial": ("warehouse", "factory", "machine_shop"),
        "residential": ("apartment", "house", "corner_store"),
        "downtown": ("office", "bank", "restaurant"),
        "slums": ("tenement", "pawn_shop", "backroom_clinic"),
        "corporate": ("tower", "lab", "server_hub"),
        "military": ("barracks", "armory", "checkpoint"),
        "entertainment": ("nightclub", "arcade", "bar", "tavern"),
    }

    OPTIONAL_BUILDINGS_BY_DISTRICT = {
        "industrial": ("recycling_plant", "auto_garage", "freight_depot", "cold_storage", "tool_depot", "contractor_office", "service_station", "outerwear_shop"),
        "residential": ("daycare", "laundromat", "pharmacy", "herbalist_shop", "bookshop", "hardware_store", "outfitter", "outfitter", "surplus_store", "thrift_store", "service_station", "barbershop", "salon", "top_shop", "bottom_shop", "shoe_shop", "hair_studio", "clothing_superstore", "employment_agency", "butcher_shop"),
        "downtown": ("hotel", "courthouse", "jail", "jail", "metro_exchange", "courier_office", "employment_agency", "bounty_office", "gallery", "casino", "tavern", "outfitter", "herbalist_shop", "clothing_superstore", "salon", "barbershop", "top_shop", "dress_shop", "shoe_shop", "outerwear_shop", "headwear_shop", "jewelry_shop", "accessory_shop", "hair_studio", "makeup_counter", "tattoo_parlor", "butcher_shop"),
        "slums": ("chop_shop", "junk_market", "soup_kitchen", "flophouse", "street_kitchen", "jail", "thrift_store", "barbershop", "tattoo_parlor", "accessory_shop", "shoe_shop", "herbalist_shop", "butcher_shop"),
        "corporate": ("data_center", "co_working_hub", "biotech_clinic", "brokerage", "media_lab", "employment_agency", "salon", "jewelry_shop", "makeup_counter", "dress_shop", "clothing_superstore", "herbalist_shop"),
        "military": ("command_center", "motor_pool", "field_hospital", "recruitment_office", "bounty_office", "supply_bunker", "prison", "surplus_store"),
        "entertainment": ("theater", "music_venue", "gaming_hall", "karaoke_box", "pool_hall", "casino", "bounty_office", "clothing_superstore", "salon", "barbershop", "hair_studio", "makeup_counter", "tattoo_parlor", "jewelry_shop", "accessory_shop", "dress_shop"),
    }

    # Optional archetypes stay seed-available; city variation should come from
    # district placement and local rolls rather than pruning whole businesses
    # out of a world upfront.

    ROOM_TEMPLATES = {
        "warehouse": ("loading_bay", "receiving", "storage", "dispatch", "office", "secure_cage"),
        "factory": ("assembly", "maintenance", "control", "parts_store", "breakroom"),
        "machine_shop": ("shop_floor", "parts", "breakroom", "tool_crib"),
        "apartment": ("hallway", "bedroom", "kitchen", "bathroom"),
        "house": ("living_room", "bedroom", "kitchen"),
        "corner_store": ("entrance", "shop_floor", "storage"),
        "contractor_office": ("front_desk", "materials_counter", "plan_table", "workshop", "dispatch"),
        "office": ("lobby", "open_office", "meeting_room", "records", "archive", "breakroom", "executive_office"),
        "bank": ("lobby", "teller_row", "records", "security_room", "manager_office", "vault"),
        "restaurant": ("dining", "kitchen", "office"),
        "butcher_shop": ("front_counter", "cold_case", "cutting_room", "back_stock"),
        "tenement": ("hallway", "units", "laundry", "boiler", "storage"),
        "pawn_shop": ("sales", "storage", "back_office"),
        "backroom_clinic": ("waiting", "exam", "storage", "back_office"),
        "tower": ("reception", "workspace", "meeting_room", "records", "archive", "boardroom", "server_room", "executive_suite"),
        "lab": ("intake", "lab_floor", "chemical_storage", "office", "testing_lab", "specimen_vault"),
        "server_hub": ("security_room", "racks", "power_room", "noc", "cold_backup"),
        "barracks": ("bunks", "mess", "armory"),
        "armory": ("entry", "secure_storage", "office"),
        "checkpoint": ("gate", "inspection", "control"),
        "nightclub": ("entrance", "dance_floor", "bar"),
        "arcade": ("floor", "prize_room", "staff"),
        "bar": ("seating", "bar_top", "storage"),
        "tavern": ("common_room", "bar_top", "booth_row", "cellar"),
        "recycling_plant": ("sorting_line", "crusher_floor", "hazmat_bay", "parts_store"),
        "auto_garage": ("front_office", "service_bay", "parts_room", "repair_bench"),
        "freight_depot": ("loading_lane", "sorting_floor", "dispatch_desk", "storage"),
        "cold_storage": ("loading_bay", "freezer_row", "packing_line", "dispatch_desk", "cold_storage"),
        "tool_depot": ("showroom", "stock_rack", "service_counter", "repair_bench"),
        "daycare": ("reception", "playroom", "nap_room", "kitchenette"),
        "laundromat": ("machine_row", "folding_station", "supply_closet"),
        "pharmacy": ("counter", "shelving", "dispensary", "storage"),
        "herbalist_shop": ("front_counter", "drying_shelves", "remedy_room", "back_stock"),
        "bookshop": ("front_table", "shelves", "reading_nook", "back_stock"),
        "hardware_store": ("counter", "aisles", "stock_room", "repair_bench"),
        "outfitter": ("counter", "aisles", "stock_room", "storage"),
        "top_shop": ("front_rack", "fitting_room", "counter", "stock_room"),
        "bottom_shop": ("front_rack", "fitting_room", "counter", "stock_room"),
        "dress_shop": ("showroom", "fitting_room", "counter", "stock_room"),
        "shoe_shop": ("shoe_wall", "fitting_bench", "counter", "stock_room"),
        "outerwear_shop": ("coat_rack", "fitting_room", "counter", "stock_room"),
        "headwear_shop": ("hat_wall", "mirror", "counter", "stock_room"),
        "jewelry_shop": ("display_case", "mirror", "counter", "safe_room"),
        "accessory_shop": ("display_wall", "mirror", "counter", "stock_room"),
        "clothing_superstore": ("entry", "rack_row", "fitting_room", "checkout", "stock_room", "returns_desk"),
        "hair_studio": ("reception", "styling_chair", "wash_station", "stock_room"),
        "makeup_counter": ("display_counter", "mirror_station", "consultation_chair", "stock_room"),
        "tattoo_parlor": ("front_counter", "design_wall", "tattoo_chair", "sterilization"),
        "barbershop": ("front_chair", "mirror_wall", "wash_sink", "back_room"),
        "salon": ("reception", "styling_chair", "wash_station", "stock_room"),
        "surplus_store": ("sales", "stock_room", "secure_storage", "back_office"),
        "thrift_store": ("donation_counter", "rack_row", "front_table", "sorting_room", "back_stock"),
        "service_station": ("front_counter", "cooler_row", "pump_counter", "service_bay", "stock_room"),
        "hotel": ("lobby", "front_desk", "guest_floor", "guest_lounge", "laundry", "housekeeping", "linen_closet", "service_office", "bar"),
        "courthouse": ("public_hall", "courtroom", "clerk_office", "records_office", "holding", "judge_chambers", "evidence_lockup"),
        "jail": ("booking", "holding", "visitation", "cell_block", "control_room", "records_office", "armory"),
        "prison": ("intake", "holding", "cell_block", "visitation", "records_office", "workshop", "control_room", "exercise_yard"),
        "metro_exchange": ("entry", "ticketing", "concourse", "platform", "locker_wall", "control_booth", "service_corridor", "maintenance_tunnel"),
        "courier_office": ("front_counter", "sorting_rack", "dispatch_desk", "locker_wall", "records"),
        "employment_agency": ("front_counter", "job_board", "interview_room", "records", "dispatch_desk"),
        "bounty_office": ("front_counter", "case_board", "interview_room", "locker_wall", "records"),
        "gallery": ("foyer", "exhibit_room", "prep_room", "office"),
        "chop_shop": ("tear_down_bay", "parts_shelf", "back_gate"),
        "junk_market": ("open_stalls", "weigh_station", "salvage_pile"),
        "soup_kitchen": ("serving_line", "prep_kitchen", "storage", "commons"),
        "flophouse": ("desk", "shared_room", "washroom", "linen_closet"),
        "street_kitchen": ("service_window", "grill_line", "prep_corner", "supply_crate"),
        "data_center": ("airlock", "security_room", "racks", "power_room", "noc", "cold_backup", "loading_bay"),
        "co_working_hub": ("reception", "hotdesk_floor", "meeting_room", "quiet_room", "event_space", "records", "server_room"),
        "biotech_clinic": ("intake", "testing_lab", "treatment_room", "records", "cold_storage", "clean_room"),
        "brokerage": ("reception", "trading_floor", "conference", "records_room", "archive", "executive_office"),
        "media_lab": ("reception", "edit_bay", "control_room", "studio", "archive", "screening_room"),
        "command_center": ("ops_floor", "briefing_room", "signals_room", "armored_store"),
        "motor_pool": ("garage_bay", "parts_depot", "fuel_pad", "dispatch"),
        "field_hospital": ("triage", "surgery", "recovery", "supply_tent", "records"),
        "recruitment_office": ("lobby", "interview_room", "records_office", "briefing_room", "holding"),
        "supply_bunker": ("airlock", "supply_lockup", "issue_room", "armored_store"),
        "theater": ("foyer", "stage", "backstage", "costume_room", "green_room", "sound_booth", "balcony"),
        "music_venue": ("entrance", "bar", "stage_floor", "green_room", "sound_booth", "backstage", "storage"),
        "gaming_hall": ("main_floor", "cash_cage", "count_room", "surveillance_room", "vip_lounge"),
        "casino": ("gaming_floor", "cash_cage", "count_room", "surveillance_room", "vip_lounge"),
        "karaoke_box": ("host_desk", "song_room", "bar_nook", "sound_closet"),
        "pool_hall": ("front_counter", "table_floor", "back_bar", "storage"),
    }

    MULTI_FLOOR_ARCHETYPES = {
        "apartment",
        "arcade",
        "backroom_clinic",
        "bank",
        "bar",
        "biotech_clinic",
        "brokerage",
        "co_working_hub",
        "cold_storage",
        "courthouse",
        "jail",
        "prison",
        "courier_office",
        "data_center",
        "factory",
        "field_hospital",
        "flophouse",
        "freight_depot",
        "gaming_hall",
        "casino",
        "hotel",
        "lab",
        "machine_shop",
        "media_lab",
        "metro_exchange",
        "music_venue",
        "nightclub",
        "office",
        "pawn_shop",
        "server_hub",
        "soup_kitchen",
        "tenement",
        "theater",
        "tool_depot",
        "tower",
        "warehouse",
    }

    TALL_BUILDING_ARCHETYPES = {
        "apartment",
        "bank",
        "brokerage",
        "co_working_hub",
        "courthouse",
        "prison",
        "data_center",
        "hotel",
        "metro_exchange",
        "office",
        "server_hub",
        "tenement",
        "tower",
    }

    BASEMENT_ARCHETYPES = {
        "apartment",
        "backroom_clinic",
        "bank",
        "biotech_clinic",
        "brokerage",
        "cold_storage",
        "courthouse",
        "jail",
        "data_center",
        "field_hospital",
        "flophouse",
        "hotel",
        "lab",
        "machine_shop",
        "metro_exchange",
        "office",
        "pawn_shop",
        "pharmacy",
        "surplus_store",
        "casino",
        "server_hub",
        "soup_kitchen",
        "supply_bunker",
        "tavern",
        "tenement",
        "tool_depot",
        "tower",
        "warehouse",
    }

    LOW_RISE_ARCHETYPES = {
        "accessory_shop",
        "armory",
        "bait_shop",
        "bar",
        "barbershop",
        "bookshop",
        "bottom_shop",
        "bounty_office",
        "dress_shop",
        "clothing_superstore",
        "employment_agency",
        "hair_studio",
        "headwear_shop",
        "herbalist_shop",
        "jewelry_shop",
        "makeup_counter",
        "outerwear_shop",
        "thrift_store",
        "outfitter",
        "salon",
        "shoe_shop",
        "surplus_store",
        "tattoo_parlor",
        "tavern",
        "top_shop",
        "corner_store",
        "daycare",
        "dock_shack",
        "hardware_store",
        "house",
        "inspection_shed",
        "laundromat",
        "lookout_post",
        "pool_hall",
        "pump_house",
        "ranger_hut",
        "relay_post",
        "restaurant",
        "roadhouse",
        "service_station",
        "street_kitchen",
        "truck_stop",
        "work_shed",
    }

    LARGE_PARCEL_ARCHETYPES = {
        "apartment",
        "bank",
        "biotech_clinic",
        "brokerage",
        "casino",
        "co_working_hub",
        "command_center",
        "courthouse",
        "prison",
        "data_center",
        "factory",
        "field_hospital",
        "freight_depot",
        "gaming_hall",
        "hotel",
        "lab",
        "machine_shop",
        "media_lab",
        "metro_exchange",
        "music_venue",
        "office",
        "recruitment_office",
        "server_hub",
        "supply_bunker",
        "tenement",
        "theater",
        "tool_depot",
        "tower",
        "warehouse",
    }

    LARGE_PARCEL_BASE_CHANCE_BY_DISTRICT = {
        "residential": 0.08,
        "downtown": 0.24,
        "industrial": 0.18,
        "slums": 0.10,
        "corporate": 0.28,
        "military": 0.16,
        "entertainment": 0.18,
    }

    CITY_PLACEMENT_SOLO_POINTS = (
        ("solo_center", 0.50, 0.50),
        ("solo_edge_north", 0.46, 0.24),
        ("solo_edge_south", 0.54, 0.76),
        ("solo_edge_west", 0.24, 0.48),
        ("solo_edge_east", 0.76, 0.52),
        ("solo_offset_northwest", 0.34, 0.20),
        ("solo_offset_northeast", 0.66, 0.20),
        ("solo_offset_southwest", 0.34, 0.80),
        ("solo_offset_southeast", 0.66, 0.80),
        ("solo_corner_nw", 0.24, 0.24),
        ("solo_corner_ne", 0.76, 0.25),
        ("solo_corner_sw", 0.25, 0.76),
        ("solo_corner_se", 0.76, 0.76),
        ("solo_frontage_setback", 0.50, 0.30),
    )

    CITY_PLACEMENT_PAIR_PATTERNS = (
        ("pair_staggered", ((0.22, 0.28), (0.78, 0.72))),
        ("pair_diagonal", ((0.24, 0.24), (0.76, 0.76))),
        ("pair_reverse_diagonal", ((0.76, 0.24), (0.24, 0.76))),
        ("pair_broken_row", ((0.22, 0.38), (0.78, 0.62))),
        ("pair_broken_column", ((0.38, 0.22), (0.62, 0.78))),
        ("pair_offset_fronts", ((0.24, 0.76), (0.76, 0.26))),
        ("pair_side_yard", ((0.18, 0.36), (0.82, 0.64))),
        ("pair_back_alley", ((0.35, 0.18), (0.65, 0.82))),
    )

    CITY_PLACEMENT_CLUSTER_PATTERNS = (
        ("cluster_broken_row", ((0.22, 0.22), (0.78, 0.22), (0.22, 0.78), (0.78, 0.78))),
        ("cluster_broken_column", ((0.22, 0.22), (0.22, 0.78), (0.78, 0.78), (0.78, 0.22))),
        ("cluster_courtyard", ((0.78, 0.22), (0.22, 0.78), (0.78, 0.78), (0.22, 0.22))),
        ("cluster_zigzag", ((0.22, 0.78), (0.78, 0.22), (0.22, 0.22), (0.78, 0.78))),
        ("cluster_front_court", ((0.22, 0.22), (0.78, 0.22), (0.50, 0.78), (0.78, 0.78))),
        ("cluster_side_court", ((0.22, 0.22), (0.22, 0.78), (0.78, 0.50), (0.78, 0.78))),
        ("cluster_rear_court", ((0.22, 0.78), (0.78, 0.78), (0.50, 0.22), (0.78, 0.22))),
        ("cluster_lane", ((0.22, 0.22), (0.78, 0.50), (0.22, 0.78), (0.78, 0.78))),
    )

    CITY_PLACEMENT_ROOMY_PAIR_ARCHETYPES = {
        "bank",
        "command_center",
        "courthouse",
        "data_center",
        "field_hospital",
        "hotel",
        "jail",
        "metro_exchange",
        "office",
        "prison",
        "server_hub",
        "tower",
    }

    CAREERS_BY_ARCHETYPE = {
        "warehouse": ("warehouse_loader", "inventory_clerk", "forklift_operator", "dock_dispatcher", "ore_yard_clerk", "manifest_checker", "cold_chain_runner"),
        "factory": ("assembly_tech", "line_supervisor", "maintenance_tech", "quality_inspector", "smelter_operator", "shift_foreman", "foundry_runner"),
        "machine_shop": ("machinist", "tool_technician", "parts_buyer", "cnc_operator", "drill_rig_technician", "prototype_fitter"),
        "apartment": ("building_super", "tenant_caretaker", "rent_coordinator", "janitorial_lead", "lease_agent"),
        "house": ("contractor", "handyman", "home_aide", "landscaper", "repair_broker"),
        "corner_store": ("shopkeeper", "cashier", "stocker", "delivery_runner", "lottery_clerk"),
        "contractor_office": ("contractor", "glazier", "mason", "shopfitter", "property_repair_tech"),
        "office": ("office_admin", "analyst", "executive_assistant", "records_manager", "project_coordinator", "scheduler"),
        "bank": ("bank_teller", "loan_officer", "vault_manager", "fraud_analyst", "account_specialist"),
        "restaurant": ("chef", "server", "dishwasher", "line_cook", "prep_cook", "host"),
        "tenement": ("maintenance_worker", "community_aide", "caretaker", "utility_worker", "hall_monitor"),
        "pawn_shop": ("pawnbroker", "appraiser", "counter_clerk", "repair_tech", "watch_repairer"),
        "backroom_clinic": ("medic", "triage_nurse", "clinic_manager", "pharmacology_aide", "sanitation_aide"),
        "tower": ("corporate_manager", "floor_coordinator", "hr_specialist", "compliance_auditor", "risk_officer"),
        "lab": ("lab_technician", "researcher", "qa_specialist", "sample_custodian", "sample_runner"),
        "server_hub": ("network_engineer", "sysadmin", "datacenter_tech", "noc_operator", "cable_technician"),
        "barracks": ("quartermaster", "drill_instructor", "logistics_officer", "mess_sergeant"),
        "armory": ("armorer", "security_specialist", "ordnance_clerk", "inventory_sergeant"),
        "checkpoint": ("checkpoint_guard", "inspector", "patrol_officer", "scanner_operator"),
        "nightclub": ("dj", "bartender", "bouncer", "promoter", "light_tech"),
        "arcade": ("arcade_operator", "machine_repair_tech", "prize_attendant", "tournament_host", "token_attendant"),
        "bar": ("bartender", "barback", "door_staff", "cocktail_server", "cellar_runner"),
        "tavern": ("bartender", "barback", "taproom_server", "kitchen_runner", "cellar_runner"),
        "recycling_plant": ("sorting_operator", "scrap_buyer", "reclamation_tech", "compactor_tech", "salvage_breaker"),
        "auto_garage": ("mechanic", "service_writer", "parts_runner", "tow_dispatcher", "rig_mechanic", "diagnostics_tech"),
        "freight_depot": ("freight_handler", "route_planner", "customs_clerk", "yard_manager", "ore_hauler"),
        "cold_storage": ("cold_chain_runner", "freezer_tech", "inventory_clerk", "dock_dispatcher", "packing_supervisor"),
        "tool_depot": ("tool_counter_clerk", "stock_runner", "repair_technician", "supply_buyer", "yard_picker"),
        "daycare": ("childcare_worker", "early_educator", "nutrition_aide", "parent_liaison", "play_monitor"),
        "laundromat": ("laundry_attendant", "machine_technician", "folding_clerk", "supply_runner"),
        "pharmacy": ("pharmacist", "pharmacy_technician", "inventory_pharmacist", "front_counter_clerk", "insurance_biller"),
        "bookshop": ("bookseller", "inventory_clerk", "reading_host", "small_press_buyer"),
        "hardware_store": ("hardware_clerk", "repair_advisor", "stock_runner", "paint_mixer", "key_cutter"),
        "outfitter": ("outfitter_clerk", "trail_supplier", "sporting_buyer", "stock_runner"),
        "top_shop": ("shirt_seller", "rack_runner", "fitting_room_attendant", "stock_runner"),
        "bottom_shop": ("pants_seller", "rack_runner", "fitting_room_attendant", "stock_runner"),
        "bounty_office": ("bounty_coordinator", "case_board_clerk", "field_pickup_dispatcher", "records_clerk"),
        "butcher_shop": ("butcher", "meat_cutter", "counter_clerk", "cold_case_runner"),
        "clothing_superstore": ("floor_clerk", "fitting_room_attendant", "returns_clerk", "stock_runner", "loss_prevention_clerk"),
        "dress_shop": ("dress_seller", "tailoring_aide", "fitting_room_attendant", "stock_runner"),
        "employment_agency": ("job_agent", "intake_clerk", "dispatch_coordinator", "records_clerk"),
        "herbalist_shop": ("herbalist", "remedy_mixer", "drying_shelf_clerk", "recipe_keeper"),
        "shoe_shop": ("shoe_seller", "fit_specialist", "stock_runner", "repair_counter_clerk"),
        "outerwear_shop": ("coat_seller", "gear_fitter", "stock_runner", "rack_runner"),
        "headwear_shop": ("hat_seller", "display_clerk", "stock_runner", "mirror_attendant"),
        "jewelry_shop": ("jewelry_clerk", "case_attendant", "watch_seller", "stock_runner"),
        "accessory_shop": ("accessory_clerk", "display_clerk", "stock_runner", "gift_counter_attendant"),
        "hair_studio": ("hair_stylist", "colorist", "receptionist", "wash_station_attendant"),
        "makeup_counter": ("makeup_artist", "counter_clerk", "consultant", "stock_runner"),
        "tattoo_parlor": ("tattoo_artist", "front_counter_clerk", "sterilization_aide", "design_assistant"),
        "barbershop": ("barber", "receptionist", "sweep_attendant", "apprentice_barber"),
        "salon": ("hair_stylist", "colorist", "makeup_artist", "receptionist"),
        "surplus_store": ("gear_clerk", "surplus_buyer", "stock_armorer", "counter_specialist"),
        "thrift_store": ("thrift_clerk", "donation_sorter", "refurbisher", "rack_runner"),
        "service_station": ("cashier", "fuel_attendant", "bay_technician", "night_clerk", "stock_runner"),
        "hotel": ("concierge", "housekeeper", "front_desk_agent", "night_auditor", "bellhop"),
        "courthouse": ("court_clerk", "bailiff", "records_archivist", "legal_aide"),
        "jail": ("corrections_officer", "booking_clerk", "transport_deputy", "detention_nurse", "records_sergeant"),
        "prison": ("corrections_officer", "yard_sergeant", "intake_clerk", "prison_counselor", "transport_guard", "control_operator"),
        "metro_exchange": ("station_agent", "ticketing_clerk", "transit_controller", "platform_supervisor", "fare_inspector"),
        "courier_office": ("courier_dispatcher", "parcel_sorter", "route_coordinator", "front_counter_clerk"),
        "gallery": ("gallery_attendant", "curator_aide", "installation_tech", "ticket_clerk"),
        "chop_shop": ("parts_stripper", "fence_broker", "lookout", "engine_chop_tech"),
        "junk_market": ("salvage_vendor", "stall_keeper", "scavenger_buyer", "scrap_appraiser", "junk_sorter"),
        "soup_kitchen": ("volunteer_cook", "meal_coordinator", "donation_manager", "outreach_worker", "dish_line_volunteer"),
        "flophouse": ("desk_clerk", "housekeeper", "linen_runner", "night_attendant"),
        "street_kitchen": ("grill_cook", "window_clerk", "prep_runner", "dish_line_worker"),
        "data_center": ("site_reliability_engineer", "cooling_technician", "rack_installer", "fiber_splicer", "backup_operator"),
        "co_working_hub": ("community_manager", "facility_coordinator", "event_host", "startup_consultant"),
        "biotech_clinic": ("biotech_nurse", "genetic_counselor", "lab_screening_tech", "clinical_coordinator"),
        "brokerage": ("broker", "accounts_specialist", "compliance_auditor", "floor_coordinator"),
        "media_lab": ("media_editor", "broadcast_technician", "studio_producer", "archive_runner"),
        "command_center": ("operations_officer", "signals_analyst", "duty_controller", "intel_briefer"),
        "motor_pool": ("vehicle_technician", "fleet_dispatcher", "fuel_specialist", "recovery_driver"),
        "field_hospital": ("trauma_doctor", "combat_medic", "surgical_technician", "care_logistics_coordinator", "ward_aide"),
        "recruitment_office": ("recruiter", "records_clerk", "screening_officer", "front_desk_agent"),
        "supply_bunker": ("quartermaster", "inventory_sergeant", "supply_guard", "issue_clerk"),
        "theater": ("stage_manager", "lighting_technician", "ticket_manager", "costume_tailor", "usher"),
        "music_venue": ("sound_engineer", "tour_manager", "booking_agent", "merch_seller", "stagehand"),
        "gaming_hall": ("table_dealer", "cage_cashier", "floor_manager", "surveillance_operator", "pit_boss"),
        "casino": ("table_dealer", "casino_host", "cage_cashier", "floor_manager", "pit_boss", "surveillance_operator"),
        "karaoke_box": ("karaoke_host", "bartender", "room_runner", "sound_tech"),
        "pool_hall": ("table_attendant", "bartender", "cashier", "door_staff"),
        "truck_stop": ("route_clerk", "line_cook", "yard_host", "fuel_attendant"),
        "inspection_shed": ("permit_checker", "customs_reader", "road_guard"),
        "breaker_yard": ("salvage_breaker", "parts_stripper", "rig_cutter"),
        "salvage_camp": ("salvage_buyer", "parts_picker", "camp_tinkerer", "scrap_sorter"),
        "pump_house": ("utility_worker", "valve_tech", "maintenance_runner"),
        "work_shed": ("handyman", "tool_keeper", "repair_tinkerer"),
        "net_house": ("net_mender", "dock_worker", "coastal_supplier"),
        "firewatch_tower": ("firewatch_keeper", "range_spotter", "signal_keeper"),
        "weather_station": ("weather_tech", "instrument_keeper", "storm_reader"),
        "herbalist_camp": ("field_herbalist", "remedy_mixer", "forager"),
        "bait_shop": ("bait_seller", "dock_runner", "net_mender"),
        "drydock_yard": ("dock_mechanic", "hull_worker", "yard_rigger"),
        "coast_watch": ("shore_patrol", "signal_keeper", "watch_officer"),
    }

    STOREFRONT_ARCHETYPES = {
        "corner_store",
        "restaurant",
        "pawn_shop",
        "backroom_clinic",
        "nightclub",
        "arcade",
        "bar",
        "tavern",
        "daycare",
        "laundromat",
        "pharmacy",
        "hotel",
        "junk_market",
        "soup_kitchen",
        "theater",
        "music_venue",
        "gaming_hall",
        "casino",
        "auto_garage",
        "tool_depot",
        "bookshop",
        "hardware_store",
        "accessory_shop",
        "barbershop",
        "bottom_shop",
        "bounty_office",
        "butcher_shop",
        "clothing_superstore",
        "dress_shop",
        "employment_agency",
        "hair_studio",
        "headwear_shop",
        "herbalist_shop",
        "jewelry_shop",
        "makeup_counter",
        "outerwear_shop",
        "outfitter",
        "salon",
        "shoe_shop",
        "surplus_store",
        "tattoo_parlor",
        "thrift_store",
        "top_shop",
        "service_station",
        "gallery",
        "flophouse",
        "street_kitchen",
        "karaoke_box",
        "pool_hall",
    }
    PUBLIC_BUILDING_ARCHETYPES = {
        "metro_exchange",
    }

    NAMED_BUSINESS_ARCHETYPES = {
        "warehouse",
        "factory",
        "machine_shop",
        "corner_store",
        "contractor_office",
        "office",
        "bank",
        "restaurant",
        "pawn_shop",
        "backroom_clinic",
        "nightclub",
        "arcade",
        "bar",
        "tavern",
        "recycling_plant",
        "auto_garage",
        "freight_depot",
        "cold_storage",
        "tool_depot",
        "daycare",
        "laundromat",
        "pharmacy",
        "bookshop",
        "hardware_store",
        "accessory_shop",
        "barbershop",
        "bottom_shop",
        "dress_shop",
        "hair_studio",
        "headwear_shop",
        "jewelry_shop",
        "makeup_counter",
        "outerwear_shop",
        "outfitter",
        "salon",
        "shoe_shop",
        "surplus_store",
        "tattoo_parlor",
        "thrift_store",
        "top_shop",
        "service_station",
        "hotel",
        "metro_exchange",
        "jail",
        "courier_office",
        "gallery",
        "chop_shop",
        "junk_market",
        "soup_kitchen",
        "flophouse",
        "street_kitchen",
        "data_center",
        "co_working_hub",
        "biotech_clinic",
        "brokerage",
        "media_lab",
        "theater",
        "music_venue",
        "gaming_hall",
        "casino",
        "karaoke_box",
        "pool_hall",
    }

    NAMED_NON_CITY_SITE_KINDS = set(NON_CITY_SITE_LABELS)

    BUSINESS_SUFFIX_BY_ARCHETYPE = {
        "warehouse": ("Logistics", "Warehousing", "Supply Co."),
        "factory": ("Foundry", "Fabrication", "Works"),
        "machine_shop": ("Machine Shop", "Precision Works", "Toolhouse"),
        "corner_store": ("Corner", "Bodega", "Market"),
        "contractor_office": ("Contracting", "Property Services", "Build & Repair"),
        "office": ("Advisory", "Consulting", "Group"),
        "bank": ("Trust", "Savings", "Credit Union"),
        "restaurant": ("Kitchen", "Eatery", "Grill"),
        "pawn_shop": ("Pawn", "Trade Post", "Collateral"),
        "backroom_clinic": ("Clinic", "Care Room", "Medi-Point"),
        "nightclub": ("Club", "Lounge", "Afterhours"),
        "arcade": ("Arcade", "Game Hall", "Pixel Room"),
        "bar": ("Bar", "Taproom", "Public House"),
        "tavern": ("Tavern", "Alehouse", "Tap House"),
        "recycling_plant": ("Recycling", "Reclamation", "Scrap Works"),
        "auto_garage": ("Garage", "Auto Works", "Motor Service"),
        "freight_depot": ("Freight", "Cargo Terminal", "Haulage"),
        "cold_storage": ("Cold Storage", "Icehouse", "Freezer Depot"),
        "tool_depot": ("Tool Depot", "Supply House", "Workyard"),
        "daycare": ("Daycare", "Learning Nest", "Child Center"),
        "laundromat": ("Laundry", "Wash House", "Cleaners"),
        "pharmacy": ("Pharmacy", "Apothecary", "Drugstore"),
        "bookshop": ("Bookshop", "Books", "Reading Room"),
        "hardware_store": ("Hardware", "Fix-It", "Supply"),
        "accessory_shop": ("Accessories", "Finds", "Little Goods"),
        "barbershop": ("Barber", "Cuts", "Chair"),
        "bottom_shop": ("Trousers", "Bottoms", "Rack"),
        "bounty_office": ("Bounty Office", "Recovery Desk", "Pickup Board"),
        "butcher_shop": ("Butcher", "Meat Counter", "Cut House"),
        "clothing_superstore": ("Clothing Superstore", "Off-Price", "Fashion Outlet"),
        "dress_shop": ("Dresses", "Dress Room", "Fittings"),
        "employment_agency": ("Employment Agency", "Work Desk", "Day Labor Office"),
        "hair_studio": ("Hair Studio", "Styling", "Color Room"),
        "headwear_shop": ("Hats", "Caps", "Headwear"),
        "herbalist_shop": ("Herbalist", "Remedies", "Green Apothecary"),
        "jewelry_shop": ("Jewelry", "Rings", "Case"),
        "makeup_counter": ("Makeup", "Cosmetics", "Counter"),
        "outerwear_shop": ("Outerwear", "Coats", "Jackets"),
        "outfitter": ("Outfitter", "Trail Supply", "Field Goods"),
        "salon": ("Salon", "Styling", "Beauty Room"),
        "shoe_shop": ("Shoes", "Boots", "Footwear"),
        "surplus_store": ("Surplus", "Supply Cache", "Kit House"),
        "tattoo_parlor": ("Tattoo", "Ink Room", "Linework"),
        "thrift_store": ("Thrift", "Second Chance", "Exchange"),
        "top_shop": ("Shirts", "Tops", "Thread Shop"),
        "service_station": ("Service Station", "Fuel & Fix", "Motor Stop"),
        "hotel": ("Hotel", "Inn", "Suites"),
        "metro_exchange": ("Transit Exchange", "Terminal", "Station"),
        "jail": ("Jail", "Detention Center", "Holding House"),
        "prison": ("Prison", "Correctional Complex", "Correctional Facility"),
        "courier_office": ("Courier", "Parcel Office", "Dispatch"),
        "gallery": ("Gallery", "Studio", "Exhibit House"),
        "chop_shop": ("Garage", "Parts Yard", "Scrap Bay"),
        "junk_market": ("Junk Market", "Salvage Row", "Swap Lot"),
        "soup_kitchen": ("Soup Kitchen", "Community Meals", "Aid Kitchen"),
        "flophouse": ("Rooms", "Lodging", "Flophouse"),
        "street_kitchen": ("Street Kitchen", "Griddle", "Late Window"),
        "data_center": ("Data Center", "Compute Works", "Cloud Yard"),
        "co_working_hub": ("Collective", "Co-Working", "Workspace"),
        "biotech_clinic": ("BioClinic", "Gene Care", "Vital Lab"),
        "brokerage": ("Brokerage", "Capital", "Exchange"),
        "media_lab": ("Media Lab", "Studio", "Signal House"),
        "theater": ("Theater", "Playhouse", "Stageworks"),
        "music_venue": ("Music Hall", "Live House", "Venue"),
        "gaming_hall": ("Gaming Hall", "Lucky Room", "Tables"),
        "casino": ("Casino", "Lucky Palace", "Card Room"),
        "karaoke_box": ("Karaoke", "Song Rooms", "Mic Lounge"),
        "pool_hall": ("Pool Hall", "Billiards", "Cue Room"),
        "roadhouse": ("Roadhouse", "Rest Stop", "Travel House"),
        "truck_stop": ("Truck Stop", "Fuel Stop", "Travel Plaza"),
        "relay_post": ("Relay Post", "Signal Post", "Comms Relay"),
        "inspection_shed": ("Inspection Shed", "Permit Post", "Checkpoint"),
        "salvage_camp": ("Salvage Camp", "Recovery Yard", "Scrap Camp"),
        "breaker_yard": ("Breaker Yard", "Parts Yard", "Wrecking"),
        "pump_house": ("Pump House", "Waterworks", "Valve House"),
        "work_shed": ("Work Shed", "Tool Shed", "Yard Shop"),
        "field_camp": ("Field Camp", "Outcamp", "Trail Camp"),
        "survey_post": ("Survey Post", "Range Post", "Survey Camp"),
        "ranger_hut": ("Ranger Hut", "Trail Hut", "Range Hut"),
        "ruin_shelter": ("Ruin Shelter", "Refuge", "Hideout"),
        "lookout_post": ("Lookout Post", "Watch Post", "Vantage"),
        "firewatch_tower": ("Firewatch Tower", "Watchtower", "Signal Tower"),
        "weather_station": ("Weather Station", "Storm Station", "Sky Station"),
        "herbalist_camp": ("Herbalist Camp", "Remedy Camp", "Green Camp"),
        "flea_market": ("Flea Market", "Swap Meet", "Market Compound"),
        "dock_shack": ("Dock Shack", "Pier Supply", "Harbor Shack"),
        "ferry_post": ("Ferry Post", "Ferry Landing", "Crossing"),
        "tide_station": ("Tide Station", "Harbor Station", "Sounding House"),
        "net_house": ("Net House", "Fish House", "Harbor Net House"),
        "beacon_house": ("Beacon House", "Signal House", "Lamp House"),
        "bait_shop": ("Bait Shop", "Tackle", "Harbor Supply"),
        "drydock_yard": ("Drydock", "Slipworks", "Shipyard"),
        "coast_watch": ("Coast Watch", "Shore Watch", "Watch House"),
    }

    BUSINESS_NAME_TEMPLATES = (
        "{founder_last} {suffix}",
        "{adj} {noun} {suffix}",
        "{street} {suffix}",
        "{founder_first} & {founder_last} {suffix}",
        "{adj} {suffix}",
        "{noun} {suffix}",
        "The {adj} {suffix}",
        "{founder_last}'s {suffix}",
        "{adj} {street} {suffix}",
        "{noun} on {street}",
        "{founder_last} & {noun}",
    )

    NON_CITY_SITE_NAME_TEMPLATES = (
        "{adj} {suffix}",
        "{adj} {noun} {suffix}",
        "{adj} {street} {suffix}",
        "The {adj} {suffix}",
        "{adj} {founder_last} {suffix}",
        "{adj} {suffix} on {street}",
        "{adj} {noun} {suffix} at {street}",
    )

    DEFAULT_BUSINESS_NAME_DATA = {
        "adjectives": (
            "Amber", "Atomic", "Brass", "Bright", "Cedar", "Cinder", "Copper", "Crimson",
            "Drift", "Dusty", "Electric", "Emerald", "Feral", "First", "Golden", "Grand",
            "Harbor", "Hidden", "High", "Hollow", "Iron", "Ivory", "Jade", "Lucky",
            "Lunar", "Metro", "Midnight", "Moss", "Neon", "North", "Nova", "Old",
            "Open", "Quiet", "Rapid", "Red", "River", "Rust", "Silver", "South",
            "Static", "Steel", "Stone", "Sunny", "Third", "True", "Urban", "Velvet",
            "West", "Wild",
        ),
        "nouns": (
            "Anchor", "Arc", "Beacon", "Bridge", "Circuit", "Clover", "Comet", "Corner",
            "Crown", "Current", "Dawn", "Echo", "Elm", "Falcon", "Field", "Forge",
            "Garden", "Gate", "Grove", "Harbor", "Horizon", "Junction", "Key", "Lane",
            "Market", "Mesa", "Mill", "Needle", "Oak", "Orbit", "Point", "Pulse",
            "Quarter", "River", "Signal", "Spire", "Square", "Station", "Summit", "Thread",
            "Transit", "Vale", "Vanguard", "Vault", "Vertex", "Vista", "Wharf", "Willow",
            "Yard", "Zenith",
        ),
        "street_terms": (
            "8th Street", "Aster", "Bell", "Bridgeway", "Canal", "Dockside", "Eastline", "Elm",
            "Foundry", "Garnet", "Grant", "Harbor", "Hillcrest", "Iron", "Jasper", "Juniper",
            "King", "Lantern", "Liberty", "Market", "Maple", "Mercury", "Morrow", "Northgate",
            "Oak", "Old Port", "Orchid", "Park", "Pioneer", "Prospect", "Quarry", "Rail",
            "Ridge", "Riverfront", "Sable", "Second", "Station", "Summit", "Sunset", "Third",
            "Union", "Valley", "Verdant", "Walnut", "Westgate", "Wharf", "Willow", "York",
        ),
    }

    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.chunks = {}
        self.loaded_chunks = {}
        self.focus = None
        self._overworld_region_cache = {}

        self.business_name_data = self._load_business_name_data()
        self.buildings_by_district = self._build_district_building_pools()

        self.building_archetypes = self._all_building_archetypes()
        self.career_pool = self._all_careers()
        self.custom_world_profiles = {}
        missing_career_mappings = [
            archetype
            for archetype in self.building_archetypes
            if archetype not in self.CAREERS_BY_ARCHETYPE
        ]

        if missing_career_mappings:
            raise ValueError(
                "Missing career mappings for building archetypes: "
                + ", ".join(sorted(missing_career_mappings))
            )

        if len(self.career_pool) < len(self.building_archetypes):
            raise ValueError(
                "Career pool must be at least as large as building archetype count. "
                f"careers={len(self.career_pool)} buildings={len(self.building_archetypes)}"
            )

    def _rebuild_runtime_state(self):
        self._overworld_region_cache = {}
        self.business_name_data = self._load_business_name_data()
        self.buildings_by_district = self._build_district_building_pools()
        self.building_archetypes = self._all_building_archetypes()
        self.career_pool = self._all_careers()
        self.custom_world_profiles = {}

    def set_custom_world_profiles(self, profiles=None):
        parsed = {}
        if isinstance(profiles, dict):
            iterable = profiles.items()
        else:
            iterable = ()
        for profile_id, profile in iterable:
            key = str(profile_id or "").strip().lower()
            if not key or not isinstance(profile, dict):
                continue
            clean = dict(profile)
            clean["id"] = key
            parsed[key] = clean
        self.custom_world_profiles = parsed
        return len(parsed)

    def __getstate__(self):
        state = dict(self.__dict__)
        for key in self.RUNTIME_ONLY_STATE_KEYS:
            state.pop(key, None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state if isinstance(state, dict) else {})
        self._rebuild_runtime_state()

    def get_chunk(self, cx, cy):

        key = (cx, cy)

        if key not in self.chunks:
            self.chunks[key] = self.generate_chunk(cx, cy)

        return self.chunks[key]

    def chunk_rng(self, cx, cy):
        return random.Random(f"{self.seed}:{cx}:{cy}")

    def chunk_site_rng(self, cx, cy):
        return random.Random(f"{self.seed}:{cx}:{cy}:sites")

    def _coerce_word_list(self, source, key):
        raw = source.get(key, [])
        if not isinstance(raw, list):
            raw = []
        parsed = [str(word).strip() for word in raw if str(word).strip()]
        if parsed:
            return tuple(parsed)
        return tuple(self.DEFAULT_BUSINESS_NAME_DATA[key])

    def _load_business_name_data(self, path=BUSINESS_NAME_DATA_PATH):
        raw = None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            warn_content_fallback(path, "built-in business-name defaults", exc=exc)
            raw = None

        if raw is not None and not isinstance(raw, dict):
            warn_content_fallback(path, "built-in business-name defaults", problem="top-level JSON must be an object")
        if not isinstance(raw, dict):
            raw = {}

        parsed = {}
        for key in self.DEFAULT_BUSINESS_NAME_DATA:
            parsed[key] = self._coerce_word_list(raw, key)

        human_names = NPC_NAME_CATALOG.get("human", {}) if isinstance(NPC_NAME_CATALOG, dict) else {}
        human_defaults = DEFAULT_NAME_CATALOG.get("human", {}) if isinstance(DEFAULT_NAME_CATALOG, dict) else {}
        founder_firsts = human_names.get("first_names") or human_defaults.get("first_names") or ()
        founder_lasts = human_names.get("last_names") or human_defaults.get("last_names") or ()
        parsed["founder_first_names"] = tuple(str(name).strip() for name in founder_firsts if str(name).strip())
        parsed["founder_last_names"] = tuple(str(name).strip() for name in founder_lasts if str(name).strip())
        return parsed

    def _build_district_building_pools(self):
        pools = {}
        for district in self.DISTRICT_TYPES:
            core = list(self.CORE_BUILDINGS_BY_DISTRICT.get(district, ()))
            optional = list(self.OPTIONAL_BUILDINGS_BY_DISTRICT.get(district, ()))
            pools[district] = tuple(dict.fromkeys(core + optional))

        return pools

    def _all_building_archetypes(self):
        archetypes = set()
        for buildings in self.CORE_BUILDINGS_BY_DISTRICT.values():
            archetypes.update(buildings)
        for buildings in self.OPTIONAL_BUILDINGS_BY_DISTRICT.values():
            archetypes.update(buildings)
        return tuple(sorted(archetypes))

    def _all_careers(self):
        careers = set()
        for archetype in self.building_archetypes:
            careers.update(self.careers_for_building(archetype))
        return tuple(sorted(careers))

    def careers_for_building(self, archetype):
        return self.CAREERS_BY_ARCHETYPE.get(archetype, ("general_worker",))

    def draw_career(self, rng, preferred_archetype=None):
        if preferred_archetype:
            options = self.careers_for_building(preferred_archetype)
            if options:
                return rng.choice(options)

        return rng.choice(self.career_pool)

    def pick_district_type(self, cx, cy):
        # Keep district drift readable by assigning districts in small chunk cells.
        cell_size = int(max(1, self.OVERWORLD_DISTRICT_CELL_SIZE))
        qx = int(cx) // cell_size
        qy = int(cy) // cell_size
        idx = abs(qx * 31 + qy * 17 + self.seed) % len(self.DISTRICT_TYPES)
        return self.DISTRICT_TYPES[idx]

    @staticmethod
    def _smoothstep(value):
        value = max(0.0, min(1.0, float(value)))
        return value * value * (3.0 - (2.0 * value))

    @staticmethod
    def _lerp(a, b, t):
        t = max(0.0, min(1.0, float(t)))
        return (float(a) * (1.0 - t)) + (float(b) * t)

    def _noise_lattice(self, key, x, y):
        rng = random.Random(f"{self.seed}:{key}:{int(x)}:{int(y)}")
        return float(rng.random())

    def _value_noise(self, key, x, y, scale):
        scale = max(0.5, float(scale))
        sx = float(x) / scale
        sy = float(y) / scale
        x0 = int(math.floor(sx))
        y0 = int(math.floor(sy))
        tx = self._smoothstep(sx - x0)
        ty = self._smoothstep(sy - y0)

        v00 = self._noise_lattice(key, x0, y0)
        v10 = self._noise_lattice(key, x0 + 1, y0)
        v01 = self._noise_lattice(key, x0, y0 + 1)
        v11 = self._noise_lattice(key, x0 + 1, y0 + 1)
        i0 = self._lerp(v00, v10, tx)
        i1 = self._lerp(v01, v11, tx)
        return self._lerp(i0, i1, ty)

    def pick_region_area_type(self, rx, ry):
        rx = int(rx)
        ry = int(ry)
        urban = self._value_noise("overworld_urban", rx, ry, self.OVERWORLD_URBAN_NOISE_SCALE)
        ridge = self._value_noise("overworld_ridge", rx, ry, self.OVERWORLD_RIDGE_NOISE_SCALE)
        coastal = self._value_noise("overworld_coastal", rx, ry, self.OVERWORLD_COAST_NOISE_SCALE)
        wild = self._value_noise("overworld_wild", rx, ry, self.OVERWORLD_WILD_NOISE_SCALE)

        urban_score = (urban * 0.85) + (ridge * 0.35)
        wild_score = (wild * 0.95) - (urban * 0.18)

        if (
            urban_score >= float(self.OVERWORLD_CITY_CORE_THRESHOLD)
            and wild_score <= float(self.OVERWORLD_CITY_CORE_WILD_CAP)
        ):
            return "city"
        if (
            urban_score >= float(self.OVERWORLD_CITY_EDGE_THRESHOLD)
            and ridge >= float(self.OVERWORLD_CITY_EDGE_RIDGE_THRESHOLD)
            and wild_score <= float(self.OVERWORLD_CITY_EDGE_WILD_CAP)
        ):
            return "city"
        if (
            coastal >= float(self.OVERWORLD_COAST_CORE_THRESHOLD)
            and wild_score < (float(self.OVERWORLD_WILDERNESS_THRESHOLD) + 0.02)
        ):
            return "coastal"
        if wild_score >= float(self.OVERWORLD_WILDERNESS_THRESHOLD):
            return "wilderness"
        if urban_score >= float(self.OVERWORLD_FRONTIER_URBAN_THRESHOLD):
            return "frontier"
        if (
            coastal >= float(self.OVERWORLD_COAST_EDGE_THRESHOLD)
            and wild_score < float(self.OVERWORLD_WILDERNESS_THRESHOLD)
        ):
            return "coastal"
        return "wilderness"

    def _nearby_region_influences(self, cx, cy, radius=1):
        size = int(max(10, self.OVERWORLD_REGION_SIZE))
        rx = int(cx) // size
        ry = int(cy) // size
        influences = []

        for dy in range(-int(radius), int(radius) + 1):
            for dx in range(-int(radius), int(radius) + 1):
                region = self._region_anchor(rx + dx, ry + dy)
                dist = max(abs(int(cx) - int(region["cx"])), abs(int(cy) - int(region["cy"])))
                influence = int(region["radius"]) - dist
                influences.append((region, int(influence), int(dist)))

        return influences

    def pick_area_type(self, cx, cy):
        area_scores = {}
        best_influence_by_area = {}

        for region, influence, _dist in self._nearby_region_influences(cx, cy, radius=1):
            area_type = str(region.get("area_type", "city")).strip().lower() or "city"
            weighted = float(influence) + 2.0
            if area_type == "city":
                weighted -= 1.5
            area_scores[area_type] = area_scores.get(area_type, 0.0) + weighted
            best_influence_by_area[area_type] = max(
                float(influence),
                best_influence_by_area.get(area_type, float("-inf")),
            )

        if area_scores:
            area_priority = {"wilderness": 3, "frontier": 2, "coastal": 1, "city": 0}
            best_area = max(
                area_scores.items(),
                key=lambda item: (
                    float(item[1]),
                    best_influence_by_area.get(item[0], float("-inf")),
                    area_priority.get(item[0], -1),
                ),
            )[0]
            return str(best_area)

        size = int(max(10, self.OVERWORLD_REGION_SIZE))
        return self.pick_region_area_type(int(cx) // size, int(cy) // size)

    def _region_anchor(self, rx, ry):
        key = (int(rx), int(ry))
        cached = self._overworld_region_cache.get(key)
        if cached is not None:
            return cached

        size = int(max(10, self.OVERWORLD_REGION_SIZE))
        margin = int(max(1, min(size // 3, self.OVERWORLD_REGION_MARGIN)))
        hi = max(margin + 1, size - margin - 1)

        rng = random.Random(f"{self.seed}:overworld_region:{key[0]}:{key[1]}")
        base_x = key[0] * size
        base_y = key[1] * size
        anchor_x = base_x + rng.randint(margin, hi)
        anchor_y = base_y + rng.randint(margin, hi)
        area_type = self.pick_region_area_type(key[0], key[1])
        terrain_options = self.OVERWORLD_TERRAIN_VARIANTS.get(
            area_type,
            ("plains",),
        )
        terrain = rng.choice(terrain_options)
        if area_type == "city":
            radius = rng.randint(max(4, size // 4), max(7, size // 2))
        else:
            radius = rng.randint(max(6, size // 3), max(10, (size * 2) // 3))

        landmark = None
        landmark_chance = 0.28 if area_type == "city" else 0.42
        if rng.random() < landmark_chance:
            template = rng.choice(self.OVERWORLD_LANDMARK_TEMPLATES)
            landmark = {
                "id": template["id"],
                "name": template["name"],
                "glyph": str(template.get("glyph", "?"))[:1] or "?",
                "terrain": template.get("terrain", terrain),
                "color": template.get("color", "human"),
                "radius": rng.randint(
                    int(template.get("radius_min", 4)),
                    int(template.get("radius_max", 7)),
                ),
                "cx": anchor_x,
                "cy": anchor_y,
            }
        region_name = self._region_name_for(key[0], key[1], area_type)
        settlement_name = self._settlement_name_for(key[0], key[1], area_type)

        data = {
            "rx": key[0],
            "ry": key[1],
            "cx": anchor_x,
            "cy": anchor_y,
            "area_type": area_type,
            "terrain": terrain,
            "radius": radius,
            "landmark": landmark,
            "region_name": region_name,
            "settlement_name": settlement_name,
        }
        self._overworld_region_cache[key] = data
        return data

    def _region_name_for(self, rx, ry, area_type):
        rng = random.Random(f"{self.seed}:region_name:{rx}:{ry}:{area_type}")
        prefix = rng.choice(self.OVERWORLD_REGION_PREFIXES)
        suffixes = self.OVERWORLD_REGION_SUFFIX_BY_AREA.get(
            str(area_type).strip().lower(),
            self.OVERWORLD_REGION_SUFFIX_BY_AREA["city"],
        )
        suffix = rng.choice(suffixes)
        return f"{prefix} {suffix}"

    def _settlement_name_for(self, rx, ry, area_type):
        if str(area_type).strip().lower() != "city":
            return None

        rng = random.Random(f"{self.seed}:settlement_name:{rx}:{ry}")
        roll = rng.random()
        prefix = rng.choice(self.SETTLEMENT_PREFIXES)
        root = rng.choice(self.SETTLEMENT_ROOTS)
        suffix = rng.choice(self.SETTLEMENT_SUFFIXES)

        if roll < 0.40:
            return f"{prefix} {root}"
        if roll < 0.78:
            return f"{root} {suffix}"
        return f"{prefix} {root} {suffix}"

    def _non_city_site_pool(self, descriptor):
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        district_type = str(descriptor.get("district_type", "unknown")).strip().lower() or "unknown"
        terrain = str(descriptor.get("terrain", "")).strip().lower()
        path = str(descriptor.get("path", "")).strip().lower()
        landmark = descriptor.get("landmark") or descriptor.get("nearest_landmark") or {}
        landmark_id = str(landmark.get("id", "") or "").strip().lower()

        options = list(self.NON_CITY_SITE_POOLS.get(area_type, ()))
        if area_type == "frontier":
            options.extend(("outfitter", "surplus_store"))
            if path in {"road", "freeway"}:
                options.extend(("relay_post", "roadhouse", "truck_stop", "outfitter", "surplus_store"))
            if path == "freeway" or (path == "road" and district_type in {"industrial", "military"}):
                options.append("inspection_shed")
            if terrain in {"badlands", "dunes", "ruins"}:
                options.extend(("salvage_camp", "work_shed", "breaker_yard", "surplus_store"))
            if terrain in {"forest", "hills"}:
                options.append("outfitter")
        elif area_type == "wilderness":
            if terrain in {"ruins"} or landmark_id == "shatter_ruins":
                options.extend(("ruin_shelter", "survey_post", "weather_station"))
            if terrain in {"forest", "marsh"}:
                options.extend(("field_camp", "ranger_hut", "outfitter"))
            if terrain == "marsh":
                options.append("herbalist_camp")
            if landmark_id in {"ancient_grove", "glass_marsh"}:
                options.extend(("field_camp", "ranger_hut", "herbalist_camp", "herbalist_camp", "outfitter"))
            if terrain in {"hills"} or landmark_id == "radio_spire":
                options.extend(("firewatch_tower", "weather_station", "outfitter"))
        elif area_type == "coastal":
            if terrain in {"shore", "shoals", "lake", "island", "ocean", "waterway"}:
                options.extend(("dock_shack", "ferry_post", "net_house", "bait_shop", "drydock_yard"))
            if path:
                options.extend(("ferry_post", "tide_station", "coast_watch"))

        return tuple(options or self.NON_CITY_SITE_POOLS["frontier"])

    def _non_city_dense_site_count(self, descriptor, rng, count):
        count = max(0, int(count))
        if count < 2:
            return count

        descriptor = descriptor if isinstance(descriptor, dict) else {}
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        terrain = str(descriptor.get("terrain", "")).strip().lower()
        path = str(descriptor.get("path", "")).strip().lower()
        district_type = str(descriptor.get("district_type", "")).strip().lower()
        landmark = descriptor.get("landmark") or descriptor.get("nearest_landmark") or {}
        landmark_id = str(landmark.get("id", "") or "").strip().lower()
        try:
            landmark_dist = int(landmark.get("distance", 99))
        except (TypeError, ValueError):
            landmark_dist = 99

        affinity = 0.0
        if area_type == "frontier":
            if path in {"road", "freeway"}:
                affinity += 0.9
            if terrain in {"badlands", "ruins", "industrial_waste"}:
                affinity += 0.6
            if district_type in {"industrial", "military"}:
                affinity += 0.5
            if landmark_dist <= 2:
                affinity += 0.5
        elif area_type == "wilderness":
            if path in {"trail", "road", "freeway"}:
                affinity += 0.7
            if terrain in {"ruins", "forest", "marsh", "hills"}:
                affinity += 0.5
            if landmark_id in {"radio_spire", "shatter_ruins", "ancient_grove", "glass_marsh"}:
                affinity += 0.8
            elif landmark_dist <= 1:
                affinity += 0.5
        elif area_type == "coastal":
            if path in {"road", "freeway", "trail"}:
                affinity += 0.7
            if terrain in {"shore", "shoals", "lake", "cliffs", "island", "ocean", "waterway"}:
                affinity += 0.6
            if landmark_dist <= 2:
                affinity += 0.5

        if affinity <= 0.0:
            return min(2, count)

        chance = float(self.NON_CITY_DENSE_SITE_CHANCE_BY_AREA.get(area_type, 0.0))
        chance = min(0.16, chance * min(2.0, affinity))
        if chance > 0.0 and rng.random() < chance:
            return min(3, count + 1)
        return min(2, count)

    def _non_city_site_count(self, descriptor, rng):
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        terrain = str(descriptor.get("terrain", "")).strip().lower()
        path = str(descriptor.get("path", "")).strip().lower()
        landmark = descriptor.get("landmark") or descriptor.get("nearest_landmark") or {}
        landmark_id = str(landmark.get("id", "") or "").strip().lower()
        try:
            landmark_dist = int(landmark.get("distance", 99))
        except (TypeError, ValueError):
            landmark_dist = 99

        count = 0
        if area_type == "frontier":
            if path in {"road", "freeway"}:
                count += 1
            elif path and rng.random() < 0.50:
                count += 1
            elif terrain in {"badlands", "ruins"} and rng.random() < 0.24:
                count += 1
            elif rng.random() < 0.10:
                count += 1

            if landmark_dist <= 1:
                count += 1
            elif landmark_dist <= 2 and rng.random() < 0.45:
                count += 1

            if path in {"road", "freeway"} and landmark_dist <= 2 and rng.random() < 0.35:
                count += 1
            return max(0, self._non_city_dense_site_count(descriptor, rng, count))

        if area_type == "wilderness":
            if terrain in {"forest", "marsh"}:
                if rng.random() < 0.18:
                    count += 1
            elif terrain in {"hills", "ruins"}:
                if rng.random() < 0.26:
                    count += 1
            elif rng.random() < 0.08:
                count += 1

            if path in {"trail", "road"} and rng.random() < 0.38:
                count += 1
            elif path == "freeway" and rng.random() < 0.55:
                count += 1

            if landmark_id in {"radio_spire", "shatter_ruins", "ancient_grove", "glass_marsh"}:
                count += 1
            elif landmark_dist <= 1:
                count += 1
            elif landmark_dist <= 2 and rng.random() < 0.30:
                count += 1

            return max(0, self._non_city_dense_site_count(descriptor, rng, count))

        if area_type == "coastal":
            if terrain in {"shore", "shoals", "lake", "island", "ocean", "waterway"}:
                if rng.random() < 0.34:
                    count += 1
            elif rng.random() < 0.16:
                count += 1

            if path in {"road", "freeway"} and rng.random() < 0.55:
                count += 1
            elif path and rng.random() < 0.35:
                count += 1

            if landmark_dist <= 1:
                count += 1
            elif landmark_dist <= 2 and rng.random() < 0.45:
                count += 1

            return max(0, self._non_city_dense_site_count(descriptor, rng, count))

        if path:
            count += 1
        if landmark_dist <= 2:
            count += 1
        return max(0, self._non_city_dense_site_count(descriptor, rng, count))

    def _build_non_city_site_record(self, descriptor, kind, idx, used_site_names=None):
        kind = str(kind or "").strip().lower()
        if not kind:
            return {}

        descriptor = descriptor if isinstance(descriptor, dict) else {}
        used_site_names = used_site_names if isinstance(used_site_names, set) else set()
        site_name = self.NON_CITY_SITE_LABELS.get(kind, kind.replace("_", " ").title())
        business_founder = None
        if kind in self.NAMED_NON_CITY_SITE_KINDS or kind in self.NAMED_BUSINESS_ARCHETYPES:
            name_rng = random.Random(
                f"{self.seed}:non_city_site_name:{descriptor.get('cx')}:{descriptor.get('cy')}:{idx}:{kind}"
            )
            site_name, business_founder = self._non_city_site_name_for(kind, name_rng, used_site_names)

        return {
            "site_id": f"site:{int(idx)}",
            "kind": kind,
            "name": site_name,
            "business_name": site_name if business_founder else None,
            "business_founder_name": business_founder.get("full_name") if business_founder else None,
            "business_founder_first_name": business_founder.get("first_name") if business_founder else None,
            "business_founder_last_name": business_founder.get("last_name") if business_founder else None,
            "public": kind in self.PUBLIC_NON_CITY_SITE_KINDS,
        }

    def _non_city_weighted_city_service_candidates(self, *, existing_kinds=(), weights=()):
        existing = {
            str(kind).strip().lower()
            for kind in tuple(existing_kinds or ())
            if str(kind).strip()
        }
        archetypes = {
            str(kind).strip().lower()
            for kind in tuple(self.building_archetypes or ())
            if str(kind).strip()
        }
        candidates = []
        for raw_kind in tuple(weights or ()):
            key = str(raw_kind).strip().lower()
            if not key or key in existing:
                continue
            if key not in archetypes and key not in self.NAMED_BUSINESS_ARCHETYPES:
                continue
            candidates.append(key)
        return tuple(candidates)

    def _non_city_outsider_site_candidates(self, descriptor, *, existing_kinds=()):
        descriptor = descriptor if isinstance(descriptor, dict) else {}
        native_kinds = {
            str(kind).strip().lower()
            for kind in tuple(self._non_city_site_pool(descriptor) or ())
            if str(kind).strip()
        }
        existing = {
            str(kind).strip().lower()
            for kind in tuple(existing_kinds or ())
            if str(kind).strip()
        }

        cross_area = []
        for kind in sorted(self.NON_CITY_SITE_LABELS):
            if kind in native_kinds or kind in existing:
                continue
            profile = site_gameplay_profile({"kind": kind})
            if not (
                bool(profile.get("public"))
                or bool(profile.get("is_storefront"))
                or tuple(profile.get("finance_services", ()))
                or tuple(profile.get("site_services", ()))
            ):
                continue
            cross_area.append(kind)

        rural_like = list(self._non_city_weighted_city_service_candidates(
            existing_kinds=tuple(existing | native_kinds),
            weights=self.NON_CITY_RURAL_COUNTERPART_WEIGHTS,
        ))

        city_like = []
        for kind in tuple(self.building_archetypes or ()):
            key = str(kind).strip().lower()
            if not key or key in native_kinds or key in existing:
                continue
            if key in self.STOREFRONT_ARCHETYPES or key in self.PUBLIC_BUILDING_ARCHETYPES:
                city_like.append(key)
                continue
            if key in FINANCE_SERVICE_FALLBACKS:
                city_like.append(key)
                continue
            if default_site_services_for_archetype(key):
                city_like.append(key)

        # Bias toward rural counterparts first, while still allowing cross-area
        # site kinds and the wider service-building pool to show up once in a while.
        return tuple(cross_area + rural_like + city_like)

    def _build_non_city_outsider_site_record(self, descriptor, kind, idx, used_site_names=None):
        descriptor = descriptor if isinstance(descriptor, dict) else {}
        key = str(kind or "").strip().lower()
        site = self._build_non_city_site_record(descriptor, key, idx, used_site_names)
        if not site:
            return {}

        if key not in self.NON_CITY_SITE_LABELS:
            seed_token = (
                f"non-city-outsider:{self.seed}:{descriptor.get('cx')}:{descriptor.get('cy')}:"
                f"{descriptor.get('area_type', '')}:{descriptor.get('district_type', '')}:{idx}:{key}"
            )
            finance_services = list(FINANCE_SERVICE_FALLBACKS.get(key, ()))
            if finance_services:
                site["finance_services"] = list(finance_services)
            site_services = list(default_site_services_for_archetype(key, seed_token=seed_token))
            if site_services:
                site["site_services"] = list(site_services)
            if key in self.STOREFRONT_ARCHETYPES:
                site["is_storefront"] = True
            if key in self.NON_CITY_RURAL_COUNTERPART_ARCHETYPES:
                site["rural_counterpart"] = True
            site["public"] = bool(
                site.get("public")
                or key in self.STOREFRONT_ARCHETYPES
                or key in self.PUBLIC_BUILDING_ARCHETYPES
                or finance_services
                or site_services
            )
            site["outsider_source"] = "city_building"
        else:
            site["outsider_source"] = "cross_area_site"

        site["outsider"] = True
        site["native_area_type"] = str(descriptor.get("area_type", "") or "").strip().lower()
        site["native_district_type"] = str(descriptor.get("district_type", "") or "").strip().lower()
        return site

    def _apply_non_city_outsider_sites(self, descriptor, rng, sites):
        prepared = [dict(site) for site in tuple(sites or ()) if isinstance(site, dict)]
        if not prepared or len(prepared) >= 2:
            return prepared

        descriptor = descriptor if isinstance(descriptor, dict) else {}
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        chance = float(self.NON_CITY_OUTSIDER_SITE_CHANCE_BY_AREA.get(area_type, 0.03))
        if chance <= 0.0 or rng.random() >= chance:
            return prepared

        existing_kinds = [
            str(site.get("kind", "") or "").strip().lower()
            for site in prepared
            if str(site.get("kind", "") or "").strip()
        ]
        candidates = list(self._non_city_outsider_site_candidates(descriptor, existing_kinds=existing_kinds))
        if not candidates:
            return prepared

        used_site_names = {
            str(site.get("name", "")).strip()
            for site in prepared
            if str(site.get("name", "")).strip()
        }
        outsider_kind = str(rng.choice(candidates)).strip().lower()
        outsider_site = self._build_non_city_outsider_site_record(
            descriptor,
            outsider_kind,
            len(prepared),
            used_site_names,
        )
        if outsider_site:
            prepared.append(outsider_site)
        return prepared

    def _apply_non_city_compound_service_sites(self, descriptor, rng, sites):
        prepared = [dict(site) for site in tuple(sites or ()) if isinstance(site, dict)]
        if len(prepared) < 3:
            return prepared

        descriptor = descriptor if isinstance(descriptor, dict) else {}
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        chance = float(self.NON_CITY_COMPOUND_SERVICE_CHANCE_BY_AREA.get(area_type, 0.0))
        if chance <= 0.0 or rng.random() >= chance:
            return prepared

        replace_index = len(prepared) - 1
        existing_kinds = [
            str(site.get("kind", "") or "").strip().lower()
            for index, site in enumerate(prepared)
            if index != replace_index and str(site.get("kind", "") or "").strip()
        ]
        candidates = list(self._non_city_weighted_city_service_candidates(
            existing_kinds=existing_kinds,
            weights=self.NON_CITY_COMPOUND_SERVICE_WEIGHTS,
        ))
        if not candidates:
            return prepared

        used_site_names = {
            str(site.get("name", "")).strip()
            for index, site in enumerate(prepared)
            if index != replace_index and str(site.get("name", "")).strip()
        }
        service_kind = str(rng.choice(candidates)).strip().lower()
        service_site = self._build_non_city_outsider_site_record(
            descriptor,
            service_kind,
            replace_index,
            used_site_names,
        )
        if service_site:
            service_site["compound_service"] = True
            service_site["city_weighted_service"] = True
            prepared[replace_index] = service_site
        return prepared

    def _apply_non_city_compound_market_site(self, descriptor, rng, sites):
        prepared = [dict(site) for site in tuple(sites or ()) if isinstance(site, dict)]
        if len(prepared) < 3:
            return prepared

        descriptor = descriptor if isinstance(descriptor, dict) else {}
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        chance = float(self.NON_CITY_COMPOUND_MARKET_CHANCE_BY_AREA.get(area_type, 0.0))
        if chance <= 0.0 or rng.random() >= chance:
            return prepared
        if any(str(site.get("span_kind", "") or "").strip().lower() == "non_city_compound_market" for site in prepared):
            return prepared

        used_site_names = {
            str(site.get("name", "")).strip()
            for site in prepared
            if str(site.get("name", "")).strip()
        }
        market_site = self._build_non_city_compound_market_site_record(
            descriptor,
            0,
            used_site_names,
            rng,
        )
        if not market_site:
            return prepared
        return [market_site] + prepared

    def _generate_non_city_sites_base(self, descriptor, rng):
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        if area_type == "city":
            return []

        pool = list(self._non_city_site_pool(descriptor))
        if not pool:
            return []

        count = int(self._non_city_site_count(descriptor, rng))
        if count <= 0:
            return []

        sites = []
        used_kinds = set()
        used_site_names = set()
        for idx in range(count):
            kind = rng.choice(pool)
            if len(used_kinds) < len(set(pool)):
                attempts = 0
                while kind in used_kinds and attempts < 8:
                    kind = rng.choice(pool)
                    attempts += 1
            used_kinds.add(kind)
            sites.append(self._build_non_city_site_record(descriptor, kind, idx, used_site_names))

        sites = self._apply_non_city_compound_service_sites(descriptor, rng, sites)
        sites = self._apply_non_city_compound_market_site(descriptor, rng, sites)
        return self._apply_non_city_outsider_sites(descriptor, rng, sites)

    def generate_non_city_sites(self, descriptor, rng):
        return self._apply_non_city_specialty(
            descriptor,
            self._generate_non_city_sites_base(descriptor, rng),
        )

    def predict_non_city_sites(self, cx, cy, descriptor=None):
        cx = int(cx)
        cy = int(cy)
        if descriptor is None:
            descriptor = self.overworld_descriptor(cx, cy)
        return self.generate_non_city_sites(descriptor, self.chunk_site_rng(cx, cy))

    @staticmethod
    def _interest_site_detail(sites):
        names = [
            str(site.get("name", "")).strip()
            for site in sites or ()
            if isinstance(site, dict) and str(site.get("name", "")).strip()
        ]
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} + {names[1]}"
        return f"{names[0]} + {names[1]} +{len(names) - 2}"

    @staticmethod
    def _focus_join(labels):
        cleaned = [str(label).strip() for label in labels or () if str(label).strip()]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return cleaned[0]
        return f"{cleaned[0]} + {cleaned[1]}"

    @staticmethod
    def _ordered_unique_labels(labels):
        ordered = []
        seen = set()
        for raw in labels or ():
            label = str(raw).strip().lower()
            if not label or label in seen:
                continue
            seen.add(label)
            ordered.append(label)
        return tuple(ordered)

    def _city_identity_label(self, district_type):
        district_type = str(district_type or "").strip().lower() or "unknown"
        return str(
            self.CITY_TRAVEL_LABELS.get(district_type, district_type.replace("_", " ").strip() or "city blocks")
        ).strip() or "city blocks"

    def _non_city_identity_label(self, area_type, *, terrain="", path="", landmark_id="", site_kinds=()):
        area_type = str(area_type or "").strip().lower() or "frontier"
        terrain = str(terrain or "").strip().lower()
        path = str(path or "").strip().lower()
        landmark_id = str(landmark_id or "").strip().lower()
        site_kinds = {
            str(kind).strip().lower()
            for kind in tuple(site_kinds or ())
            if str(kind).strip()
        }

        if area_type == "frontier":
            if site_kinds.intersection({"relay_post", "truck_stop", "roadhouse"}) and path in {"road", "freeway"}:
                return "relay corridor"
            if site_kinds.intersection({"salvage_camp", "breaker_yard", "work_shed"}):
                return "salvage belt"
            if "inspection_shed" in site_kinds:
                return "watch strip"
            if "pump_house" in site_kinds:
                return "pump line"
            if terrain in {"badlands", "dunes"}:
                return "dry reach"
            if terrain == "ruins" or landmark_id == "shatter_ruins":
                return "broken reach"
            return "open frontier"

        if area_type == "wilderness":
            if terrain == "marsh" or "herbalist_camp" in site_kinds or landmark_id == "glass_marsh":
                return "marsh belt"
            if terrain == "ruins" or "ruin_shelter" in site_kinds or landmark_id == "shatter_ruins":
                return "ruin tract"
            if (
                terrain == "hills"
                or site_kinds.intersection({"firewatch_tower", "weather_station", "survey_post", "lookout_post"})
                or landmark_id == "radio_spire"
            ):
                return "ridge watch"
            if terrain == "forest" or site_kinds.intersection({"field_camp", "ranger_hut"}) or landmark_id == "ancient_grove":
                return "deep green"
            return "wild interior"

        if area_type == "coastal":
            if site_kinds.intersection({"ferry_post", "tide_station"}):
                return "ferry chain"
            if site_kinds.intersection({"coast_watch", "beacon_house"}) or landmark_id == "storm_break":
                return "storm watch"
            if "drydock_yard" in site_kinds:
                return "drydock reach"
            if site_kinds.intersection({"dock_shack", "net_house", "bait_shop"}):
                return "working shore"
            return "open coast"

        return area_type.replace("_", " ").strip() or "outlands"

    def non_city_specialty_profile(self, descriptor, *, site_kinds=()):
        descriptor = descriptor if isinstance(descriptor, dict) else {}
        area_type = str(descriptor.get("area_type", "frontier")).strip().lower() or "frontier"
        if area_type == "city":
            return {}

        terrain = str(descriptor.get("terrain", self.OVERWORLD_TERRAIN_DEFAULT.get(area_type, "plains"))).strip().lower()
        path = str(descriptor.get("path", "")).strip().lower()
        landmark = descriptor.get("landmark") or descriptor.get("nearest_landmark") or {}
        landmark_id = str(landmark.get("id", "") or "").strip().lower()
        identity_label = self._non_city_identity_label(
            area_type,
            terrain=terrain,
            path=path,
            landmark_id=landmark_id,
            site_kinds=site_kinds,
        )
        theme_id = str(self.NON_CITY_SPECIALTY_ALIASES.get(identity_label, "") or "").strip().lower()
        if not theme_id:
            return {
                "theme_id": "",
                "identity_label": str(identity_label).strip(),
                "site_services_by_kind": {},
                "opportunity_tags_by_kind": {},
                "discovery_overrides": {},
            }

        raw = self.NON_CITY_SPECIALTY_PROFILES.get(theme_id, {})
        site_services_by_kind = {}
        for kind, services in dict(raw.get("site_services_by_kind", {})).items():
            key = str(kind).strip().lower()
            labels = self._ordered_unique_labels(services)
            if key and labels:
                site_services_by_kind[key] = labels

        opportunity_tags_by_kind = {}
        for kind, tags in dict(raw.get("opportunity_tags_by_kind", {})).items():
            key = str(kind).strip().lower()
            labels = self._ordered_unique_labels(tags)
            if key and labels:
                opportunity_tags_by_kind[key] = labels

        discovery_overrides = {}
        for kind, payload in dict(raw.get("discovery_overrides", {})).items():
            key = str(kind).strip().lower()
            if not key or not isinstance(payload, dict):
                continue
            cleaned = {}
            label = str(payload.get("label", "")).strip()
            if label:
                cleaned["label"] = label
            item_pool = self._ordered_unique_labels(payload.get("item_pool", ()))
            if item_pool:
                cleaned["item_pool"] = item_pool
            for field in ("credits_min", "credits_max", "energy_gain", "safety_gain", "social_gain", "intel_radius"):
                if field in payload:
                    try:
                        cleaned[field] = int(payload.get(field, 0))
                    except (TypeError, ValueError):
                        continue
            if cleaned:
                discovery_overrides[key] = cleaned

        bonus_site_kinds_by_identity = {}
        for identity_key, kinds in dict(raw.get("bonus_site_kinds_by_identity", {})).items():
            key = str(identity_key).strip().lower()
            labels = self._ordered_unique_labels(kinds)
            if key and labels:
                bonus_site_kinds_by_identity[key] = labels

        bonus_site_kinds = self._ordered_unique_labels(
            tuple(bonus_site_kinds_by_identity.get(str(identity_label).strip().lower(), ()))
            + tuple(raw.get("bonus_site_kinds", ()))
        )
        focus_site_kinds = self._ordered_unique_labels(
            tuple(site_services_by_kind.keys())
            + tuple(opportunity_tags_by_kind.keys())
            + tuple(bonus_site_kinds)
        )

        try:
            minimum_focus_sites = max(0, int(raw.get("minimum_focus_sites", 0)))
        except (TypeError, ValueError):
            minimum_focus_sites = 0

        return {
            "theme_id": theme_id,
            "identity_label": str(identity_label).strip(),
            "site_services_by_kind": site_services_by_kind,
            "opportunity_tags_by_kind": opportunity_tags_by_kind,
            "discovery_overrides": discovery_overrides,
            "bonus_site_kinds": bonus_site_kinds,
            "focus_site_kinds": focus_site_kinds,
            "minimum_focus_sites": minimum_focus_sites,
        }

    def _apply_non_city_specialty(self, descriptor, sites):
        prepared = [dict(site) for site in tuple(sites or ()) if isinstance(site, dict)]
        if not prepared:
            return []

        site_kinds = tuple(
            str(site.get("kind", "") or "").strip().lower()
            for site in prepared
            if str(site.get("kind", "") or "").strip()
        )
        specialty = self.non_city_specialty_profile(descriptor, site_kinds=site_kinds)
        theme_id = str((specialty or {}).get("theme_id", "") or "").strip().lower()
        label = str((specialty or {}).get("identity_label", "") or "").strip()
        service_map = (specialty or {}).get("site_services_by_kind", {})
        opportunity_map = (specialty or {}).get("opportunity_tags_by_kind", {})
        focus_kinds = {
            str(kind).strip().lower()
            for kind in tuple((specialty or {}).get("focus_site_kinds", ()))
            if str(kind).strip()
        }
        bonus_kinds = [
            str(kind).strip().lower()
            for kind in tuple((specialty or {}).get("bonus_site_kinds", ()))
            if str(kind).strip()
        ]
        minimum_focus_sites = int((specialty or {}).get("minimum_focus_sites", 0) or 0)

        if theme_id and focus_kinds and bonus_kinds:
            current_focus = {
                kind
                for kind in site_kinds
                if kind in focus_kinds
            }
            if len(current_focus) < minimum_focus_sites:
                used_kinds = {kind for kind in site_kinds if kind}
                available_bonus = [kind for kind in bonus_kinds if kind not in used_kinds]
                if available_bonus:
                    bonus_rng = random.Random(
                        f"{self.seed}:non_city_specialty_bonus:{descriptor.get('cx')}:{descriptor.get('cy')}:{theme_id}:{label}"
                    )
                    used_site_names = {
                        str(site.get("name", "")).strip()
                        for site in prepared
                        if str(site.get("name", "")).strip()
                    }
                    bonus_rng.shuffle(available_bonus)
                    for bonus_kind in available_bonus:
                        if len(current_focus) >= minimum_focus_sites:
                            break
                        prepared.append(
                            self._build_non_city_site_record(descriptor, bonus_kind, len(prepared), used_site_names)
                        )
                        used_kinds.add(bonus_kind)
                        current_focus.add(bonus_kind)
                        used_site_names = {
                            str(site.get("name", "")).strip()
                            for site in prepared
                            if str(site.get("name", "")).strip()
                        }

        enriched = []
        for site in prepared:
            kind = str(site.get("kind", "") or "").strip().lower()
            extra_services = tuple(service_map.get(kind, ())) if kind else ()
            extra_opportunities = tuple(opportunity_map.get(kind, ())) if kind else ()
            if extra_services:
                site["site_services"] = list(
                    self._ordered_unique_labels(tuple(site.get("site_services", ())) + tuple(extra_services))
                )
            if extra_opportunities:
                site["opportunity_tags"] = list(
                    self._ordered_unique_labels(tuple(site.get("opportunity_tags", ())) + tuple(extra_opportunities))
                )
            if theme_id:
                site["specialty_theme"] = theme_id
            if label:
                site["specialty_label"] = label
            enriched.append(site)
        return enriched

    def overworld_identity_profile(self, cx, cy, descriptor=None, interest=None, travel=None, discovery=None, site_kinds=None):
        cx = int(cx)
        cy = int(cy)
        if descriptor is None:
            descriptor = self.overworld_descriptor(cx, cy)
        if interest is None:
            interest = self.overworld_interest(cx, cy, descriptor=descriptor)
        if travel is None:
            travel = self.overworld_travel_profile(cx, cy, descriptor=descriptor, interest=interest)
        if discovery is None:
            discovery = self.overworld_discovery_profile(
                cx,
                cy,
                descriptor=descriptor,
                interest=interest,
                travel=travel,
            )

        area_type = str(descriptor.get("area_type", "city")).strip().lower() or "city"
        district_type = str(descriptor.get("district_type", "unknown")).strip().lower() or "unknown"
        terrain = str(descriptor.get("terrain", self.OVERWORLD_TERRAIN_DEFAULT.get(area_type, "plains"))).strip().lower()
        path = str(descriptor.get("path", "")).strip().lower()
        landmark = descriptor.get("landmark") or descriptor.get("nearest_landmark") or {}
        landmark_id = str(landmark.get("id", "") or "").strip().lower()
        support_tags = tuple(
            str(tag).strip().lower()
            for tag in tuple((travel or {}).get("support_tags", ()) or ())
            if str(tag).strip()
        )
        opportunity_tags = tuple(
            str(tag).strip().lower()
            for tag in tuple((travel or {}).get("opportunity_tags", ()) or ())
            if str(tag).strip()
        )
        risk_label = str((travel or {}).get("risk_label", "low")).strip().lower() or "low"

        if site_kinds is None:
            sites = self.predict_non_city_sites(cx, cy, descriptor=descriptor) if area_type != "city" else ()
            site_kinds = tuple(
                sorted(
                    {
                        str((site or {}).get("kind", "") or "").strip().lower()
                        for site in tuple(sites or ())
                        if isinstance(site, dict) and str((site or {}).get("kind", "") or "").strip()
                    }
                )
            )
        else:
            site_kinds = tuple(
                sorted(
                    {
                        str(kind).strip().lower()
                        for kind in tuple(site_kinds or ())
                        if str(kind).strip()
                    }
                )
            )

        specialty = {}
        if area_type != "city":
            specialty = self.non_city_specialty_profile(descriptor, site_kinds=site_kinds)

        if area_type == "city":
            label = self._city_identity_label(district_type)
        else:
            label = self._non_city_identity_label(
                area_type,
                terrain=terrain,
                path=path,
                landmark_id=landmark_id,
                site_kinds=site_kinds,
            )

        focus_bits = []
        if area_type != "city" and path in {"freeway", "road", "trail"}:
            focus_bits.append(f"{path}-linked")
        support_focus = self._focus_join(self.OVERWORLD_SUPPORT_READS.get(tag, "") for tag in support_tags[:2])
        if support_focus:
            focus_bits.append(support_focus)
        else:
            opportunity_focus = self._focus_join(self.OVERWORLD_OPPORTUNITY_READS.get(tag, "") for tag in opportunity_tags[:2])
            if opportunity_focus:
                focus_bits.append(opportunity_focus)

        if risk_label == "hazardous":
            focus_bits.append("rougher travel")
        elif risk_label == "exposed":
            focus_bits.append("watchful travel")
        elif risk_label == "low" and area_type != "city":
            focus_bits.append("lighter travel")

        hook = ", ".join(bit for bit in focus_bits[:3] if str(bit).strip())
        detail = str(label).strip()
        if hook:
            detail = f"{detail}; {hook}"

        return {
            "label": str(label).strip(),
            "hook": hook,
            "detail": detail,
            "theme_id": str((specialty or {}).get("theme_id", "") or "").strip().lower(),
            "specialty_label": str((specialty or {}).get("identity_label", "") or "").strip(),
            "site_kinds": site_kinds,
            "support_tags": support_tags,
            "opportunity_tags": opportunity_tags,
            "region_name": str(descriptor.get("region_name", "") or "").strip(),
            "settlement_name": str(descriptor.get("settlement_name", "") or "").strip(),
            "interest_detail": str((interest or {}).get("detail", "") or "").strip(),
            "discovery_label": str((discovery or {}).get("label", "") or "").strip(),
        }

    def overworld_interest(self, cx, cy, descriptor=None):
        cx = int(cx)
        cy = int(cy)
        if descriptor is None:
            descriptor = self.overworld_descriptor(cx, cy)

        area_type = str(descriptor.get("area_type", "city")).strip().lower() or "city"
        district_type = str(descriptor.get("district_type", "unknown")).strip().lower() or "unknown"
        path = str(descriptor.get("path", "")).strip().lower()
        landmark = descriptor.get("landmark") or descriptor.get("nearest_landmark") or {}
        try:
            landmark_dist = int(landmark.get("distance", 99))
        except (TypeError, ValueError):
            landmark_dist = 99

        if area_type == "city":
            label = self.CITY_TRAVEL_LABELS.get(district_type, district_type.replace("_", " ").strip())
            return {
                "kind": "district_focus",
                "label": str(label or "city blocks").strip() or "city blocks",
                "detail": str(label or "city blocks").strip() or "city blocks",
                "glyph": "",
                "color": "",
                "count": 0,
                "prominence": 1,
                "show_on_map": False,
            }

        sites = self.predict_non_city_sites(cx, cy, descriptor=descriptor)
        if not sites:
            terrain = str(descriptor.get("terrain", area_type)).replace("_", " ").strip()
            fallback = terrain or area_type
            return {
                "kind": "terrain",
                "label": fallback,
                "detail": fallback,
                "glyph": "",
                "color": "",
                "count": 0,
                "prominence": 0,
                "show_on_map": False,
            }

        primary = next(
            (site for site in sites if isinstance(site, dict) and site.get("public")),
            sites[0],
        )
        kind = str(primary.get("kind", "site")).strip().lower() or "site"
        label = str(primary.get("name", self.NON_CITY_SITE_LABELS.get(kind, "Site"))).strip() or "Site"
        detail = self._interest_site_detail(sites) or label
        prominence = 1
        if primary.get("public"):
            prominence += 1
        if path:
            prominence += 1
        if len(sites) > 1:
            prominence += 1
        if landmark_dist <= 2:
            prominence += 1

        return {
            "kind": "site",
            "label": label,
            "detail": detail,
            "glyph": self.NON_CITY_SITE_GLYPHS.get(kind, "S"),
            "color": self.NON_CITY_SITE_COLORS.get(kind, "human"),
            "count": len(sites),
            "prominence": prominence,
            "show_on_map": prominence >= 2,
        }

    def overworld_travel_profile(self, cx, cy, descriptor=None, interest=None):
        cx = int(cx)
        cy = int(cy)
        if descriptor is None:
            descriptor = self.overworld_descriptor(cx, cy)
        if interest is None:
            interest = self.overworld_interest(cx, cy, descriptor=descriptor)

        area_type = str(descriptor.get("area_type", "city")).strip().lower() or "city"
        district_type = str(descriptor.get("district_type", "unknown")).strip().lower() or "unknown"
        terrain = str(descriptor.get("terrain", self.OVERWORLD_TERRAIN_DEFAULT.get(area_type, "plains"))).strip().lower()
        path = str(descriptor.get("path", "")).strip().lower()

        base = dict(self.OVERWORLD_TRAVEL_BASE.get(area_type, self.OVERWORLD_TRAVEL_BASE["frontier"]))
        energy_cost = int(base.get("energy", 0))
        safety_cost = int(base.get("safety", 0))
        social_cost = int(base.get("social", 0))
        risk_score = int(base.get("risk", 0))

        terrain_mods = self.OVERWORLD_TERRAIN_TRAVEL_MODS.get(terrain, {})
        energy_cost += int(terrain_mods.get("energy", 0))
        safety_cost += int(terrain_mods.get("safety", 0))
        social_cost += int(terrain_mods.get("social", 0))
        risk_score += int(terrain_mods.get("risk", 0))

        support_tags = set()
        opportunity_counts = Counter()

        if area_type == "city":
            city_support = tuple(self.CITY_TRAVEL_SUPPORT.get(district_type, ("services",)))
            support_tags.update(city_support)
            opportunity_counts.update(city_support)

            district = self.get_chunk(cx, cy).get("district", {})
            try:
                security_level = int(district.get("security_level", 5))
            except (TypeError, ValueError):
                security_level = 5
            if security_level >= 7:
                risk_score -= 1
                safety_cost -= 1
            elif security_level <= 3:
                risk_score += 1
                safety_cost += 1
            if district_type == "slums":
                risk_score += 1
            elif district_type == "military":
                risk_score -= 1
        else:
            sites = self.predict_non_city_sites(cx, cy, descriptor=descriptor)
            public_support = False
            for site in sites:
                kind = str((site or {}).get("kind", "") or "").strip().lower()
                profile = site_gameplay_profile(site)
                if profile.get("public"):
                    public_support = True
                if profile.get("is_storefront"):
                    support_tags.add("trade")
                for service in profile.get("site_services", ()):
                    support_tags.update(self.NON_CITY_SITE_SERVICE_SUPPORTS.get(str(service).strip().lower(), ()))
                opportunity_counts.update(self.NON_CITY_SITE_TRAVEL_OPPORTUNITIES.get(kind, ()))
                opportunity_counts.update(profile.get("opportunity_tags", ()))

            if public_support:
                safety_cost -= 1
                risk_score -= 1
            if "shelter" in support_tags:
                energy_cost -= 1
                social_cost -= 1
            if "intel" in support_tags:
                risk_score -= 1
            if "trade" in support_tags:
                energy_cost -= 1

        path_mods = self.OVERWORLD_PATH_TRAVEL_MODS.get(path, {})
        energy_cost += int(path_mods.get("energy", 0))
        safety_cost += int(path_mods.get("safety", 0))
        social_cost += int(path_mods.get("social", 0))
        risk_score += int(path_mods.get("risk", 0))

        nearest_landmark = descriptor.get("nearest_landmark") or {}
        landmark_name = str(nearest_landmark.get("name", "")).strip()
        try:
            landmark_dist = int(nearest_landmark.get("distance", 99))
        except (TypeError, ValueError):
            landmark_dist = 99
        if landmark_name and landmark_dist <= 2:
            opportunity_counts["landmark"] += 2 if area_type != "city" else 1
            if terrain in {"ruins", "industrial_waste", "badlands"}:
                risk_score += 1

        if area_type == "city":
            energy_cost = min(1, energy_cost)
            safety_cost = min(1, safety_cost)
            social_cost = 0

        energy_cost = max(0, min(4, energy_cost))
        safety_cost = max(0, min(3, safety_cost))
        social_cost = max(0, min(2, social_cost))
        risk_score = max(0, min(4, risk_score))

        if risk_score <= 0:
            risk_label = "calm"
        elif risk_score == 1:
            risk_label = "low"
        elif risk_score == 2:
            risk_label = "exposed"
        else:
            risk_label = "hazardous"

        support_order = (
            "services",
            "trade",
            "shelter",
            "intel",
            "security",
            "social",
            "supplies",
        )
        support_list = [tag for tag in support_order if tag in support_tags]
        support_label = "/".join(support_list[:2]) if support_list else "none"

        opportunity_order = ("landmark", "salvage", "water", "tools", "supplies")
        opportunity_list = sorted(
            (tag for tag in opportunity_order if int(opportunity_counts.get(tag, 0)) > 0),
            key=lambda tag: (-int(opportunity_counts.get(tag, 0)), opportunity_order.index(tag)),
        )

        return {
            "risk_score": risk_score,
            "risk_label": risk_label,
            "support_tags": tuple(support_list),
            "support_label": support_label,
            "opportunity_tags": tuple(opportunity_list),
            "opportunity_counts": {
                tag: int(opportunity_counts.get(tag, 0))
                for tag in opportunity_order
                if int(opportunity_counts.get(tag, 0)) > 0
            },
            "energy_cost": energy_cost,
            "safety_cost": safety_cost,
            "social_cost": social_cost,
            "interest_detail": str((interest or {}).get("detail", "")).strip(),
        }

    def overworld_discovery_profile(self, cx, cy, descriptor=None, interest=None, travel=None):
        cx = int(cx)
        cy = int(cy)
        if descriptor is None:
            descriptor = self.overworld_descriptor(cx, cy)
        if interest is None:
            interest = self.overworld_interest(cx, cy, descriptor=descriptor)
        if travel is None:
            travel = self.overworld_travel_profile(cx, cy, descriptor=descriptor, interest=interest)

        area_type = str(descriptor.get("area_type", "city")).strip().lower() or "city"
        opportunity_tags = tuple(
            str(tag).strip().lower()
            for tag in travel.get("opportunity_tags", ())
            if str(tag).strip()
        )
        discovery_kind = ""
        for candidate in opportunity_tags:
            if candidate in self.OVERWORLD_DISCOVERY_PROFILES:
                discovery_kind = candidate
                break
        if not discovery_kind:
            for candidate in ("salvage", "water", "supplies", "tools", "landmark"):
                if candidate in opportunity_tags:
                    discovery_kind = candidate
                    break
        if not discovery_kind:
            return {
                "kind": "",
                "label": "",
                "item_pool": (),
                "credits_min": 0,
                "credits_max": 0,
                "energy_gain": 0,
                "safety_gain": 0,
                "social_gain": 0,
                "intel_radius": 0,
            }

        profile = dict(self.OVERWORLD_DISCOVERY_PROFILES.get(discovery_kind, {}))
        specialty = {}
        if area_type != "city":
            sites = self.predict_non_city_sites(cx, cy, descriptor=descriptor)
            site_kinds = tuple(
                str((site or {}).get("kind", "") or "").strip().lower()
                for site in tuple(sites or ())
                if isinstance(site, dict) and str((site or {}).get("kind", "") or "").strip()
            )
            specialty = self.non_city_specialty_profile(descriptor, site_kinds=site_kinds)
        override = {}
        if isinstance(specialty, dict):
            override = dict((specialty.get("discovery_overrides") or {}).get(discovery_kind, {}) or {})

        item_pool = self._ordered_unique_labels(tuple(profile.get("item_pool", ())) + tuple(override.get("item_pool", ())))
        return {
            "kind": discovery_kind,
            "label": str(override.get("label", profile.get("label", discovery_kind.replace("_", " ")))).strip(),
            "item_pool": item_pool,
            "credits_min": int(override.get("credits_min", profile.get("credits_min", 0))),
            "credits_max": int(override.get("credits_max", profile.get("credits_max", 0))),
            "energy_gain": int(override.get("energy_gain", profile.get("energy_gain", 0))),
            "safety_gain": int(override.get("safety_gain", profile.get("safety_gain", 0))),
            "social_gain": int(override.get("social_gain", profile.get("social_gain", 0))),
            "intel_radius": int(override.get("intel_radius", profile.get("intel_radius", 0))),
        }

    @staticmethod
    def _segment_hit(cx, cy, x1, y1, x2, y2, width=0):
        w = int(max(0, width))
        if y1 == y2:
            lo, hi = sorted((x1, x2))
            return lo <= cx <= hi and abs(cy - y1) <= w
        if x1 == x2:
            lo, hi = sorted((y1, y2))
            return lo <= cy <= hi and abs(cx - x1) <= w
        return False

    def _path_kind_at(self, cx, cy):
        size = int(max(10, self.OVERWORLD_REGION_SIZE))
        rx = int(cx) // size
        ry = int(cy) // size
        priority = {"freeway": 3, "road": 2, "trail": 1}
        best = None

        for dy in range(-1, 2):
            for dx in range(-1, 2):
                src = self._region_anchor(rx + dx, ry + dy)
                east = self._region_anchor(rx + dx + 1, ry + dy)
                south = self._region_anchor(rx + dx, ry + dy + 1)

                for dst, via_x_first in ((east, True), (south, False)):
                    if src["area_type"] == "city" and dst["area_type"] == "city":
                        kind = "freeway"
                    elif src["area_type"] == "city" or dst["area_type"] == "city":
                        kind = "road"
                    else:
                        kind = "trail"
                    width = 2 if kind == "freeway" else 1 if kind == "road" else 0
                    hit = False

                    if via_x_first:
                        hit = (
                            self._segment_hit(cx, cy, src["cx"], src["cy"], dst["cx"], src["cy"], width=width)
                            or self._segment_hit(cx, cy, dst["cx"], src["cy"], dst["cx"], dst["cy"], width=width)
                        )
                    else:
                        hit = (
                            self._segment_hit(cx, cy, src["cx"], src["cy"], src["cx"], dst["cy"], width=width)
                            or self._segment_hit(cx, cy, src["cx"], dst["cy"], dst["cx"], dst["cy"], width=width)
                        )

                    if not hit:
                        continue
                    if best is None or priority[kind] > priority.get(best, 0):
                        best = kind

        return best

    def _nearest_landmark(self, cx, cy, max_distance=14):
        size = int(max(10, self.OVERWORLD_REGION_SIZE))
        rx = int(cx) // size
        ry = int(cy) // size
        best = None

        for dy in range(-2, 3):
            for dx in range(-2, 3):
                region = self._region_anchor(rx + dx, ry + dy)
                landmark = region.get("landmark")
                if not landmark:
                    continue
                dist = max(abs(int(cx) - int(landmark["cx"])), abs(int(cy) - int(landmark["cy"])))
                if dist > max_distance:
                    continue
                if best is None or dist < best["distance"]:
                    best = {
                        "id": landmark["id"],
                        "name": landmark["name"],
                        "glyph": landmark["glyph"],
                        "color": landmark.get("color", "human"),
                        "terrain": landmark.get("terrain", region.get("terrain", "plains")),
                        "cx": int(landmark["cx"]),
                        "cy": int(landmark["cy"]),
                        "distance": int(dist),
                        "radius": int(landmark.get("radius", 0)),
                    }

        return best

    def overworld_descriptor(self, cx, cy):
        cx = int(cx)
        cy = int(cy)
        area_type = self.pick_area_type(cx, cy)
        district_type = self.pick_district_type(cx, cy)
        terrain = self.OVERWORLD_TERRAIN_DEFAULT.get(area_type, "plains")

        size = int(max(10, self.OVERWORLD_REGION_SIZE))
        rx = cx // size
        ry = cy // size
        best_influence = None
        best_region = None
        nearest_city_region = None
        nearest_city_dist = None
        nearest = self._nearest_landmark(cx, cy, max_distance=14)
        landmark_here = None

        for region, raw_influence, dist in self._nearby_region_influences(cx, cy, radius=1):
            influence = int(raw_influence)
            if str(region.get("area_type", "")).strip().lower() == "city":
                if nearest_city_dist is None or dist < nearest_city_dist:
                    nearest_city_region = region
                    nearest_city_dist = dist
            if str(region.get("area_type", "")) != area_type:
                influence -= 2
            if best_influence is None or influence > best_influence:
                best_influence = influence
                best_region = region
                if influence >= 0:
                    candidate = str(region.get("terrain", terrain))
                    if area_type != "city" and candidate in {"urban", "industrial_waste", "park"} and influence < 3:
                        pass
                    else:
                        terrain = candidate

            landmark = region.get("landmark")
            if landmark:
                lm_dist = max(abs(cx - int(landmark["cx"])), abs(cy - int(landmark["cy"])))
                if lm_dist <= int(landmark.get("radius", 0)):
                    terrain = str(landmark.get("terrain", terrain))
                if lm_dist == 0:
                    landmark_here = {
                        "id": landmark["id"],
                        "name": landmark["name"],
                        "glyph": landmark["glyph"],
                        "color": landmark.get("color", "human"),
                    }

        path = self._path_kind_at(cx, cy)
        region_name = ""
        if best_region:
            region_name = str(best_region.get("region_name", "")).strip()
        settlement_name = None
        if area_type == "city":
            if best_region and best_region.get("settlement_name"):
                settlement_name = str(best_region.get("settlement_name")).strip() or None
            elif nearest_city_region and nearest_city_region.get("settlement_name"):
                settlement_name = str(nearest_city_region.get("settlement_name")).strip() or None
        return {
            "cx": cx,
            "cy": cy,
            "area_type": area_type,
            "district_type": district_type,
            "terrain": terrain,
            "path": path,
            "landmark": landmark_here,
            "nearest_landmark": nearest,
            "region_name": region_name,
            "settlement_name": settlement_name,
        }

    def _buildings_for_district(self, district_type):
        buildings = self.buildings_by_district.get(district_type)
        if buildings:
            return buildings
        return self.CORE_BUILDINGS_BY_DISTRICT.get(district_type, ())

    def _custom_world_profile_candidates(self, *, area_type, district_type):
        profiles = getattr(self, "custom_world_profiles", {}) or {}
        if not isinstance(profiles, dict) or not profiles:
            return ()
        area_type = str(area_type or "").strip().lower()
        district_type = str(district_type or "").strip().lower()
        candidates = []
        for profile_id, profile in sorted(profiles.items()):
            if not isinstance(profile, dict):
                continue
            area_types = {
                str(value).strip().lower()
                for value in profile.get("area_types", ()) or ()
                if str(value).strip()
            }
            if area_types and area_type not in area_types:
                continue
            district_types = {
                str(value).strip().lower()
                for value in profile.get("district_types", ()) or ()
                if str(value).strip()
            }
            if district_types and district_type not in district_types:
                continue
            try:
                weight = float(profile.get("selection_weight", 1.0) or 1.0)
            except (TypeError, ValueError):
                weight = 1.0
            if weight <= 0.0:
                continue
            candidates.append((str(profile_id), profile, weight))
        return tuple(candidates)

    def _select_custom_world_profile(self, cx, cy, *, area_type, district_type):
        candidates = self._custom_world_profile_candidates(area_type=area_type, district_type=district_type)
        if not candidates:
            return None
        token = ",".join(profile_id for profile_id, _profile, _weight in candidates)
        rng = random.Random(f"{self.seed}:custom_world_profile:{cx}:{cy}:{area_type}:{district_type}:{token}")
        # Keep custom styles as a bias, not a hard replacement for every eligible chunk.
        if rng.random() >= 0.42:
            return None
        total = sum(weight for _profile_id, _profile, weight in candidates)
        pick = rng.uniform(0.0, total)
        running = 0.0
        for _profile_id, profile, weight in candidates:
            running += weight
            if pick <= running:
                return profile
        return candidates[-1][1]

    @staticmethod
    def _density_from_level(level, rng, fallback):
        level = str(level or "none").strip().lower()
        if level == "low":
            return rng.randint(2, 4)
        if level == "medium":
            return rng.randint(5, 7)
        if level == "high":
            return rng.randint(8, 10)
        return fallback

    def _choose_building_archetype(self, options, rng, district):
        options = [str(option).strip().lower() for option in options if str(option).strip()]
        if not options:
            return "house"
        profile_id = str((district or {}).get("custom_world_profile_id", "") or "").strip().lower()
        profile = (getattr(self, "custom_world_profiles", {}) or {}).get(profile_id)
        if not isinstance(profile, dict):
            return rng.choice(options)
        weights = profile.get("building_weights") if isinstance(profile.get("building_weights"), dict) else {}
        service_weights = (
            profile.get("service_building_weights")
            if isinstance(profile.get("service_building_weights"), dict)
            else {}
        )
        weighted = []
        for archetype in options:
            weight = 1.0
            if archetype in weights:
                try:
                    weight *= max(0.01, float(weights.get(archetype, 1.0) or 1.0))
                except (TypeError, ValueError):
                    pass
            if archetype in service_weights:
                try:
                    weight *= max(0.01, float(service_weights.get(archetype, 1.0) or 1.0))
                except (TypeError, ValueError):
                    pass
            weighted.append((archetype, weight))
        total = sum(weight for _archetype, weight in weighted)
        if total <= 0.0:
            return rng.choice(options)
        pick = rng.uniform(0.0, total)
        running = 0.0
        for archetype, weight in weighted:
            running += weight
            if pick <= running:
                return archetype
        return weighted[-1][0]

    def _business_suffix(self, archetype, rng):
        options = self.BUSINESS_SUFFIX_BY_ARCHETYPE.get(archetype, ("Works",))
        return rng.choice(options)

    def _name_token(self, key, rng):
        values = self.business_name_data.get(key, ())
        if not values:
            values = self.DEFAULT_BUSINESS_NAME_DATA[key]
        return rng.choice(values)

    def _default_name_token(self, key, rng):
        values = self.DEFAULT_BUSINESS_NAME_DATA.get(key, ())
        if not values:
            values = self.business_name_data.get(key, ())
        return rng.choice(values)

    def _business_founder(self, rng):
        founder_first = self._name_token("founder_first_names", rng)
        founder_last = self._name_token("founder_last_names", rng)
        return {
            "first_name": founder_first,
            "last_name": founder_last,
            "full_name": f"{founder_first} {founder_last}".strip(),
        }

    def _render_business_name(self, archetype, rng, founder=None):
        founder = founder if isinstance(founder, dict) else self._business_founder(rng)
        template = rng.choice(self.BUSINESS_NAME_TEMPLATES)
        return " ".join(template.format(
            adj=self._name_token("adjectives", rng),
            noun=self._name_token("nouns", rng),
            street=self._name_token("street_terms", rng),
            founder_first=founder.get("first_name", self._name_token("founder_first_names", rng)),
            founder_last=founder.get("last_name", self._name_token("founder_last_names", rng)),
            suffix=self._business_suffix(archetype, rng),
        ).split())

    def _render_non_city_site_name(self, archetype, rng, founder=None):
        founder = founder if isinstance(founder, dict) else self._business_founder(rng)
        template = rng.choice(self.NON_CITY_SITE_NAME_TEMPLATES)
        return " ".join(template.format(
            adj=self._default_name_token("adjectives", rng),
            noun=self._default_name_token("nouns", rng),
            street=self._default_name_token("street_terms", rng),
            founder_first=founder.get("first_name", self._default_name_token("founder_first_names", rng)),
            founder_last=founder.get("last_name", self._default_name_token("founder_last_names", rng)),
            suffix=self._business_suffix(archetype, rng),
        ).split())

    def _business_name_for(self, archetype, rng, used_names):
        for _ in range(8):
            founder = self._business_founder(rng)
            candidate = self._render_business_name(archetype, rng, founder=founder)
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate, founder

        founder = self._business_founder(rng)
        fallback = f"{founder['last_name']} {self._business_suffix(archetype, rng)} {rng.randint(11, 99)}"
        used_names.add(fallback)
        return fallback, founder

    def _non_city_site_name_for(self, archetype, rng, used_names):
        for _ in range(8):
            founder = self._business_founder(rng)
            candidate = self._render_non_city_site_name(archetype, rng, founder=founder)
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate, founder

        fallback = (
            f"{self._default_name_token('adjectives', rng)} "
            f"{self._business_suffix(archetype, rng)} {rng.randint(11, 99)}"
        )
        used_names.add(fallback)
        return fallback, None

    def _span_name_for(self, span_kind, archetype, rng, used_names):
        span_kind = str(span_kind or "").strip().lower()
        archetype = str(archetype or "").strip().lower()
        if span_kind not in {"vertical_mixed_use", "indoor_city_market"}:
            return "", None

        templates = (
            "{street} {suffix}",
            "{adj} {suffix}",
            "{noun} {suffix}",
            "{founder_last} {suffix}",
            "The {adj} {suffix}",
            "{adj} {street} {suffix}",
        )
        suffixes = tuple(self.VERTICAL_MIXED_USE_SPAN_SUFFIXES)
        if span_kind == "indoor_city_market":
            suffixes = tuple(self.INDOOR_CITY_MARKET_SPAN_SUFFIXES)
            templates = (
                "{street} {suffix}",
                "{adj} {suffix}",
                "{noun} {suffix}",
                "The {adj} {suffix}",
                "{adj} {street} {suffix}",
            )
        elif archetype in {"apartment", "tenement"}:
            suffixes = ("Flats", "House", "Court", "Gardens", "Landing", "Lofts", "Terrace", "Walk")
        elif archetype in {"bank", "brokerage"}:
            suffixes = ("Exchange", "Center", "Chambers", "Building", "Arcade", "Court", "Plaza")
        elif archetype in {"office", "co_working_hub"}:
            suffixes = ("Center", "Chambers", "Building", "Arcade", "Hall", "Galleria", "Exchange", "Plaza")
        elif archetype == "tower":
            suffixes = ("Tower", "Spire")
        elif archetype == "hotel":
            suffixes = ("House", "Arcade", "Court", "Gardens", "Landing", "Hall")

        for _ in range(8):
            founder = self._business_founder(rng)
            template = rng.choice(templates)
            candidate = " ".join(template.format(
                adj=self._default_name_token("adjectives", rng),
                noun=self._default_name_token("nouns", rng),
                street=self._default_name_token("street_terms", rng),
                founder_last=founder.get("last_name", self._default_name_token("founder_last_names", rng)),
                suffix=rng.choice(suffixes),
            ).split())
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate, founder

        fallback = f"{self._default_name_token('street_terms', rng)} {rng.choice(suffixes)} {rng.randint(11, 99)}"
        used_names.add(fallback)
        return fallback, None

    def _named_span_spec(self, archetype, rng, used_business_names, *, floor=0, child_kind="tenant", public=None):
        archetype = str(archetype or "").strip().lower()
        if not archetype:
            return {}
        business_name = None
        founder = None
        if archetype in self.NAMED_BUSINESS_ARCHETYPES:
            business_name, founder = self._business_name_for(archetype, rng, used_business_names)
        label = business_name or self.NON_CITY_SITE_LABELS.get(archetype, archetype.replace("_", " ").title())
        if public is None:
            public = archetype in self.STOREFRONT_ARCHETYPES or archetype in self.PUBLIC_BUILDING_ARCHETYPES
        return {
            "child_kind": str(child_kind or "tenant").strip().lower() or "tenant",
            "archetype": archetype,
            "name": label,
            "business_name": business_name,
            "business_founder_name": founder.get("full_name") if founder else None,
            "business_founder_first_name": founder.get("first_name") if founder else None,
            "business_founder_last_name": founder.get("last_name") if founder else None,
            "floor": int(floor),
            "public": bool(public),
            "is_storefront": archetype in self.STOREFRONT_ARCHETYPES,
        }

    def _span_specs_from_pool(self, rng, pool, count, used_business_names, *, floors=(0,), child_kind="tenant", public=None):
        specs = []
        used = set()
        pool = tuple(str(value).strip().lower() for value in tuple(pool or ()) if str(value).strip())
        floors = tuple(int(floor) for floor in tuple(floors or (0,)))
        if not pool or not floors:
            return specs
        for index in range(max(0, int(count))):
            candidates = [value for value in pool if value not in used]
            if not candidates:
                candidates = list(pool)
            archetype = str(rng.choice(candidates)).strip().lower()
            used.add(archetype)
            spec = self._named_span_spec(
                archetype,
                rng,
                used_business_names,
                floor=floors[index % len(floors)],
                child_kind=child_kind,
                public=public,
            )
            if spec:
                specs.append(spec)
        return specs

    def _ensure_span_service_anchor(self, specs, rng, used_business_names, *, anchor_pool, floors=(0,), child_kind="tenant", public=None):
        specs = [dict(spec) for spec in tuple(specs or ()) if isinstance(spec, dict)]
        if any(str(spec.get("archetype", "") or "").strip().lower() in self.SPAN_SERVICE_ANCHOR_ARCHETYPES for spec in specs):
            return specs

        anchors = tuple(
            str(archetype).strip().lower()
            for archetype in tuple(anchor_pool or ())
            if str(archetype).strip().lower()
        )
        if not anchors:
            return specs
        try:
            floor = int((specs[-1] if specs else {}).get("floor", tuple(floors or (0,))[-1]))
        except (TypeError, ValueError, IndexError):
            floor = 0
        anchor_spec = self._named_span_spec(
            rng.choice(anchors),
            rng,
            used_business_names,
            floor=floor,
            child_kind=child_kind,
            public=public,
        )
        if not anchor_spec:
            return specs
        if specs:
            specs[-1] = anchor_spec
        else:
            specs.append(anchor_spec)
        return specs

    def _vertical_mixed_use_chance(self, district_type, density, wealth, archetype):
        chance = float(self.VERTICAL_MIXED_USE_CHANCE_BY_DISTRICT.get(district_type, 0.0))
        if chance <= 0.0:
            return 0.0
        if archetype not in self.VERTICAL_MIXED_USE_PARENT_ARCHETYPES:
            return 0.0
        if density >= 7:
            chance += 0.018
        if wealth >= 7:
            chance += 0.012
        return max(0.0, min(0.12, chance))

    def _maybe_apply_vertical_mixed_use_span(self, building, district, rng, used_business_names):
        if not isinstance(building, dict):
            return building
        if building.get("span_kind"):
            return building
        district_type = str(district.get("district_type", "residential") or "residential").strip().lower()
        density = int(district.get("population_density", 5) or 5)
        wealth = int(district.get("wealth", 5) or 5)
        archetype = str(building.get("archetype", "") or "").strip().lower()
        chance = self._vertical_mixed_use_chance(district_type, density, wealth, archetype)
        if chance <= 0.0 or rng.random() >= chance:
            return building

        floors = max(2, int(building.get("floors", 1) or 1))
        if floors < 3 and density >= 7 and rng.random() < 0.45:
            floors = 3
        building["floors"] = max(2, min(3, floors))
        span_id = f"span:{building.get('building_id', 'vertical')}:vertical"
        span_name, span_founder = self._span_name_for(
            "vertical_mixed_use",
            archetype,
            rng,
            used_business_names,
        )
        tenant_floors = (1,) if int(building["floors"]) <= 2 else (1, 2)
        tenant_count = 2 + int(int(building["floors"]) >= 3 and rng.random() < 0.35)
        building["span_kind"] = "vertical_mixed_use"
        building["span_id"] = span_id
        building["span_name"] = span_name or str(building.get("business_name", "") or "").strip()
        building["span_founder_name"] = span_founder.get("full_name") if span_founder else None
        building["span_founder_first_name"] = span_founder.get("first_name") if span_founder else None
        building["span_founder_last_name"] = span_founder.get("last_name") if span_founder else None
        building["rooms"] = [
            "lobby",
            "hallway",
            "stair",
            "open_office",
            "meeting_room",
            "shop_floor",
            "units",
            "service_corridor",
        ]
        building["public"] = True
        tenant_specs = self._span_specs_from_pool(
            rng,
            self.VERTICAL_MIXED_USE_TENANT_WEIGHTS,
            tenant_count,
            used_business_names,
            floors=tenant_floors,
            child_kind="tenant",
            public=None,
        )
        building["tenant_specs"] = self._ensure_span_service_anchor(
            tenant_specs,
            rng,
            used_business_names,
            anchor_pool=("office", "brokerage", "bank", "backroom_clinic", "pawn_shop"),
            floors=tenant_floors,
            child_kind="tenant",
            public=None,
        )
        housing_specs = []
        if int(building["floors"]) >= 3 and rng.random() < 0.65:
            housing_specs = self._span_specs_from_pool(
                rng,
                self.VERTICAL_MIXED_USE_HOUSING_WEIGHTS,
                1,
                used_business_names,
                floors=(2,),
                child_kind="housing",
                public=False,
            )
        building["housing_specs"] = housing_specs
        return building

    def _indoor_city_market_chance(self, district_type, density, wealth):
        chance = float(self.INDOOR_CITY_MARKET_CHANCE_BY_DISTRICT.get(district_type, 0.0))
        if chance <= 0.0:
            return 0.0
        if density >= 7:
            chance += 0.03
        if wealth >= 7:
            chance += 0.015
        return max(0.0, min(0.24, chance))

    def _build_indoor_city_market_building(self, district, bx, by, rng, used_business_names):
        business_name, founder = self._span_name_for("indoor_city_market", "junk_market", rng, used_business_names)
        span_id = f"span:{int(bx)}:{int(by)}:indoor_market"
        tenant_count = 4 + int(rng.random() < 0.45)
        tenant_specs = self._span_specs_from_pool(
            rng,
            self.INDOOR_CITY_MARKET_TENANT_WEIGHTS,
            tenant_count,
            used_business_names,
            floors=(0,),
            child_kind="tenant",
            public=None,
        )
        tenant_specs = self._ensure_span_service_anchor(
            tenant_specs,
            rng,
            used_business_names,
            anchor_pool=("bank", "tavern", "pawn_shop", "backroom_clinic"),
            floors=(0,),
            child_kind="tenant",
            public=None,
        )
        return {
            "building_id": f"{bx}:{by}:market",
            "archetype": "junk_market",
            "floors": 1,
            "basement_levels": 0,
            "rooms": ["market_aisle", "open_stalls", "vendor_row", "food_court", "service_corridor"],
            "career_roles": list(self.careers_for_building("junk_market")),
            "security_features": ["cameras"] if int(district.get("security_level", 5) or 5) >= 6 else [],
            "loot_table": "junk_market",
            "business_name": business_name,
            "business_founder_name": founder.get("full_name") if founder else None,
            "business_founder_first_name": founder.get("first_name") if founder else None,
            "business_founder_last_name": founder.get("last_name") if founder else None,
            "is_storefront": True,
            "public": True,
            "span_kind": "indoor_city_market",
            "span_id": span_id,
            "span_name": business_name,
            "span_founder_name": founder.get("full_name") if founder else None,
            "span_founder_first_name": founder.get("first_name") if founder else None,
            "span_founder_last_name": founder.get("last_name") if founder else None,
            "tenant_specs": tenant_specs,
            "housing_specs": [],
        }

    def _build_non_city_compound_market_site_record(self, descriptor, idx, used_site_names, rng):
        site_name, founder = self._non_city_site_name_for("flea_market", rng, used_site_names)
        used_business_names = set(used_site_names or set())
        span_id = f"span:{int(descriptor.get('cx', 0))}:{int(descriptor.get('cy', 0))}:compound_market"
        tenant_specs = self._span_specs_from_pool(
            rng,
            self.NON_CITY_COMPOUND_MARKET_TENANT_WEIGHTS,
            4 + int(rng.random() < 0.35),
            used_business_names,
            floors=(0,),
            child_kind="tenant",
            public=None,
        )
        tenant_specs = self._ensure_span_service_anchor(
            tenant_specs,
            rng,
            used_business_names,
            anchor_pool=("bank", "tavern", "pawn_shop", "service_station"),
            floors=(0,),
            child_kind="tenant",
            public=None,
        )
        housing_specs = [
            self._named_span_spec("field_camp", rng, used_business_names, floor=0, child_kind="housing", public=False),
            self._named_span_spec("flophouse", rng, used_business_names, floor=0, child_kind="shelter", public=True),
        ]
        return {
            "site_id": f"compound_market:{int(idx)}",
            "kind": "flea_market",
            "name": site_name,
            "business_name": site_name,
            "business_founder_name": founder.get("full_name") if founder else None,
            "business_founder_first_name": founder.get("first_name") if founder else None,
            "business_founder_last_name": founder.get("last_name") if founder else None,
            "public": True,
            "is_storefront": True,
            "span_kind": "non_city_compound_market",
            "span_id": span_id,
            "span_name": site_name,
            "span_founder_name": founder.get("full_name") if founder else None,
            "span_founder_first_name": founder.get("first_name") if founder else None,
            "span_founder_last_name": founder.get("last_name") if founder else None,
            "rooms": ["market_aisle", "shared_yard", "vendor_row", "bunk_room", "service_corridor"],
            "tenant_specs": [spec for spec in tenant_specs if spec],
            "housing_specs": [spec for spec in housing_specs if spec],
            "compound_market": True,
        }

    def generate_district(self, cx, cy, rng):
        descriptor = self.overworld_descriptor(cx, cy)
        area_type = str(descriptor.get("area_type", self.pick_area_type(cx, cy))).strip().lower() or "city"
        district_type = str(descriptor.get("district_type", self.pick_district_type(cx, cy))).strip().lower() or "residential"
        wealth = rng.randint(1, 10)
        security_level = rng.randint(1, 10)
        population_density = rng.randint(2, 10)
        crime_rate = max(1, 11 - security_level + rng.randint(-2, 2))

        dominant_faction = rng.choice(self.FACTIONS)
        if district_type in {"corporate", "downtown"}:
            dominant_faction = "corpsec"
        elif district_type == "military":
            dominant_faction = "coppers"
        elif district_type == "slums":
            dominant_faction = rng.choice(("neon_gang", "syndicate"))
        elif district_type == "residential":
            population_density = min(population_density, rng.randint(3, 7))

        if area_type != "city":
            wealth = max(1, wealth - rng.randint(1, 3))
            security_level = max(1, security_level - rng.randint(1, 3))
            population_density = max(1, population_density - rng.randint(2, 4))
            crime_rate = min(10, max(1, crime_rate + rng.randint(0, 2)))

        custom_profile = self._select_custom_world_profile(
            cx,
            cy,
            area_type=area_type,
            district_type=district_type,
        )
        custom_profile_id = ""
        custom_profile_label = ""
        custom_water_level = "none"
        custom_building_density_level = "none"
        custom_population_density_level = "none"
        if isinstance(custom_profile, dict):
            profile_rng = random.Random(
                f"{self.seed}:custom_world_profile_apply:{cx}:{cy}:{custom_profile.get('id', '')}"
            )
            custom_profile_id = str(custom_profile.get("id", "") or "").strip().lower()
            custom_profile_label = str(custom_profile.get("label", "") or "").strip()
            profile_districts = [
                str(value).strip().lower()
                for value in custom_profile.get("district_types", ()) or ()
                if str(value).strip().lower() in self.DISTRICT_TYPES
            ]
            if profile_districts:
                district_type = profile_rng.choice(profile_districts)
            custom_population_density_level = str(custom_profile.get("population_density", "none") or "none").strip().lower()
            population_density = self._density_from_level(
                custom_population_density_level,
                profile_rng,
                population_density,
            )
            custom_building_density_level = str(custom_profile.get("building_density", "none") or "none").strip().lower()
            custom_water_level = str(custom_profile.get("water", "none") or "none").strip().lower()

        return {
            "area_type": area_type,
            "district_type": district_type,
            "wealth": wealth,
            "security_level": security_level,
            "dominant_faction": dominant_faction,
            "population_density": population_density,
            "crime_rate": crime_rate,
            "building_archetypes": list(self._buildings_for_district(district_type)),
            "region_name": descriptor.get("region_name"),
            "settlement_name": descriptor.get("settlement_name"),
            "custom_world_profile_id": custom_profile_id,
            "custom_world_profile_label": custom_profile_label,
            "custom_water_level": custom_water_level,
            "custom_population_density_level": custom_population_density_level,
            "custom_building_density_level": custom_building_density_level,
        }

    @staticmethod
    def _placement_pct(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.50
        return round(max(0.12, min(0.88, value)), 2)

    def _placement_frontage_side(self, anchor_x_pct, anchor_y_pct, rng, preferred=None):
        preferred = str(preferred or "").strip().lower()
        if preferred in {"north", "south", "west", "east"}:
            return preferred

        x_pct = self._placement_pct(anchor_x_pct)
        y_pct = self._placement_pct(anchor_y_pct)
        if 0.38 <= x_pct <= 0.62 and 0.38 <= y_pct <= 0.62:
            return rng.choice(("north", "south", "west", "east"))

        gaps = (
            ("west", x_pct),
            ("east", 1.0 - x_pct),
            ("north", y_pct),
            ("south", 1.0 - y_pct),
        )
        nearest = sorted(gaps, key=lambda item: (item[1], item[0]))[:2]
        return rng.choice(tuple(side for side, _gap in nearest))

    def _building_placement_profile(self, *, cx, cy, block, building, building_index, building_count, district):
        bx = int(block.get("grid_x", 0))
        by = int(block.get("grid_y", 0))
        building_id = str((building or {}).get("building_id", f"{bx}:{by}:{building_index}") or "").strip()
        archetype = str((building or {}).get("archetype", "") or "").strip().lower()
        parcel_span_x = max(1, int((building or {}).get("parcel_span_x", 1) or 1))
        parcel_span_y = max(1, int((building or {}).get("parcel_span_y", 1) or 1))
        district_type = str((district or {}).get("district_type", "residential") or "residential").strip().lower()
        rng = random.Random(
            f"{self.seed}:city-placement:{int(cx)}:{int(cy)}:{bx}:{by}:"
            f"{int(building_index)}:{int(building_count)}:{building_id}:{archetype}:{district_type}"
        )

        if parcel_span_x > 1 or parcel_span_y > 1:
            row_overlap = parcel_span_y > 1
            column_overlap = parcel_span_x > 1
            if row_overlap and column_overlap:
                kind = "row_column_overlap"
                anchor_x = 0.50 + rng.choice((-0.08, 0.08, 0.0))
                anchor_y = 0.50 + rng.choice((-0.08, 0.08, 0.0))
                preferred_side = rng.choice(("north", "south", "west", "east"))
            elif row_overlap:
                kind = "row_overlap"
                anchor_x = rng.choice((0.28, 0.72, 0.50))
                anchor_y = 0.50 + rng.choice((-0.08, 0.08, 0.0))
                preferred_side = rng.choice(("west", "east"))
            else:
                kind = "column_overlap"
                anchor_x = 0.50 + rng.choice((-0.08, 0.08, 0.0))
                anchor_y = rng.choice((0.28, 0.72, 0.50))
                preferred_side = rng.choice(("north", "south"))
            anchor_x = self._placement_pct(anchor_x)
            anchor_y = self._placement_pct(anchor_y)
            return {
                "placement_kind": kind,
                "anchor_x_pct": anchor_x,
                "anchor_y_pct": anchor_y,
                "frontage_side": self._placement_frontage_side(anchor_x, anchor_y, rng, preferred=preferred_side),
                "row_overlap": bool(row_overlap),
                "column_overlap": bool(column_overlap),
            }

        try:
            building_count = int(building_count)
        except (TypeError, ValueError):
            building_count = 1
        building_count = max(1, building_count)

        if building_count <= 1:
            kind, anchor_x, anchor_y = rng.choice(self.CITY_PLACEMENT_SOLO_POINTS)
        elif building_count == 2:
            pattern_kind, anchors = rng.choice(self.CITY_PLACEMENT_PAIR_PATTERNS)
            anchor_x, anchor_y = anchors[int(building_index) % len(anchors)]
            kind = pattern_kind
        else:
            pattern_kind, anchors = rng.choice(self.CITY_PLACEMENT_CLUSTER_PATTERNS)
            anchor_x, anchor_y = anchors[int(building_index) % len(anchors)]
            kind = pattern_kind

        anchor_x = self._placement_pct(anchor_x)
        anchor_y = self._placement_pct(anchor_y)
        return {
            "placement_kind": kind,
            "anchor_x_pct": anchor_x,
            "anchor_y_pct": anchor_y,
            "frontage_side": self._placement_frontage_side(anchor_x, anchor_y, rng),
        }

    def _assign_city_placement_profiles(self, blocks, district, *, cx, cy):
        for block in blocks:
            if not isinstance(block, dict) or block.get("parcel_reserved"):
                continue
            buildings = block.get("buildings", ())
            if not isinstance(buildings, list) or not buildings:
                continue
            building_count = len(buildings)
            bx = int(block.get("grid_x", 0))
            by = int(block.get("grid_y", 0))
            multi_building = building_count > 1 and all(
                isinstance(building, dict)
                and int(building.get("parcel_span_x", 1) or 1) == 1
                and int(building.get("parcel_span_y", 1) or 1) == 1
                for building in buildings
            )
            shared_kind = None
            shared_anchors = ()
            if multi_building:
                block_rng = random.Random(
                    f"{self.seed}:city-placement-block:{int(cx)}:{int(cy)}:{bx}:{by}:{building_count}"
                )
                if building_count == 2:
                    pair_patterns = tuple(self.CITY_PLACEMENT_PAIR_PATTERNS)
                    if any(
                        str(building.get("archetype", "") or "").strip().lower() in self.CITY_PLACEMENT_ROOMY_PAIR_ARCHETYPES
                        for building in buildings
                        if isinstance(building, dict)
                    ):
                        pair_patterns = tuple(
                            pattern for pattern in pair_patterns
                            if str(pattern[0]) in {"pair_broken_row", "pair_broken_column"}
                        ) or pair_patterns
                    shared_kind, shared_anchors = block_rng.choice(pair_patterns)
                else:
                    shared_kind, shared_anchors = block_rng.choice(self.CITY_PLACEMENT_CLUSTER_PATTERNS)
            for index, building in enumerate(buildings):
                if not isinstance(building, dict):
                    continue
                if isinstance(building.get("placement_profile"), dict):
                    continue
                if multi_building and shared_kind and shared_anchors:
                    anchor_x, anchor_y = shared_anchors[int(index) % len(shared_anchors)]
                    side_rng = random.Random(
                        f"{self.seed}:city-placement-front:{int(cx)}:{int(cy)}:{bx}:{by}:{index}:{shared_kind}"
                    )
                    anchor_x = self._placement_pct(anchor_x)
                    anchor_y = self._placement_pct(anchor_y)
                    building["placement_profile"] = {
                        "placement_kind": str(shared_kind),
                        "anchor_x_pct": anchor_x,
                        "anchor_y_pct": anchor_y,
                        "frontage_side": self._placement_frontage_side(anchor_x, anchor_y, side_rng),
                    }
                else:
                    building["placement_profile"] = self._building_placement_profile(
                        cx=cx,
                        cy=cy,
                        block=block,
                        building=building,
                        building_index=index,
                        building_count=building_count,
                        district=district,
                    )

    def generate_building(self, district, bx, by, i, rng, used_business_names=None, preferred_archetypes=None):
        district_type = district["district_type"]
        options = list(self._buildings_for_district(district_type))
        preferred = [
            str(archetype).strip().lower()
            for archetype in (preferred_archetypes or ())
            if str(archetype).strip().lower() in options
        ]
        if preferred:
            options = preferred
        archetype = self._choose_building_archetype(options, rng, district)
        wealth = int(district.get("wealth", 5))
        density = int(district.get("population_density", 5))
        floors = 1
        vertical_chance = 0.12
        if wealth >= 6:
            vertical_chance += 0.10
        if density >= 7:
            vertical_chance += 0.08
        if district_type in {"downtown", "corporate"}:
            vertical_chance += 0.22
        elif district_type in {"industrial", "entertainment", "slums"}:
            vertical_chance += 0.12
        if archetype in self.MULTI_FLOOR_ARCHETYPES:
            vertical_chance += 0.18
        if archetype in self.TALL_BUILDING_ARCHETYPES:
            vertical_chance += 0.10
        if archetype in self.LOW_RISE_ARCHETYPES:
            vertical_chance -= 0.18
        if district_type == "residential" and archetype not in {"apartment", "tenement", "hotel", "flophouse"}:
            vertical_chance -= 0.14

        if rng.random() < max(0.0, vertical_chance):
            floors += 1

        extra_floor_chance = 0.0
        if floors > 1:
            if district_type in {"downtown", "corporate"}:
                extra_floor_chance += 0.16
            if wealth >= 8:
                extra_floor_chance += 0.08
            if archetype in self.TALL_BUILDING_ARCHETYPES:
                extra_floor_chance += 0.14
        if rng.random() < extra_floor_chance:
            floors += 1
        if archetype == "prison":
            floors = max(floors, 2)
        floors = max(1, min(3, floors))

        basement_levels = 0
        basement_chance = 0.0
        if archetype in self.BASEMENT_ARCHETYPES:
            basement_chance = 0.10
            if floors > 1:
                basement_chance += 0.12
            if wealth >= 6:
                basement_chance += 0.06
            if district_type in {"downtown", "corporate", "industrial", "slums", "military"}:
                basement_chance += 0.06
        if rng.random() < basement_chance:
            basement_levels = 1
        floors, basement_levels = normalize_building_levels(archetype, floors, basement_levels)

        rooms = list(self.ROOM_TEMPLATES.get(archetype, ("entry", "room", "storage")))

        security_features = []
        if district["security_level"] >= 6:
            security_features.append("cameras")
        if district["security_level"] >= 7:
            security_features.append("locked_doors")
        if district["security_level"] >= 8:
            security_features.append("guards")

        used_business_names = used_business_names if used_business_names is not None else set()
        business_name = None
        business_founder = None
        if archetype in self.NAMED_BUSINESS_ARCHETYPES:
            business_name, business_founder = self._business_name_for(archetype, rng, used_business_names)

        return {
            "building_id": f"{bx}:{by}:{i}",
            "archetype": archetype,
            "floors": floors,
            "basement_levels": basement_levels,
            "rooms": rooms,
            "career_roles": list(self.careers_for_building(archetype)),
            "security_features": security_features,
            "loot_table": archetype,
            "business_name": business_name,
            "business_founder_name": business_founder.get("full_name") if business_founder else None,
            "business_founder_first_name": business_founder.get("first_name") if business_founder else None,
            "business_founder_last_name": business_founder.get("last_name") if business_founder else None,
            "is_storefront": archetype in self.STOREFRONT_ARCHETYPES,
            "public": archetype in self.PUBLIC_BUILDING_ARCHETYPES,
        }

    def _apply_vertical_mixed_use_spans(self, blocks, district, rng, used_business_names):
        for block in blocks:
            if not isinstance(block, dict) or block.get("parcel_reserved"):
                continue
            buildings = block.get("buildings", ())
            if not isinstance(buildings, list) or len(buildings) != 1:
                continue
            building = buildings[0]
            if not isinstance(building, dict):
                continue
            self._maybe_apply_vertical_mixed_use_span(building, district, rng, used_business_names)

    def _large_parcel_chance(self, district_type, density, wealth):
        chance = float(self.LARGE_PARCEL_BASE_CHANCE_BY_DISTRICT.get(district_type, 0.0))
        if chance <= 0.0:
            return 0.0
        density = int(max(1, density))
        wealth = int(max(0, wealth))
        if district_type in {"downtown", "corporate"}:
            chance += 0.10
        elif district_type in {"industrial", "military", "entertainment"}:
            chance += 0.08
        elif district_type == "slums":
            chance += 0.06
        if density <= 4:
            chance += 0.06
        elif density >= 8:
            chance += 0.03
        if wealth >= 7:
            chance += 0.04
        return max(0.0, min(0.58, chance))

    def _reserve_large_city_parcel(self, blocks_by_coord, district, rng, used_business_names):
        district_type = str(district.get("district_type", "residential")).strip().lower() or "residential"
        density = int(max(1, district.get("population_density", 5)))
        wealth = int(max(0, district.get("wealth", 5)))
        chance = self._large_parcel_chance(district_type, density, wealth)
        if chance <= 0.0 or rng.random() >= chance:
            return False

        preferred = [
            archetype
            for archetype in self._buildings_for_district(district_type)
            if archetype in self.LARGE_PARCEL_ARCHETYPES
        ]
        if not preferred:
            return False

        candidates = []
        for by in range(2):
            for bx in range(2):
                if bx < 1 and not blocks_by_coord[(bx, by)].get("buildings") and not blocks_by_coord[(bx + 1, by)].get("buildings"):
                    candidates.append((bx, by, 2, 1))
                if by < 1 and not blocks_by_coord[(bx, by)].get("buildings") and not blocks_by_coord[(bx, by + 1)].get("buildings"):
                    candidates.append((bx, by, 1, 2))
        if not candidates:
            return False

        anchor_bx, anchor_by, span_x, span_y = rng.choice(candidates)
        anchor_block = blocks_by_coord[(anchor_bx, anchor_by)]
        market_chance = self._indoor_city_market_chance(district_type, density, wealth)
        if market_chance > 0.0 and rng.random() < market_chance:
            building = self._build_indoor_city_market_building(
                district,
                anchor_bx,
                anchor_by,
                rng,
                used_business_names,
            )
        else:
            building = self.generate_building(
                district,
                anchor_bx,
                anchor_by,
                0,
                rng,
                used_business_names=used_business_names,
                preferred_archetypes=preferred,
            )
        building["parcel_span_x"] = int(span_x)
        building["parcel_span_y"] = int(span_y)
        building["large_parcel"] = True
        anchor_block["buildings"] = [building]
        anchor_block["parcel_span_x"] = int(span_x)
        anchor_block["parcel_span_y"] = int(span_y)

        for dy in range(span_y):
            for dx in range(span_x):
                if dx == 0 and dy == 0:
                    continue
                covered = blocks_by_coord[(anchor_bx + dx, anchor_by + dy)]
                covered["parcel_reserved"] = True
                covered["reserved_by"] = building["building_id"]
                covered["buildings"] = []
        return True

    def generate_blocks(self, district, rng, cx=0, cy=0):
        blocks = [
            {
                "grid_x": bx,
                "grid_y": by,
                "street_edges": ["N", "S", "E", "W"],
                "buildings": [],
            }
            for by in range(2)
            for bx in range(2)
        ]
        blocks_by_coord = {
            (int(block.get("grid_x", 0)), int(block.get("grid_y", 0))): block
            for block in blocks
        }
        used_business_names = set()
        district_type = str(district.get("district_type", "residential")).strip().lower() or "residential"
        density = int(max(1, district.get("population_density", 5)))

        min_buildings = 1
        max_buildings = 3
        empty_block_chance = 0.0

        if district_type == "residential":
            min_buildings = 0
            max_buildings = 2
            empty_block_chance = 0.30
        elif district_type in {"downtown", "corporate"}:
            min_buildings = 2
            max_buildings = 3
        elif district_type in {"industrial", "military", "entertainment"}:
            min_buildings = 1
            max_buildings = 2

        if density <= 4:
            max_buildings = max(min_buildings, max_buildings - 1)
            if district_type == "residential":
                empty_block_chance = max(empty_block_chance, 0.45)
            else:
                empty_block_chance = max(empty_block_chance, 0.10)
        elif density >= 8:
            if district_type in {"downtown", "corporate", "slums"}:
                min_buildings = min(max_buildings, min_buildings + 1)
            empty_block_chance = max(0.0, empty_block_chance - 0.15)

        custom_building_density = str(district.get("custom_building_density_level", "none") or "none").strip().lower()
        if custom_building_density == "low":
            min_buildings = 0
            max_buildings = max(1, min(max_buildings, 1))
            empty_block_chance = max(empty_block_chance, 0.45)
        elif custom_building_density == "medium":
            empty_block_chance = max(0.0, empty_block_chance - 0.06)
        elif custom_building_density == "high":
            max_buildings = max(max_buildings, 3)
            min_buildings = min(max_buildings, max(min_buildings, 2))
            empty_block_chance = max(0.0, empty_block_chance - 0.22)

        self._reserve_large_city_parcel(
            blocks_by_coord,
            district,
            rng,
            used_business_names,
        )

        populated_blocks = 0
        for block in blocks:
            if block.get("parcel_reserved"):
                continue
            if block.get("buildings"):
                populated_blocks += 1
                continue

            bx = int(block.get("grid_x", 0))
            by = int(block.get("grid_y", 0))
            if min_buildings == 0 and rng.random() < empty_block_chance:
                building_count = 0
            else:
                building_count = rng.randint(min_buildings, max_buildings)
            block["buildings"] = [
                self.generate_building(
                    district,
                    bx,
                    by,
                    i,
                    rng,
                    used_business_names=used_business_names,
                )
                for i in range(building_count)
            ]
            if block["buildings"]:
                populated_blocks += 1

        if populated_blocks == 0 and blocks:
            fallback_candidates = [block for block in blocks if not block.get("parcel_reserved")]
            fallback_block = rng.choice(fallback_candidates or blocks)
            fallback_block["buildings"] = [
                self.generate_building(
                    district,
                    int(fallback_block.get("grid_x", 0)),
                    int(fallback_block.get("grid_y", 0)),
                    0,
                    rng,
                    used_business_names=used_business_names,
                ),
            ]

        self._apply_vertical_mixed_use_spans(blocks, district, rng, used_business_names)
        self._assign_city_placement_profiles(blocks, district, cx=cx, cy=cy)
        return blocks

    def generate_infrastructure(self, district, rng):
        nodes = []

        if district["security_level"] >= 6:
            nodes.append("police_hub")
        if district["wealth"] >= 6:
            nodes.append("network_hub")
        if district["district_type"] in {"industrial", "corporate"}:
            nodes.append("power_station")
        if district["district_type"] in {"residential", "downtown"} and rng.random() < 0.5:
            nodes.append("clinic")

        return nodes

    def generate_chunk(self, cx, cy):
        rng = self.chunk_rng(cx, cy)
        district = self.generate_district(cx, cy, rng)
        descriptor = self.overworld_descriptor(cx, cy)
        area_type = str(district.get("area_type", descriptor.get("area_type", "city"))).strip().lower() or "city"
        blocks = self.generate_blocks(district, rng, cx=cx, cy=cy) if area_type == "city" else []
        sites = self.generate_non_city_sites(descriptor, self.chunk_site_rng(cx, cy)) if area_type != "city" else []
        infrastructure = self.generate_infrastructure(district, rng)

        return {
            "cx": cx,
            "cy": cy,
            "district": district,
            "blocks": blocks,
            "sites": sites,
            "infrastructure": infrastructure,
            "tiles": [],
            "entities": [],
        }

    def stream_chunks(self, center_cx, center_cy, active_radius=1, loaded_radius=2):
        if loaded_radius < active_radius:
            loaded_radius = active_radius

        desired = {}
        for dy in range(-loaded_radius, loaded_radius + 1):
            for dx in range(-loaded_radius, loaded_radius + 1):
                cx = center_cx + dx
                cy = center_cy + dy
                dist = max(abs(dx), abs(dy))
                detail = "active" if dist <= active_radius else "coarse"
                desired[(cx, cy)] = {
                    "chunk": self.get_chunk(cx, cy),
                    "detail": detail,
                }

        prev_keys = set(self.loaded_chunks.keys())
        next_keys = set(desired.keys())

        loaded = sorted(next_keys - prev_keys)
        unloaded = sorted(prev_keys - next_keys)
        detail_changed = sorted(
            key
            for key in (prev_keys & next_keys)
            if self.loaded_chunks[key]["detail"] != desired[key]["detail"]
        )

        old_focus = self.focus
        self.focus = (center_cx, center_cy)
        focus_changed = old_focus != self.focus
        self.loaded_chunks = desired

        changed = focus_changed or bool(loaded) or bool(unloaded) or bool(detail_changed)

        return {
            "changed": changed,
            "focus": self.focus,
            "focus_changed": focus_changed,
            "loaded": loaded,
            "unloaded": unloaded,
            "detail_changed": detail_changed,
            "loaded_count": len(next_keys),
            "active_count": sum(1 for data in desired.values() if data["detail"] == "active"),
        }
