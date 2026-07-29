from __future__ import annotations

import random
from dataclasses import dataclass

from engine.buildings import layout_chunk_building, world_building_id
from engine.fixtures import generate_chunk_fixture_records
from engine.sites import layout_chunk_site, site_gameplay_profile, site_layout_reserved_footprints
from engine.tilemap import Tile
from game.bones import maybe_seed_bones_for_chunk
from game.components import (
    ArmorLoadout,
    AppearanceLoadout,
    Collider,
    ContactLedger,
    CoreStats,
    CoverState,
    CreatureIdentity,
    FinancialProfile,
    InsightStats,
    Inventory,
    NPCNeeds,
    NoiseProfile,
    PlayerAssets,
    PlayerControlled,
    PlayerModeState,
    Position,
    PropertyKnowledge,
    PropertyPortfolio,
    Render,
    StatusEffects,
    VehicleState,
    Vitality,
    WeaponLoadout,
)
from game.appearance_loadout import (
    cosmetic_variant_metadata,
    equip_appearance_item,
    is_appearance_item,
    mark_inventory_instance_worn,
    seed_player_starting_outfit,
    stow_cosmetic_outer_for_armor,
)
from game.human_identity import seed_player_identity_profile
from game.economy import chunk_economy_profile
from game.flora_runtime import ensure_chunk_flora
from game.items import ITEM_CATALOG
from game.large_span_places import register_large_span_child_properties
from game.opportunities import seed_run_opportunities
from game.organizations import (
    ensure_property_organization,
    seed_chunk_organizations,
    seed_property_organization_defaults,
)
from game.population import seed_chunk_items, spawn_chunk_npcs, spawn_chunk_special_population
from game.profession_loadouts import NORMAL_START_LOADOUT_IDS, NORMAL_START_LOADOUTS
from game.property_access import COMMON_AREA_ROOM_KINDS, default_site_services_for_archetype
from game.property_keys import ensure_actor_has_property_key, ensure_property_lock
from game.quick_travel_ramps import generate_quick_travel_ramp_records
from game.run_echoes import maybe_seed_run_echo_for_chunk
from game.run_objectives import seed_run_objective
from game.skills import seed_skill_profile
from game.weapons import WEAPON_CATALOG, roll_weapon_instance
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)


JUSTICE_VEHICLE_STATION_ARCHETYPES = {
    "checkpoint",
    "courthouse",
    "jail",
    "police_precinct",
    "police_station",
    "prison",
    "security_office",
}
JUSTICE_VEHICLE_DISPLAY_COLOR = "vehicle_police"


@dataclass(frozen=True)
class NormalRunBootstrapProfile:
    profile_id: str = "normal"
    preferred_area_type: str = "city"
    starter_wallet_credit_range: tuple[int, int] = (30, 76)
    starter_bank_credit_range: tuple[int, int] = (10, 32)
    starter_bank_credit_chance: float = 0.22
    vehicle_seed_chance: float = 0.42
    bootstrap_player_opportunity_intel: bool = False
    objective_visible: bool = False
    starter_loadout_ids: tuple[str, ...] = NORMAL_START_LOADOUT_IDS
    street_kit_base: tuple[tuple[str, int], ...] = (
        ("street_ration", 1),
        ("bottled_water", 2),
        ("med_gel", 1),
        ("city_pass_token", 1),
    )
    street_kit_variants: tuple[tuple[str, int], ...] = (
        ("calm_patch", 1),
        ("caff_shot", 1),
        ("hydration_salts", 1),
    )
    starter_melee_weapon_chance: float = 0.28
    starter_firearm_chance: float = 0.09
    starter_armor_chance: float = 0.22
    starter_melee_weapon_pool: tuple[str, ...] = (
        "crowbar_club",
        "crowbar_club",
        "shiv_knife",
        "trail_machete",
    )
    starter_firearm_pool: tuple[str, ...] = (
        "holdout_pistol",
        "holdout_pistol",
        "rust_revolver",
    )
    starter_armor_pool: tuple[str, ...] = (
        "padded_jacket",
        "padded_jacket",
        "security_vest",
    )


@dataclass(frozen=True)
class NormalRunBootstrapResult:
    player_eid: int
    world_item_count: int
    ambient_npc_count: int
    start_chunk: tuple[int, int]
    start_name: str
    start_district_type: str
    local_note: str
    pressure_note: str
    starter_vehicle_seeded: bool
    starter_loadout_id: str
    starter_loadout_items: tuple[tuple[str, int], ...]
    street_kit_items: tuple[tuple[str, int], ...]
    starter_wallet_credits: int
    starter_bank_credits: int
    starter_weapon_id: str
    starter_armor_item_id: str
    opening_rumor_text: str
    opening_rumor_topics_text: str


DEFAULT_NORMAL_RUN_BOOTSTRAP_PROFILE = NormalRunBootstrapProfile()


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


def _ensure_walkable(sim, x, y, z, glyph="."):
    if hasattr(sim, "door_state_at") and hasattr(sim, "apply_door_state"):
        state = sim.door_state_at(x, y, z)
        if isinstance(state, dict):
            sim.apply_door_state(x, y, z)
            return
    existing = sim.tilemap.tile_at(x, y, z)
    if existing and existing.walkable:
        return
    sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph=glyph), z=z)


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _justice_vehicle_profile():
    return {
        "quality": "new",
        "make": "Warden",
        "model": "Patrol",
        "vehicle_class": "cruiser",
        "vehicle_medium": "land",
        "power": 7,
        "durability": 9,
        "fuel_efficiency": 5,
        "fuel_capacity": 82,
        "fuel": 82,
        "price": 0,
        "glyph": "&",
        "paint": JUSTICE_VEHICLE_DISPLAY_COLOR,
    }


def _chunk_contains_xy(origin_x, origin_y, chunk_size, x, y):
    return (
        int(origin_x) <= int(x) < int(origin_x) + int(chunk_size)
        and int(origin_y) <= int(y) < int(origin_y) + int(chunk_size)
    )


def _justice_vehicle_parking_tile(sim, station_prop, *, origin_x, origin_y, chunk_size):
    if not isinstance(station_prop, dict):
        return None
    try:
        sx = int(station_prop.get("x", 0))
        sy = int(station_prop.get("y", 0))
        sz = int(station_prop.get("z", 0))
    except (TypeError, ValueError):
        return None
    if sz != 0:
        return None

    candidates = []
    for radius in range(1, 7):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x = sx + dx
                y = sy + dy
                if not _chunk_contains_xy(origin_x, origin_y, chunk_size, x, y):
                    continue
                if sim.property_at(x, y, 0) is not None:
                    continue
                if sim.structure_at(x, y, 0) is not None:
                    continue
                tile = sim.tilemap.tile_at(x, y, 0)
                if tile is None:
                    continue
                road_score = 0
                for ny in range(y - 1, y + 2):
                    for nx in range(x - 1, x + 2):
                        neighbor = sim.tilemap.tile_at(nx, ny, 0)
                        glyph = str(getattr(neighbor, "glyph", "") or "")[:1]
                        if glyph == "=":
                            road_score = max(road_score, 4)
                        elif glyph == ":":
                            road_score = max(road_score, 3)
                walkable_score = 2 if bool(getattr(tile, "walkable", False)) else 0
                if walkable_score <= 0 and road_score <= 0:
                    continue
                candidates.append((road_score + walkable_score, radius, x, y))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-int(row[0]), int(row[1]), int(row[3]), int(row[2])))
    _score, _radius, x, y = candidates[0]
    return int(x), int(y), 0


def _register_justice_station_vehicles(sim, chunk, records, *, origin_x, origin_y, chunk_size):
    chunk_key = (int(chunk["cx"]), int(chunk["cy"]))
    existing_station_ids = {
        str(_property_metadata(prop).get("station_property_id", "") or "").strip()
        for prop in getattr(sim, "properties", {}).values()
        if str(prop.get("kind", "")).strip().lower() == "vehicle"
        and str(_property_metadata(prop).get("restricted_use", "") or "").strip().lower() == "justice"
    }
    created = []
    for record in list(records):
        prop_id = str(record.get("id", "") or "").strip()
        station_prop = sim.properties.get(prop_id)
        metadata = _property_metadata(station_prop)
        archetype = str(record.get("archetype") or metadata.get("archetype") or "").strip().lower()
        if archetype not in JUSTICE_VEHICLE_STATION_ARCHETYPES:
            continue
        if prop_id in existing_station_ids:
            continue
        tile = _justice_vehicle_parking_tile(
            sim,
            station_prop,
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
        )
        if tile is None:
            continue
        x, y, z = tile
        _ensure_walkable(sim, x, y, z, glyph="=")
        profile = _justice_vehicle_profile()
        vehicle_token = f"veh:justice:{chunk_key[0]}:{chunk_key[1]}:{prop_id}"
        vehicle_meta = vehicle_metadata(
            profile,
            chunk=chunk_key,
            owner_tag="justice",
            display_color=JUSTICE_VEHICLE_DISPLAY_COLOR,
            locked=True,
            key_id=vehicle_token,
            key_label="Warden Patrol",
            lock_tier=4,
        )
        vehicle_meta.update({
            "vehicle_id": vehicle_token,
            "vehicle_paint": JUSTICE_VEHICLE_DISPLAY_COLOR,
            "display_color": JUSTICE_VEHICLE_DISPLAY_COLOR,
            "restricted_use": "justice",
            "vehicle_restricted_use": "justice",
            "justice_vehicle": True,
            "vehicle_role": "police",
            "station_property_id": prop_id,
            "station_archetype": archetype,
            "public": False,
        })
        vehicle_id = sim.register_property(
            name="Police Cruiser",
            kind="vehicle",
            x=x,
            y=y,
            z=z,
            owner_eid=None,
            owner_tag="justice",
            metadata=vehicle_meta,
        )
        created.append({
            "id": vehicle_id,
            "kind": "vehicle",
            "x": x,
            "y": y,
            "z": z,
            "archetype": "vehicle",
            "building_id": None,
        })
        existing_station_ids.add(prop_id)
    records.extend(created)
    return created


def _pick_playtest_start_chunk(sim, rng, radius=14, attempts=48, preferred_area_type="city"):
    fallback = (0, 0)
    wanted = str(preferred_area_type or "").strip().lower()
    for _ in range(max(1, int(attempts))):
        cx = rng.randint(-int(radius), int(radius))
        cy = rng.randint(-int(radius), int(radius))
        fallback = (cx, cy)
        if not wanted:
            return fallback
        area_type = str(sim.world.pick_area_type(cx, cy)).strip().lower()
        if area_type == wanted:
            return fallback
    return fallback


def _pick_chunk_street_spawn(sim, chunk, rng, reserved=None, z=0):
    reserved_positions = {tuple(pos) for pos in (reserved or ())}
    chunk_size = int(max(8, sim.chunk_size))
    origin_x, origin_y = sim.chunk_origin(chunk["cx"], chunk["cy"])
    street_candidates = []
    fallback_candidates = []
    for y in range(origin_y + 1, origin_y + chunk_size - 1):
        for x in range(origin_x + 1, origin_x + chunk_size - 1):
            pos = (x, y, z)
            if pos in reserved_positions:
                continue
            tile = sim.tilemap.tile_at(x, y, z)
            if not tile or not tile.walkable:
                continue
            if sim.structure_at(x, y, z) is None and sim.property_at(x, y, z) is None:
                street_candidates.append(pos)
                continue
            fallback_candidates.append(pos)
    if street_candidates:
        return rng.choice(street_candidates)
    if fallback_candidates:
        return rng.choice(fallback_candidates)
    center_x = origin_x + max(2, chunk_size // 2)
    center_y = origin_y + max(2, chunk_size // 2)
    return (center_x, center_y, z)


def _merge_site_services(metadata, extra_services):
    base = []
    if isinstance(metadata, dict):
        raw = metadata.get("site_services", ())
        if isinstance(raw, (list, tuple, set)):
            base = [str(service).strip().lower() for service in raw if str(service).strip()]
    merged = list(dict.fromkeys(base + [str(service).strip().lower() for service in extra_services if str(service).strip()]))
    if isinstance(metadata, dict):
        metadata["site_services"] = merged
    return merged


def _pick_nearest_vehicle_property(sim, x, y, z=0, radius=5, owner_tags=None):
    allowed_tags = None
    if owner_tags:
        allowed_tags = {str(tag).strip().lower() for tag in owner_tags if str(tag).strip()}
    best = None
    best_dist = 999999
    for prop in sim.properties.values():
        if int(prop.get("z", -1)) != int(z):
            continue
        if str(prop.get("kind", "")).strip().lower() != "vehicle":
            continue
        if allowed_tags is not None:
            owner_tag = str(prop.get("owner_tag", "")).strip().lower()
            if owner_tag not in allowed_tags:
                continue
        dist = abs(int(prop.get("x", 0)) - int(x)) + abs(int(prop.get("y", 0)) - int(y))
        if dist > int(radius):
            continue
        if dist < best_dist:
            best = prop
            best_dist = dist
    return best


def _ensure_starter_vehicle(sim, player_eid, player_pos, rng):
    if player_eid is None or not player_pos:
        return None
    vehicle_state = sim.ecs.get(VehicleState).get(player_eid)
    if not vehicle_state:
        return None

    nearby = _pick_nearest_vehicle_property(
        sim,
        x=player_pos[0],
        y=player_pos[1],
        z=player_pos[2],
        radius=5,
        owner_tags={"public", "unowned", "none", "neutral"},
    )
    if nearby:
        sim.assign_property_owner(nearby["id"], owner_eid=player_eid, owner_tag="player")
        metadata = nearby.get("metadata", {})
        if isinstance(metadata, dict):
            metadata["display_color"] = "vehicle_player"
            metadata["vehicle_owner_tag"] = "player"
            try:
                fuel_capacity = int(metadata.get("fuel_capacity", metadata.get("fuel", 60)))
            except (TypeError, ValueError):
                fuel_capacity = 60
            metadata["fuel"] = max(10, fuel_capacity)
        ensure_property_lock(
            nearby,
            locked=True,
            key_label=str(nearby.get("name", "Vehicle")).strip() or "Vehicle",
            lock_tier=int(metadata.get("property_lock_tier", 2)) if isinstance(metadata, dict) else 2,
        )
        key_ok, _instance_id, _created = ensure_actor_has_property_key(sim, player_eid, nearby, owner_tag="player")
        if not key_ok and isinstance(metadata, dict):
            metadata["property_locked"] = False
        vehicle_state.set_active_vehicle(nearby["id"], tick=sim.tick)
        return nearby

    cx, cy = sim.chunk_coords(player_pos[0], player_pos[1])
    chunk = sim.world.get_chunk(cx, cy)
    profile = roll_vehicle_profile(rng, quality="used")
    try:
        profile["fuel"] = int(profile.get("fuel_capacity", profile.get("fuel", 60)))
    except (TypeError, ValueError):
        profile["fuel"] = 60
    vehicle_name = f"{profile['make']} {profile['model']}"
    vehicle_token = f"veh:starter:{cx}:{cy}:{sim.tick}"
    metadata = vehicle_metadata(
        profile,
        chunk=(cx, cy),
        owner_tag="player",
        display_color="vehicle_player",
        locked=True,
        key_id=vehicle_token,
        key_label=vehicle_name,
        lock_tier=2,
    )
    metadata["vehicle_id"] = vehicle_token
    vehicle_id = sim.register_property(
        name=vehicle_name,
        kind="vehicle",
        x=int(player_pos[0]),
        y=int(player_pos[1]),
        z=int(player_pos[2]),
        owner_eid=player_eid,
        owner_tag="player",
        metadata=metadata,
    )
    record = {
        "id": vehicle_id,
        "kind": "vehicle",
        "x": int(player_pos[0]),
        "y": int(player_pos[1]),
        "z": int(player_pos[2]),
        "archetype": "vehicle",
        "building_id": None,
    }
    chunk_key = (int(chunk.get("cx", cx)), int(chunk.get("cy", cy)))
    sim.chunk_property_records.setdefault(chunk_key, []).append(record)
    vehicle = sim.properties.get(vehicle_id)
    key_ok, _instance_id, _created = ensure_actor_has_property_key(sim, player_eid, vehicle, owner_tag="player")
    if not key_ok and vehicle:
        vehicle_meta = vehicle.get("metadata", {})
        if isinstance(vehicle_meta, dict):
            vehicle_meta["property_locked"] = False
    vehicle_state.set_active_vehicle(vehicle_id, tick=sim.tick)
    return vehicle


def _register_chunk_properties(sim, chunk):
    seed_chunk_organizations(sim, chunk)
    rng = random.Random(f"{sim.seed}:{chunk['cx']}:{chunk['cy']}:properties")
    records = []

    chunk_size = int(max(8, sim.chunk_size))
    origin_x = chunk["cx"] * chunk_size
    origin_y = chunk["cy"] * chunk_size
    area_type = str(chunk.get("district", {}).get("area_type", "city")).strip().lower() or "city"
    finance_by_archetype = {
        "bank": ("banking", "insurance"),
        "brokerage": ("banking", "insurance"),
        "office": ("insurance",),
        "tower": ("insurance",),
        "pawn_shop": ("insurance",),
        "backroom_clinic": ("insurance",),
    }

    for block in chunk.get("blocks", []):
        bx = block.get("grid_x", 0)
        by = block.get("grid_y", 0)
        building_count = len(block.get("buildings", []))
        for i, building in enumerate(block.get("buildings", [])):
            layout = layout_chunk_building(
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
                block_grid_x=bx,
                block_grid_y=by,
                building_index=i,
                building=building,
                building_count=building_count,
            )
            if not layout:
                continue
            x = int(layout["anchor_x"])
            y = int(layout["anchor_y"])
            z = 0
            _ensure_walkable(sim, x, y, z, glyph=".")
            archetype = building["archetype"]
            local_building_id = str(building.get("building_id", "") or "").strip()
            chunk_building_id = world_building_id(chunk["cx"], chunk["cy"], local_building_id)
            records.extend(register_large_span_child_properties(
                sim,
                parent_source=building,
                parent_layout=layout,
                parent_building_id=chunk_building_id,
                chunk_key=(chunk["cx"], chunk["cy"]),
                area_type=area_type,
                rng=rng,
                ensure_walkable=_ensure_walkable,
                district=chunk.get("district"),
            ))
            finance_services = list(finance_by_archetype.get(archetype, ()))
            site_services = list(dict.fromkeys(
                list(default_site_services_for_archetype(archetype))
                + list(vehicle_services_for_archetype(archetype))
            ))
            business_name = str(building.get("business_name") or "").strip()
            span_name = str(building.get("span_name") or "").strip()
            business_founder_name = str(building.get("business_founder_name") or "").strip()
            business_founder_first_name = str(building.get("business_founder_first_name") or "").strip()
            business_founder_last_name = str(building.get("business_founder_last_name") or "").strip()
            display_name = span_name or business_name or f"{archetype}:{building['building_id']}"
            property_id = sim.register_property(
                name=display_name,
                kind="building",
                x=x,
                y=y,
                z=z,
                owner_eid=None,
                owner_tag="city",
                metadata={
                    "archetype": archetype,
                    "building_id": chunk_building_id,
                    "local_building_id": local_building_id or None,
                    "large_parcel": bool(building.get("large_parcel")),
                    "parcel_span_x": int(building.get("parcel_span_x", 1) or 1),
                    "parcel_span_y": int(building.get("parcel_span_y", 1) or 1),
                    "floors": int(building.get("floors", 1)),
                    "basement_levels": int(building.get("basement_levels", 0)),
                    "rooms": list(building.get("rooms", ())),
                    "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "common_area_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "span_kind": str(building.get("span_kind", "") or "").strip().lower() or None,
                    "span_id": str(building.get("span_id", "") or "").strip() or None,
                    "span_name": span_name or None,
                    "span_founder_name": str(building.get("span_founder_name", "") or "").strip() or None,
                    "span_founder_first_name": str(building.get("span_founder_first_name", "") or "").strip() or None,
                    "span_founder_last_name": str(building.get("span_founder_last_name", "") or "").strip() or None,
                    "span_parent": bool(building.get("span_kind")),
                    "tenant_specs": [dict(spec) for spec in building.get("tenant_specs", ()) if isinstance(spec, dict)],
                    "housing_specs": [dict(spec) for spec in building.get("housing_specs", ()) if isinstance(spec, dict)],
                    "footprint": dict(layout.get("footprint", {})),
                    "placement": dict(layout.get("placement", {})),
                    "placement_profile": dict(building.get("placement_profile", {})) if isinstance(building.get("placement_profile"), dict) else None,
                    "entry": dict(layout.get("entry", {})),
                    "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                    "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                    "security_features": list(building.get("security_features", ())),
                    "purchase_cost": rng.randint(180, 460),
                    "finance_services": finance_services,
                    "site_services": site_services,
                    "is_storefront": bool(building.get("is_storefront")) and not bool(building.get("span_kind")),
                    "public": bool(building.get("public")),
                    "business_name": business_name or None,
                    "business_founder_name": business_founder_name or None,
                    "business_founder_first_name": business_founder_first_name or None,
                    "business_founder_last_name": business_founder_last_name or None,
                    "chunk": (chunk["cx"], chunk["cy"]),
                },
            )
            prop = sim.properties.get(property_id)
            seed_property_organization_defaults(prop, district=chunk.get("district"))
            ensure_property_organization(sim, prop)
            records.append({
                "id": property_id,
                "kind": "building",
                "x": x,
                "y": y,
                "z": z,
                "archetype": archetype,
                "building_id": chunk_building_id,
                "basement_levels": int(building.get("basement_levels", 0)),
            })

    reserved_site_footprints = []
    for idx, site in enumerate(chunk.get("sites", ())):
        if not isinstance(site, dict):
            continue
        layout = layout_chunk_site(
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            site_index=idx,
            site=site,
            reserved_footprints=reserved_site_footprints,
        )
        if not layout:
            continue
        reserved_site_footprints.extend(site_layout_reserved_footprints(layout))
        x = int(layout["anchor_x"])
        y = int(layout["anchor_y"])
        z = 0
        _ensure_walkable(sim, x, y, z, glyph=".")
        site_kind = str(site.get("kind", "site")).strip().lower() or "site"
        site_building_id = f"{chunk['cx']}:{chunk['cy']}:{site.get('site_id', idx)}"
        records.extend(register_large_span_child_properties(
            sim,
            parent_source=site,
            parent_layout=layout,
            parent_building_id=site_building_id,
            chunk_key=(chunk["cx"], chunk["cy"]),
            area_type=area_type,
            rng=rng,
            ensure_walkable=_ensure_walkable,
            district=chunk.get("district"),
        ))
        span_name = str(site.get("span_name") or "").strip()
        site_name = span_name or str(site.get("name", site_kind.replace("_", " ").title())).strip() or "Site"
        gameplay = site_gameplay_profile(site)
        public = bool(gameplay.get("public"))
        site_services = list(gameplay.get("site_services", ()))
        site_services = _merge_site_services(
            {"site_services": site_services},
            vehicle_services_for_archetype(site_kind),
        )
        property_id = sim.register_property(
            name=site_name,
            kind="building",
            x=x,
            y=y,
            z=z,
            owner_eid=None,
            owner_tag="public" if public else area_type,
            metadata={
                "archetype": site_kind,
                "site_kind": site_kind,
                "floors": 1,
                "rooms": list(site.get("rooms", ("entry", "room")) or ("entry", "room")),
                "building_id": site_building_id,
                "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                "common_area_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                "span_kind": str(site.get("span_kind", "") or "").strip().lower() or None,
                "span_id": str(site.get("span_id", "") or "").strip() or None,
                "span_name": span_name or None,
                "span_founder_name": str(site.get("span_founder_name", "") or "").strip() or None,
                "span_founder_first_name": str(site.get("span_founder_first_name", "") or "").strip() or None,
                "span_founder_last_name": str(site.get("span_founder_last_name", "") or "").strip() or None,
                "span_parent": bool(site.get("span_kind")),
                "tenant_specs": [dict(spec) for spec in site.get("tenant_specs", ()) if isinstance(spec, dict)],
                "housing_specs": [dict(spec) for spec in site.get("housing_specs", ()) if isinstance(spec, dict)],
                "footprint": dict(layout.get("footprint", {})),
                "entry": dict(layout.get("entry", {})),
                "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                "purchase_cost": rng.randint(110, 260),
                "finance_services": list(gameplay.get("finance_services", ())),
                "is_storefront": bool(gameplay.get("is_storefront")) and not bool(site.get("span_kind")),
                "site_services": list(site_services),
                "public": public,
                "chunk": (chunk["cx"], chunk["cy"]),
            },
        )
        prop = sim.properties.get(property_id)
        seed_property_organization_defaults(prop, district=chunk.get("district"))
        ensure_property_organization(sim, prop)
        records.append({
            "id": property_id,
            "kind": "building",
            "x": x,
            "y": y,
            "z": z,
            "archetype": site_kind,
            "building_id": site_building_id,
        })

    fixture_count = max(1, chunk_size // 8) if area_type != "city" else max(4, chunk_size // 4)
    fixtures = generate_chunk_fixture_records(
        sim,
        chunk,
        rng,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        target_count=fixture_count,
    )
    for fixture in fixtures:
        x = int(fixture["x"])
        y = int(fixture["y"])
        kind = str(fixture.get("kind", "fixture")).strip().lower() or "fixture"
        metadata = dict(fixture.get("metadata", {}))
        metadata["chunk"] = (chunk["cx"], chunk["cy"])
        property_id = sim.register_property(
            name=str(fixture.get("name", "Fixture")).strip() or "Fixture",
            kind=kind,
            x=x,
            y=y,
            z=0,
            owner_eid=None,
            owner_tag=str(fixture.get("owner_tag", "city")).strip() or "city",
            metadata=metadata,
        )
        records.append({
            "id": property_id,
            "kind": kind,
            "x": x,
            "y": y,
            "z": 0,
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })

    ramps = generate_quick_travel_ramp_records(
        sim,
        chunk,
        rng,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
    )
    for ramp in ramps:
        x = int(ramp["x"])
        y = int(ramp["y"])
        z = int(ramp.get("z", 0) or 0)
        if sim.property_at(x, y, z):
            continue
        metadata = dict(ramp.get("metadata", {}))
        metadata["chunk"] = (chunk["cx"], chunk["cy"])
        property_id = sim.register_property(
            name=str(ramp.get("name", "Entrance Ramp")).strip() or "Entrance Ramp",
            kind=str(ramp.get("kind", "asset")).strip().lower() or "asset",
            x=x,
            y=y,
            z=z,
            owner_eid=None,
            owner_tag=str(ramp.get("owner_tag", "city")).strip() or "city",
            metadata=metadata,
        )
        records.append({
            "id": property_id,
            "kind": str(ramp.get("kind", "asset")).strip().lower() or "asset",
            "x": x,
            "y": y,
            "z": z,
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })

    _register_justice_station_vehicles(
        sim,
        chunk,
        records,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
    )

    vehicle_target_count = max(2, chunk_size // 12) if area_type == "city" else (1 if rng.random() < 0.55 else 0)
    vehicles = generate_chunk_vehicle_records(
        sim,
        chunk,
        rng,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        target_count=vehicle_target_count,
    )
    for vehicle in vehicles:
        x = int(vehicle["x"])
        y = int(vehicle["y"])
        if sim.property_at(x, y, 0):
            continue
        property_id = sim.register_property(
            name=str(vehicle.get("name", "Vehicle")).strip() or "Vehicle",
            kind="vehicle",
            x=x,
            y=y,
            z=0,
            owner_eid=None,
            owner_tag=str(vehicle.get("owner_tag", "public")).strip() or "public",
            metadata={**dict(vehicle.get("metadata", {})), "chunk": (chunk["cx"], chunk["cy"])},
        )
        records.append({
            "id": property_id,
            "kind": "vehicle",
            "x": x,
            "y": y,
            "z": 0,
            "archetype": "vehicle",
            "building_id": None,
        })
    return records


def _register_streamed_chunk_properties(sim, chunk):
    """Use the canonical streaming path for the initial chunk too."""

    from game.world_progression_systems import WorldStreamingSystem

    chunk_key = (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
    streamer = WorldStreamingSystem(sim, focus_eid=0)
    streamer._ensure_chunk_properties(chunk_key[0], chunk_key[1])
    records = sim.chunk_property_records.setdefault(chunk_key, [])
    chunk_size = int(max(8, sim.chunk_size))
    origin_x = chunk_key[0] * chunk_size
    origin_y = chunk_key[1] * chunk_size
    _register_justice_station_vehicles(
        sim,
        chunk,
        records,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
    )
    return list(records)


def _seed_world_items(sim, property_records):
    chunk = getattr(sim, "active_chunk", None)
    if not isinstance(chunk, dict):
        return 0
    return int(seed_chunk_items(sim, chunk, property_records))


def _add_item(sim, eid, item_id, quantity=1, owner_tag="npc", metadata=None):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return ""
    item_def = ITEM_CATALOG.get(item_id)
    if not item_def:
        return ""
    added, instance_id = inventory.add_item(
        item_id=item_id,
        quantity=quantity,
        stack_max=item_def.get("stack_max", 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata=dict(metadata or {"starter_item": True}),
    )
    return str(instance_id or "") if added else ""


def _give_item(sim, eid, item_id, quantity=1, owner_tag="npc", metadata=None):
    return bool(
        _add_item(
            sim,
            eid,
            item_id,
            quantity=quantity,
            owner_tag=owner_tag,
            metadata=metadata,
        )
    )


def _normal_start_loadout_choices(profile):
    choices = []
    for raw_id in tuple(getattr(profile, "starter_loadout_ids", ()) or ()):
        loadout_id = str(raw_id or "").strip().lower()
        if loadout_id == "street" or loadout_id in NORMAL_START_LOADOUTS:
            if loadout_id not in choices:
                choices.append(loadout_id)
    return tuple(choices) or ("street",)


def _pick_normal_start_loadout(profile, rng):
    return str(rng.choice(_normal_start_loadout_choices(profile)))


def _give_normal_start_loadout_item(sim, eid, loadout_id, item_id, quantity=1):
    metadata = {
        "starter_item": True,
        "starter_loadout_id": str(loadout_id),
    }
    if is_appearance_item(item_id, item_catalog=ITEM_CATALOG):
        metadata.update(
            cosmetic_variant_metadata(
                item_id,
                seed_token=f"normal-start:{sim.seed}:{eid}:{loadout_id}:{item_id}",
                item_catalog=ITEM_CATALOG,
                sim=sim,
            )
        )
        metadata["starter_item"] = True
        metadata["starter_loadout_id"] = str(loadout_id)
    return _add_item(
        sim,
        eid,
        item_id,
        quantity=quantity,
        owner_tag="player",
        metadata=metadata,
    )


def _starter_int_range(rng, bounds, *, minimum=0):
    if not isinstance(bounds, (tuple, list)) or len(bounds) < 2:
        return int(max(minimum, 0))
    try:
        lo = int(bounds[0])
        hi = int(bounds[1])
    except (TypeError, ValueError):
        return int(max(minimum, 0))
    if hi < lo:
        lo, hi = hi, lo
    lo = max(int(minimum), lo)
    hi = max(lo, hi)
    return int(rng.randint(lo, hi))


def _give_starter_weapon(sim, eid, weapon_id, *, owner_tag="player", named_chance=0.0):
    weapon_id = str(weapon_id or "").strip()
    if not weapon_id:
        return False
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    inventory = sim.ecs.get(Inventory).get(eid)
    item_def = ITEM_CATALOG.get(weapon_id)
    weapon_def = WEAPON_CATALOG.get(weapon_id)
    if loadout is None or inventory is None or item_def is None or weapon_def is None:
        return False

    rng = random.Random(f"{sim.seed}:starter_weapon:{eid}:{weapon_id}")
    instance = roll_weapon_instance(rng, weapon_id, named_chance=named_chance)
    metadata = {
        "starter_item": True,
        "weapon_instance": dict(instance),
    }
    custom_name = str(instance.get("custom_name", "")).strip()
    if custom_name:
        metadata["display_name"] = custom_name
    added, instance_id = inventory.add_item(
        item_id=weapon_id,
        quantity=1,
        stack_max=item_def.get("stack_max", 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata=metadata,
    )
    if not added:
        return False
    instance["inventory_instance_id"] = instance_id
    loadout.add_weapon(weapon_id, instance=instance)
    return True


def _give_starter_armor(sim, eid, item_id, *, owner_tag="player"):
    item_id = str(item_id or "").strip()
    if not item_id:
        return False
    loadout = sim.ecs.get(ArmorLoadout).get(eid)
    inventory = sim.ecs.get(Inventory).get(eid)
    item_def = ITEM_CATALOG.get(item_id)
    if loadout is None or inventory is None or item_def is None:
        return False
    armor = item_def.get("armor", {})
    if not isinstance(armor, dict):
        return False
    added, instance_id = inventory.add_item(
        item_id=item_id,
        quantity=1,
        stack_max=item_def.get("stack_max", 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata={"starter_item": True},
    )
    if not added:
        return False
    outer_result = stow_cosmetic_outer_for_armor(sim, eid)
    if not bool(getattr(outer_result, "ok", False)):
        return False
    loadout.equip(
        instance_id=instance_id,
        item_id=item_id,
        name=item_def.get("name"),
        damage_reduction=armor.get("damage_reduction", 0.0),
        slot=armor.get("slot", "body"),
    )
    mark_inventory_instance_worn(sim, eid, instance_id, worn=True, slot="outer")
    return True


def _pick_false_claim(pool, true_value, rng):
    options = [value for value in pool if value != true_value]
    if not options:
        return true_value
    return rng.choice(options)


def _rumor_text(topic, claim_value):
    claim = str(claim_value or "").replace("_", " ").strip() or "unknown"
    topic = str(topic or "").strip().lower()
    if topic == "cat_toxin_coat":
        return f"{claim} cats are poisonous."
    if topic == "contamination_taxonomy":
        return f"{claim} animals are contaminated this cycle."
    if topic == "illness_human_role":
        return f"{claim} groups are carrying an illness."
    if topic == "war_human_role":
        return f"{claim} groups are gearing for conflict."
    if topic == "blessing_taxonomy":
        return f"{claim} animals are said to be lucky this run."
    return f"{topic.replace('_', ' ')} -> {claim}."


def _seed_world_start_flavor(sim):
    cat_trait_rng = random.Random(f"{sim.seed}:cat_trait_profile")
    cat_coat_pool = (
        "orange_tabby",
        "black",
        "calico",
        "tabby",
        "gray",
        "white",
        "tuxedo",
        "purple",
    )
    animal_taxonomy_pool = (
        "feline",
        "canine",
        "avian",
        "rodent",
        "reptile",
        "insect",
        "arachnid",
    )
    active_animal_taxonomies = ("feline",)
    active_human_roles = ("guard", "scout", "civilian")
    human_role_pool = (
        "guard",
        "scout",
        "civilian",
        "courier",
        "medic",
        "merchant",
        "mechanic",
        "technician",
        "bartender",
        "fixer",
    )
    spawned_cat_coats = list(cat_trait_rng.sample(cat_coat_pool, 3))
    toxic_cat_coat = cat_trait_rng.choice(spawned_cat_coats)
    false_cat_toxin_coat = _pick_false_claim(cat_coat_pool, toxic_cat_coat, cat_trait_rng)
    contamination_taxonomy = cat_trait_rng.choice(active_animal_taxonomies)
    false_contamination_taxonomy = _pick_false_claim(animal_taxonomy_pool, contamination_taxonomy, cat_trait_rng)
    illness_role = cat_trait_rng.choice(active_human_roles)
    false_illness_role = _pick_false_claim(human_role_pool, illness_role, cat_trait_rng)
    war_candidates = [role for role in active_human_roles if role != illness_role]
    war_role = cat_trait_rng.choice(war_candidates or list(active_human_roles))
    false_war_role = _pick_false_claim(human_role_pool, war_role, cat_trait_rng)
    if toxic_cat_coat == "purple":
        blessing_taxonomy = "feline"
    else:
        blessing_taxonomy = cat_trait_rng.choice(active_animal_taxonomies)
    false_blessing_taxonomy = _pick_false_claim(animal_taxonomy_pool, blessing_taxonomy, cat_trait_rng)
    misguided_rumor_chance = round(cat_trait_rng.uniform(0.18, 0.42), 2)
    contact_chance = round(cat_trait_rng.uniform(0.2, 0.48), 2)
    contact_cooldown = cat_trait_rng.randint(10, 24)
    condition_scale = round(cat_trait_rng.uniform(0.82, 1.18), 2)
    world_conditions = [
        {
            "id": "cat_toxin_coat",
            "topic": "cat_toxin_coat",
            "target_kind": "coat_variant",
            "target_value": toxic_cat_coat,
            "is_positive": False,
            "status": "ambient_contamination",
            "duration": cat_trait_rng.randint(8, 16),
            "chance": round(0.018 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(48, 96),
            "modifiers": {
                "safety_tick_delta": -0.12,
                "move_speed_mult": -0.02,
            },
            "chip_damage": 0,
            "safety_hit": -2.0,
            "source_tag": "ambient_contamination",
        },
        {
            "id": "contamination_taxonomy",
            "topic": "contamination_taxonomy",
            "target_kind": "taxonomy",
            "target_value": contamination_taxonomy,
            "is_positive": False,
            "status": "ambient_contamination",
            "duration": cat_trait_rng.randint(9, 18),
            "chance": round(0.014 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(52, 104),
            "modifiers": {
                "safety_tick_delta": -0.09,
                "energy_tick_delta": -0.03,
            },
            "chip_damage": 0,
            "safety_hit": -1.6,
            "energy_hit": -0.9,
            "source_tag": "ambient_contamination",
        },
        {
            "id": "illness_human_role",
            "topic": "illness_human_role",
            "target_kind": "human_role",
            "target_value": illness_role,
            "is_positive": False,
            "status": "illness_wave",
            "duration": cat_trait_rng.randint(12, 22),
            "chance": round(0.016 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(50, 108),
            "modifiers": {
                "energy_tick_delta": -0.08,
                "move_speed_mult": -0.05,
            },
            "chip_damage": 0,
            "energy_hit": -2.0,
            "source_tag": "illness_wave",
        },
        {
            "id": "war_human_role",
            "topic": "war_human_role",
            "target_kind": "human_role",
            "target_value": war_role,
            "is_positive": False,
            "status": "war_tension",
            "duration": cat_trait_rng.randint(11, 20),
            "chance": round(0.015 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(52, 108),
            "modifiers": {
                "safety_tick_delta": -0.16,
                "social_tick_delta": -0.04,
                "move_speed_mult": -0.04,
            },
            "chip_damage": 0,
            "safety_hit": -3.0,
            "social_hit": -1.4,
            "source_tag": "war_tension",
        },
        {
            "id": "blessing_taxonomy",
            "topic": "blessing_taxonomy",
            "target_kind": "taxonomy",
            "target_value": blessing_taxonomy,
            "is_positive": True,
            "status": "lucky_currents",
            "duration": cat_trait_rng.randint(10, 18),
            "chance": round(0.012 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(54, 115),
            "modifiers": {
                "safety_tick_delta": 0.09,
                "energy_tick_delta": 0.06,
                "move_speed_mult": 0.08,
            },
            "chip_damage": 0,
            "safety_hit": 1.6,
            "energy_hit": 1.1,
            "social_hit": 0.6,
            "source_tag": "lucky_currents",
        },
    ]
    rumor_claim_pools = {
        "cat_toxin_coat": list(cat_coat_pool),
        "contamination_taxonomy": list(animal_taxonomy_pool),
        "illness_human_role": list(human_role_pool),
        "war_human_role": list(human_role_pool),
        "blessing_taxonomy": list(animal_taxonomy_pool),
    }
    sim.world_rumors = [
        {
            "topic": "cat_toxin_coat",
            "true_value": toxic_cat_coat,
            "false_value": false_cat_toxin_coat,
            "tone": "danger",
            "seed_share_chance": 0.95,
            "misguided_chance": min(0.72, round(misguided_rumor_chance + 0.06, 2)),
        },
        {
            "topic": "contamination_taxonomy",
            "true_value": contamination_taxonomy,
            "false_value": false_contamination_taxonomy,
            "tone": "danger",
            "seed_share_chance": 0.74,
            "misguided_chance": misguided_rumor_chance,
        },
        {
            "topic": "illness_human_role",
            "true_value": illness_role,
            "false_value": false_illness_role,
            "tone": "danger",
            "seed_share_chance": 0.66,
            "misguided_chance": min(0.75, round(misguided_rumor_chance + 0.08, 2)),
        },
        {
            "topic": "war_human_role",
            "true_value": war_role,
            "false_value": false_war_role,
            "tone": "danger",
            "seed_share_chance": 0.6,
            "misguided_chance": min(0.75, round(misguided_rumor_chance + 0.09, 2)),
        },
        {
            "topic": "blessing_taxonomy",
            "true_value": blessing_taxonomy,
            "false_value": false_blessing_taxonomy,
            "tone": "boon",
            "seed_share_chance": 0.54,
            "misguided_chance": max(0.05, round(misguided_rumor_chance - 0.08, 2)),
        },
    ]
    sim.world_traits.update({
        "cat_coat_pool": list(cat_coat_pool),
        "toxic_cat_coat": toxic_cat_coat,
        "false_cat_toxin_coat": false_cat_toxin_coat,
        "active_human_roles": list(active_human_roles),
        "active_animal_taxonomies": list(active_animal_taxonomies),
        "misguided_rumor_chance": misguided_rumor_chance,
        "toxic_cat_contact_chance": contact_chance,
        "toxic_cat_contact_cooldown": contact_cooldown,
        "rumor_claim_pools": rumor_claim_pools,
        "world_conditions": world_conditions,
    })
    pressure_rng = random.Random(f"{sim.seed}:market_pressures")
    pressure_templates = {
        "war_tension": {
            "summary": "checkpoint searches slow freight",
            "tag_weights": {"restricted": 0.6, "medical": 0.4, "tool": 0.4, "food": -0.2},
            "stock_mult": 0.9,
            "price_mult": 1.12,
        },
        "illness_wave": {
            "summary": "clinics and pharmacies are under strain",
            "tag_weights": {"medical": 0.9, "food": 0.2},
            "stock_mult": 0.94,
            "price_mult": 1.08,
        },
        "ambient_contamination": {
            "summary": "clean food and meds are tighter than usual",
            "tag_weights": {"medical": 0.8, "food": -0.4, "drink": -0.2},
            "stock_mult": 0.92,
            "price_mult": 1.1,
        },
        "lucky_currents": {
            "summary": "a lucky run has loosened supply lines",
            "tag_weights": {"food": 0.4, "drink": 0.4, "token": 0.2},
            "stock_mult": 1.1,
            "price_mult": 0.94,
        },
    }
    active_pressure_count = 1 + (1 if pressure_rng.random() < 0.6 else 0)
    active_pressure_keys = pressure_rng.sample(
        list(pressure_templates.keys()),
        k=min(active_pressure_count, len(pressure_templates)),
    )
    sim.world_traits["market_pressures"] = [
        {
            "status": key,
            "summary": pressure_templates[key]["summary"],
            "tag_weights": dict(pressure_templates[key]["tag_weights"]),
            "stock_mult": pressure_templates[key]["stock_mult"],
            "price_mult": pressure_templates[key]["price_mult"],
            "intensity": round(pressure_rng.uniform(0.4, 0.9), 2),
        }
        for key in active_pressure_keys
    ]


def _pick_opening_rumor_text(sim):
    if not isinstance(getattr(sim, "world_rumors", None), list) or not sim.world_rumors:
        return "", ""
    traits = getattr(sim, "world_traits", {}) if isinstance(getattr(sim, "world_traits", {}), dict) else {}
    misguided_default = float(traits.get("misguided_rumor_chance", 0.28) or 0.28)
    opening_rng = random.Random(f"{sim.seed}:opening_rumor_claim")
    opening_rumor = opening_rng.choice(sim.world_rumors)
    opening_topic = str(opening_rumor.get("topic", "world_trait")).strip().lower()
    opening_true = str(opening_rumor.get("true_value", "")).strip().lower()
    opening_false = str(opening_rumor.get("false_value", "")).strip().lower()
    try:
        opening_misguided = float(opening_rumor.get("misguided_chance", misguided_default))
    except (TypeError, ValueError):
        opening_misguided = misguided_default
    opening_misguided = max(0.0, min(0.95, opening_misguided))
    opening_claim = opening_true
    if opening_false and opening_rng.random() < opening_misguided:
        opening_claim = opening_false
    rumor_text = _rumor_text(opening_topic, opening_claim)
    rumor_topics = ", ".join(
        str(rumor.get("topic", "world_trait")).replace("_", " ")
        for rumor in sim.world_rumors
    )
    return rumor_text, rumor_topics


def bootstrap_normal_run(
    sim,
    character_name,
    run_rng,
    *,
    gender_identity="nonbinary",
    profile=DEFAULT_NORMAL_RUN_BOOTSTRAP_PROFILE,
):
    if not isinstance(run_rng, random.Random):
        run_rng = random.Random(str(run_rng))

    start_chunk_cx, start_chunk_cy = _pick_playtest_start_chunk(
        sim,
        run_rng,
        preferred_area_type=profile.preferred_area_type,
    )
    start_focus_x, start_focus_y = sim.chunk_origin(start_chunk_cx, start_chunk_cy)
    start_focus_x += max(2, sim.chunk_size // 2)
    start_focus_y += max(2, sim.chunk_size // 2)

    sim.stream_world(start_focus_x, start_focus_y)
    sim.ensure_loaded_chunk_terrain()
    property_records = _register_streamed_chunk_properties(sim, sim.active_chunk)
    sim.chunk_property_records[(sim.active_chunk["cx"], sim.active_chunk["cy"])] = list(property_records)
    world_item_count = _seed_world_items(sim, property_records)
    maybe_seed_bones_for_chunk(sim, sim.active_chunk)
    maybe_seed_run_echo_for_chunk(sim, sim.active_chunk)
    _seed_world_start_flavor(sim)
    sim.world_traits["local_economy"] = chunk_economy_profile(sim, sim.active_chunk)
    sim.world_traits["bootstrap_player_opportunity_intel"] = bool(profile.bootstrap_player_opportunity_intel)
    seed_run_objective(sim, run_rng, visible=bool(profile.objective_visible))

    player_pos = _pick_chunk_street_spawn(sim, sim.active_chunk, run_rng)
    _ensure_walkable(sim, player_pos[0], player_pos[1], player_pos[2], glyph=".")

    core_stats_rng = random.Random(f"{sim.seed}:player_core_stats")
    player_core_stats = CoreStats(
        brawn=core_stats_rng.randint(3, 8),
        athleticism=core_stats_rng.randint(4, 9),
        dexterity=core_stats_rng.randint(4, 9),
        access=core_stats_rng.randint(4, 9),
        charm=core_stats_rng.randint(3, 8),
        common_sense=core_stats_rng.randint(4, 9),
    )
    player_insight = InsightStats(
        charm=player_core_stats.charm,
        common_sense=player_core_stats.common_sense,
    )
    player_skill_profile = seed_skill_profile(
        random.Random(f"{sim.seed}:player_skill_profile"),
        role="player",
        core=player_core_stats,
        insight=player_insight,
        jitter=0.18,
        birth_key=f"{sim.seed}:player_birth",
    )
    player_identity_profile = seed_player_identity_profile(
        f"{sim.seed}:player_identity",
        gender_identity,
    )
    player_identity = CreatureIdentity(
        taxonomy_class="hominid",
        species="homo sapiens",
        creature_type="human",
        common_name="operator",
        personal_name=str(character_name or "").strip() or "operator",
        assigned_sex=player_identity_profile.get("assigned_sex"),
        gender_identity=player_identity_profile.get("gender_identity"),
        pronoun_set=player_identity_profile.get("pronoun_set"),
        name_gender_score=None,
        gender_inference_source=None,
    )
    starter_wallet_credits = _starter_int_range(
        run_rng,
        profile.starter_wallet_credit_range,
        minimum=0,
    )
    starter_bank_credits = 0
    if run_rng.random() < float(profile.starter_bank_credit_chance):
        starter_bank_credits = _starter_int_range(
            run_rng,
            profile.starter_bank_credit_range,
            minimum=0,
        )
    player = _spawn(
        sim,
        Position(*player_pos),
        Render("@"),
        player_identity,
        PlayerControlled(),
        PlayerModeState(),
        Collider(blocks=True),
        NoiseProfile(move_radius=6),
        PlayerAssets(credits=int(starter_wallet_credits)),
        VehicleState(),
        FinancialProfile(bank_balance=int(starter_bank_credits)),
        player_core_stats,
        player_insight,
        player_skill_profile,
        NPCNeeds(energy=78, safety=68, social=54, hunger=86, thirst=90),
        Inventory(capacity=28),
        StatusEffects(),
        Vitality(max_hp=120, recover_to_hp=42),
        ArmorLoadout(),
        AppearanceLoadout(),
        WeaponLoadout(),
        CoverState(),
        ContactLedger(),
        PropertyKnowledge(),
        PropertyPortfolio(),
    )
    sim.player_eid = player

    starter_outfit_items = seed_player_starting_outfit(
        sim,
        player,
        seed_token=f"{character_name}:{sim.seed}:bootstrap",
    )
    player_appearance = sim.ecs.get(AppearanceLoadout).get(player)
    starter_basewear = {
        str(slot): dict(profile)
        for slot, profile in dict(getattr(player_appearance, "basewear", {}) or {}).items()
        if isinstance(profile, dict) and profile
    }

    starter_loadout_id = _pick_normal_start_loadout(profile, run_rng)
    street_kit_items = []
    starter_loadout_items = []
    worn_item_instances = {}
    if starter_loadout_id == "street":
        street_kit_items = list(profile.street_kit_base)
        if profile.street_kit_variants:
            street_kit_items.append(run_rng.choice(profile.street_kit_variants))
        loadout_item_rows = tuple(street_kit_items)
        loadout_profile = {}
    else:
        loadout_profile = dict(NORMAL_START_LOADOUTS.get(starter_loadout_id, {}))
        loadout_item_rows = tuple(loadout_profile.get("items", ()) or ())

    for item_id, quantity in loadout_item_rows:
        instance_id = _give_normal_start_loadout_item(
            sim,
            player,
            starter_loadout_id,
            item_id,
            quantity=quantity,
        )
        if instance_id:
            starter_loadout_items.append((str(item_id), int(quantity)))
            worn_item_instances[str(item_id)] = str(instance_id)

    worn_item_id = str(loadout_profile.get("worn_item_id", "") or "").strip()
    worn_instance_id = worn_item_instances.get(worn_item_id, "")
    if worn_instance_id:
        equip_appearance_item(
            sim,
            player,
            worn_instance_id,
            preferred_slot="outer",
            record_fashion=False,
        )

    starter_weapon_id = ""
    if starter_loadout_id == "street":
        if profile.starter_melee_weapon_pool and run_rng.random() < float(profile.starter_melee_weapon_chance):
            rolled_weapon = str(run_rng.choice(profile.starter_melee_weapon_pool) or "").strip()
            if _give_starter_weapon(sim, player, rolled_weapon, owner_tag="player"):
                starter_weapon_id = rolled_weapon
        elif profile.starter_firearm_pool and run_rng.random() < float(profile.starter_firearm_chance):
            rolled_weapon = str(run_rng.choice(profile.starter_firearm_pool) or "").strip()
            if _give_starter_weapon(sim, player, rolled_weapon, owner_tag="player"):
                starter_weapon_id = rolled_weapon
    else:
        rolled_weapon = str(loadout_profile.get("weapon_id", "") or "").strip()
        if rolled_weapon and _give_starter_weapon(sim, player, rolled_weapon, owner_tag="player"):
            starter_weapon_id = rolled_weapon
    if starter_weapon_id:
        starter_loadout_items.append((starter_weapon_id, 1))

    starter_armor_item_id = ""
    if starter_loadout_id == "street":
        if profile.starter_armor_pool and run_rng.random() < float(profile.starter_armor_chance):
            rolled_armor = str(run_rng.choice(profile.starter_armor_pool) or "").strip()
            if _give_starter_armor(sim, player, rolled_armor, owner_tag="player"):
                starter_armor_item_id = rolled_armor
    else:
        rolled_armor = str(loadout_profile.get("armor_item_id", "") or "").strip()
        if rolled_armor and _give_starter_armor(sim, player, rolled_armor, owner_tag="player"):
            starter_armor_item_id = rolled_armor
    if starter_armor_item_id:
        starter_loadout_items.append((starter_armor_item_id, 1))

    vehicle = None
    if run_rng.random() < float(profile.vehicle_seed_chance):
        vehicle = _ensure_starter_vehicle(sim, player, player_pos, run_rng)

    ambient_npc_count = len(spawn_chunk_npcs(sim, sim.active_chunk, property_records, reserved_property_ids=set()))
    ambient_npc_count += len(spawn_chunk_special_population(sim, sim.active_chunk, property_records))
    ensure_chunk_flora(sim, sim.active_chunk, property_records=property_records)

    sim.stream_world(player_pos[0], player_pos[1])
    sim.ensure_loaded_chunk_terrain()
    seed_run_opportunities(sim, player_eid=player, rng=run_rng)

    start_district = sim.active_chunk.get("district", {}) if isinstance(sim.active_chunk, dict) else {}
    start_name = (
        str(start_district.get("settlement_name") or "").strip()
        or str(start_district.get("region_name") or "").strip()
        or "unknown district"
    )
    start_district_type = str(start_district.get("district_type", "district")).replace("_", " ")
    local_economy = sim.world_traits.get("local_economy", {}) if isinstance(sim.world_traits, dict) else {}
    local_note = str(local_economy.get("chunk_note", "")).strip()
    pressure_note = str(local_economy.get("pressure_note", "")).strip()
    opening_rumor_text, opening_rumor_topics_text = _pick_opening_rumor_text(sim)

    sim.world_traits["normal_start"] = {
        "profile_id": str(profile.profile_id),
        "character_name": str(character_name or "").strip(),
        "gender_identity": str(player_identity.gender_identity or "nonbinary"),
        "start_chunk": {"cx": int(sim.active_chunk["cx"]), "cy": int(sim.active_chunk["cy"])},
        "starter_vehicle_seeded": bool(vehicle),
        "starter_loadout_id": starter_loadout_id,
        "starter_loadout_items": [
            {"item_id": str(item_id).strip().lower(), "quantity": int(quantity)}
            for item_id, quantity in starter_loadout_items
        ],
        "starter_wallet_credits": int(starter_wallet_credits),
        "starter_bank_credits": int(starter_bank_credits),
        "bootstrap_player_opportunity_intel": bool(profile.bootstrap_player_opportunity_intel),
        "run_objective_visible": bool(profile.objective_visible),
        "street_kit_items": [
            {"item_id": str(item_id).strip().lower(), "quantity": int(quantity)}
            for item_id, quantity in street_kit_items
        ],
        "starter_outfit_items": [dict(row) for row in tuple(starter_outfit_items or ())],
        "starter_basewear": starter_basewear,
        "starter_weapon_id": starter_weapon_id,
        "starter_armor_item_id": starter_armor_item_id,
    }

    return NormalRunBootstrapResult(
        player_eid=player,
        world_item_count=int(world_item_count),
        ambient_npc_count=int(ambient_npc_count),
        start_chunk=(int(sim.active_chunk["cx"]), int(sim.active_chunk["cy"])),
        start_name=start_name,
        start_district_type=start_district_type,
        local_note=local_note,
        pressure_note=pressure_note,
        starter_vehicle_seeded=bool(vehicle),
        starter_loadout_id=str(starter_loadout_id),
        starter_loadout_items=tuple(
            (str(item_id), int(quantity))
            for item_id, quantity in starter_loadout_items
        ),
        street_kit_items=tuple((str(item_id), int(quantity)) for item_id, quantity in street_kit_items),
        starter_wallet_credits=int(starter_wallet_credits),
        starter_bank_credits=int(starter_bank_credits),
        starter_weapon_id=str(starter_weapon_id),
        starter_armor_item_id=str(starter_armor_item_id),
        opening_rumor_text=opening_rumor_text,
        opening_rumor_topics_text=opening_rumor_topics_text,
    )
