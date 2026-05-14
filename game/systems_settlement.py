"""NPC settlement and newcomer runtime extracted from ``game/systems.py``.

This seam keeps newcomer arrival, settlement, relocation, and chunk-level
population accounting together while ``game/systems.py`` remains the
compatibility facade for the rest of the project.
"""

import random

from engine.events import Event
from engine.systems import System
from game import systems as _systems
from game.location_presentation_runtime import _location_building_category
from game.system_support.settlement_runtime import (
    _home_property,
    _property_chunk_key,
    _track_entity_in_chunk_population,
)

AI = _systems.AI
CreatureIdentity = _systems.CreatureIdentity
NPCMemory = _systems.NPCMemory
NPCNeeds = _systems.NPCNeeds
NPCRoutine = _systems.NPCRoutine
NPCSettlement = _systems.NPCSettlement
NPCSocial = _systems.NPCSocial
NPCWill = _systems.NPCWill
Occupation = _systems.Occupation
PlayerControlled = _systems.PlayerControlled
Position = _systems.Position
RESIDENTIAL_ARCHETYPES = _systems.RESIDENTIAL_ARCHETYPES
SECURITY_ARCHETYPES = _systems.SECURITY_ARCHETYPES
Vitality = _systems.Vitality
_actor_skill = _systems._actor_skill
_bond_pair = _systems._bond_pair
_clamp = _systems._clamp
_manhattan = _systems._manhattan
_property_access_level = _systems._property_access_level
_property_archetype = _systems._property_archetype
_property_covering = _systems._property_covering
_property_focus_position = _systems._property_focus_position
_property_is_public = _systems._property_is_public
_property_is_storefront = _systems._property_is_storefront
_property_metadata = _systems._property_metadata
_shift_window_for = _systems._shift_window_for
_site_services_for_property = _systems._site_services_for_property
_spawn_human = _systems._spawn_human
_transit_services_connecting_chunks = _systems._transit_services_connecting_chunks
_workplace_property = _systems._workplace_property
actor_player_business_employment = _systems.actor_player_business_employment
chunk_economy_profile = _systems.chunk_economy_profile
ensure_property_organization = _systems.ensure_property_organization
pick_career_for_workplace = _systems.pick_career_for_workplace
sync_actor_organization_affiliations = _systems.sync_actor_organization_affiliations
unload_chunk_state = _systems.unload_chunk_state
workplace_archetype_weight = _systems.workplace_archetype_weight
def _anchor_distance(left, right):
    if not isinstance(left, (tuple, list)) or len(left) < 3:
        return 999999
    if not isinstance(right, (tuple, list)) or len(right) < 3:
        return 999999
    distance = _manhattan(int(left[0]), int(left[1]), int(right[0]), int(right[1]))
    if int(left[2]) != int(right[2]):
        distance += 8
    return int(distance)


_NEWCOMER_HOME_RETRY_TICKS = 120
_NEWCOMER_JOB_RETRY_TICKS = 180
_NEWCOMER_SOCIAL_RETRY_TICKS = 120
_NEWCOMER_DRIFT_WINDOW_TICKS = 900
_NEWCOMER_SPAWN_INTERVAL_TICKS = 900
_NEWCOMER_LOCAL_CAP = 2
_NEWCOMER_DRIFTER_TIMEOUT_TICKS = 2400
_NPC_LIFE_REVIEW_TICKS = 1800
_NPC_LIFE_MOVE_COOLDOWN_TICKS = 7200
_NPC_LIFE_REMOTE_SEARCH_RADIUS = 8
_NPC_LIFE_REMOTE_CANDIDATE_LIMIT = 4
_NPC_LIFE_LOCAL_IMPROVEMENT_DELTA = 1.35
_NPC_LIFE_LOCAL_JOB_SWITCH_DELTA = 0.8
_NPC_LIFE_REMOTE_MOVE_DELTA = 3.4
_NPC_LIFE_PLAYER_BUFFER = 10
_NPC_LIFE_MEMORY_LOOKBACK_TICKS = 2400
_NPC_LIFE_LOCAL_CONFLICT_MOVE_PRESSURE = 1.0
_NPC_LIFE_REMOTE_TRANSIT_REQUIRED_DISTANCE = 2
_NPC_LIFE_SETTLEMENT_TRANSIT_RADIUS = 2
_NPC_LIFE_HOUSEHOLD_BOND_MIN = 0.72
_NPC_LIFE_HOUSEHOLD_SPLIT_SCALE = 0.55
_NPC_SETTLEMENT_BACKFILL_INTERVAL_TICKS = 300
_NPC_SETTLEMENT_MAX_BACKFILL_PER_UPDATE = 12
_NPC_SETTLEMENT_MAX_LIFE_UPDATES_PER_UPDATE = 8
_NPC_SETTLEMENT_ACTIVE_CHUNK_RADIUS = 0
_BUSINESS_EVENT_RELEASE_CAP = _NEWCOMER_LOCAL_CAP + 1


def _business_event_scene_state(sim):
    return _systems._business_event_scene_state(sim)


def _newcomer_runtime_state(sim):
    state = getattr(sim, "newcomer_runtime_state", None)
    if isinstance(state, dict):
        state.setdefault("next_story_id", 1)
        state.setdefault("last_spawn_tick", -10_000)
        return state
    state = {
        "next_story_id": 1,
        "last_spawn_tick": -10_000,
    }
    sim.newcomer_runtime_state = state
    return state


def _next_newcomer_story_id(sim):
    state = _newcomer_runtime_state(sim)
    next_id = int(state.get("next_story_id", 1) or 1)
    state["next_story_id"] = next_id + 1
    return f"arrival:{next_id}"


def _weighted_choice(rng, weighted_rows):
    cleaned = []
    total = 0.0
    for value, weight in tuple(weighted_rows or ()):
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            continue
        if weight <= 0.0:
            continue
        cleaned.append((value, weight))
        total += weight
    if not cleaned:
        return None
    if total <= 0.0:
        return cleaned[-1][0]
    pick = rng.uniform(0.0, total)
    running = 0.0
    for value, weight in cleaned:
        running += weight
        if pick <= running:
            return value
    return cleaned[-1][0]


def _ensure_npc_routine(sim, eid):
    routine = sim.ecs.get(NPCRoutine).get(eid)
    if routine:
        return routine
    pos = sim.ecs.get(Position).get(eid)
    home = (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else None
    routine = NPCRoutine(home=home, work=None)
    sim.ecs.add(eid, routine)
    return routine


def _adjacent_street_tiles(sim, anchor, *, reserved=None):
    if not isinstance(anchor, (tuple, list)) or len(anchor) < 3:
        return []
    reserved = {
        (int(pos[0]), int(pos[1]), int(pos[2]))
        for pos in (reserved or ())
        if isinstance(pos, (tuple, list)) and len(pos) >= 3
    }
    ax, ay, az = int(anchor[0]), int(anchor[1]), int(anchor[2])
    tiles = []
    for radius in (1, 2):
        for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
            nx, ny = ax + dx, ay + dy
            pos = (nx, ny, az)
            if pos in reserved:
                continue
            if not sim.tilemap.is_walkable(nx, ny, az):
                continue
            if sim.structure_at(nx, ny, az):
                continue
            if sim.property_covering(nx, ny, az):
                continue
            if sim.tilemap.entities_at(nx, ny, az):
                continue
            tiles.append(pos)
    return tiles


def _newcomer_home_kind(prop):
    if not isinstance(prop, dict):
        return ""
    if str(prop.get("kind", "") or "").strip().lower() != "building":
        return ""
    services = {
        str(service or "").strip().lower()
        for service in tuple(_site_services_for_property(prop) or ())
        if str(service or "").strip()
    }
    archetype = _property_archetype(prop)
    if "shelter" in services:
        return "shelter"
    if archetype in {"hotel", "flophouse"} or "rest" in services:
        return "lodging"
    if archetype in RESIDENTIAL_ARCHETYPES:
        return "housing"
    return ""


def _newcomer_home_capacity(prop):
    archetype = _property_archetype(prop)
    kind = _newcomer_home_kind(prop)
    if archetype == "house":
        return 2
    if archetype in {"apartment", "beacon_house", "survey_post"}:
        return 4
    if archetype in {"tenement", "field_camp", "ranger_hut"}:
        return 6
    if archetype in {"hotel", "flophouse"}:
        return 10
    if archetype in {"ruin_shelter", "barracks"} or kind == "shelter":
        return 12
    if kind == "lodging":
        return 8
    if kind == "housing":
        return 4
    return 0


def _newcomer_home_load(sim, prop):
    property_id = str((prop or {}).get("id", "") or "").strip()
    if not property_id:
        return 0
    total = 0
    vitalities = sim.ecs.get(Vitality)
    for eid, routine in sim.ecs.get(NPCRoutine).items():
        vitality = vitalities.get(eid)
        if vitality and bool(getattr(vitality, "downed", False)):
            continue
        current = _home_property(sim, routine=routine)
        if current and str(current.get("id", "") or "").strip() == property_id:
            total += 1
    return total


def _newcomer_work_capacity(sim, prop):
    if not isinstance(prop, dict):
        return 0
    if str(prop.get("kind", "") or "").strip().lower() != "building":
        return 0
    archetype = _property_archetype(prop)
    if not archetype:
        return 0
    if _newcomer_home_kind(prop) and archetype not in {"hotel", "flophouse", "barracks"}:
        return 0

    try:
        chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (TypeError, ValueError):
        chunk = None
    chunk_context = {"cx": int(chunk[0]), "cy": int(chunk[1]), "district": {}} if isinstance(chunk, (tuple, list)) and len(chunk) >= 2 else None
    profile = chunk_economy_profile(sim, chunk_context)
    capacity = 1 + int(round(workplace_archetype_weight(profile, archetype)))
    category = _location_building_category(
        archetype,
        storefront=bool(_property_is_storefront(prop)),
    )
    if category in {"hospitality", "industrial", "medical", "office", "retail", "transit"}:
        capacity += 1
    if _property_is_storefront(prop) or _property_access_level(prop) == "public":
        capacity += 1
    return max(1, min(6, int(capacity)))


def _newcomer_work_load(sim, prop):
    property_id = str((prop or {}).get("id", "") or "").strip()
    if not property_id:
        return 0
    total = 0
    positions = sim.ecs.get(Position)
    vitalities = sim.ecs.get(Vitality)
    for eid, occupation in sim.ecs.get(Occupation).items():
        workplace = getattr(occupation, "workplace", None)
        if not isinstance(workplace, dict):
            continue
        vitality = vitalities.get(eid)
        if vitality and bool(getattr(vitality, "downed", False)):
            continue
        if eid not in positions:
            continue
        if str(workplace.get("property_id", "") or "").strip() == property_id:
            total += 1
    return total


def _live_newcomer_count_in_chunk(sim, chunk):
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return 0
    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return 0

    total = 0
    vitalities = sim.ecs.get(Vitality)
    settlements = sim.ecs.get(NPCSettlement)
    for eid in getattr(sim, "entity_ids_in_chunk", lambda _chunk: ())((int(chunk[0]), int(chunk[1]))):
        if eid not in settlements:
            continue
        vitality = vitalities.get(eid)
        if vitality and bool(getattr(vitality, "downed", False)):
            continue
        total += 1
    return total
def _business_scene_origin(newcomer):
    if not isinstance(newcomer, NPCSettlement):
        return ""
    return str(getattr(newcomer, "origin", "") or "").strip().lower()


def _is_business_scene_spillover(newcomer):
    return _business_scene_origin(newcomer).startswith("business_scene:")


def _business_scene_spillover_unsettled(newcomer):
    if not isinstance(newcomer, NPCSettlement):
        return False
    return not (
        str(getattr(newcomer, "home_property_id", "") or "").strip()
        and str(getattr(newcomer, "work_property_id", "") or "").strip()
    )


def _active_business_scene_actor_ids(sim):
    active = _business_event_scene_state(sim).get("active", {})
    if not isinstance(active, dict):
        return set()
    active_actor_ids = set()
    positions = sim.ecs.get(Position)
    for scene in active.values():
        if not isinstance(scene, dict):
            continue
        for eid in tuple(scene.get("spawned_entity_ids", ()) or ()):
            try:
                int_eid = int(eid)
            except (TypeError, ValueError):
                continue
            if positions.get(int_eid) is None:
                continue
            active_actor_ids.add(int_eid)
    return active_actor_ids


def _chunk_entity_tallies(sim):
    tallies = {}
    ais = sim.ecs.get(AI)
    vitalities = sim.ecs.get(Vitality)
    settlements = sim.ecs.get(NPCSettlement)
    active_actor_ids = _active_business_scene_actor_ids(sim)
    player_eid = getattr(sim, "player_eid", None)
    loaded_chunks = getattr(getattr(sim, "world", None), "loaded_chunks", {})
    chunk_keys = {
        (int(chunk[0]), int(chunk[1]))
        for chunk in tuple(getattr(sim, "chunk_entity_index", {}).keys())
    }
    if isinstance(loaded_chunks, dict) and loaded_chunks:
        loaded_keys = {(int(chunk[0]), int(chunk[1])) for chunk in loaded_chunks.keys()}
        chunk_keys &= loaded_keys

    for key in sorted(chunk_keys):
        for int_eid in getattr(sim, "entity_ids_in_chunk", lambda _chunk: ())((int(key[0]), int(key[1]))):
            ai = ais.get(int_eid)
            if ai is None:
                continue
            if player_eid is not None:
                try:
                    if int(player_eid) == int_eid:
                        continue
                except (TypeError, ValueError):
                    if player_eid == int_eid:
                        continue
            vitality = vitalities.get(int_eid)
            if vitality and bool(getattr(vitality, "downed", False)):
                continue
            role = str(getattr(ai, "role", "") or "").strip().lower()
            if role == "wildlife":
                continue
            entry = tallies.setdefault(key, {
                "live_entities": 0,
                "persistent_entities": 0,
                "active_scene_entities": 0,
                "business_scene_spillovers": 0,
                "business_scene_unsettled": 0,
            })
            entry["live_entities"] += 1
            if int_eid in active_actor_ids:
                entry["active_scene_entities"] += 1
            else:
                entry["persistent_entities"] += 1
            newcomer = settlements.get(int_eid)
            if _is_business_scene_spillover(newcomer):
                entry["business_scene_spillovers"] += 1
                if _business_scene_spillover_unsettled(newcomer):
                    entry["business_scene_unsettled"] += 1

    sim.chunk_entity_tallies = tallies
    return tallies


def _business_event_chunk_population_target(sim, chunk):
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return 0
    try:
        key = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return 0

    baselines = getattr(sim, "chunk_population_baselines", None)
    if isinstance(baselines, dict):
        try:
            baseline = int(baselines.get(key, 0) or 0)
        except (TypeError, ValueError):
            baseline = 0
        if baseline > 0:
            return baseline

    weight = 0
    for prop in sim.properties.values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("kind", "") or "").strip().lower() != "building":
            continue
        try:
            prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        if prop_chunk != key:
            continue
        weight += 2 if _property_is_storefront(prop) or _property_is_public(prop) else 1
    return max(_BUSINESS_EVENT_RELEASE_CAP, min(8, 1 + max(0, weight // 2)))


def _newcomer_distance_to_property(pos, prop):
    if pos is None or not isinstance(prop, dict):
        return 999999
    focus = _property_focus_position(prop)
    if not focus:
        return 999999
    distance = _manhattan(int(pos.x), int(pos.y), int(focus[0]), int(focus[1]))
    if int(pos.z) != int(focus[2]):
        distance += 8
    return int(distance)


def _ensure_newcomer_component(
    sim,
    eid,
    *,
    origin="",
    arrived_tick=None,
    drift_preferred=None,
    phase="arriving",
    housing_status="unhoused",
    employment_status="unemployed",
):
    settlements = sim.ecs.get(NPCSettlement)
    newcomer = settlements.get(eid)
    current_tick = int(getattr(sim, "tick", 0) if arrived_tick is None else arrived_tick)
    if newcomer is None:
        if drift_preferred is None:
            rng = random.Random(f"{getattr(sim, 'seed', 0)}:newcomer:{eid}:{origin}:{getattr(sim, 'tick', 0)}")
            drift_preferred = rng.random() < 0.22
        newcomer = NPCSettlement(
            arrived_tick=current_tick,
            origin=origin,
            phase=phase,
            housing_status=housing_status,
            employment_status=employment_status,
            last_housing_tick=current_tick - _NEWCOMER_HOME_RETRY_TICKS,
            last_job_tick=current_tick - _NEWCOMER_JOB_RETRY_TICKS,
            last_social_tick=current_tick - _NEWCOMER_SOCIAL_RETRY_TICKS,
            last_life_tick=current_tick - _NPC_LIFE_REVIEW_TICKS,
            last_move_tick=current_tick - _NPC_LIFE_MOVE_COOLDOWN_TICKS,
            drift_preferred=bool(drift_preferred),
            story_id=_next_newcomer_story_id(sim),
            life_goal="settling_in",
        )
        sim.ecs.add(eid, newcomer)
    else:
        if origin:
            newcomer.origin = str(origin).strip().lower()
        if arrived_tick is not None:
            newcomer.arrived_tick = int(arrived_tick)
        if drift_preferred is not None:
            newcomer.drift_preferred = bool(drift_preferred)
        if phase:
            newcomer.phase = str(phase).strip().lower() or newcomer.phase
        if housing_status:
            newcomer.housing_status = str(housing_status).strip().lower() or newcomer.housing_status
        if employment_status:
            newcomer.employment_status = str(employment_status).strip().lower() or newcomer.employment_status
        if not newcomer.story_id:
            newcomer.story_id = _next_newcomer_story_id(sim)
        if not hasattr(newcomer, "last_life_tick"):
            newcomer.last_life_tick = current_tick - _NPC_LIFE_REVIEW_TICKS
        if not hasattr(newcomer, "last_move_tick"):
            newcomer.last_move_tick = current_tick - _NPC_LIFE_MOVE_COOLDOWN_TICKS
        if not hasattr(newcomer, "life_goal"):
            newcomer.life_goal = "settling_in"

    occupation = sim.ecs.get(Occupation).get(eid)
    if occupation is None:
        occupation = Occupation(
            career="drifter" if newcomer.drift_preferred else "unemployed",
            workplace=None,
            shift_start=None,
            shift_end=None,
        )
        sim.ecs.add(eid, occupation)
    elif not isinstance(getattr(occupation, "workplace", None), dict):
        occupation.workplace = None
        if str(getattr(occupation, "career", "") or "").strip().lower() in {"", "resident"}:
            occupation.career = "drifter" if newcomer.drift_preferred else "unemployed"

    routine = _ensure_npc_routine(sim, eid)
    ai = sim.ecs.get(AI).get(eid)
    if ai and str(ai.role or "").strip().lower() in {"", "local", "worker"}:
        ai.role = "civilian"
    if ai and newcomer.employment_status != "employed":
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None
    if routine and newcomer.housing_status in {"unhoused", "drifting"} and newcomer.home_property_id == "":
        routine.home = None
    _track_entity_in_chunk_population(sim, eid)
    return newcomer


def spawn_persistent_newcomer(
    sim,
    position,
    *,
    source_prop=None,
    source="",
    personal_name=None,
    role="civilian",
    drift_preferred=None,
):
    if not isinstance(position, (tuple, list)) or len(position) < 3:
        return None
    source_prop = source_prop if isinstance(source_prop, dict) else None
    source_text = str(source or "").strip().lower()
    if not source_text and source_prop is not None:
        source_text = str(_property_archetype(source_prop) or source_prop.get("id", "arrival")).strip().lower()
    rng = random.Random(
        f"{getattr(sim, 'seed', 0)}:persistent-newcomer:{position[0]}:{position[1]}:{position[2]}:{source_text}:{getattr(sim, 'tick', 0)}"
    )
    drift_preferred = bool(rng.random() < 0.22) if drift_preferred is None else bool(drift_preferred)
    career = "drifter" if drift_preferred else "unemployed"
    eid = _spawn_human(
        sim,
        rng,
        str(role or "civilian").strip().lower() or "civilian",
        (int(position[0]), int(position[1]), int(position[2])),
        career=career,
        workplace=None,
        home=None,
        work=None,
        shift_window=None,
        personal_name=personal_name,
    )
    routine = sim.ecs.get(NPCRoutine).get(eid)
    if routine:
        routine.home = None
        routine.work = None
    _ensure_newcomer_component(
        sim,
        eid,
        origin=source_text,
        drift_preferred=drift_preferred,
        phase="drifting" if drift_preferred else "arriving",
        housing_status="drifting" if drift_preferred else "unhoused",
        employment_status="unemployed",
    )
    return eid


def _release_actor_to_newcomer(
    sim,
    eid,
    *,
    origin="",
    arrived_tick=None,
    drift_preferred=None,
):
    if eid is None or sim.ecs.get(Position).get(eid) is None:
        return None

    existing = sim.ecs.get(NPCSettlement).get(eid)
    if existing is not None and drift_preferred is None:
        drift_preferred = bool(existing.drift_preferred)

    released = _ensure_newcomer_component(
        sim,
        eid,
        origin=origin,
        arrived_tick=(sim.tick if arrived_tick is None else arrived_tick),
        drift_preferred=drift_preferred,
        phase="arriving",
        housing_status="drifting" if bool(drift_preferred) else "unhoused",
        employment_status="unemployed",
    )
    occupation = sim.ecs.get(Occupation).get(eid)
    routine = _ensure_npc_routine(sim, eid)
    ai = sim.ecs.get(AI).get(eid)
    will = sim.ecs.get(NPCWill).get(eid)

    if occupation:
        occupation.workplace = None
        occupation.shift_start = None
        occupation.shift_end = None
        occupation.career = "drifter" if released.drift_preferred else "unemployed"
    if routine:
        routine.work = None
    released.last_job_tick = int(sim.tick) - _NEWCOMER_JOB_RETRY_TICKS
    released.last_housing_tick = int(sim.tick) - _NEWCOMER_HOME_RETRY_TICKS
    if ai:
        ai.role = "civilian"
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None
    if will:
        will.intent = "idle"
        will.score = 0.0
        will.target = None
        will.target_eid = None
    return released


class NPCSettlementSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        self.rng = random.Random(f"{sim.seed}:npc-settlement")
        self._streaming_system = None
        if not hasattr(self.sim, "chunk_saved_states"):
            self.sim.chunk_saved_states = {}
        if not hasattr(self.sim, "chunk_property_records"):
            self.sim.chunk_property_records = {}
        if not hasattr(self.sim, "chunk_ground_item_records"):
            self.sim.chunk_ground_item_records = {}
        if not hasattr(self.sim, "chunk_population_records"):
            self.sim.chunk_population_records = {}
        self._last_backfill_tick = -10_000
        self._backfill_cursor = 0
        self._life_cursor = 0

    def _world_streaming_system(self):
        current = self._streaming_system
        if current is not None and current in getattr(self.sim, "systems", ()):
            return current
        for system in getattr(self.sim, "systems", ()):
            if hasattr(system, "_ensure_chunk_properties") and hasattr(system, "_ensure_chunk_population"):
                self._streaming_system = system
                return system
        return None


    def _actor_chunk_key(self, eid):
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None:
            return None
        try:
            return self.sim.chunk_coords(int(pos.x), int(pos.y))
        except (TypeError, ValueError):
            return None

    def _in_active_settlement_scope(self, eid):
        active = self._active_chunk_coord()
        if active is None:
            return True
        chunk = self._actor_chunk_key(eid)
        if chunk is None:
            return False
        radius = max(0, int(_NPC_SETTLEMENT_ACTIVE_CHUNK_RADIUS))
        return max(abs(int(chunk[0]) - active[0]), abs(int(chunk[1]) - active[1])) <= radius

    def _settlement_worklist(self):
        items = [
            (int(eid), newcomer)
            for eid, newcomer in tuple(self.sim.ecs.get(NPCSettlement).items())
            if self._in_active_settlement_scope(eid)
        ]
        if not items:
            return []
        items.sort(key=lambda row: row[0])
        budget = max(1, int(_NPC_SETTLEMENT_MAX_LIFE_UPDATES_PER_UPDATE))
        if len(items) <= budget:
            self._life_cursor = 0
            return items
        start = int(self._life_cursor) % len(items)
        ordered = items[start:] + items[:start]
        self._life_cursor = (start + budget) % len(items)
        return ordered[:budget]

    def _chunk_loaded(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return False
        key = (int(chunk[0]), int(chunk[1]))
        return key in getattr(getattr(self.sim, "world", None), "loaded_chunks", {})

    def _player_near_actor(self, pos):
        if pos is None:
            return False
        player_eid = getattr(self.sim, "player_eid", None)
        if player_eid is None:
            return False
        player_pos = self.sim.ecs.get(Position).get(player_eid)
        if player_pos is None:
            return False
        if int(player_pos.z) != int(pos.z):
            return False
        return _manhattan(int(pos.x), int(pos.y), int(player_pos.x), int(player_pos.y)) <= _NPC_LIFE_PLAYER_BUFFER

    def _eligible_life_actor(self, eid):
        if self.sim.ecs.get(PlayerControlled).get(eid) is not None:
            return False
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None:
            return False
        vitality = self.sim.ecs.get(Vitality).get(eid)
        if vitality and bool(getattr(vitality, "downed", False)):
            return False
        identity = self.sim.ecs.get(CreatureIdentity).get(eid)
        if identity is None or str(getattr(identity, "creature_type", "") or "").strip().lower() != "human":
            return False
        ai = self.sim.ecs.get(AI).get(eid)
        role = str(getattr(ai, "role", "") or "").strip().lower()
        if role in {"guard", "scout", "thief", "wildlife"}:
            return False
        player_eid = getattr(self.sim, "player_eid", None)
        if player_eid is not None and actor_player_business_employment(self.sim, eid, owner_eid=player_eid) is not None:
            return False
        return True

    def _settlement_chunk(self, pos=None, *, routine=None, occupation=None):
        home_prop = _home_property(self.sim, routine=routine)
        if home_prop is not None:
            return _property_chunk_key(self.sim, home_prop)
        work_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)
        if work_prop is not None:
            return _property_chunk_key(self.sim, work_prop)
        if pos is None:
            return None
        try:
            return self.sim.chunk_coords(int(pos.x), int(pos.y))
        except (TypeError, ValueError):
            return None

    def _settlement_label(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2 or getattr(self.sim, "world", None) is None:
            return ""
        descriptor = self.sim.world.overworld_descriptor(int(chunk[0]), int(chunk[1]))
        label = str((descriptor or {}).get("settlement_name", "") or "").strip()
        if label:
            return label.lower()
        district = self.sim.world.get_chunk(int(chunk[0]), int(chunk[1])).get("district", {})
        district_type = str((district or {}).get("district_type", "") or "").strip()
        if district_type:
            return district_type.lower()
        return str((descriptor or {}).get("area_type", "city") or "city").strip().lower()

    def _settlement_name(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2 or getattr(self.sim, "world", None) is None:
            return ""
        descriptor = self.sim.world.overworld_descriptor(int(chunk[0]), int(chunk[1]))
        return str((descriptor or {}).get("settlement_name", "") or "").strip().lower()

    def _settlement_transit_chunks(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2 or getattr(self.sim, "world", None) is None:
            return []
        origin = (int(chunk[0]), int(chunk[1]))
        settlement_name = self._settlement_name(origin)
        if not settlement_name:
            return [origin]
        candidates = [origin]
        seen = {origin}
        radius = max(0, int(_NPC_LIFE_SETTLEMENT_TRANSIT_RADIUS))
        for qy in range(origin[1] - radius, origin[1] + radius + 1):
            for qx in range(origin[0] - radius, origin[0] + radius + 1):
                candidate = (int(qx), int(qy))
                if candidate in seen:
                    continue
                if self._settlement_name(candidate) != settlement_name:
                    continue
                seen.add(candidate)
                candidates.append(candidate)
        return candidates

    def _bond_destination_chunks(self, social):
        if social is None:
            return []
        weighted = []
        positions = self.sim.ecs.get(Position)
        routines = self.sim.ecs.get(NPCRoutine)
        for other_eid, bond in tuple(getattr(social, "bonds", {}).items()):
            other_routine = routines.get(other_eid)
            other_pos = positions.get(other_eid)
            other_chunk = self._settlement_chunk(other_pos, routine=other_routine)
            if other_chunk is None:
                continue
            score = float(bond.get("closeness", 0.0) or 0.0) + (float(bond.get("trust", 0.0) or 0.0) * 0.6)
            weighted.append((score, (int(other_chunk[0]), int(other_chunk[1]))))
        weighted.sort(key=lambda row: (row[0], -abs(row[1][0]), -abs(row[1][1])), reverse=True)
        ranked = []
        seen = set()
        for _score, chunk in weighted:
            if chunk in seen:
                continue
            seen.add(chunk)
            ranked.append(chunk)
            if len(ranked) >= 3:
                break
        return ranked

    def _social_support_score(self, eid, target_chunk, social=None):
        if not isinstance(target_chunk, (tuple, list)) or len(target_chunk) < 2:
            return 0.0
        social = social if isinstance(social, NPCSocial) else self.sim.ecs.get(NPCSocial).get(eid)
        if social is None:
            return 0.0
        target_chunk = (int(target_chunk[0]), int(target_chunk[1]))
        target_label = self._settlement_label(target_chunk)
        positions = self.sim.ecs.get(Position)
        routines = self.sim.ecs.get(NPCRoutine)
        total = 0.0
        for other_eid, bond in tuple(getattr(social, "bonds", {}).items()):
            other_routine = routines.get(other_eid)
            other_pos = positions.get(other_eid)
            other_chunk = self._settlement_chunk(other_pos, routine=other_routine)
            if other_chunk is None:
                continue
            other_chunk = (int(other_chunk[0]), int(other_chunk[1]))
            proximity = 0.0
            if other_chunk == target_chunk:
                proximity = 1.0
            elif target_label and self._settlement_label(other_chunk) == target_label:
                proximity = 0.65
            if proximity <= 0.0:
                continue
            kind = str(bond.get("kind", "") or "").strip().lower()
            relation_weight = {
                "partner": 2.15,
                "family": 1.8,
                "friend": 1.15,
                "coworker": 0.85,
                "neighbor": 0.65,
            }.get(kind, 0.55)
            closeness = float(bond.get("closeness", 0.0) or 0.0)
            trust = float(bond.get("trust", 0.0) or 0.0)
            total += ((closeness * 0.8) + (trust * 0.4)) * relation_weight * proximity
        return min(5.5, total)

    def _household_bond_profile(self, first_eid, second_eid):
        best = None
        socials = self.sim.ecs.get(NPCSocial)
        for source_eid, other_eid in ((first_eid, second_eid), (second_eid, first_eid)):
            social = socials.get(source_eid)
            if social is None:
                continue
            bond = social.bonds.get(other_eid)
            if not isinstance(bond, dict):
                continue
            kind = str(bond.get("kind", "") or "").strip().lower()
            if kind not in {"family", "partner"}:
                continue
            closeness = _clamp(float(bond.get("closeness", 0.0) or 0.0), lo=0.0, hi=1.0)
            trust = _clamp(float(bond.get("trust", 0.0) or 0.0), lo=0.0, hi=1.0)
            protectiveness = _clamp(float(bond.get("protectiveness", 0.0) or 0.0), lo=0.0, hi=1.0)
            strength = ((closeness * 0.55) + (trust * 0.3) + (protectiveness * 0.15)) * (
                1.06 if kind == "partner" else 1.0
            )
            if best is None or strength > best["strength"]:
                best = {
                    "kind": kind,
                    "closeness": float(closeness),
                    "trust": float(trust),
                    "protectiveness": float(protectiveness),
                    "strength": float(strength),
                }
        return best

    def _household_cohort(self, eid, *, home_prop=None):
        routine = self.sim.ecs.get(NPCRoutine).get(eid)
        home_prop = home_prop if isinstance(home_prop, dict) else _home_property(self.sim, routine=routine)
        property_id = str((home_prop or {}).get("id", "") or "").strip()
        if not property_id:
            return []
        positions = self.sim.ecs.get(Position)
        routines = self.sim.ecs.get(NPCRoutine)
        same_home = []
        for other_eid, other_routine in tuple(routines.items()):
            if int(other_eid) == int(eid) or not self._eligible_life_actor(other_eid):
                continue
            other_home = _home_property(self.sim, routine=other_routine)
            if not other_home or str(other_home.get("id", "") or "").strip() != property_id:
                continue
            if positions.get(other_eid) is None:
                continue
            same_home.append(int(other_eid))
        if not same_home:
            return []
        household = []
        visited = {int(eid)}
        frontier = [int(eid)]
        while frontier:
            source_eid = frontier.pop(0)
            for other_eid in same_home:
                if other_eid in visited:
                    continue
                bond = self._household_bond_profile(source_eid, other_eid)
                if bond is None or float(bond["strength"]) < _NPC_LIFE_HOUSEHOLD_BOND_MIN:
                    continue
                other_pos = positions.get(other_eid)
                visited.add(other_eid)
                frontier.append(other_eid)
                household.append({
                    "eid": int(other_eid),
                    "kind": bond["kind"],
                    "strength": float(bond["strength"]),
                    "closeness": float(bond["closeness"]),
                    "trust": float(bond["trust"]),
                    "can_relocate": not self._player_near_actor(other_pos),
                })
        household.sort(key=lambda row: (row["strength"], -row["eid"]), reverse=True)
        return household

    def _portable_household_support(self, eid, household, *, relocatable_only=False):
        if not household:
            return 0.0
        total = 0.0
        for member in tuple(household):
            if relocatable_only and not bool(member.get("can_relocate", False)):
                continue
            bond = self._household_bond_profile(eid, member.get("eid"))
            if bond is None:
                continue
            relation_weight = 2.15 if bond["kind"] == "partner" else 1.8
            total += ((bond["closeness"] * 0.8) + (bond["trust"] * 0.4)) * relation_weight
        return min(4.8, total)

    def _household_split_penalty(self, eid, household):
        if not household:
            return 0.0
        portable_support = self._portable_household_support(eid, household)
        penalty = (portable_support * _NPC_LIFE_HOUSEHOLD_SPLIT_SCALE) + (0.3 * len(tuple(household)))
        return min(2.8, float(penalty))

    def _transit_link_profile(self, current_chunk, target_chunk):
        if not isinstance(current_chunk, (tuple, list)) or len(current_chunk) < 2:
            return {"required": False, "connected": False, "score_bonus": 0.0, "service": ""}
        if not isinstance(target_chunk, (tuple, list)) or len(target_chunk) < 2:
            return {"required": False, "connected": False, "score_bonus": 0.0, "service": ""}
        current_chunk = (int(current_chunk[0]), int(current_chunk[1]))
        target_chunk = (int(target_chunk[0]), int(target_chunk[1]))
        distance = _manhattan(current_chunk[0], current_chunk[1], target_chunk[0], target_chunk[1])
        required = distance >= _NPC_LIFE_REMOTE_TRANSIT_REQUIRED_DISTANCE
        if distance <= 0:
            return {"required": False, "connected": True, "score_bonus": 0.0, "service": ""}
        best = None
        for origin_option in self._settlement_transit_chunks(current_chunk):
            for target_option in self._settlement_transit_chunks(target_chunk):
                services = _transit_services_connecting_chunks(self.sim, origin_option, target_option)
                if not services:
                    continue
                local_leg = _manhattan(current_chunk[0], current_chunk[1], origin_option[0], origin_option[1]) + _manhattan(
                    target_chunk[0],
                    target_chunk[1],
                    target_option[0],
                    target_option[1],
                )
                for service in tuple(services):
                    score_bonus = {
                        "rail_transit": 0.95,
                        "ferry_transit": 0.82,
                        "bus_transit": 0.58,
                        "shuttle_transit": 0.34,
                    }.get(str(service).strip().lower(), 0.28) - (float(local_leg) * 0.08)
                    if best is None or score_bonus > best["score_bonus"]:
                        best = {
                            "required": bool(required),
                            "connected": True,
                            "score_bonus": max(0.0, float(score_bonus)),
                            "service": str(service).strip().lower(),
                            "origin_chunk": origin_option,
                            "target_chunk": target_option,
                        }
        if best is not None:
            return best
        return {"required": bool(required), "connected": False, "score_bonus": 0.0, "service": ""}

    def _memory_entry_chunk(self, entry):
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        property_id = str(data.get("property_id", "") or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            chunk = _property_chunk_key(self.sim, prop)
            if chunk is not None:
                return (int(chunk[0]), int(chunk[1]))
        if "x" in data and "y" in data:
            try:
                return self.sim.chunk_coords(int(data.get("x", 0)), int(data.get("y", 0)))
            except (TypeError, ValueError):
                pass
        for actor_key in ("source_eid", "offender_eid", "against_eid", "ally_eid", "side_eid"):
            actor_eid = data.get(actor_key)
            pos = self.sim.ecs.get(Position).get(actor_eid)
            if pos is None:
                continue
            try:
                return self.sim.chunk_coords(int(pos.x), int(pos.y))
            except (TypeError, ValueError):
                continue
        return None

    def _memory_pressure(self, eid, *, target_chunk=None, target_prop=None, memory=None):
        memory = memory if isinstance(memory, NPCMemory) else self.sim.ecs.get(NPCMemory).get(eid)
        if memory is None:
            return 0.0
        prop_id = str((target_prop or {}).get("id", "") or "").strip() if isinstance(target_prop, dict) else ""
        if target_chunk is not None and isinstance(target_chunk, (tuple, list)) and len(target_chunk) >= 2:
            target_chunk = (int(target_chunk[0]), int(target_chunk[1]))
        else:
            target_chunk = None
        current_tick = int(getattr(self.sim, "tick", 0))
        total = 0.0
        for entry in tuple(getattr(memory, "entries", ()) or ()):
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind", "")).strip().lower()
            weight = {
                "threat": 1.55,
                "property_threat": 1.9,
                "offense": 1.35,
                "ally_threatened": 1.15,
                "conflict_side": 1.0,
            }.get(kind, 0.0)
            if weight <= 0.0:
                continue
            age = max(0, current_tick - int(entry.get("tick", current_tick) or current_tick))
            if age > _NPC_LIFE_MEMORY_LOOKBACK_TICKS:
                continue
            strength = _clamp(float(entry.get("strength", 0.0) or 0.0), lo=0.0, hi=1.0)
            if strength <= 0.0:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            match = 0.0
            if prop_id and str(data.get("property_id", "") or "").strip() == prop_id:
                match = 1.0
            entry_chunk = self._memory_entry_chunk(entry)
            if target_chunk is not None and entry_chunk == target_chunk:
                match = max(match, 0.72)
            if prop_id and "x" in data and "y" in data:
                try:
                    prop = _property_covering(self.sim, int(data.get("x", 0)), int(data.get("y", 0)), int(data.get("z", 0)))
                except (TypeError, ValueError):
                    prop = None
                if isinstance(prop, dict) and str(prop.get("id", "") or "").strip() == prop_id:
                    match = max(match, 0.92)
            if match <= 0.0:
                continue
            age_mult = max(0.25, 1.0 - (age / float(_NPC_LIFE_MEMORY_LOOKBACK_TICKS + 1)))
            total += float(weight) * strength * age_mult * match
        return min(4.8, total)

    def _housing_quality(self, prop):
        kind = _newcomer_home_kind(prop)
        if not kind:
            return 0.0, ""
        archetype = _property_archetype(prop)
        score = {
            "housing": 4.0,
            "lodging": 2.7,
            "shelter": 1.4,
        }.get(kind, 0.0)
        score += {
            "apartment": 0.55,
            "house": 0.42,
            "tenement": 0.18,
            "hotel": 0.05,
            "flophouse": -0.18,
            "ranger_hut": 0.12,
            "field_camp": -0.05,
            "ruin_shelter": -0.32,
        }.get(archetype, 0.0)
        return max(0.0, score), kind

    def _actor_workplace_skill_fit(self, eid, category, archetype=""):
        category = str(category or "").strip().lower()
        archetype = str(archetype or "").strip().lower()
        skill_sets = {
            "retail": (("conversation", 0.45), ("perception", 0.3), ("streetwise", 0.25)),
            "hospitality": (("conversation", 0.5), ("streetwise", 0.25), ("perception", 0.25)),
            "industrial": (("mechanics", 0.52), ("athletics", 0.28), ("perception", 0.2)),
            "office": (("conversation", 0.38), ("perception", 0.34), ("streetwise", 0.28)),
            "medical": (("perception", 0.45), ("conversation", 0.35), ("mechanics", 0.2)),
            "transit": (("streetwise", 0.34), ("perception", 0.31), ("athletics", 0.2), ("conversation", 0.15)),
            "finance": (("conversation", 0.42), ("perception", 0.38), ("streetwise", 0.2)),
            "general": (("conversation", 0.3), ("streetwise", 0.28), ("perception", 0.24), ("mechanics", 0.18)),
            "secure": (("perception", 0.4), ("athletics", 0.32), ("intrusion", 0.28)),
        }
        total = 0.0
        for skill_id, weight in skill_sets.get(category, skill_sets["general"]):
            total += (float(_actor_skill(self.sim, eid, skill_id, default=5.0)) - 5.0) * float(weight)
        if archetype in {"auto_garage", "hardware_store", "tool_depot", "repair_shop"}:
            total += (float(_actor_skill(self.sim, eid, "mechanics", default=5.0)) - 5.0) * 0.12
        elif archetype in {"bar", "cafe", "restaurant", "hotel", "corner_store"}:
            total += (float(_actor_skill(self.sim, eid, "conversation", default=5.0)) - 5.0) * 0.1
        elif archetype in {"freight_depot", "truck_stop", "relay_post", "metro_exchange"}:
            total += (float(_actor_skill(self.sim, eid, "streetwise", default=5.0)) - 5.0) * 0.08
        return _clamp(total * 0.42, lo=-0.95, hi=1.45)

    def _chunk_context(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2 or getattr(self.sim, "world", None) is None:
            return None, {}, {}, {}
        cx, cy = int(chunk[0]), int(chunk[1])
        world_chunk = self.sim.world.get_chunk(cx, cy)
        district = world_chunk.get("district", {}) if isinstance(world_chunk.get("district"), dict) else {}
        descriptor = self.sim.world.overworld_descriptor(cx, cy)
        return {"cx": cx, "cy": cy, "district": district}, world_chunk, district, descriptor

    def _workplace_quality(self, prop, chunk, *, eid=None, occupation=None):
        if not isinstance(prop, dict):
            return 0.0
        chunk_context, _world_chunk, _district, _descriptor = self._chunk_context(chunk)
        if chunk_context is None:
            return 0.0
        archetype = _property_archetype(prop)
        if not archetype:
            return 0.0
        profile = chunk_economy_profile(self.sim, chunk_context)
        category = _location_building_category(
            archetype,
            storefront=bool(_property_is_storefront(prop)),
        )
        score = 1.8 + float(workplace_archetype_weight(profile, archetype))
        score += {
            "retail": 0.9,
            "hospitality": 0.85,
            "industrial": 0.8,
            "office": 0.7,
            "medical": 0.68,
            "transit": 0.72,
            "finance": 0.62,
            "general": 0.4,
        }.get(category, 0.15)
        if eid is not None:
            score += self._actor_workplace_skill_fit(eid, category, archetype=archetype)
        career = str(getattr(occupation, "career", "") or "").strip().lower().replace(" ", "_")
        if career and getattr(getattr(self.sim, "world", None), "careers_for_building", None) is not None:
            careers = {
                str(option).strip().lower().replace(" ", "_")
                for option in tuple(self.sim.world.careers_for_building(archetype) or ())
                if str(option).strip()
            }
            if career in careers:
                score += 0.85
        if _property_is_storefront(prop) or _property_access_level(prop) == "public":
            score += 0.18
        return max(0.0, score)

    def _life_score(self, eid, newcomer, *, home_prop=None, work_prop=None, target_chunk=None):
        if target_chunk is None:
            pos = self.sim.ecs.get(Position).get(eid)
            routine = self.sim.ecs.get(NPCRoutine).get(eid)
            occupation = self.sim.ecs.get(Occupation).get(eid)
            target_chunk = self._settlement_chunk(pos, routine=routine, occupation=occupation)
        if target_chunk is None:
            return 0.0
        occupation = self.sim.ecs.get(Occupation).get(eid)
        memory = self.sim.ecs.get(NPCMemory).get(eid)
        score = 0.0
        housing_score, _home_kind = self._housing_quality(home_prop)
        score += housing_score if home_prop is not None else -1.6
        score += self._workplace_quality(work_prop, target_chunk, eid=eid, occupation=occupation) if work_prop is not None else -1.8
        _chunk_context, _world_chunk, district, _descriptor = self._chunk_context(target_chunk)
        try:
            wealth = int(district.get("wealth", 5))
        except (TypeError, ValueError):
            wealth = 5
        try:
            security = int(district.get("security_level", 5))
        except (TypeError, ValueError):
            security = 5
        try:
            crime = int(district.get("crime_rate", 5))
        except (TypeError, ValueError):
            crime = 5
        score += (wealth * 0.24) + (security * 0.36) - (crime * 0.28)
        score += self._social_support_score(eid, target_chunk)
        score -= self._memory_pressure(eid, target_chunk=target_chunk, memory=memory)
        if home_prop is not None:
            score -= self._memory_pressure(eid, target_prop=home_prop, memory=memory) * 0.65
        if work_prop is not None:
            score -= self._memory_pressure(eid, target_prop=work_prop, memory=memory) * 0.5
        if home_prop is not None and work_prop is not None:
            commute = _anchor_distance(_property_focus_position(home_prop), _property_focus_position(work_prop))
            if commute < 999999:
                score -= min(2.8, float(commute) / 10.0)
        if str(getattr(newcomer, "housing_status", "") or "").strip().lower() in {"lodging", "shelter"}:
            score -= 0.22
        return float(score)

    def _remote_move_cost(self, eid, newcomer, current_chunk, target_chunk):
        if current_chunk == target_chunk:
            return 0.0
        cost = 1.7
        if str(getattr(newcomer, "employment_status", "") or "").strip().lower() != "employed":
            cost -= 0.45
        if str(getattr(newcomer, "housing_status", "") or "").strip().lower() in {"unhoused", "drifting", "shelter", "lodging"}:
            cost -= 0.4
        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        if needs is not None and float(getattr(needs, "safety", 75.0) or 75.0) < 45.0:
            cost -= 0.28
        if self._social_support_score(eid, target_chunk) > (self._social_support_score(eid, current_chunk) + 0.6):
            cost -= 0.35
        return max(0.55, float(cost))

    def _ensure_chunk_props_available(self, chunk):
        chunk = (int(chunk[0]), int(chunk[1]))
        if self._props_in_chunk(chunk):
            return True
        streamer = self._world_streaming_system()
        if streamer is None:
            return False
        streamer._ensure_chunk_properties(chunk[0], chunk[1])
        return bool(self._props_in_chunk(chunk))

    def _props_in_chunk(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return []
        key = (int(chunk[0]), int(chunk[1]))
        props = []
        seen = set()
        for record in tuple(getattr(self.sim, "chunk_property_records", {}).get(key, ()) or ()):
            prop_id = str((record or {}).get("id", "") or "").strip()
            if not prop_id:
                continue
            prop = self.sim.properties.get(prop_id)
            if not isinstance(prop, dict):
                continue
            seen.add(prop_id)
            props.append(prop)
        for prop_id, prop in tuple(getattr(self.sim, "properties", {}).items()):
            if prop_id in seen or not isinstance(prop, dict):
                continue
            if _property_chunk_key(self.sim, prop) == key:
                props.append(prop)
        return props

    def _home_available_slots(self, prop, *, moving_eids=()):
        capacity = _newcomer_home_capacity(prop)
        if capacity <= 0:
            return 0
        load = _newcomer_home_load(self.sim, prop)
        property_id = str((prop or {}).get("id", "") or "").strip()
        if property_id and moving_eids:
            routines = self.sim.ecs.get(NPCRoutine)
            for eid in {int(value) for value in tuple(moving_eids or ())}:
                routine = routines.get(eid)
                current = _home_property(self.sim, routine=routine)
                if current and str(current.get("id", "") or "").strip() == property_id:
                    load = max(0, load - 1)
        return max(0, int(capacity) - int(load))

    def _home_can_fit_members(self, prop, member_eids):
        member_eids = [int(value) for value in tuple(member_eids or ()) if value is not None]
        if not member_eids:
            return False
        return self._home_available_slots(prop, moving_eids=member_eids) >= len(member_eids)

    def _candidate_home_in_chunk(self, chunk, *, exclude_property_id="", required_capacity=1, moving_eids=()):
        best_prop = None
        best_kind = ""
        best_score = float("-inf")
        exclude_property_id = str(exclude_property_id or "").strip()
        required_capacity = max(1, int(required_capacity or 1))
        for prop in self._props_in_chunk(chunk):
            if exclude_property_id and str(prop.get("id", "") or "").strip() == exclude_property_id:
                continue
            home_kind = _newcomer_home_kind(prop)
            if not home_kind:
                continue
            if self._home_available_slots(prop, moving_eids=moving_eids) < required_capacity:
                continue
            score, _kind = self._housing_quality(prop)
            if score > best_score or (
                score == best_score
                and str(prop.get("id", "") or "") < str((best_prop or {}).get("id", "") or "")
            ):
                best_prop = prop
                best_kind = home_kind
                best_score = score
        if best_prop is None:
            return None, "", 0.0
        return best_prop, best_kind, float(best_score)

    def _home_candidate_with_pressure(self, eid, chunk, current_home, *, memory=None, required_capacity=1, moving_eids=()):
        current_home_id = str((current_home or {}).get("id", "") or "").strip()
        home_choice, home_kind, home_score = self._candidate_home_in_chunk(
            chunk,
            required_capacity=required_capacity,
            moving_eids=moving_eids,
        )
        if current_home is not None and str((home_choice or {}).get("id", "") or "").strip() == current_home_id:
            if self._memory_pressure(eid, target_prop=current_home, memory=memory) >= _NPC_LIFE_LOCAL_CONFLICT_MOVE_PRESSURE:
                alt_home, alt_kind, alt_score = self._candidate_home_in_chunk(
                    chunk,
                    exclude_property_id=current_home_id,
                    required_capacity=required_capacity,
                    moving_eids=moving_eids,
                )
                if alt_home is not None:
                    return alt_home, alt_kind, alt_score
        return home_choice, home_kind, home_score

    def _candidate_workplace_in_chunk(self, chunk, *, eid=None, occupation=None, exclude_property_id=""):
        best_prop = None
        best_score = float("-inf")
        exclude_property_id = str(exclude_property_id or "").strip()
        for prop in self._props_in_chunk(chunk):
            if exclude_property_id and str(prop.get("id", "") or "").strip() == exclude_property_id:
                continue
            capacity = _newcomer_work_capacity(self.sim, prop)
            if capacity <= 0 or _newcomer_work_load(self.sim, prop) >= capacity:
                continue
            score = self._workplace_quality(prop, chunk, eid=eid, occupation=occupation)
            if score > best_score or (
                score == best_score
                and str(prop.get("id", "") or "") < str((best_prop or {}).get("id", "") or "")
            ):
                best_prop = prop
                best_score = score
        if best_prop is None:
            return None, 0.0
        return best_prop, float(best_score)

    def _candidate_life_chunks(self, eid, current_chunk, social=None):
        if not isinstance(current_chunk, (tuple, list)) or len(current_chunk) < 2 or getattr(self.sim, "world", None) is None:
            return []
        current_chunk = (int(current_chunk[0]), int(current_chunk[1]))
        candidates = [current_chunk]
        seen = {current_chunk}
        social = social if isinstance(social, NPCSocial) else self.sim.ecs.get(NPCSocial).get(eid)
        for chunk in self._bond_destination_chunks(social):
            if chunk in seen:
                continue
            descriptor = self.sim.world.overworld_descriptor(chunk[0], chunk[1])
            district = self.sim.world.get_chunk(chunk[0], chunk[1]).get("district", {})
            area_type = str((district or {}).get("area_type", (descriptor or {}).get("area_type", "city")) or "").strip().lower()
            if area_type != "city":
                continue
            seen.add(chunk)
            candidates.append(chunk)
        prospect_chunks = []
        for prop in tuple(getattr(self.sim, "properties", {}).values()):
            chunk = _property_chunk_key(self.sim, prop)
            if chunk is None or chunk in seen:
                continue
            if max(abs(int(chunk[0]) - current_chunk[0]), abs(int(chunk[1]) - current_chunk[1])) > _NPC_LIFE_REMOTE_SEARCH_RADIUS:
                continue
            descriptor = self.sim.world.overworld_descriptor(int(chunk[0]), int(chunk[1]))
            if not _newcomer_home_kind(prop) and _newcomer_work_capacity(self.sim, prop) <= 0:
                continue
            district = self.sim.world.get_chunk(int(chunk[0]), int(chunk[1])).get("district", {})
            area_type = str((district or {}).get("area_type", (descriptor or {}).get("area_type", "city")) or "").strip().lower()
            if area_type != "city":
                continue
            try:
                wealth = int(district.get("wealth", 5))
            except (TypeError, ValueError):
                wealth = 5
            try:
                security = int(district.get("security_level", 5))
            except (TypeError, ValueError):
                security = 5
            try:
                crime = int(district.get("crime_rate", 5))
            except (TypeError, ValueError):
                crime = 5
            score = (wealth * 0.24) + (security * 0.5) - (crime * 0.32)
            if _newcomer_home_kind(prop):
                score += 0.8
            if _newcomer_work_capacity(self.sim, prop) > 0:
                score += 0.6
            prospect_chunks.append((float(score), (int(chunk[0]), int(chunk[1]))))
        prospect_chunks.sort(key=lambda row: (row[0], -abs(row[1][0] - current_chunk[0]), -abs(row[1][1] - current_chunk[1])), reverse=True)
        for _score, chunk in prospect_chunks:
            if chunk in seen:
                continue
            seen.add(chunk)
            candidates.append(chunk)
            if len(candidates) >= (1 + _NPC_LIFE_REMOTE_CANDIDATE_LIMIT):
                return candidates
        coarse = []
        for qy in range(current_chunk[1] - _NPC_LIFE_REMOTE_SEARCH_RADIUS, current_chunk[1] + _NPC_LIFE_REMOTE_SEARCH_RADIUS + 1):
            for qx in range(current_chunk[0] - _NPC_LIFE_REMOTE_SEARCH_RADIUS, current_chunk[0] + _NPC_LIFE_REMOTE_SEARCH_RADIUS + 1):
                chunk = (int(qx), int(qy))
                if chunk in seen:
                    continue
                descriptor = self.sim.world.overworld_descriptor(chunk[0], chunk[1])
                district = self.sim.world.get_chunk(chunk[0], chunk[1]).get("district", {})
                area_type = str((district or {}).get("area_type", (descriptor or {}).get("area_type", "city")) or "").strip().lower()
                if area_type != "city":
                    continue
                try:
                    wealth = int(district.get("wealth", 5))
                except (TypeError, ValueError):
                    wealth = 5
                try:
                    security = int(district.get("security_level", 5))
                except (TypeError, ValueError):
                    security = 5
                try:
                    crime = int(district.get("crime_rate", 5))
                except (TypeError, ValueError):
                    crime = 5
                coarse_score = (wealth * 0.28) + (security * 0.48) - (crime * 0.34)
                if str((descriptor or {}).get("path", "") or "").strip().lower() in {"road", "freeway"}:
                    coarse_score += 0.3
                coarse.append((float(coarse_score), chunk))
        coarse.sort(key=lambda row: (row[0], -abs(row[1][0] - current_chunk[0]), -abs(row[1][1] - current_chunk[1])), reverse=True)
        for _score, chunk in coarse:
            if chunk in seen:
                continue
            seen.add(chunk)
            candidates.append(chunk)
            if len(candidates) >= (1 + _NPC_LIFE_REMOTE_CANDIDATE_LIMIT):
                break
        return candidates

    def _ensure_actor_settlement(self, eid):
        newcomer = self.sim.ecs.get(NPCSettlement).get(eid)
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None:
            return newcomer
        occupation = self.sim.ecs.get(Occupation).get(eid)
        routine = _ensure_npc_routine(self.sim, eid)
        home_prop = _home_property(self.sim, routine=routine)
        work_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)
        chunk = self._settlement_chunk(pos, routine=routine, occupation=occupation)
        if newcomer is None:
            home_kind = _newcomer_home_kind(home_prop) or ("housing" if home_prop is not None else "unhoused")
            newcomer = NPCSettlement(
                arrived_tick=int(getattr(self.sim, "tick", 0)),
                origin=self._settlement_label(chunk),
                phase="settled" if home_prop and work_prop else ("settling" if home_prop else "arriving"),
                housing_status=home_kind,
                employment_status="employed" if work_prop is not None else "unemployed",
                home_property_id=str((home_prop or {}).get("id", "") or "").strip(),
                work_property_id=str((work_prop or {}).get("id", "") or "").strip(),
                last_housing_tick=int(getattr(self.sim, "tick", 0)) - _NEWCOMER_HOME_RETRY_TICKS,
                last_job_tick=int(getattr(self.sim, "tick", 0)) - _NEWCOMER_JOB_RETRY_TICKS,
                last_social_tick=int(getattr(self.sim, "tick", 0)) - _NEWCOMER_SOCIAL_RETRY_TICKS,
                last_life_tick=int(getattr(self.sim, "tick", 0)) - _NPC_LIFE_REVIEW_TICKS,
                last_move_tick=int(getattr(self.sim, "tick", 0)) - _NPC_LIFE_MOVE_COOLDOWN_TICKS,
                drift_preferred=str(getattr(occupation, "career", "") or "").strip().lower() == "drifter",
                life_goal="holding_steady",
            )
            self.sim.ecs.add(eid, newcomer)
        else:
            if not hasattr(newcomer, "last_life_tick"):
                newcomer.last_life_tick = int(getattr(self.sim, "tick", 0)) - _NPC_LIFE_REVIEW_TICKS
            if not hasattr(newcomer, "last_move_tick"):
                newcomer.last_move_tick = int(getattr(self.sim, "tick", 0)) - _NPC_LIFE_MOVE_COOLDOWN_TICKS
            if not hasattr(newcomer, "life_goal"):
                newcomer.life_goal = "holding_steady"
            if not str(getattr(newcomer, "origin", "") or "").strip():
                newcomer.origin = self._settlement_label(chunk)
        self._refresh_status(eid, newcomer)
        return newcomer

    def _backfill_resident_settlements(self):
        current_tick = int(getattr(self.sim, "tick", 0))
        if current_tick - int(self._last_backfill_tick) < _NPC_SETTLEMENT_BACKFILL_INTERVAL_TICKS:
            return
        self._last_backfill_tick = current_tick
        candidates = [
            int(eid)
            for eid in tuple(self.sim.ecs.get(AI).keys())
            if self._eligible_life_actor(eid) and self._in_active_settlement_scope(eid)
        ]
        if not candidates:
            self._backfill_cursor = 0
            return
        candidates.sort()
        budget = max(1, int(_NPC_SETTLEMENT_MAX_BACKFILL_PER_UPDATE))
        start = int(self._backfill_cursor) % len(candidates)
        ordered = candidates[start:] + candidates[:start]
        self._backfill_cursor = (start + budget) % len(candidates)
        for eid in ordered[:budget]:
            self._ensure_actor_settlement(eid)

    def _housing_upgrade_worthwhile(self, newcomer, current_prop, candidate_prop, candidate_kind, candidate_score):
        if candidate_prop is None:
            return False
        current_score, current_kind = self._housing_quality(current_prop)
        if current_prop is None:
            return True
        if current_kind in {"lodging", "shelter"} and candidate_kind == "housing":
            return True
        return float(candidate_score) >= float(current_score) + 0.85

    def _home_move_worthwhile(self, eid, current_prop, candidate_prop, candidate_kind, candidate_score, *, memory=None):
        if candidate_prop is None:
            return False
        if self._housing_upgrade_worthwhile(None, current_prop, candidate_prop, candidate_kind, candidate_score):
            return True
        current_score, _current_kind = self._housing_quality(current_prop)
        if current_prop is None:
            return True
        if str(current_prop.get("id", "") or "").strip() == str(candidate_prop.get("id", "") or "").strip():
            return False
        conflict_pressure = self._memory_pressure(eid, target_prop=current_prop, memory=memory)
        if conflict_pressure < _NPC_LIFE_LOCAL_CONFLICT_MOVE_PRESSURE:
            return False
        return float(candidate_score) >= float(current_score) - 0.25

    def _workplace_upgrade_worthwhile(self, eid, current_prop, candidate_prop, current_score, candidate_score, *, memory=None):
        if candidate_prop is None:
            return False
        if current_prop is None:
            return True
        if str(current_prop.get("id", "") or "").strip() == str(candidate_prop.get("id", "") or "").strip():
            return False
        current_category = _location_building_category(
            _property_archetype(current_prop),
            storefront=bool(_property_is_storefront(current_prop)),
        )
        candidate_category = _location_building_category(
            _property_archetype(candidate_prop),
            storefront=bool(_property_is_storefront(candidate_prop)),
        )
        if float(candidate_score) >= float(current_score) + _NPC_LIFE_LOCAL_JOB_SWITCH_DELTA:
            return True
        conflict_pressure = self._memory_pressure(eid, target_prop=current_prop, memory=memory)
        if conflict_pressure >= _NPC_LIFE_LOCAL_CONFLICT_MOVE_PRESSURE and float(candidate_score) >= float(current_score) - 0.15:
            return True
        if current_category == "transit" and candidate_category in {"industrial", "retail", "office", "medical"} and float(candidate_score) >= float(current_score) + 0.35:
            return True
        if current_category in {"lodging", "hospitality", "general"} and candidate_category == "industrial" and float(candidate_score) >= float(current_score) + 0.35:
            return True
        return False

    def _clear_work_assignment(self, eid):
        occupation = self.sim.ecs.get(Occupation).get(eid)
        routine = _ensure_npc_routine(self.sim, eid)
        if occupation is not None:
            occupation.workplace = None
            occupation.shift_start = None
            occupation.shift_end = None
            if str(getattr(occupation, "career", "") or "").strip().lower() not in {"resident", "lodger", "drifter"}:
                occupation.career = "unemployed"
        routine.work = None

    def _set_entity_position(self, eid, destination):
        if not isinstance(destination, (tuple, list)) or len(destination) < 3:
            return False
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None:
            return False
        nx, ny, nz = int(destination[0]), int(destination[1]), int(destination[2])
        self.sim.tilemap.move_entity(
            eid,
            oldx=int(pos.x),
            oldy=int(pos.y),
            oldz=int(pos.z),
            newx=nx,
            newy=ny,
            newz=nz,
        )
        pos.x = nx
        pos.y = ny
        pos.z = nz
        return True

    def _assign_household_home(self, member_eids, prop, home_kind, *, current_tick=None):
        member_eids = [int(value) for value in tuple(member_eids or ()) if value is not None]
        if not member_eids or not self._home_can_fit_members(prop, member_eids):
            return False
        current_tick = int(getattr(self.sim, "tick", 0) if current_tick is None else current_tick)
        for member_eid in member_eids:
            member_newcomer = self._ensure_actor_settlement(member_eid)
            if member_newcomer is None or not self._assign_home(member_eid, member_newcomer, prop, home_kind):
                return False
            member_newcomer.last_housing_tick = current_tick
            member_newcomer.last_life_tick = current_tick
            member_newcomer.life_goal = "holding_steady"
            self._refresh_status(member_eid, member_newcomer)
        return True

    def _relocate_actor_to_chunk(
        self,
        eid,
        newcomer,
        current_chunk,
        target_chunk,
        home_prop,
        home_kind,
        work_prop,
        *,
        unload_target_if_offscreen=True,
    ):
        current_tick = int(getattr(self.sim, "tick", 0))
        home_anchor = _property_focus_position(home_prop)
        work_anchor = _property_focus_position(work_prop) if isinstance(work_prop, dict) else None
        if home_anchor is None:
            return False
        routine = _ensure_npc_routine(self.sim, eid)
        old_chunk = current_chunk if isinstance(current_chunk, (tuple, list)) and len(current_chunk) >= 2 else None
        arrival_tiles = _adjacent_street_tiles(self.sim, home_anchor)
        arrival = arrival_tiles[0] if arrival_tiles else home_anchor
        if not self._set_entity_position(eid, arrival):
            return False
        target_key = (int(target_chunk[0]), int(target_chunk[1]))
        tracker = getattr(self.sim, "track_population_entity", None)
        if callable(tracker):
            tracker(eid, chunk=target_key)
        if work_prop is None:
            self._clear_work_assignment(eid)
        self._assign_home(eid, newcomer, home_prop, home_kind)
        if work_prop is not None:
            self._assign_workplace(eid, newcomer, work_prop)
        else:
            routine.work = None
        routine.home = home_anchor
        if work_anchor is not None:
            routine.work = work_anchor
        newcomer.origin = self._settlement_label(target_key)
        newcomer.arrived_tick = current_tick
        newcomer.phase = "settled"
        newcomer.last_move_tick = current_tick
        newcomer.last_life_tick = current_tick
        newcomer.life_goal = "holding_steady"
        self._refresh_status(eid, newcomer)
        if unload_target_if_offscreen and not self._chunk_loaded(target_key):
            unload_chunk_state(self.sim, target_key)
        return True

    def _relocate_household_to_chunk(self, eid, newcomer, target_chunk, home_prop, home_kind, work_prop, household):
        member_eids = [int(eid)] + [int(row["eid"]) for row in tuple(household or ())]
        if not self._home_can_fit_members(home_prop, member_eids):
            return False
        if not self._ensure_chunk_props_available(target_chunk):
            return False
        positions = self.sim.ecs.get(Position)
        occupations = self.sim.ecs.get(Occupation)
        for member_eid in member_eids:
            member_pos = positions.get(member_eid)
            if member_pos is None:
                return False
            member_newcomer = newcomer if int(member_eid) == int(eid) else self._ensure_actor_settlement(member_eid)
            member_occupation = occupations.get(member_eid)
            member_routine = _ensure_npc_routine(self.sim, member_eid)
            member_chunk = self._settlement_chunk(member_pos, routine=member_routine, occupation=member_occupation)
            member_work = work_prop if int(member_eid) == int(eid) else None
            if not self._relocate_actor_to_chunk(
                member_eid,
                member_newcomer,
                member_chunk,
                target_chunk,
                home_prop,
                home_kind,
                member_work,
                unload_target_if_offscreen=False,
            ):
                return False
        target_key = (int(target_chunk[0]), int(target_chunk[1]))
        if not self._chunk_loaded(target_key):
            unload_chunk_state(self.sim, target_key)
        return True

    def _consider_life_upgrade(self, eid, newcomer):
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None or self._player_near_actor(pos):
            return
        current_tick = int(getattr(self.sim, "tick", 0))
        if current_tick - int(getattr(newcomer, "last_life_tick", 0) or 0) < _NPC_LIFE_REVIEW_TICKS:
            return
        newcomer.last_life_tick = current_tick
        occupation = self.sim.ecs.get(Occupation).get(eid)
        routine = _ensure_npc_routine(self.sim, eid)
        social = self.sim.ecs.get(NPCSocial).get(eid)
        memory = self.sim.ecs.get(NPCMemory).get(eid)
        current_chunk = self._settlement_chunk(pos, routine=routine, occupation=occupation)
        if current_chunk is None:
            return
        current_home = _home_property(self.sim, routine=routine)
        current_work = _workplace_property(self.sim, occupation=occupation, routine=routine)
        household = self._household_cohort(eid, home_prop=current_home)
        household_eids = [int(eid)] + [int(row["eid"]) for row in tuple(household or ())]
        household_can_relocate = bool(household) and all(bool(row.get("can_relocate", False)) for row in household)
        household_split_penalty = self._household_split_penalty(eid, household)
        portable_household_support = (
            self._portable_household_support(eid, household, relocatable_only=True)
            if household_can_relocate else 0.0
        )
        current_score = self._life_score(eid, newcomer, home_prop=current_home, work_prop=current_work, target_chunk=current_chunk)
        solo_home_choice, solo_home_kind, solo_home_score = self._home_candidate_with_pressure(
            eid,
            current_chunk,
            current_home,
            memory=memory,
        )
        home_choice = solo_home_choice
        home_kind = solo_home_kind
        home_score = solo_home_score
        home_choice_is_group = False
        if household:
            group_home_choice, group_home_kind, group_home_score = self._home_candidate_with_pressure(
                eid,
                current_chunk,
                current_home,
                memory=memory,
                required_capacity=len(household_eids),
                moving_eids=household_eids,
            )
            if group_home_choice is not None:
                home_choice = group_home_choice
                home_kind = group_home_kind
                home_score = group_home_score
                home_choice_is_group = True
            elif current_home is not None and self._memory_pressure(eid, target_prop=current_home, memory=memory) < (
                _NPC_LIFE_LOCAL_CONFLICT_MOVE_PRESSURE + household_split_penalty
            ):
                home_choice = None
                home_kind = ""
                home_score = 0.0
        work_choice, work_score = self._candidate_workplace_in_chunk(current_chunk, eid=eid, occupation=occupation)
        current_home_id = str((current_home or {}).get("id", "") or "").strip()
        current_work_id = str((current_work or {}).get("id", "") or "").strip()
        if current_work is not None and str((work_choice or {}).get("id", "") or "").strip() == current_work_id:
            if self._memory_pressure(eid, target_prop=current_work, memory=memory) >= _NPC_LIFE_LOCAL_CONFLICT_MOVE_PRESSURE:
                alt_work, alt_work_score = self._candidate_workplace_in_chunk(
                    current_chunk,
                    eid=eid,
                    occupation=occupation,
                    exclude_property_id=current_work_id,
                )
                if alt_work is not None:
                    work_choice, work_score = alt_work, alt_work_score
        current_work_score = self._workplace_quality(current_work, current_chunk, eid=eid, occupation=occupation) if current_work is not None else 0.0
        local_changed = False
        if self._home_move_worthwhile(eid, current_home, home_choice, home_kind, home_score, memory=memory):
            if home_choice_is_group and self._assign_household_home(household_eids, home_choice, home_kind, current_tick=current_tick):
                local_changed = True
            elif self._assign_home(eid, newcomer, home_choice, home_kind):
                newcomer.last_housing_tick = current_tick
                local_changed = True
        if self._workplace_upgrade_worthwhile(eid, current_work, work_choice, current_work_score, work_score, memory=memory):
            self._assign_workplace(eid, newcomer, work_choice)
            newcomer.last_job_tick = current_tick
            local_changed = True
        if local_changed:
            current_home = _home_property(self.sim, routine=routine)
            current_work = _workplace_property(self.sim, occupation=occupation, routine=routine)
            current_chunk = self._settlement_chunk(pos, routine=routine, occupation=occupation)
            current_score = self._life_score(eid, newcomer, home_prop=current_home, work_prop=current_work, target_chunk=current_chunk)
            newcomer.life_goal = "holding_steady"
            current_work_score = self._workplace_quality(current_work, current_chunk, eid=eid, occupation=occupation) if current_work is not None else 0.0
        district = self.sim.world.get_chunk(int(current_chunk[0]), int(current_chunk[1])).get("district", {}) if getattr(self.sim, "world", None) is not None else {}
        try:
            security = int(district.get("security_level", 5))
        except (TypeError, ValueError):
            security = 5
        try:
            crime = int(district.get("crime_rate", 5))
        except (TypeError, ValueError):
            crime = 5
        remote_trigger = (
            str(getattr(newcomer, "employment_status", "") or "").strip().lower() != "employed"
            or str(getattr(newcomer, "housing_status", "") or "").strip().lower() in {"unhoused", "drifting", "lodging", "shelter"}
            or security <= 3
            or crime >= 7
            or self._social_support_score(eid, current_chunk, social=social) < 0.45
            or self._memory_pressure(eid, target_chunk=current_chunk, memory=memory) >= 1.1
            or self._memory_pressure(eid, target_prop=current_home, memory=memory) >= 1.1
            or self._memory_pressure(eid, target_prop=current_work, memory=memory) >= 1.1
        )
        if not remote_trigger:
            newcomer.life_goal = "holding_steady"
            return
        if current_tick - int(getattr(newcomer, "last_move_tick", 0) or 0) < _NPC_LIFE_MOVE_COOLDOWN_TICKS:
            newcomer.life_goal = "holding_steady"
            return
        best = None
        materialized = set()
        for chunk in self._candidate_life_chunks(eid, current_chunk, social=social):
            if chunk == current_chunk:
                continue
            if not self._chunk_loaded(chunk):
                materialized.add((int(chunk[0]), int(chunk[1])))
            if not self._ensure_chunk_props_available(chunk):
                continue
            transit_link = self._transit_link_profile(current_chunk, chunk)
            if bool(transit_link.get("required")) and not bool(transit_link.get("connected")):
                continue
            household_move = False
            if household_can_relocate:
                group_home_prop, group_home_kind, _group_home_score = self._candidate_home_in_chunk(
                    chunk,
                    required_capacity=len(household_eids),
                    moving_eids=household_eids,
                )
                if group_home_prop is not None:
                    home_prop = group_home_prop
                    remote_home_kind = group_home_kind
                    household_move = True
                else:
                    home_prop, remote_home_kind, _remote_home_score = self._candidate_home_in_chunk(chunk)
            else:
                home_prop, remote_home_kind, _remote_home_score = self._candidate_home_in_chunk(chunk)
            work_prop, _remote_work_score = self._candidate_workplace_in_chunk(chunk, occupation=occupation)
            if home_prop is None or work_prop is None:
                continue
            candidate_score = self._life_score(
                eid,
                newcomer,
                home_prop=home_prop,
                work_prop=work_prop,
                target_chunk=chunk,
            ) - self._remote_move_cost(eid, newcomer, current_chunk, chunk)
            candidate_score += float(transit_link.get("score_bonus", 0.0) or 0.0)
            if household_move:
                candidate_score += portable_household_support
            if best is None or candidate_score > best["score"]:
                best = {
                    "chunk": (int(chunk[0]), int(chunk[1])),
                    "home_prop": home_prop,
                    "home_kind": remote_home_kind,
                    "work_prop": work_prop,
                    "score": float(candidate_score),
                    "household_move": bool(household_move),
                    "transit_service": str(transit_link.get("service", "") or "").strip().lower(),
                }
        for chunk in tuple(materialized):
            if best is not None and chunk == best["chunk"]:
                continue
            unload_chunk_state(self.sim, chunk)
        if best is None or float(best["score"]) < (float(current_score) + _NPC_LIFE_REMOTE_MOVE_DELTA):
            if security <= 3 or crime >= 7:
                newcomer.life_goal = "seeking_safer_ground"
            elif str(getattr(newcomer, "employment_status", "") or "").strip().lower() != "employed":
                newcomer.life_goal = "seeking_work"
            else:
                newcomer.life_goal = "holding_steady"
            return
        target_chunk = best["chunk"]
        support_delta = self._social_support_score(eid, target_chunk, social=social) - self._social_support_score(eid, current_chunk, social=social)
        if support_delta > 0.7:
            newcomer.life_goal = "relocating_for_family"
        elif security <= 3 or crime >= 7:
            newcomer.life_goal = "relocating_for_safety"
        else:
            newcomer.life_goal = "relocating_for_work"
        relocated = False
        if bool(best.get("household_move")):
            relocated = self._relocate_household_to_chunk(
                eid,
                newcomer,
                target_chunk,
                best["home_prop"],
                best["home_kind"],
                best["work_prop"],
                household,
            )
        if not relocated:
            relocated = self._relocate_actor_to_chunk(
                eid,
                newcomer,
                current_chunk,
                target_chunk,
                best["home_prop"],
                best["home_kind"],
                best["work_prop"],
            )
        if relocated:
            newcomer.last_move_tick = current_tick
            newcomer.last_life_tick = current_tick
            newcomer.life_goal = "holding_steady"

    def _active_chunk_coord(self):
        coord = getattr(self.sim, "active_chunk_coord", None)
        if not isinstance(coord, (tuple, list)) or len(coord) != 2:
            return None
        try:
            return (int(coord[0]), int(coord[1]))
        except (TypeError, ValueError):
            return None

    def _local_newcomer_count(self, chunk):
        return _live_newcomer_count_in_chunk(self.sim, chunk)

    def _arrival_source_candidates(self, chunk):
        candidates = []
        for prop in self.sim.properties.values():
            if not isinstance(prop, dict):
                continue
            try:
                if self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))) != chunk:
                    continue
            except (TypeError, ValueError):
                continue
            archetype = _property_archetype(prop)
            category = _location_building_category(
                archetype,
                storefront=bool(_property_is_storefront(prop)),
            )
            weight = 0.0
            if category == "transit":
                weight += 3.2
            elif category in {"hospitality", "retail"}:
                weight += 2.4
            elif category in {"industrial", "office", "medical"}:
                weight += 1.5
            elif _newcomer_home_kind(prop):
                weight += 1.1
            if _property_access_level(prop) == "public":
                weight += 0.5
            if weight <= 0.0:
                continue
            anchor = _property_focus_position(prop)
            if not anchor:
                continue
            street_tiles = _adjacent_street_tiles(self.sim, anchor)
            if not street_tiles:
                continue
            candidates.append((prop, street_tiles, weight))
        return candidates

    def _maybe_spawn_newcomer(self):
        if int(self.sim.tick) < 600:
            return
        state = _newcomer_runtime_state(self.sim)
        if int(self.sim.tick) - int(state.get("last_spawn_tick", -10_000)) < _NEWCOMER_SPAWN_INTERVAL_TICKS:
            return
        chunk = self._active_chunk_coord()
        if chunk is None or self._local_newcomer_count(chunk) >= _NEWCOMER_LOCAL_CAP:
            return
        desc = self.sim.world.overworld_descriptor(chunk[0], chunk[1]) if getattr(self.sim, "world", None) is not None else {}
        if str((desc or {}).get("area_type", "") or "").strip().lower() != "city":
            return

        candidates = self._arrival_source_candidates(chunk)
        if not candidates:
            return
        props = [row[0] for row in candidates]
        weights = [row[2] for row in candidates]
        chosen_prop = self.rng.choices(props, weights=weights, k=1)[0]
        chosen_tiles = next((row[1] for row in candidates if row[0].get("id") == chosen_prop.get("id")), ())
        if not chosen_tiles:
            return
        spawn_pos = chosen_tiles[self.rng.randrange(len(chosen_tiles))]
        spawn_persistent_newcomer(
            self.sim,
            spawn_pos,
            source_prop=chosen_prop,
            source=_property_archetype(chosen_prop),
        )
        state["last_spawn_tick"] = int(self.sim.tick)

    def _candidate_home(self, newcomer, pos):
        if newcomer.drift_preferred and int(self.sim.tick) - int(newcomer.arrived_tick) < _NEWCOMER_DRIFT_WINDOW_TICKS:
            return None, ""

        weighted = []
        try:
            search_props = self._props_in_chunk(self.sim.chunk_coords(int(pos.x), int(pos.y)))
        except (TypeError, ValueError):
            search_props = tuple(self.sim.properties.values())
        for prop in search_props:
            home_kind = _newcomer_home_kind(prop)
            if not home_kind:
                continue
            capacity = _newcomer_home_capacity(prop)
            if capacity <= 0 or _newcomer_home_load(self.sim, prop) >= capacity:
                continue
            distance = _newcomer_distance_to_property(pos, prop)
            if distance > 28:
                continue
            weight = {
                "housing": 4.0,
                "lodging": 2.8,
                "shelter": 2.2,
            }.get(home_kind, 1.0)
            weight = weight / max(1.0, 1.0 + (distance * 0.12))
            weighted.append(((prop, home_kind), weight))
        choice = _weighted_choice(self.rng, weighted)
        if not choice:
            return None, ""
        return choice[0], choice[1]

    def _candidate_workplace(self, pos, *, anchor=None):
        weighted = []
        probe = pos
        if isinstance(anchor, (tuple, list)) and len(anchor) >= 3:
            try:
                probe = Position(int(anchor[0]), int(anchor[1]), int(anchor[2]))
            except (TypeError, ValueError):
                probe = pos
        search_props = []
        seen = set()
        try:
            origin_chunk = self.sim.chunk_coords(int(probe.x), int(probe.y))
        except (AttributeError, TypeError, ValueError):
            origin_chunk = None
        if isinstance(origin_chunk, (tuple, list)) and len(origin_chunk) >= 2:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    chunk = (int(origin_chunk[0]) + dx, int(origin_chunk[1]) + dy)
                    for prop in self._props_in_chunk(chunk):
                        prop_id = str((prop or {}).get("id", "") or "").strip()
                        if not prop_id or prop_id in seen:
                            continue
                        seen.add(prop_id)
                        search_props.append(prop)
        if not search_props:
            search_props = tuple(self.sim.properties.values())
        for prop in search_props:
            capacity = _newcomer_work_capacity(self.sim, prop)
            if capacity <= 0 or _newcomer_work_load(self.sim, prop) >= capacity:
                continue
            distance = _newcomer_distance_to_property(probe, prop)
            if distance > 30:
                continue
            archetype = _property_archetype(prop)
            category = _location_building_category(
                archetype,
                storefront=bool(_property_is_storefront(prop)),
            )
            weight = {
                "hospitality": 3.1,
                "retail": 3.0,
                "industrial": 2.7,
                "office": 2.2,
                "medical": 2.1,
                "transit": 2.0,
                "finance": 1.6,
                "general": 1.4,
            }.get(category, 1.0)
            weight = weight / max(1.0, 1.0 + (distance * 0.1))
            prop_chunk = _property_chunk_key(self.sim, prop)
            if (
                isinstance(origin_chunk, (tuple, list))
                and len(origin_chunk) >= 2
                and isinstance(prop_chunk, (tuple, list))
                and len(prop_chunk) >= 2
            ):
                chunk_step = max(
                    abs(int(prop_chunk[0]) - int(origin_chunk[0])),
                    abs(int(prop_chunk[1]) - int(origin_chunk[1])),
                )
                weight = weight / max(1.0, 1.0 + (chunk_step * 0.35))
            weighted.append((prop, weight))
        return _weighted_choice(self.rng, weighted)

    def _assign_home(self, eid, newcomer, prop, home_kind):
        routine = _ensure_npc_routine(self.sim, eid)
        anchor = _property_focus_position(prop)
        if anchor is None:
            return False
        routine.home = anchor
        newcomer.home_property_id = str(prop.get("id", "") or "").strip()
        newcomer.housing_status = home_kind
        newcomer.phase = "settling" if home_kind == "housing" else "lodged"

        occupation = self.sim.ecs.get(Occupation).get(eid)
        if occupation and not isinstance(getattr(occupation, "workplace", None), dict):
            if home_kind == "housing":
                occupation.career = "resident"
            elif home_kind == "shelter":
                occupation.career = "shelter_guest"
            else:
                occupation.career = "lodger"
        return True

    def _assign_workplace(self, eid, newcomer, prop):
        archetype = _property_archetype(prop)
        if not archetype:
            return False
        occupation = self.sim.ecs.get(Occupation).get(eid)
        if occupation is None:
            occupation = Occupation(career="unemployed", workplace=None, shift_start=None, shift_end=None)
            self.sim.ecs.add(eid, occupation)
        role = "guard" if archetype in SECURITY_ARCHETYPES else "worker"
        rng = random.Random(f"{self.sim.seed}:settle-work:{eid}:{prop.get('id')}:{self.sim.tick}")
        try:
            chunk = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            chunk = None
        chunk_context = {"cx": int(chunk[0]), "cy": int(chunk[1]), "district": {}} if isinstance(chunk, (tuple, list)) and len(chunk) >= 2 else None
        economy_profile = chunk_economy_profile(self.sim, chunk_context)
        career = pick_career_for_workplace(
            self.sim.world,
            rng,
            archetype=archetype,
            economy_profile=economy_profile,
        )
        shift_window = _shift_window_for(archetype, role, rng)
        organization_eid = ensure_property_organization(self.sim, prop)
        occupation.workplace = {
            "property_id": prop.get("id"),
            "building_id": _property_metadata(prop).get("building_id"),
            "archetype": archetype,
            "organization_eid": organization_eid,
        }
        occupation.career = str(career or "worker").strip().lower().replace(" ", "_")
        occupation.shift_start = int(shift_window[0])
        occupation.shift_end = int(shift_window[1])
        routine = _ensure_npc_routine(self.sim, eid)
        routine.work = _property_focus_position(prop)
        newcomer.work_property_id = str(prop.get("id", "") or "").strip()
        newcomer.employment_status = "employed"
        ai = self.sim.ecs.get(AI).get(eid)
        if ai:
            ai.role = role
        sync_actor_organization_affiliations(self.sim, eid, occupation=occupation)
        return True

    def _seed_home_bonds(self, eid, newcomer, home_prop):
        property_id = str((home_prop or {}).get("id", "") or "").strip()
        if not property_id:
            return False
        bonded = False
        candidates = []
        for other_eid, routine in self.sim.ecs.get(NPCRoutine).items():
            if other_eid == eid:
                continue
            other_home = _home_property(self.sim, routine=routine)
            if not other_home or str(other_home.get("id", "") or "").strip() != property_id:
                continue
            candidates.append(int(other_eid))
        for other_eid in sorted(candidates)[:3]:
            rng = random.Random(f"{self.sim.seed}:newcomer-home:{property_id}:{min(eid, other_eid)}:{max(eid, other_eid)}")
            bonded = _bond_pair(
                self.sim,
                eid,
                other_eid,
                kind="friend",
                closeness=rng.uniform(0.38, 0.66),
                trust=rng.uniform(0.34, 0.62),
            ) or bonded
        return bonded

    def _seed_work_bonds(self, eid, newcomer, work_prop):
        property_id = str((work_prop or {}).get("id", "") or "").strip()
        if not property_id:
            return False
        bonded = False
        candidates = []
        for other_eid, occupation in self.sim.ecs.get(Occupation).items():
            if other_eid == eid:
                continue
            workplace = getattr(occupation, "workplace", None)
            if not isinstance(workplace, dict):
                continue
            if str(workplace.get("property_id", "") or "").strip() != property_id:
                continue
            candidates.append(int(other_eid))
        for other_eid in sorted(candidates)[:4]:
            rng = random.Random(f"{self.sim.seed}:newcomer-work:{property_id}:{min(eid, other_eid)}:{max(eid, other_eid)}")
            bonded = _bond_pair(
                self.sim,
                eid,
                other_eid,
                kind="coworker",
                closeness=rng.uniform(0.4, 0.68),
                trust=rng.uniform(0.38, 0.64),
            ) or bonded
        return bonded

    def _refresh_status(self, eid, newcomer):
        occupation = self.sim.ecs.get(Occupation).get(eid)
        routine = _ensure_npc_routine(self.sim, eid)
        home_prop = _home_property(self.sim, routine=routine)
        work_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)

        if home_prop:
            newcomer.home_property_id = str(home_prop.get("id", "") or "").strip()
            newcomer.housing_status = _newcomer_home_kind(home_prop) or "housing"
        else:
            newcomer.home_property_id = ""
            newcomer.housing_status = "drifting" if newcomer.drift_preferred else "unhoused"
            if occupation and not isinstance(getattr(occupation, "workplace", None), dict):
                occupation.career = "drifter" if newcomer.drift_preferred else "unemployed"

        if work_prop:
            newcomer.work_property_id = str(work_prop.get("id", "") or "").strip()
            newcomer.employment_status = "employed"
        else:
            newcomer.work_property_id = ""
            if occupation and isinstance(getattr(occupation, "workplace", None), dict):
                occupation.workplace = None
                occupation.shift_start = None
                occupation.shift_end = None
                occupation.career = "resident" if home_prop and newcomer.housing_status == "housing" else (
                    "lodger" if home_prop else ("drifter" if newcomer.drift_preferred else "unemployed")
                )
            newcomer.employment_status = "unemployed"

        bonded = False
        if int(self.sim.tick) - int(newcomer.last_social_tick) >= _NEWCOMER_SOCIAL_RETRY_TICKS:
            if home_prop:
                bonded = self._seed_home_bonds(eid, newcomer, home_prop) or bonded
            if work_prop:
                bonded = self._seed_work_bonds(eid, newcomer, work_prop) or bonded
            newcomer.last_social_tick = int(self.sim.tick)

        if home_prop and work_prop and bonded:
            newcomer.phase = "settled"
        elif home_prop and work_prop:
            newcomer.phase = "working"
        elif home_prop:
            newcomer.phase = "lodged" if newcomer.housing_status in {"lodging", "shelter"} else "settling"
        else:
            newcomer.phase = "drifting" if newcomer.drift_preferred else "arriving"

    def _update_newcomer(self, eid, newcomer):
        pos = self.sim.ecs.get(Position).get(eid)
        if not pos:
            return
        vitality = self.sim.ecs.get(Vitality).get(eid)
        if vitality and bool(getattr(vitality, "downed", False)):
            return

        routine = _ensure_npc_routine(self.sim, eid)
        occupation = self.sim.ecs.get(Occupation).get(eid)
        home_prop = _home_property(self.sim, routine=routine)
        work_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)

        housing_status = str(getattr(newcomer, "housing_status", "") or "").strip().lower()
        employment_status = str(getattr(newcomer, "employment_status", "") or "").strip().lower()
        is_unsettled = (housing_status in {"unhoused", "drifting"}) and employment_status != "employed"
        if is_unsettled and int(self.sim.tick) - int(newcomer.arrived_tick) >= _NEWCOMER_DRIFTER_TIMEOUT_TICKS:
            self.sim.remove_entity(eid)
            return

        if not home_prop and int(self.sim.tick) - int(newcomer.last_housing_tick) >= _NEWCOMER_HOME_RETRY_TICKS:
            newcomer.last_housing_tick = int(self.sim.tick)
            home_choice, home_kind = self._candidate_home(newcomer, pos)
            if home_choice is not None:
                self._assign_home(eid, newcomer, home_choice, home_kind)
                home_prop = home_choice
            elif occupation and not isinstance(getattr(occupation, "workplace", None), dict):
                occupation.career = "drifter" if newcomer.drift_preferred else "unemployed"

        if not work_prop and int(self.sim.tick) - int(newcomer.last_job_tick) >= _NEWCOMER_JOB_RETRY_TICKS:
            newcomer.last_job_tick = int(self.sim.tick)
            work_choice = self._candidate_workplace(pos, anchor=getattr(routine, "home", None))
            if work_choice is not None:
                self._assign_workplace(eid, newcomer, work_choice)

        self._refresh_status(eid, newcomer)

    def update(self):
        if int(self.sim.tick) % 30 != 0:
            return
        self._backfill_resident_settlements()
        self._maybe_spawn_newcomer()
        for eid, newcomer in self._settlement_worklist():
            self._update_newcomer(eid, newcomer)
            self._consider_life_upgrade(eid, newcomer)
