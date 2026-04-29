import curses
import os
import random
import sys
import time

from engine.buildings import layout_chunk_building, world_building_id
from engine.events import Event
from engine.fixtures import generate_chunk_fixture_records
from engine.persistence import (
    character_save_exists,
    delete_character_save,
    load_character_run,
    normalize_character_name,
    save_character_run,
)
from engine.sites import layout_chunk_site, site_gameplay_profile, site_layout_reserved_footprints
from engine.sim import Simulation
from engine.tilemap import Tile
from game.components import (
    AI,
    ArmorLoadout,
    Collider,
    ContactLedger,
    CoreStats,
    CoverState,
    CreatureIdentity,
    FinancialProfile,
    InsightStats,
    Inventory,
    ItemUseProfile,
    JusticeProfile,
    MovementThrottle,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSocial,
    NPCTraits,
    NPCWill,
    NoiseProfile,
    Occupation,
    PlayerAssets,
    PlayerControlled,
    PlayerModeState,
    Position,
    PropertyKnowledge,
    PropertyPortfolio,
    Render,
    SkillProfile,
    StatusEffects,
    VehicleState,
    Vitality,
    WildlifeBehavior,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.bones import maybe_seed_bones_for_chunk, prime_bones_runtime
from game.economy import chunk_economy_profile, pick_career_for_workplace, workplace_archetype_weight
from game.finance_services import FinanceSystem
from game.items import ITEM_CATALOG
from game.npc_names import (
    generate_human_household_names,
    generate_human_personal_name,
    human_descriptor,
)
from game.organizations import ensure_property_organization, seed_property_organization_defaults, sync_actor_organization_affiliations
from game.population import human_max_hp_for_role, seed_chunk_items, seed_npc_finance, spawn_chunk_npcs
from game.player_businesses import PlayerBusinessSystem
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)
from game.opportunities import evaluate_opportunity_board, seed_run_opportunities
from game.property_access import default_site_services_for_archetype
from game.property_controllers import PropertySystem
from game.property_keys import ensure_actor_has_property_key, ensure_property_lock
from game.run_objectives import evaluate_run_objective, seed_run_objective
from game.service_menu import ServiceMenuSystem
from game.site_services import SiteServiceSystem
from game.skill_progression import SkillProgressionSystem
from game.skills import seed_skill_profile
from game.systems import (
    BusinessPulseAftermathSystem,
    BusinessPulseSceneSystem,
    CameraSystem,
    CoverSystem,
    CriminalJusticeSystem,
    CombatPacingSystem,
    CreatureHazardSystem,
    DoorWaitSystem,
    EavesdropSystem,
    EventLogSystem,
    FinalOperationSystem,
    ItemSystem,
    InputSystem,
    LightingSystem,
    NPCInteractionSystem,
    NPCInvestigateSystem,
    NPCItemUseSystem,
    NPCMemorySystem,
    NPCNeedsSystem,
    NPCSettlementSystem,
    NPCWeaponSystem,
    RumorSystem,
    NPCSocialDynamicsSystem,
    NPCWillSystem,
    NoiseSystem,
    SuppressionSystem,
    ObjectiveProgressSystem,
    OrganizationReputationSystem,
    OpportunitySystem,
    PlayerActionSystem,
    PropertyAwarenessSystem,
    PropertyDefenseSystem,
    RenderSystem,
    RivalOperatorSystem,
    RunPressureSystem,
    StatusEffectSystem,
    StealthSystem,
    TradeSystem,
    VisibilitySystem,
    WeaponSystem,
    WorldStreamingSystem,
)
from game.weapons import roll_weapon_instance
from ui.curses_view import CursesView
from ui.pygame_view import PygameView, atlas_manifest_tile_size


def _spawn(sim, *components):
    eid = sim.ecs.create()
    position = None

    for component in components:
        sim.ecs.add(eid, component)
        if isinstance(component, Position):
            position = component

    if position:
        sim.tilemap.add_entity(eid, position.x, position.y, position.z)

    return eid


def _env_flag(name, default):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _env_int(name, default, minimum=None):
    raw = os.getenv(name)
    value = default
    if raw is not None:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(int(minimum), int(value))
    return int(value)


def _resolve_pygame_tile_px(default=40):
    atlas_default = atlas_manifest_tile_size(default=default, minimum=8)
    return _env_int("BAKERRRR_TILE_SIZE_PX", atlas_default, minimum=8)


def _resolve_run_seed(default=None):
    raw = os.getenv("BAKERRRR_RUN_SEED")
    if raw is not None:
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            pass
    if default is not None:
        return int(default)
    return random.SystemRandom().randrange(1, 2_147_483_648)


def _resolve_ui_backend(argv=None):
    backend = str(os.getenv("BAKERRRR_UI", "curses") or "curses").strip().lower()
    args = list(argv or sys.argv[1:])
    for idx, raw in enumerate(args):
        value = str(raw).strip()
        if value.startswith("--ui="):
            backend = value.split("=", 1)[1].strip().lower() or backend
            continue
        if value == "--ui" and idx + 1 < len(args):
            backend = str(args[idx + 1]).strip().lower() or backend

    if backend in {"pygame", "tile", "tiles"}:
        return "pygame"
    return "curses"


def _prompt_character_name_text():
    while True:
        try:
            raw = input("Character name: ")
        except EOFError:
            raw = ""
        name = normalize_character_name(raw)
        if name:
            return name
        print("Please enter a valid character name.")


def _prompt_character_name(stdscr):
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        prompt_x = max(0, min(width - 1, 2))
        prompt_y = max(0, min(height - 1, 2))
        detail_y = min(height - 1, prompt_y + 2)
        input_y = min(height - 1, prompt_y + 4)
        max_text_width = max(0, width - prompt_x)
        prompt_text = "Character name:"[:max_text_width]
        detail_text = "Existing save with this name resumes once, then is deleted on load."[:max_text_width]

        stdscr.addstr(prompt_y, prompt_x, prompt_text)
        stdscr.addstr(detail_y, prompt_x, detail_text)
        stdscr.move(input_y, prompt_x)
        stdscr.clrtoeol()
        stdscr.refresh()

        try:
            curses.echo()
            try:
                curses.curs_set(1)
            except curses.error:
                pass
            raw = stdscr.getstr(input_y, prompt_x, 48)
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except curses.error:
                pass

        name = normalize_character_name(raw)
        if name:
            stdscr.erase()
            stdscr.refresh()
            return name


def _register_runtime_systems(sim, view, player):
    input_system = InputSystem(sim, view, player)
    cover_system = CoverSystem(sim)
    player_action_system = PlayerActionSystem(sim)
    camera_system = CameraSystem(sim, player)
    skill_progression_system = SkillProgressionSystem(sim, player)
    item_system = ItemSystem(sim, player)
    criminal_justice_system = CriminalJusticeSystem(sim, player)
    service_menu_system = ServiceMenuSystem(sim, player)
    trade_system = TradeSystem(sim, player)
    weapon_system = WeaponSystem(sim, player)
    finance_system = FinanceSystem(sim, player)
    site_service_system = SiteServiceSystem(sim, player)
    npc_interaction_system = NPCInteractionSystem(sim, player)
    combat_pacing_system = CombatPacingSystem(sim, player, engage_radius=10, danger_radius=6, calm_frames_to_exit=14)
    world_streaming_system = WorldStreamingSystem(sim, player)
    noise_system = NoiseSystem(sim)
    lighting_system = LightingSystem(sim, player)
    visibility_system = VisibilitySystem(sim, player)
    stealth_system = StealthSystem(sim, player)
    creature_hazard_system = CreatureHazardSystem(sim, player)

    property_system = PropertySystem(sim, player)
    player_business_system = PlayerBusinessSystem(sim, player)
    property_awareness_system = PropertyAwarenessSystem(sim)
    property_defense_system = PropertyDefenseSystem(sim)

    npc_memory_system = NPCMemorySystem(sim)
    rumor_system = RumorSystem(sim)
    npc_needs_system = NPCNeedsSystem(sim)
    npc_settlement_system = NPCSettlementSystem(sim)
    status_effect_system = StatusEffectSystem(sim)
    npc_item_use_system = NPCItemUseSystem(sim)
    npc_social_system = NPCSocialDynamicsSystem(sim)
    eavesdrop_system = EavesdropSystem(sim, player)
    door_wait_system = DoorWaitSystem(sim)
    npc_will_system = NPCWillSystem(sim)
    business_pulse_aftermath_system = BusinessPulseAftermathSystem(sim)
    business_pulse_scene_system = BusinessPulseSceneSystem(sim, player)
    npc_weapon_system = NPCWeaponSystem(sim, player)
    npc_system = NPCInvestigateSystem(sim)

    # Register WorldEventsSystem before SuppressionSystem
    from game.systems import WorldEventsSystem
    world_events_system = WorldEventsSystem(sim, player)

    opportunity_system = OpportunitySystem(sim, player, refresh_interval=20)
    rival_operator_system = RivalOperatorSystem(sim, player)
    objective_progress_system = ObjectiveProgressSystem(sim, player)
    run_pressure_system = RunPressureSystem(sim, player)
    organization_reputation_system = OrganizationReputationSystem(sim, player)
    final_operation_system = FinalOperationSystem(sim, player)

    log_system = EventLogSystem(sim, player)
    render_system = RenderSystem(sim, view, player, hud_lines=10)

    sim.register_system(input_system)
    sim.register_system(cover_system)
    sim.register_system(combat_pacing_system)
    sim.register_system(player_action_system)
    sim.register_system(camera_system)
    sim.register_system(skill_progression_system)
    sim.register_system(item_system)
    sim.register_system(service_menu_system)
    sim.register_system(trade_system)
    sim.register_system(finance_system)
    sim.register_system(site_service_system)
    sim.register_system(npc_interaction_system)
    sim.register_system(weapon_system)
    sim.register_system(world_streaming_system)
    sim.register_system(noise_system)
    sim.register_system(lighting_system)
    sim.register_system(creature_hazard_system)

    sim.register_system(property_system)
    sim.register_system(player_business_system)
    sim.register_system(property_awareness_system)
    sim.register_system(property_defense_system)

    sim.register_system(npc_memory_system)
    sim.register_system(rumor_system)
    sim.register_system(npc_needs_system)
    sim.register_system(npc_settlement_system)
    sim.register_system(status_effect_system)
    sim.register_system(npc_item_use_system)
    sim.register_system(npc_social_system)
    sim.register_system(eavesdrop_system)
    sim.register_system(business_pulse_aftermath_system)
    sim.register_system(world_events_system)
    suppression_system = SuppressionSystem(sim, player)
    sim.register_system(door_wait_system)
    sim.register_system(npc_will_system)
    sim.register_system(business_pulse_scene_system)
    sim.register_system(npc_weapon_system)
    sim.register_system(suppression_system)
    sim.register_system(criminal_justice_system)
    sim.register_system(npc_system)

    sim.register_system(opportunity_system)
    sim.register_system(rival_operator_system)
    sim.register_system(objective_progress_system)
    sim.register_system(run_pressure_system)
    sim.register_system(organization_reputation_system)
    sim.register_system(final_operation_system)
    sim.register_system(visibility_system)
    sim.register_system(stealth_system)
    sim.register_system(log_system)
    sim.register_system(render_system)


def _run_loop(sim, view, character_name):
    frame_seconds = 1.0 / 20.0
    # Advance the world tick every WORLD_TICK_DIVISOR UI frames.
    # InputSystem (runs_while_paused=True) still fires every frame so player
    # input and event-driven movement remain fully responsive.
    # Turn-based mode (e.g. combat) bypasses the throttle so it stays snappy.
    WORLD_TICK_DIVISOR = int(
        (sim.world_traits.get("tick_divisor") if isinstance(getattr(sim, "world_traits", None), dict) else None)
        or 4
    )
    _frame = 0
    while True:
        if not sim.running:
            break

        frame_start = time.perf_counter()

        _frame += 1
        throttled = (_frame % WORLD_TICK_DIVISOR != 0) and not sim.turn_based
        if throttled:
            sim.set_time_paused(True, reason="tick_throttle")
        sim.update()
        if throttled:
            sim.set_time_paused(False, reason="tick_throttle")

        view.refresh()

        elapsed = time.perf_counter() - frame_start
        sleep_for = frame_seconds - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

    run_end = None
    if isinstance(getattr(sim, "world_traits", None), dict):
        maybe_run_end = sim.world_traits.get("run_end")
        if isinstance(maybe_run_end, dict):
            run_end = dict(maybe_run_end)

    if run_end:
        return run_end

    save_path = save_character_run(sim, character_name)
    return {
        "show_post_curses": True,
        "outcome": "saved",
        "reason": "quit",
        "objective_title": character_name,
        "tick": int(getattr(sim, "tick", 0)),
        "summary_lines": [
            f"Character saved: {character_name}",
            f"Save file: {save_path.relative_to(save_path.parent.parent)}",
        ],
    }


def _build_demo_map(sim, chunk):
    rng = random.Random(f"{sim.seed}:{chunk['cx']}:{chunk['cy']}:map")

    width = sim.tilemap.width
    height = sim.tilemap.height

    for z in range(sim.tilemap.max_floors):
        for y in range(height):
            for x in range(width):
                sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph="."), z=z)

        for x in range(width):
            sim.tilemap.set_tile(x, 0, Tile(walkable=False, transparent=False, glyph="#"), z=z)
            sim.tilemap.set_tile(x, height - 1, Tile(walkable=False, transparent=False, glyph="#"), z=z)

        for y in range(height):
            sim.tilemap.set_tile(0, y, Tile(walkable=False, transparent=False, glyph="#"), z=z)
            sim.tilemap.set_tile(width - 1, y, Tile(walkable=False, transparent=False, glyph="#"), z=z)

        for _ in range(12):
            x = rng.randint(2, width - 3)
            y = rng.randint(2, height - 3)
            sim.tilemap.set_tile(x, y, Tile(walkable=False, transparent=False, glyph="#"), z=z)

    stairs_x = 3
    stairs_y = 3
    elevator_x = width - 4
    elevator_y = 3
    rear_stairs_x = 3
    rear_stairs_y = height - 4

    sim.tilemap.add_floor_link(stairs_x, stairs_y, from_z=0, to_z=1, kind="stairs")
    sim.tilemap.add_floor_link(rear_stairs_x, rear_stairs_y, from_z=1, to_z=2, kind="stairs")
    sim.tilemap.add_floor_link(elevator_x, elevator_y, from_z=0, to_z=1, kind="elevator")
    sim.tilemap.add_floor_link(elevator_x, elevator_y, from_z=1, to_z=2, kind="elevator")

    sim.tilemap.set_tile(stairs_x, stairs_y, Tile(walkable=True, transparent=True, glyph=">"), z=0)
    sim.tilemap.set_tile(stairs_x, stairs_y, Tile(walkable=True, transparent=True, glyph="<"), z=1)
    sim.tilemap.set_tile(rear_stairs_x, rear_stairs_y, Tile(walkable=True, transparent=True, glyph=">"), z=1)
    sim.tilemap.set_tile(rear_stairs_x, rear_stairs_y, Tile(walkable=True, transparent=True, glyph="<"), z=2)

    for z in range(3):
        sim.tilemap.set_tile(elevator_x, elevator_y, Tile(walkable=True, transparent=True, glyph="E"), z=z)


def _ensure_walkable(sim, x, y, z, glyph="."):
    existing = sim.tilemap.tile_at(x, y, z)
    if existing and existing.walkable:
        return
    sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph=glyph), z=z)


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


def _bond_pair(sim, left_eid, right_eid, relation, closeness=0.75, trust=0.75):
    socials = sim.ecs.get(NPCSocial)
    left = socials.get(left_eid)
    right = socials.get(right_eid)
    if not left or not right:
        return

    left.add_bond(right_eid, kind=relation, closeness=closeness, trust=trust)
    right.add_bond(left_eid, kind=relation, closeness=closeness, trust=trust)


def _register_chunk_properties(sim, chunk):
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
            finance_services = list(finance_by_archetype.get(archetype, ()))
            site_services = list(dict.fromkeys(
                list(default_site_services_for_archetype(archetype))
                + list(vehicle_services_for_archetype(archetype))
            ))
            business_name = str(building.get("business_name") or "").strip()
            business_founder_name = str(building.get("business_founder_name") or "").strip()
            business_founder_first_name = str(building.get("business_founder_first_name") or "").strip()
            business_founder_last_name = str(building.get("business_founder_last_name") or "").strip()
            display_name = business_name if business_name else f"{archetype}:{building['building_id']}"
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
                    "footprint": dict(layout.get("footprint", {})),
                    "entry": dict(layout.get("entry", {})),
                    "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                    "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                    "security_features": list(building.get("security_features", ())),
                    "purchase_cost": rng.randint(180, 460),
                    "finance_services": finance_services,
                    "site_services": site_services,
                    "is_storefront": bool(building.get("is_storefront")),
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
        site_name = str(site.get("name", site_kind.replace("_", " ").title())).strip() or "Site"
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
                "rooms": ["entry", "room"],
                "footprint": dict(layout.get("footprint", {})),
                "entry": dict(layout.get("entry", {})),
                "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                "purchase_cost": rng.randint(110, 260),
                "finance_services": list(gameplay.get("finance_services", ())),
                "is_storefront": bool(gameplay.get("is_storefront")),
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
            "building_id": f"{chunk['cx']}:{chunk['cy']}:{site.get('site_id', idx)}",
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

    vehicle_target_count = max(1, chunk_size // 12) if area_type == "city" else (1 if rng.random() < 0.55 else 0)
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


def _pick_property(records, preferred_archetypes=None, used=None, building_only=True):
    used = used or set()
    candidates = []

    for record in records:
        if record["id"] in used:
            continue
        if building_only and record["kind"] != "building":
            continue
        if preferred_archetypes and record.get("archetype") not in preferred_archetypes:
            continue
        candidates.append(record)

    if not candidates and preferred_archetypes:
        for record in records:
            if record["id"] in used:
                continue
            if building_only and record["kind"] != "building":
                continue
            candidates.append(record)

    if not candidates:
        return None

    return candidates[0]


def _pick_job(sim, rng, property_records, preferred_archetypes=None):
    candidates = [p for p in property_records if p["kind"] == "building"]
    economy_profile = chunk_economy_profile(sim, sim.active_chunk)

    if preferred_archetypes:
        filtered = [p for p in candidates if p.get("archetype") in preferred_archetypes]
        if filtered:
            candidates = filtered

    if not candidates:
        return sim.world.draw_career(rng), {"property_id": None, "building_id": None, "archetype": None}

    weighted = []
    for property_ref in candidates:
        archetype = property_ref.get("archetype")
        weight = workplace_archetype_weight(economy_profile, archetype)
        weighted.append((property_ref, weight))

    total = sum(weight for _property_ref, weight in weighted)
    pick = rng.uniform(0.0, total) if total > 0.0 else 0.0
    running = 0.0
    property_ref = candidates[-1]
    for candidate, weight in weighted:
        running += weight
        if pick <= running:
            property_ref = candidate
            break

    career = pick_career_for_workplace(
        sim.world,
        rng,
        archetype=property_ref.get("archetype"),
        economy_profile=economy_profile,
    )
    prop = sim.properties.get(property_ref["id"])
    organization_eid = ensure_property_organization(sim, prop) if prop else None
    workplace = {
        "property_id": property_ref["id"],
        "building_id": property_ref.get("building_id"),
        "archetype": property_ref.get("archetype"),
        "organization_eid": organization_eid,
    }
    return career, workplace


def _coords_or(property_ref, fallback):
    if property_ref:
        return property_ref["x"], property_ref["y"], property_ref["z"]
    return fallback


def _claim_property(sim, property_id, owner_eid=None, owner_tag=None):
    prop = sim.properties.get(property_id)
    if not prop:
        return

    old_owner = prop.get("owner_eid")
    sim.assign_property_owner(property_id, owner_eid=owner_eid, owner_tag=owner_tag)
    sim.emit(Event(
        "property_owner_changed",
        property_id=property_id,
        old_owner_eid=old_owner,
        new_owner_eid=owner_eid,
    ))


def _seed_world_items(sim, property_records):
    chunk = getattr(sim, "active_chunk", None)
    if not isinstance(chunk, dict):
        return 0
    return int(seed_chunk_items(sim, chunk, property_records))


def _give_item(sim, eid, item_id, quantity=1, owner_tag="npc"):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return False

    item_def = ITEM_CATALOG.get(item_id)
    if not item_def:
        return False

    return inventory.add_item(
        item_id=item_id,
        quantity=quantity,
        stack_max=item_def.get("stack_max", 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata={"starter_item": True},
    )[0]


def _give_weapon(sim, eid, weapon_id, named_chance=0.2, owner_tag="npc", inventory_backed=False):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout:
        return False

    rng = random.Random(f"{sim.seed}:weapon:{eid}:{weapon_id}")
    instance = roll_weapon_instance(rng, weapon_id, named_chance=named_chance)
    if inventory_backed:
        inventory = sim.ecs.get(Inventory).get(eid)
        item_def = ITEM_CATALOG.get(weapon_id)
        if inventory and item_def:
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


def _run_new_game(view, character_name):
    screen_w, screen_h = view.size()

    map_width = max(24, min(96, screen_w))
    map_height = max(14, min(40, screen_h - 10))

    sim = Simulation(
        seed=_resolve_run_seed(),
        map_width=map_width,
        map_height=map_height,
        max_floors=3,
        chunk_size=24,
    )
    sim.character_name = character_name
    sim.world_traits["character_name"] = character_name
    sim.world_traits["clock"] = {
        "start_hour": 9,
        "ticks_per_hour": 600,
    }
    final_op_downed_fails_run = _env_flag(
        "BAKERRRR_FINAL_OP_DOWNED_FAILS_RUN",
        True,
    )
    sim.world_traits["rules"] = {
        "final_op_downed_fails_run": bool(final_op_downed_fails_run),
    }
    prime_bones_runtime(sim)
    run_nonce = random.SystemRandom().randrange(1, 1_000_000_000)
    run_rng = random.Random(run_nonce)
    start_chunk_cx, start_chunk_cy = _pick_playtest_start_chunk(sim, run_rng)
    start_focus_x, start_focus_y = sim.chunk_origin(start_chunk_cx, start_chunk_cy)
    start_focus_x += max(2, sim.chunk_size // 2)
    start_focus_y += max(2, sim.chunk_size // 2)

    sim.stream_world(start_focus_x, start_focus_y)
    sim.ensure_loaded_chunk_terrain()
    property_records = _register_chunk_properties(sim, sim.active_chunk)
    sim.chunk_property_records[(sim.active_chunk["cx"], sim.active_chunk["cy"])] = list(property_records)
    world_item_count = _seed_world_items(sim, property_records)
    maybe_seed_bones_for_chunk(sim, sim.active_chunk)
    sim.world_traits["local_economy"] = chunk_economy_profile(sim, sim.active_chunk)
    sim.world_traits["playtest_start"] = {
        "nonce": run_nonce,
        "chunk": {"cx": sim.active_chunk["cx"], "cy": sim.active_chunk["cy"]},
    }

    used_properties = set()
    guard_home = _pick_property(property_records, {"apartment", "house", "tenement"}, used=used_properties)
    if guard_home:
        used_properties.add(guard_home["id"])

    guard_work = _pick_property(property_records, {"checkpoint", "armory", "barracks", "tower", "office"}, used=used_properties)
    if guard_work:
        used_properties.add(guard_work["id"])

    scout_home = _pick_property(property_records, {"apartment", "house", "corner_store"}, used=used_properties)
    if scout_home:
        used_properties.add(scout_home["id"])

    sibling_a_home = _pick_property(property_records, {"apartment", "house", "tenement"}, used=used_properties)
    if sibling_a_home:
        used_properties.add(sibling_a_home["id"])

    sibling_b_home = _pick_property(property_records, {"apartment", "house", "tenement"}, used=used_properties)
    if sibling_b_home:
        used_properties.add(sibling_b_home["id"])

    job_rng = random.Random(f"{sim.seed}:npc_jobs")
    guard_career, guard_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"checkpoint", "armory", "barracks", "tower"},
    )
    scout_career, scout_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"warehouse", "factory", "office", "server_hub"},
    )
    sibling_a_career, sibling_a_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"apartment", "house", "corner_store", "restaurant"},
    )
    sibling_b_career, sibling_b_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"apartment", "house", "corner_store", "bar"},
    )

    chunk_origin_x, chunk_origin_y = sim.chunk_origin(sim.active_chunk["cx"], sim.active_chunk["cy"])
    chunk_min_x = chunk_origin_x + 1
    chunk_max_x = chunk_origin_x + sim.chunk_size - 2
    chunk_min_y = chunk_origin_y + 1
    chunk_max_y = chunk_origin_y + sim.chunk_size - 2

    def _clamp_chunk_tile(x, y, z=0):
        return (
            max(chunk_min_x, min(chunk_max_x, int(x))),
            max(chunk_min_y, min(chunk_max_y, int(y))),
            int(z),
        )

    chunk_mid = max(4, sim.chunk_size // 2)
    chunk_mid_x = chunk_origin_x + chunk_mid
    chunk_mid_y = chunk_origin_y + chunk_mid
    guard_pos = _coords_or(guard_work, fallback=_clamp_chunk_tile(chunk_mid_x, chunk_mid_y, 0))
    scout_pos = _coords_or(scout_home, fallback=_clamp_chunk_tile(guard_pos[0] + 3, guard_pos[1], 0))
    sibling_a_pos = _coords_or(sibling_a_home, fallback=_clamp_chunk_tile(guard_pos[0] - 5, guard_pos[1] + 2, 0))
    sibling_b_pos = _coords_or(sibling_b_home, fallback=_clamp_chunk_tile(sibling_a_pos[0] - 2, sibling_a_pos[1], 0))
    orange_cat_pos = _clamp_chunk_tile(sibling_b_pos[0] + 2, sibling_b_pos[1] + 1, 0)
    black_cat_pos = _clamp_chunk_tile(sibling_b_pos[0] + 3, sibling_b_pos[1] - 1, 0)
    calico_cat_pos = _clamp_chunk_tile(sibling_b_pos[0] + 4, sibling_b_pos[1] + 2, 0)
    player_pos = _pick_chunk_street_spawn(
        sim,
        sim.active_chunk,
        run_rng,
        reserved=(
            guard_pos,
            scout_pos,
            sibling_a_pos,
            sibling_b_pos,
            orange_cat_pos,
            black_cat_pos,
            calico_cat_pos,
        ),
    )

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
    blessing_roll = cat_trait_rng.random()
    if blessing_roll < 0.7:
        blessing_taxonomy = cat_trait_rng.choice(active_animal_taxonomies)
    else:
        blessing_taxonomy = cat_trait_rng.choice(animal_taxonomy_pool)
    false_blessing_taxonomy = _pick_false_claim(animal_taxonomy_pool, blessing_taxonomy, cat_trait_rng)

    misguided_rumor_chance = round(cat_trait_rng.uniform(0.18, 0.42), 2)
    contact_chance = round(cat_trait_rng.uniform(0.22, 0.44), 2)
    contact_cooldown = cat_trait_rng.randint(12, 24)
    condition_scale = cat_trait_rng.uniform(0.85, 1.22)

    world_conditions = [
        {
            "id": "contamination_taxonomy",
            "topic": "contamination_taxonomy",
            "target_kind": "taxonomy",
            "target_value": contamination_taxonomy,
            "is_positive": False,
            "status": "ambient_contamination",
            "duration": cat_trait_rng.randint(14, 24),
            "chance": round(0.022 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(42, 88),
            "modifiers": {
                "safety_tick_delta": -0.13,
                "energy_tick_delta": -0.05,
                "move_speed_mult": -0.08,
            },
            "chip_damage": 1,
            "safety_hit": -2.6,
            "energy_hit": -1.2,
            "source_tag": "contamination_bloom",
        },
        {
            "id": "illness_human_role",
            "topic": "illness_human_role",
            "target_kind": "human_role",
            "target_value": illness_role,
            "is_positive": False,
            "status": "illness_wave",
            "duration": cat_trait_rng.randint(12, 22),
            "chance": round(0.018 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(38, 80),
            "modifiers": {
                "energy_tick_delta": -0.11,
                "move_speed_mult": -0.1,
            },
            "chip_damage": 1,
            "energy_hit": -2.5,
            "social_hit": -0.8,
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
    sim.world_traits["local_economy"] = chunk_economy_profile(sim, sim.active_chunk)
    seed_run_objective(sim, run_rng)

    _ensure_walkable(sim, player_pos[0], player_pos[1], player_pos[2], glyph=".")
    _ensure_walkable(sim, guard_pos[0], guard_pos[1], guard_pos[2], glyph=".")
    _ensure_walkable(sim, scout_pos[0], scout_pos[1], scout_pos[2], glyph=".")
    _ensure_walkable(sim, sibling_a_pos[0], sibling_a_pos[1], sibling_a_pos[2], glyph=".")
    _ensure_walkable(sim, sibling_b_pos[0], sibling_b_pos[1], sibling_b_pos[2], glyph=".")
    _ensure_walkable(sim, orange_cat_pos[0], orange_cat_pos[1], orange_cat_pos[2], glyph=".")
    _ensure_walkable(sim, black_cat_pos[0], black_cat_pos[1], black_cat_pos[2], glyph=".")
    _ensure_walkable(sim, calico_cat_pos[0], calico_cat_pos[1], calico_cat_pos[2], glyph=".")

    npc_speed_rng = random.Random(f"{sim.seed}:npc_speed_mods")
    guard_speed = round(npc_speed_rng.uniform(0.92, 1.18), 2)
    scout_speed = round(npc_speed_rng.uniform(1.05, 1.34), 2)
    sibling_a_speed = round(npc_speed_rng.uniform(0.78, 1.0), 2)
    sibling_b_speed = round(npc_speed_rng.uniform(0.82, 1.06), 2)
    cat_a_speed = round(npc_speed_rng.uniform(1.08, 1.32), 2)
    cat_b_speed = round(npc_speed_rng.uniform(1.0, 1.26), 2)
    cat_c_speed = round(npc_speed_rng.uniform(0.96, 1.2), 2)
    starter_name_seed = (sim.world_traits.get("playtest_start", {}) or {}).get("nonce", "static")
    starter_name_rng = random.Random(f"{sim.seed}:starter_human_names:{starter_name_seed}")
    guard_name = generate_human_personal_name(sim, starter_name_rng)
    scout_name = generate_human_personal_name(sim, starter_name_rng)
    sibling_a_name, sibling_b_name = generate_human_household_names(sim, starter_name_rng, count=2)
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

    player = _spawn(
        sim,
        Position(*player_pos),
        Render("@"),
        PlayerControlled(),
        PlayerModeState(),
        Collider(blocks=True),
        NoiseProfile(move_radius=6),
        PlayerAssets(credits=140),
        VehicleState(),
        FinancialProfile(bank_balance=45),
        player_core_stats,
        player_insight,
        player_skill_profile,
        NPCNeeds(energy=80, safety=76, social=70),
        Inventory(capacity=14),
        StatusEffects(),
        Vitality(max_hp=120, recover_to_hp=42),
        ArmorLoadout(),
        WeaponLoadout(),
        CoverState(),
        ContactLedger(),
        PropertyKnowledge(),
        PropertyPortfolio(),
    )
    sim.player_eid = player

    guard = _spawn(
        sim,
        Position(*guard_pos),
        Render("G"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("guard", guard_career),
            personal_name=guard_name,
        ),
        AI("guard"),
        MovementThrottle(
            default_cooldown=1,
            state_cooldowns={"patrolling": 2, "resting": 3},
            speed_multiplier=guard_speed,
        ),
        Collider(blocks=True),
        Occupation(career=guard_career, workplace=guard_workplace),
        NPCNeeds(energy=78, safety=82, social=58),
        NPCTraits(bravery=0.75, empathy=0.45, loyalty=0.72, discipline=0.88),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=8),
        StatusEffects(),
        Vitality(max_hp=max(72, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_guard_hp"), "guard"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.82,
            aim_bias=0.7,
            min_range=1,
            max_range=11,
            cooldown_jitter=0,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.72,
            risk_tolerance=0.2,
            auto_use=True,
            cooldown_ticks=11,
            preferred_tags={"medical", "safety"},
            avoid_tags={"illegal"},
        ),
        NPCRoutine(
            home=_coords_or(guard_home, fallback=_clamp_chunk_tile(guard_pos[0] - 2, guard_pos[1] + 1, 0)),
            work=_coords_or(guard_work, fallback=_clamp_chunk_tile(*guard_pos)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=True, justice=0.92, corruption=0.06, crime_sensitivity=0.97),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_guard_skill_profile"),
            role="guard",
            career=guard_career,
            jitter=0.22,
        ),
    )

    scout = _spawn(
        sim,
        Position(*scout_pos),
        Render("S"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("scout", scout_career),
            personal_name=scout_name,
        ),
        AI("scout"),
        MovementThrottle(
            default_cooldown=2,
            state_cooldowns={"protecting": 1, "patrolling": 2, "resting": 4},
            speed_multiplier=scout_speed,
        ),
        Collider(blocks=True),
        Occupation(career=scout_career, workplace=scout_workplace),
        NPCNeeds(energy=84, safety=70, social=64),
        NPCTraits(bravery=0.63, empathy=0.56, loyalty=0.66, discipline=0.67),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=8),
        StatusEffects(),
        Vitality(max_hp=max(64, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_scout_hp"), "scout"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.65,
            aim_bias=0.64,
            min_range=1,
            max_range=10,
            cooldown_jitter=1,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.64,
            risk_tolerance=0.42,
            auto_use=True,
            cooldown_ticks=10,
            preferred_tags={"energy", "stimulant"},
            avoid_tags={"illegal"},
        ),
        NPCRoutine(
            home=_coords_or(scout_home, fallback=_clamp_chunk_tile(scout_pos[0] + 1, scout_pos[1] + 1, 0)),
            work=_coords_or(guard_work, fallback=_clamp_chunk_tile(guard_pos[0] + 1, guard_pos[1], 0)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=False, justice=0.58, corruption=0.12, crime_sensitivity=0.71),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_scout_skill_profile"),
            role="scout",
            career=scout_career,
            jitter=0.22,
        ),
    )

    sibling_a = _spawn(
        sim,
        Position(*sibling_a_pos),
        Render("C"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("civilian", sibling_a_career),
            personal_name=sibling_a_name,
        ),
        AI("civilian"),
        MovementThrottle(
            default_cooldown=3,
            state_cooldowns={"seeking_safety": 2, "patrolling": 3},
            speed_multiplier=sibling_a_speed,
        ),
        Collider(blocks=True),
        Occupation(career=sibling_a_career, workplace=sibling_a_workplace),
        NPCNeeds(energy=72, safety=74, social=82),
        NPCTraits(bravery=0.28, empathy=0.82, loyalty=0.94, discipline=0.35),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=7),
        StatusEffects(),
        Vitality(max_hp=max(56, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_sibling_a_hp"), "civilian"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.26,
            aim_bias=0.52,
            min_range=1,
            max_range=8,
            cooldown_jitter=2,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.52,
            risk_tolerance=0.16,
            auto_use=True,
            cooldown_ticks=13,
            preferred_tags={"social", "food"},
            avoid_tags={"illegal", "stimulant"},
        ),
        NPCRoutine(
            home=_coords_or(sibling_a_home, fallback=_clamp_chunk_tile(*sibling_a_pos)),
            work=_coords_or(guard_work, fallback=_clamp_chunk_tile(sibling_a_pos[0] + 2, sibling_a_pos[1] - 1, 0)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=False, justice=0.25, corruption=0.05, crime_sensitivity=0.43),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_sibling_a_skill_profile"),
            role="civilian",
            career=sibling_a_career,
            jitter=0.22,
        ),
    )

    sibling_b = _spawn(
        sim,
        Position(*sibling_b_pos),
        Render("D"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("civilian", sibling_b_career),
            personal_name=sibling_b_name,
        ),
        AI("civilian"),
        MovementThrottle(
            default_cooldown=3,
            state_cooldowns={"seeking_safety": 2, "patrolling": 3},
            speed_multiplier=sibling_b_speed,
        ),
        Collider(blocks=True),
        Occupation(career=sibling_b_career, workplace=sibling_b_workplace),
        NPCNeeds(energy=76, safety=71, social=88),
        NPCTraits(bravery=0.34, empathy=0.8, loyalty=0.91, discipline=0.33),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=7),
        StatusEffects(),
        Vitality(max_hp=max(58, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_sibling_b_hp"), "civilian"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.34,
            aim_bias=0.56,
            min_range=1,
            max_range=9,
            cooldown_jitter=2,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.56,
            risk_tolerance=0.3,
            auto_use=True,
            cooldown_ticks=12,
            preferred_tags={"social", "energy"},
            avoid_tags={"illegal"},
        ),
        NPCRoutine(
            home=_coords_or(sibling_b_home, fallback=_clamp_chunk_tile(*sibling_b_pos)),
            work=_coords_or(scout_home, fallback=_clamp_chunk_tile(sibling_b_pos[0] + 1, sibling_b_pos[1] - 1, 0)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=False, justice=0.2, corruption=0.03, crime_sensitivity=0.31),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_sibling_b_skill_profile"),
            role="civilian",
            career=sibling_b_career,
            jitter=0.22,
        ),
    )

    def _starter_workplace_prop(workplace):
        if not isinstance(workplace, dict):
            return None
        property_id = str(workplace.get("property_id", "") or "").strip()
        if not property_id:
            return None
        return sim.properties.get(property_id)

    starter_economy_profile = chunk_economy_profile(sim, sim.active_chunk)
    seed_npc_finance(
        sim,
        guard,
        random.Random(f"{sim.seed}:starter_guard_finance"),
        role="guard",
        career=guard_career,
        workplace_prop=_starter_workplace_prop(guard_workplace),
        economy_profile=starter_economy_profile,
    )
    seed_npc_finance(
        sim,
        scout,
        random.Random(f"{sim.seed}:starter_scout_finance"),
        role="worker",
        career=scout_career,
        workplace_prop=_starter_workplace_prop(scout_workplace),
        economy_profile=starter_economy_profile,
    )
    seed_npc_finance(
        sim,
        sibling_a,
        random.Random(f"{sim.seed}:starter_sibling_a_finance"),
        role="civilian",
        career=sibling_a_career,
        workplace_prop=_starter_workplace_prop(sibling_a_workplace),
        economy_profile=starter_economy_profile,
    )
    seed_npc_finance(
        sim,
        sibling_b,
        random.Random(f"{sim.seed}:starter_sibling_b_finance"),
        role="civilian",
        career=sibling_b_career,
        workplace_prop=_starter_workplace_prop(sibling_b_workplace),
        economy_profile=starter_economy_profile,
    )

    def _spawn_cat(name, coat_variant, pos, speed, target=None):
        cat = _spawn(
            sim,
            Position(*pos),
            Render("F"),
            CreatureIdentity(
                taxonomy_class="feline",
                species="felis catus",
                creature_type="animal",
                common_name=name,
                coat_variant=coat_variant,
            ),
            AI("wildlife"),
            MovementThrottle(
                default_cooldown=2,
                state_cooldowns={"patrolling": 2, "seeking_safety": 1, "resting": 3},
                speed_multiplier=speed,
            ),
            Collider(blocks=True),
            NPCNeeds(energy=86, safety=67, social=44),
            NPCTraits(bravery=0.18, empathy=0.55, loyalty=0.35, discipline=0.22),
            NPCWill(),
            NPCMemory(),
            NPCSocial(),
            Inventory(capacity=2),
            StatusEffects(),
            Vitality(max_hp=42),
            CoverState(),
            ItemUseProfile(
                willingness=0.28,
                risk_tolerance=0.08,
                auto_use=False,
                cooldown_ticks=20,
            ),
            NPCRoutine(
                home=pos,
                work=None,
            ),
            WildlifeBehavior(
                home_radius=5,
                flee_radius=6,
                flock_radius=3,
                flocking=False,
                activity_period="day",
                rest_bias=0.48,
            ),
            PropertyKnowledge(),
            PropertyPortfolio(),
        )
        sim.ecs.get(AI)[cat].state = "patrolling"
        patrol_target = target or (pos[0] - 1, pos[1], pos[2])
        sim.ecs.get(AI)[cat].target = patrol_target
        return cat

    cat_positions = (orange_cat_pos, black_cat_pos, calico_cat_pos)
    cat_speeds = (cat_a_speed, cat_b_speed, cat_c_speed)
    cat_entities = []
    for idx, coat_variant in enumerate(spawned_cat_coats):
        coat_name = str(coat_variant).replace("_", " ")
        pos = cat_positions[idx]
        speed = cat_speeds[idx]
        cat_entities.append(_spawn_cat(
            name=f"{coat_name} cat",
            coat_variant=coat_variant,
            pos=pos,
            speed=speed,
            target=(pos[0] - 1, pos[1], pos[2]),
        ))

    rumor_seed_rng = random.Random(f"{sim.seed}:seed_cat_toxin_rumors")
    memories = sim.ecs.get(NPCMemory)
    witness_eids = [guard, scout, sibling_a, sibling_b]
    for eid in witness_eids:
        memory = memories.get(eid)
        if not memory:
            continue
        for rumor in sim.world_rumors:
            if rumor_seed_rng.random() > float(rumor.get("seed_share_chance", 0.72)):
                continue
            topic = str(rumor.get("topic", "")).strip().lower()
            true_claim = str(rumor.get("true_value", "")).strip().lower()
            false_claim = str(rumor.get("false_value", "")).strip().lower()
            if not topic or not true_claim:
                continue

            try:
                local_misguided = float(rumor.get("misguided_chance", misguided_rumor_chance))
            except (TypeError, ValueError):
                local_misguided = misguided_rumor_chance
            local_misguided = max(0.0, min(0.95, local_misguided))
            heard_claim = true_claim
            if false_claim and rumor_seed_rng.random() < local_misguided:
                heard_claim = false_claim

            memory.remember(
                tick=sim.tick,
                kind="world_trait",
                strength=round(rumor_seed_rng.uniform(0.48, 0.9), 3),
                topic=topic,
                claimed_value=heard_claim,
                is_true=heard_claim == true_claim,
                via="street_rumor_seed",
                tone=rumor.get("tone", "rumor"),
            )

    _give_item(sim, player, "street_ration", quantity=2, owner_tag="player")
    _give_item(sim, player, "calm_patch", quantity=1, owner_tag="player")
    _give_item(sim, player, "city_pass_token", quantity=2, owner_tag="player")

    _give_item(sim, guard, "med_gel", quantity=1, owner_tag="npc")
    _give_item(sim, guard, "focus_inhaler", quantity=1, owner_tag="npc")

    _give_item(sim, scout, "caff_shot", quantity=1, owner_tag="npc")
    _give_item(sim, scout, "street_ration", quantity=1, owner_tag="npc")

    _give_item(sim, sibling_a, "spark_brew", quantity=1, owner_tag="npc")
    _give_item(sim, sibling_a, "street_ration", quantity=1, owner_tag="npc")

    _give_item(sim, sibling_b, "caff_shot", quantity=1, owner_tag="npc")
    _give_item(sim, sibling_b, "street_ration", quantity=1, owner_tag="npc")

    _give_weapon(sim, player, "rust_revolver", named_chance=0.45, owner_tag="player", inventory_backed=True)
    _give_weapon(sim, player, "alley_shotgun", named_chance=0.35, owner_tag="player", inventory_backed=True)

    _give_weapon(sim, guard, "compact_smg", named_chance=0.4)
    _give_weapon(sim, guard, "rust_revolver", named_chance=0.3)

    _give_weapon(sim, scout, "rust_revolver", named_chance=0.25)
    _give_weapon(sim, sibling_a, "rust_revolver", named_chance=0.18)
    _give_weapon(sim, sibling_b, "improvised_launcher", named_chance=0.22)

    _bond_pair(sim, guard, scout, relation="coworker", closeness=0.68, trust=0.72)
    _bond_pair(sim, sibling_a, sibling_b, relation="family", closeness=0.93, trust=0.9)
    _bond_pair(sim, guard, sibling_a, relation="neighbor", closeness=0.38, trust=0.52)
    _bond_pair(sim, scout, sibling_b, relation="neighbor", closeness=0.32, trust=0.45)

    for owned_ref, owner_eid in (
        (guard_home, guard),
        (guard_work, guard),
        (scout_home, scout),
        (sibling_a_home, sibling_a),
        (sibling_b_home, sibling_b),
    ):
        if owned_ref:
            _claim_property(sim, owned_ref["id"], owner_eid=owner_eid, owner_tag="npc")

    for actor_eid in (guard, scout, sibling_a, sibling_b):
        sync_actor_organization_affiliations(sim, actor_eid)

    reserved_properties = set(used_properties)
    for workplace in (guard_workplace, scout_workplace, sibling_a_workplace, sibling_b_workplace):
        if isinstance(workplace, dict):
            property_id = workplace.get("property_id")
            if property_id:
                reserved_properties.add(property_id)
    ambient_npc_count = len(
        spawn_chunk_npcs(
            sim,
            sim.active_chunk,
            property_records,
            reserved_property_ids=reserved_properties,
        )
    )

    sim.stream_world(player_pos[0], player_pos[1])
    sim.ensure_loaded_chunk_terrain()
    seed_run_opportunities(sim, player_eid=player, rng=run_rng)
    _register_runtime_systems(sim, view, player)

    sim.log.add("Booted city sandbox. The district reacts to what you do.")
    sim.log.add(f"Character: {character_name}.")
    sim.log.add(f"World seed: {sim.seed}.")
    sim.log.add(
        f"Career pool ready: {len(sim.world.career_pool)} careers for "
        f"{len(sim.world.building_archetypes)} building archetypes."
    )
    sim.log.add(
        f"Properties loaded: {len(sim.properties)}. "
        f"Items seeded: {world_item_count}. "
        f"Ambient NPCs seeded: {ambient_npc_count}. "
        "NPCs track ownership, social links, justice, and consumables."
    )
    start_district = sim.active_chunk.get("district", {}) if isinstance(sim.active_chunk, dict) else {}
    start_name = (
        str(start_district.get("settlement_name") or "").strip()
        or str(start_district.get("region_name") or "").strip()
        or "unknown district"
    )
    start_district_type = str(start_district.get("district_type", "district")).replace("_", " ")
    sim.log.add(
        f"Start area: {start_name} ({start_district_type}, chunk "
        f"{sim.active_chunk['cx']},{sim.active_chunk['cy']})."
    )
    local_economy = sim.world_traits.get("local_economy", {}) if isinstance(sim.world_traits, dict) else {}
    local_note = str(local_economy.get("chunk_note", "")).strip()
    pressure_note = str(local_economy.get("pressure_note", "")).strip()
    if local_note:
        if pressure_note:
            sim.log.add(f"Local economy: {local_note}; {pressure_note}.")
        else:
            sim.log.add(f"Local economy: {local_note}.")
    objective_eval = evaluate_run_objective(sim, player)
    if objective_eval:
        objective_title = objective_eval.get("title", "Run Objective")
        objective_summary = objective_eval.get("summary", "")
        objective_status = objective_eval.get("summary_line", "")
        objective_next = objective_eval.get("next_step", "")
        if objective_summary:
            sim.log.add(f"Run objective: {objective_title}. {objective_summary}", channel="mission", priority="high")
        else:
            sim.log.add(f"Run objective: {objective_title}.", channel="mission", priority="high")
        if objective_status:
            sim.log.add(f"{objective_status}.", channel="mission", priority="high")
        if objective_next:
            sim.log.add(f"Next step: {objective_next}", channel="mission", priority="high")
    opportunity_eval = evaluate_opportunity_board(sim, player, limit=2)
    opportunity_summary = str(opportunity_eval.get("summary_line", "")).strip()
    if opportunity_summary:
        sim.log.add(opportunity_summary + ".", channel="opportunity", priority="high")
    for raw in list(opportunity_eval.get("lines", ()))[:2]:
        line = str(raw).strip()
        if line:
            sim.log.add(f"  {line}", channel="opportunity", priority="high")
    sim.log.add("Press O for the operations report and Y for known locations on foot or in-vehicle.")
    sim.log.add("The ops report explains why the current objective matters, what counts, and which opportunities fit it.")
    sim.log.add("Known locations lists places you have a real read on, with coords and confident facts.")
    sim.log.add("Press L to open the scrollable event log if messages roll past; inside it, T cycles filters and H sets the HUD log focus.")
    sim.log.add("Press E next to people to talk, at properties to use services, and at nearby vehicles to drive.")
    sim.log.add("HUD modes show active states like SNEAK, COVER, AIM, LOOK, and TURN.")
    sim.log.add(
        "NPC speed mods: "
        f"guard {guard_speed:.2f}x, scout {scout_speed:.2f}x, "
        f"sibling-a {sibling_a_speed:.2f}x, sibling-b {sibling_b_speed:.2f}x, "
        f"cat-a {cat_a_speed:.2f}x, cat-b {cat_b_speed:.2f}x, cat-c {cat_c_speed:.2f}x."
    )
    if sim.world_rumors:
        opening_rng = random.Random(f"{sim.seed}:opening_rumor_claim")
        opening_rumor = opening_rng.choice(sim.world_rumors)
        opening_topic = str(opening_rumor.get("topic", "world_trait")).strip().lower()
        opening_true = str(opening_rumor.get("true_value", "")).strip().lower()
        opening_false = str(opening_rumor.get("false_value", "")).strip().lower()
        try:
            opening_misguided = float(opening_rumor.get("misguided_chance", misguided_rumor_chance))
        except (TypeError, ValueError):
            opening_misguided = misguided_rumor_chance
        opening_misguided = max(0.0, min(0.95, opening_misguided))
        opening_claim = opening_true
        if opening_false and opening_rng.random() < opening_misguided:
            opening_claim = opening_false
        sim.log.add(f"Street rumor: {_rumor_text(opening_topic, opening_claim)}")
        rumor_topics = ", ".join(
            str(rumor.get("topic", "world_trait")).replace("_", " ")
            for rumor in sim.world_rumors
        )
        sim.log.add(f"World rumor topics active: {rumor_topics}.")
    sim.log.add(
        "Controls: move with arrows/WASD/HJKL or numpad 1-9, and press ? for the full help panel."
    )
    sim.log.add('City legend: + closed door, \' open door, " window, / breach opening, > higher stairs, < lower stairs, : stair landing, E elevator.')
    sim.log.add("Local terrain: = road, : trail, , brush, ^ rock, ~ water, _ shore flats.")
    sim.log.add("City legend: uppercase property markers are protected, lowercase are public, and S/s mark service access.")
    sim.log.add("Infrastructure markers now use typed street symbols (for example l lamp, p pole, h hydrant, u stop, j/t utility hardware).")
    sim.log.add("City legend: world features use symbols, items are bright symbols, and NPCs are colored letters.")
    sim.log.add("Remote sites: relay/lookout/survey sites can provide intel; camps and huts can offer shelter.")
    sim.log.add(
        "Overworld legend: in-vehicle macro-grid with district or terrain center icons, route bands for travel lines, and marker badges for your notes. Bright chunks are currently loaded, dim chunks are distant."
    )
    sim.log.add("Overworld POIs: stronger frontier/wilderness/coastal chunks can replace the center glyph with a site initial.")
    sim.log.add("Finance: use B near banks/ATMs to open banking transfers, and N near banks or insurers to buy/renew policies. Bank balances do not accrue passive interest.")
    sim.log.add("Combat overlay is exposure-aware: nearby danger can trigger action-driven turn mode.")
    final_rules = sim.world_traits.get("rules", {}) if isinstance(sim.world_traits, dict) else {}
    sim.log.add(
        "Rule: final-op downed fail is "
        f"{'ON' if bool(final_rules.get('final_op_downed_fails_run', True)) else 'OFF'} "
        "(set BAKERRRR_FINAL_OP_DOWNED_FAILS_RUN=0/1)."
    )
    if bool(final_rules.get("final_op_downed_fails_run", True)):
        sim.log.add("Combat is mostly forgiving: being downed costs credits and resets HP, except during final operation where a down can fail the run.")
    else:
        sim.log.add("Combat is forgiving: being downed costs credits and resets HP instead of ending the run.")

    return _run_loop(sim, view, character_name)


def _run_loaded_game(view, character_name):
    sim = load_character_run(character_name, delete_on_load=False)
    sim.character_name = normalize_character_name(character_name) or getattr(sim, "character_name", None)
    prime_bones_runtime(sim)
    if not isinstance(getattr(sim, "world_traits", None), dict):
        sim.world_traits = {}
    if sim.character_name:
        sim.world_traits["character_name"] = sim.character_name

    if isinstance(getattr(sim, "look_ui", None), dict):
        sim.look_ui["active"] = False
    if isinstance(getattr(sim, "trade_ui", None), dict):
        sim.trade_ui["open"] = False
    if isinstance(getattr(sim, "report_ui", None), dict):
        sim.report_ui["open"] = False
        sim.report_ui["scroll"] = 0
    if isinstance(getattr(sim, "log_ui", None), dict):
        sim.log_ui["open"] = False
        sim.log_ui["scroll"] = 0
    sim.turn_advance_requested = False

    player = getattr(sim, "player_eid", None)
    if player is None:
        raise ValueError("save file is missing player entity")

    player_pos = sim.ecs.get(Position).get(player)
    if player_pos:
        sim.stream_world(player_pos.x, player_pos.y)
        sim.ensure_loaded_chunk_terrain()

    _register_runtime_systems(sim, view, player)
    delete_character_save(character_name)
    sim.log.add(f"Resumed character: {sim.character_name or character_name}.")
    sim.log.add("Save file consumed after resume setup. Quit again to write a fresh save.")
    return _run_loop(sim, view, sim.character_name or character_name)


def _run_character_session(view, character_name):
    """Launch either a resumed run or a fresh run for a given view backend."""
    if character_save_exists(character_name):
        return _run_loaded_game(view, character_name)
    return _run_new_game(view, character_name)


def _run_curses(stdscr):
    # Prompt before CursesView sets non-blocking input mode.
    character_name = _prompt_character_name(stdscr)
    view = CursesView(stdscr)
    return _run_character_session(view, character_name)


def _run_pygame():
    # Pygame defaults follow the atlas manifest tile size when present.
    # Override with BAKERRRR_TILE_SIZE_PX / _GRID_W / _GRID_H if you want a different view.
    grid_w = _env_int("BAKERRRR_TILE_GRID_W", 64, minimum=24)
    grid_h = _env_int("BAKERRRR_TILE_GRID_H", 40, minimum=14)
    tile_px = _resolve_pygame_tile_px()
    view = PygameView(
        width_cells=grid_w,
        height_cells=grid_h,
        cell_px=tile_px,
        title="bakerrrr",
    )
    try:
        character_name = view.prompt_text_input(
            "Character name:",
            detail="Existing save with this name resumes once, then is deleted on load.",
            max_length=40,
            title="bakerrrr - character",
            banner="BAKERRRR",
            subtitle="Street-level run setup",
            invalid_message="Please enter a valid character name.",
            normalizer=normalize_character_name,
            status_lines_callback=lambda raw: (
                [{
                    "text": f"Resume available for {normalize_character_name(raw)}.",
                    "color": "objective",
                }]
                if normalize_character_name(raw) and character_save_exists(normalize_character_name(raw))
                else ([{
                    "text": f"Fresh run will start for {normalize_character_name(raw)}.",
                    "color": "scout",
                }] if normalize_character_name(raw) else [{
                    "text": "Enter a name to start or resume a run.",
                    "color": "default",
                }])
            ),
        )
        if not character_name:
            return None
        view.pygame.display.set_caption(f"bakerrrr - {character_name}")
        return _run_character_session(view, character_name)
    finally:
        view.close()


if __name__ == "__main__":
    backend = _resolve_ui_backend()
    if backend == "pygame":
        run_end = _run_pygame()
    else:
        run_end = curses.wrapper(_run_curses)
    if isinstance(run_end, dict) and bool(run_end.get("show_post_curses")):
        outcome = str(run_end.get("outcome", "unknown")).strip().upper()
        reason = str(run_end.get("reason", "")).strip().replace("_", " ")
        objective_title = str(run_end.get("objective_title", "Run")).strip() or "Run"
        tick = int(run_end.get("tick", 0))
        header = f"=== RUN {outcome} @ tick {tick}: {objective_title} ==="
        if reason:
            header += f" [{reason}]"
        print(header)
        for raw in run_end.get("summary_lines", ()):
            line = str(raw).strip()
            if line:
                print(f"- {line}")
