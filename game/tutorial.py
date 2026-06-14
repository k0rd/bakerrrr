from __future__ import annotations

import random
from dataclasses import dataclass

from engine.events import Event
from engine.systems import System
from engine.tilemap import Tile
from game.components import (
    AI,
    Collider,
    ContactLedger,
    CoreStats,
    CreatureIdentity,
    FinancialProfile,
    InsightStats,
    Inventory,
    MovementThrottle,
    NPCMemory,
    NPCNeeds,
    NPCSocial,
    NPCTraits,
    NPCWill,
    NoiseProfile,
    Occupation,
    Position,
    PropertyKnowledge,
    Render,
    SkillProfile,
    StatusEffects,
    VehicleState,
    Vitality,
)
from game.final_operation import prime_tutorial_final_operation
from game.player_config import (
    PLAYER_CONFIG_PATH,
    PLAYER_CONFIG_VERSION,
    default_player_config,
    load_player_config,
    mark_tutorial_run_seen,
    save_player_config,
    tutorial_requested_from_options,
)
from game.property_keys import ensure_actor_has_property_key, ensure_property_lock
from game.run_bootstrap import NormalRunBootstrapProfile, bootstrap_normal_run
from game.vehicles import roll_vehicle_profile, vehicle_metadata


TUTORIAL_PROFILE = NormalRunBootstrapProfile(
    profile_id="tutorial",
    objective_visible=True,
    bootstrap_player_opportunity_intel=True,
    vehicle_seed_chance=1.0,
    starter_melee_weapon_chance=1.0,
    starter_firearm_chance=0.0,
    starter_armor_chance=0.0,
    starter_melee_weapon_pool=("crowbar_club",),
    street_kit_variants=(("hydration_salts", 1),),
)

TUTORIAL_STAGES = (
    {
        "id": "movement",
        "gate": "movement",
        "hint": "Tutorial: move one tile. Arrows, WASD, HJKL, or numpad all work.",
    },
    {
        "id": "look",
        "gate": "look",
        "hint": "Tutorial: press x, move the look cursor, then Enter or x to inspect.",
    },
    {
        "id": "interact_targeting",
        "gate": "interact_targeting",
        "hint": "Tutorial: press ' to target a nearby fixture or door, then confirm.",
    },
    {
        "id": "talk_targeting",
        "gate": "talk_targeting",
        "hint": "Tutorial: press / and target your handler.",
    },
    {
        "id": "guide_dialogue",
        "gate": "guide_dialogue",
        "hint": "Tutorial: ask the handler what now.",
    },
    {
        "id": "operations_report",
        "gate": "operations_report",
        "hint": "Tutorial: press O for the operations report.",
    },
    {
        "id": "places_notebook",
        "gate": "places_notebook",
        "hint": "Tutorial: press Y for places you know.",
    },
    {
        "id": "people_notebook",
        "gate": "people_notebook",
        "hint": "Tutorial: press Tab from the places notebook to see people.",
    },
    {
        "id": "character_sheet",
        "gate": "character_sheet",
        "hint": "Tutorial: press + for the character sheet.",
    },
    {
        "id": "inventory",
        "gate": "inventory",
        "hint": "Tutorial: press i to open inventory. Use E to inspect and U to use/equip.",
    },
    {
        "id": "inventory_use",
        "gate": "inventory_use",
        "hint": "Tutorial: use or equip one item from inventory with U.",
    },
    {
        "id": "pickup",
        "gate": "pickup",
        "hint": "Tutorial: stand on the practice packet and press , to pick it up.",
    },
    {
        "id": "service_menu",
        "gate": "service_menu",
        "hint": "Tutorial: stand at the service surface and press .",
    },
    {
        "id": "trade",
        "gate": "trade",
        "hint": "Tutorial: open the shop counter and look at the buy/sell panel.",
    },
    {
        "id": "log_help",
        "gate": "log_help",
        "hint": "Tutorial: press L for the event log, or ? for help.",
    },
    {
        "id": "map",
        "gate": "map",
        "hint": "Tutorial: press X to open the map.",
    },
    {
        "id": "vehicle_travel",
        "gate": "vehicle_travel",
        "hint": "Tutorial: from a road tile, open the vehicle map and move once to travel a chunk.",
    },
    {
        "id": "vehicle_exit",
        "gate": "vehicle_exit",
        "hint": "Tutorial: press t on the map to return to local driving, then t again to get out.",
    },
    {
        "id": "cover",
        "gate": "cover",
        "hint": "Tutorial: press C near cover, or v to hop cover.",
    },
    {
        "id": "safe_aim",
        "gate": "safe_aim",
        "hint": "Tutorial: press F to open safe aim mode. Esc closes it.",
    },
    {
        "id": "final_retrieval",
        "gate": "final_retrieval",
        "hint": "Tutorial: recover the Training Retrieval Case from the marked locker.",
    },
    {
        "id": "complete",
        "gate": "tutorial_complete",
        "hint": "Tutorial complete.",
    },
)

TUTORIAL_STAGE_BY_ID = {row["id"]: dict(row) for row in TUTORIAL_STAGES}
TUTORIAL_GATE_ORDER = tuple(row["gate"] for row in TUTORIAL_STAGES)


@dataclass(frozen=True)
class TutorialBootstrapResult:
    player_eid: int
    guide_eid: int
    service_property_id: str
    shop_property_id: str
    final_property_id: str
    target_item_instance_id: str
    target_ground_item_id: str
    normal_bootstrap: object


def tutorial_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("tutorial")
    if not isinstance(state, dict):
        state = {}
        traits["tutorial"] = state
    state.setdefault("active", False)
    state.setdefault("stage_id", "movement")
    state.setdefault("completed_stages", [])
    state.setdefault("observed_gates", [])
    state.setdefault("hint", "")
    state.setdefault("current_hint", "")
    state.setdefault("guide_eid", None)
    state.setdefault("fixture_ids", {})
    state.setdefault("target_item_instance_id", "")
    state.setdefault("marker_position", None)
    state.setdefault("completed", False)
    return state


def is_tutorial_run(sim):
    traits = getattr(sim, "world_traits", None)
    state = traits.get("tutorial") if isinstance(traits, dict) else None
    return bool(isinstance(state, dict) and state.get("active"))


def tutorial_no_persistence(sim):
    traits = getattr(sim, "world_traits", None)
    rules = traits.get("rules", {}) if isinstance(traits, dict) else {}
    return bool(isinstance(rules, dict) and rules.get("tutorial_no_persistence"))


def current_tutorial_stage(sim):
    stage_id = str(tutorial_state(sim).get("stage_id", "movement") or "movement").strip().lower()
    return TUTORIAL_STAGE_BY_ID.get(stage_id) or TUTORIAL_STAGE_BY_ID["movement"]


def current_tutorial_hint(sim):
    state = tutorial_state(sim)
    hint = str(state.get("hint") or state.get("current_hint") or "").strip()
    if hint:
        return hint
    return str(current_tutorial_stage(sim).get("hint", "")).strip()


def tutorial_guide_line(sim):
    stage = current_tutorial_stage(sim)
    stage_id = str(stage.get("id", "movement"))
    lines = {
        "movement": "Ease into the block first. One clean step tells you how the street answers.",
        "look": "Now read the tile before touching it. Looking keeps you alive longer than guessing.",
        "interact_targeting": "Use the targeted interact key on a fixture. Pick the thing, then commit.",
        "talk_targeting": "Target people the same way. If there are two voices nearby, make the cursor choose.",
        "guide_dialogue": "Good. Keep using real actions; I will only point, not carry you.",
        "operations_report": "Open the operations report. It is the run's sober read on what matters.",
        "places_notebook": "Places are filed separately. Check the notebook so the city stops being a blur.",
        "people_notebook": "People get their own page. Names matter when favors, warnings, and grudges start moving.",
        "character_sheet": "Look at yourself next. The sheet is not just numbers; it is what the sim knows about you.",
        "inventory": "Open the bag. Inspect before you use things, especially when the world gets weird.",
        "inventory_use": "Use one thing from the bag. Water, salts, gear, whatever makes sense.",
        "pickup": "There is a practice packet on the ground. Stand on it and pick it up.",
        "service_menu": "Service surfaces use the dot key. Same key whether someone is attending or not.",
        "trade": "The shop counter opens the buy/sell panel. You do not have to buy to learn the surface.",
        "log_help": "The log catches what the HUD drops. Help is there when the key soup gets loud.",
        "map": "Open the map. The city is bigger than the block under your feet.",
        "vehicle_travel": "Travel once from the vehicle map. Local driving becomes chunk travel after you open the route map.",
        "vehicle_exit": "Now come back to local driving. Big-map travel still resolves into street-level trouble.",
        "cover": "Try cover. If it feels slow, that is the point: it buys angles, not magic.",
        "safe_aim": "Open aim mode. You are practicing pacing and target selection, not starting a real fight.",
        "final_retrieval": "Last step: recover the Training Retrieval Case from the marked locker. Picking it up finishes the run.",
        "complete": "That is the shape. The real city will be less polite.",
    }
    return lines.get(stage_id, current_tutorial_hint(sim))


def _set_stage_hint(sim):
    state = tutorial_state(sim)
    hint = str(current_tutorial_stage(sim).get("hint", "")).strip()
    state["hint"] = hint
    state["current_hint"] = hint
    return hint


def _append_chunk_property_record(sim, prop, archetype="tutorial"):
    if not isinstance(prop, dict):
        return
    try:
        x = int(prop.get("x", 0))
        y = int(prop.get("y", 0))
        z = int(prop.get("z", 0))
    except (TypeError, ValueError):
        return
    chunk_key = sim.chunk_coords(x, y)
    records = getattr(sim, "chunk_property_records", None)
    if not isinstance(records, dict):
        sim.chunk_property_records = {}
        records = sim.chunk_property_records
    if any(str(row.get("id", "")) == str(prop.get("id", "")) for row in records.setdefault(chunk_key, [])):
        return
    records[chunk_key].append({
        "id": prop.get("id"),
        "kind": prop.get("kind"),
        "x": x,
        "y": y,
        "z": z,
        "archetype": archetype,
        "building_id": None,
    })


def _make_walkable(sim, x, y, z=0, glyph="."):
    if sim.tilemap.in_bounds(int(x), int(y)):
        sim.tilemap.set_tile(int(x), int(y), Tile(walkable=True, transparent=True, glyph=str(glyph or ".")[:1]), z=int(z))


def _nearby_position(sim, anchor, dx, dy, z=0):
    x = int(anchor[0]) + int(dx)
    y = int(anchor[1]) + int(dy)
    _make_walkable(sim, x, y, z)
    return x, y, z


def _register_tutorial_property(sim, *, name, kind, pos, archetype, metadata=None, owner_tag="tutorial"):
    x, y, z = pos
    meta = {
        "archetype": archetype,
        "tutorial": True,
        "public": True,
        "chunk": sim.chunk_coords(int(x), int(y)),
    }
    if isinstance(metadata, dict):
        meta.update(metadata)
    prop_id = sim.register_property(
        name,
        kind,
        int(x),
        int(y),
        int(z),
        owner_tag=owner_tag,
        metadata=meta,
    )
    _append_chunk_property_record(sim, sim.properties.get(prop_id), archetype=archetype)
    return prop_id


def _spawn_tutorial_guide(sim, player_eid, pos):
    x, y, z = pos
    guide = sim.ecs.create()
    sim.ecs.add(guide, Position(int(x), int(y), int(z)))
    sim.ecs.add(guide, Render("G", color="npc_friendly", semantic_id="human", priority=2))
    sim.ecs.add(guide, Collider(blocks=True))
    sim.ecs.add(guide, AI("tutorial_guide"))
    sim.ecs.add(guide, MovementThrottle(default_cooldown=4))
    sim.ecs.add(guide, NoiseProfile(move_radius=4))
    sim.ecs.add(
        guide,
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name="handler",
            personal_name="Mara Vale",
            assigned_sex="female",
            gender_identity="woman",
            pronoun_set="she",
        ),
    )
    sim.ecs.add(guide, CoreStats(brawn=5, athleticism=5, dexterity=6, access=7, charm=7, common_sense=8))
    sim.ecs.add(guide, InsightStats(perception=7, charisma=7, streetwise=8))
    sim.ecs.add(guide, SkillProfile(ratings={"social": 7, "streetwise": 8, "security": 6}))
    sim.ecs.add(guide, NPCNeeds())
    sim.ecs.add(guide, NPCTraits(bravery=0.62, empathy=0.74, loyalty=0.7, discipline=0.82))
    social = NPCSocial()
    social.add_bond(player_eid, kind="contact", closeness=0.42, trust=0.58, protectiveness=0.18)
    sim.ecs.add(guide, social)
    sim.ecs.add(guide, NPCMemory())
    sim.ecs.add(guide, NPCWill())
    sim.ecs.add(guide, Occupation("handler"))
    sim.ecs.add(guide, FinancialProfile(bank_balance=0))
    sim.ecs.add(guide, Inventory(capacity=6))
    sim.ecs.add(guide, StatusEffects())
    sim.ecs.add(guide, Vitality(max_hp=90, recover_to_hp=30))
    sim.tilemap.add_entity(guide, int(x), int(y), int(z))

    ledger = sim.ecs.get(ContactLedger).get(player_eid)
    if ledger is not None:
        ledger.remember_person(
            guide,
            source_eid=guide,
            relation_kind="contact",
            standing=0.56,
            tick=int(getattr(sim, "tick", 0)),
            benefits={"known_name"},
            met_directly=True,
            first_met_tick=int(getattr(sim, "tick", 0)),
            last_met_tick=int(getattr(sim, "tick", 0)),
            identity_snapshot={
                "personal_name": "Mara Vale",
                "common_name": "handler",
                "gender_identity": "woman",
                "creature_type": "human",
                "taxonomy_class": "hominid",
            },
        )
        ledger.remember_person_episode(
            guide,
            kind="met_tutorial_handler",
            tick=int(getattr(sim, "tick", 0)),
            valence="neutral",
            summary="Mara Vale walked you through the training block.",
            source_topic="tutorial",
        )
    return guide


def _remember_tutorial_places(sim, player_eid, *property_ids):
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid)
    ledger = sim.ecs.get(ContactLedger).get(player_eid)
    for property_id in property_ids:
        prop = sim.properties.get(property_id)
        if not isinstance(prop, dict):
            continue
        if knowledge is not None:
            knowledge.remember(
                property_id,
                owner_eid=prop.get("owner_eid"),
                owner_tag=prop.get("owner_tag"),
                confidence=1.0,
                tick=int(getattr(sim, "tick", 0)),
                anchored=True,
                anchor_kind="tutorial",
            )
            knowledge.unhide(property_id)
        if ledger is not None:
            ledger.remember(
                property_id,
                source_eid=player_eid,
                contact_kind="tutorial",
                standing=0.65,
                tick=int(getattr(sim, "tick", 0)),
                benefits={"known_name", "location"},
            )


def _ensure_tutorial_vehicle(sim, player_eid, pos, rng):
    vx, vy, vz = _nearby_position(sim, pos, -2, 1, pos[2])
    _make_walkable(sim, pos[0], pos[1], pos[2], glyph="=")
    profile = roll_vehicle_profile(rng, quality="used")
    profile["fuel"] = max(18, int(profile.get("fuel_capacity", profile.get("fuel", 60)) or 60))
    vehicle_name = f"Tutorial {profile.get('make', 'Street')} {profile.get('model', 'Runner')}"
    vehicle_id_token = f"veh:tutorial:{getattr(sim, 'seed', 0)}:{player_eid}"
    metadata = vehicle_metadata(
        profile,
        chunk=sim.chunk_coords(vx, vy),
        owner_tag="player",
        display_color="vehicle_player",
        locked=True,
        key_id=vehicle_id_token,
        key_label=vehicle_name,
        lock_tier=1,
    )
    metadata.update({
        "tutorial": True,
        "vehicle_id": vehicle_id_token,
        "site_services": ["vehicle_fetch"],
    })
    vehicle_id = sim.register_property(
        vehicle_name,
        "vehicle",
        vx,
        vy,
        vz,
        owner_eid=player_eid,
        owner_tag="player",
        metadata=metadata,
    )
    vehicle = sim.properties.get(vehicle_id)
    _append_chunk_property_record(sim, vehicle, archetype="vehicle")
    if isinstance(vehicle, dict):
        ensure_property_lock(vehicle, locked=True, key_label=vehicle_name, lock_tier=1)
        ensure_actor_has_property_key(sim, player_eid, vehicle, owner_tag="player")
    vehicle_state = sim.ecs.get(VehicleState).get(player_eid)
    if vehicle_state is not None:
        sim.move_property(vehicle_id, int(pos[0]), int(pos[1]), int(pos[2]))
        metadata["chunk"] = sim.chunk_coords(int(pos[0]), int(pos[1]))
        vehicle_state.set_active_vehicle(vehicle_id, tick=int(getattr(sim, "tick", 0)))
        vehicle_state.set_in_vehicle(True, tick=int(getattr(sim, "tick", 0)))
    return vehicle_id


def bootstrap_tutorial_run(sim, character_name, rng, gender_identity="nonbinary"):
    if not isinstance(rng, random.Random):
        rng = random.Random(str(rng))
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    rules = traits.setdefault("rules", {})
    if not isinstance(rules, dict):
        rules = {}
        traits["rules"] = rules
    rules["tutorial_no_persistence"] = True
    rules["final_op_downed_fails_run"] = False

    normal = bootstrap_normal_run(
        sim,
        character_name,
        rng,
        gender_identity=gender_identity,
        profile=TUTORIAL_PROFILE,
    )
    player_eid = normal.player_eid
    pos = sim.ecs.get(Position).get(player_eid)
    if pos is None:
        raise ValueError("tutorial bootstrap requires a player position")
    anchor = (int(pos.x), int(pos.y), int(pos.z))
    for dx in range(-4, 5):
        for dy in range(-4, 5):
            _make_walkable(sim, anchor[0] + dx, anchor[1] + dy, anchor[2])

    guide_pos = _nearby_position(sim, anchor, 1, 0, anchor[2])
    service_pos = _nearby_position(sim, anchor, 0, 2, anchor[2])
    shop_pos = _nearby_position(sim, anchor, 2, 2, anchor[2])
    cover_pos = _nearby_position(sim, anchor, -1, 1, anchor[2])
    packet_pos = _nearby_position(sim, anchor, -1, 0, anchor[2])
    locker_pos = _nearby_position(sim, anchor, 3, 0, anchor[2])

    guide_eid = _spawn_tutorial_guide(sim, player_eid, guide_pos)
    service_id = _register_tutorial_property(
        sim,
        name="Tutorial Service Surface",
        kind="fixture",
        pos=service_pos,
        archetype="tutorial_service_surface",
        metadata={
            "display_glyph": "s",
            "display_color": "property_service",
            "site_services": ["banking"],
            "finance_services": ["banking"],
            "interaction_role": "service_terminal",
            "storefront_mode": "automated",
        },
    )
    shop_id = _register_tutorial_property(
        sim,
        name="Tutorial Shop Counter",
        kind="building",
        pos=shop_pos,
        archetype="general_store",
        metadata={
            "display_glyph": "t",
            "display_color": "property_store",
            "is_storefront": True,
            "storefront_mode": "automated",
            "site_services": ["trade"],
            "trade_tags": ["food", "drink", "medical", "tool"],
            "public": True,
        },
    )
    cover_id = _register_tutorial_property(
        sim,
        name="Practice Cover Barrier",
        kind="fixture",
        pos=cover_pos,
        archetype="tutorial_cover",
        metadata={
            "display_glyph": "#",
            "display_color": "property_fixture",
            "cover_value": 0.45,
            "cover_kind": "low",
            "public": True,
        },
    )
    locker_id = _register_tutorial_property(
        sim,
        name="Tutorial Retrieval Locker",
        kind="asset",
        pos=locker_pos,
        archetype="tutorial_retrieval_locker",
        metadata={
            "display_glyph": "!",
            "display_color": "objective",
            "interaction_role": "cache_target",
            "fixture_kind": "cache",
            "container_kind": "cache",
            "container_label": "Training Locker",
            "public": True,
        },
    )

    packet_id = sim.register_ground_item(
        "city_pass_token",
        packet_pos[0],
        packet_pos[1],
        packet_pos[2],
        quantity=1,
        owner_tag="public",
        metadata={
            "display_name": "Practice Packet",
            "tutorial": True,
            "claim_class": "public_free",
            "source_context": "tutorial",
        },
    )
    del packet_id
    target_instance_id = sim.new_item_instance_id()
    target_ground_id = sim.register_ground_item(
        "access_badge",
        locker_pos[0],
        locker_pos[1],
        locker_pos[2],
        quantity=1,
        owner_tag="public",
        instance_id=target_instance_id,
        metadata={
            "display_name": "Training Retrieval Case",
            "tutorial": True,
            "claim_class": "public_free",
            "source_context": "tutorial",
        },
    )
    _ensure_tutorial_vehicle(sim, player_eid, anchor, rng)
    _remember_tutorial_places(sim, player_eid, service_id, shop_id, cover_id, locker_id)

    final_state = prime_tutorial_final_operation(
        sim,
        player_eid,
        target_property_id=locker_id,
        target_item_instance_id=target_instance_id,
        target_ground_item_id=target_ground_id,
        target_item_id="access_badge",
        target_item_name="Training Retrieval Case",
        target_label="tutorial block",
    )
    state = tutorial_state(sim)
    state.update({
        "active": True,
        "stage_id": "movement",
        "completed_stages": [],
        "observed_gates": [],
        "guide_eid": guide_eid,
        "fixture_ids": {
            "service": service_id,
            "shop": shop_id,
            "cover": cover_id,
            "locker": locker_id,
        },
        "target_item_instance_id": target_instance_id,
        "target_ground_item_id": target_ground_id,
        "marker_position": {
            "x": int(locker_pos[0]),
            "y": int(locker_pos[1]),
            "z": int(locker_pos[2]),
        },
        "final_operation": dict(final_state or {}),
        "completed": False,
    })
    _set_stage_hint(sim)
    sim.log.add("Tutorial mode: this run is disposable and will not write a save or cross-run echo.")
    sim.log.add("Mara Vale waits beside the training block. Press / when the talk lesson comes up.")
    return TutorialBootstrapResult(
        player_eid=player_eid,
        guide_eid=guide_eid,
        service_property_id=service_id,
        shop_property_id=shop_id,
        final_property_id=locker_id,
        target_item_instance_id=target_instance_id,
        target_ground_item_id=target_ground_id,
        normal_bootstrap=normal,
    )


def record_tutorial_gate(sim, gate):
    gate = str(gate or "").strip().lower()
    if not gate:
        return False
    state = tutorial_state(sim)
    if not bool(state.get("active")):
        return False
    observed = list(state.get("observed_gates", ()) or ())
    if gate not in observed:
        observed.append(gate)
        state["observed_gates"] = observed
    return _advance_tutorial_if_ready(sim)


def _advance_tutorial_if_ready(sim):
    state = tutorial_state(sim)
    observed = set(str(gate).strip().lower() for gate in tuple(state.get("observed_gates", ()) or ()) if str(gate).strip())
    completed = list(state.get("completed_stages", ()) or ())
    changed = False
    while True:
        stage = current_tutorial_stage(sim)
        stage_id = str(stage.get("id", "movement"))
        gate = str(stage.get("gate", "")).strip().lower()
        if gate not in observed:
            break
        if stage_id not in completed:
            completed.append(stage_id)
        if stage_id == "complete":
            state["completed"] = True
            break
        next_stage_id = "complete"
        for idx, row in enumerate(TUTORIAL_STAGES):
            if str(row.get("id")) == stage_id:
                next_stage_id = str(TUTORIAL_STAGES[min(idx + 1, len(TUTORIAL_STAGES) - 1)].get("id"))
                break
        if next_stage_id == stage_id:
            break
        state["stage_id"] = next_stage_id
        changed = True
    state["completed_stages"] = completed
    _set_stage_hint(sim)
    if changed:
        sim.log.add(current_tutorial_hint(sim), channel="system", priority="low")
    return changed


class TutorialSystem(System):
    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.runs_while_paused = True
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("dialog_topic_request", self.on_dialog_topic_request)
        self.sim.events.subscribe("inventory_panel_toggled", self.on_inventory_panel_toggled)
        self.sim.events.subscribe("trade_panel_toggled", self.on_trade_panel_toggled)
        self.sim.events.subscribe("item_picked_up", self.on_item_picked_up)
        self.sim.events.subscribe("item_used", self.on_item_used)
        self.sim.events.subscribe("vehicle_exited", self.on_vehicle_exited)
        self.sim.events.subscribe("final_operation_completed", self.on_final_operation_completed)

    def _matches_player(self, event):
        return event.data.get("eid") == self.player_eid

    def on_player_action(self, event):
        if not self._matches_player(event):
            return
        action = str(event.data.get("action", "") or "").strip().lower()
        gate_by_action = {
            "move": "movement",
            "examine_cursor": "look",
            "interact": "interact_targeting",
            "talk": "talk_targeting",
            "service_interact": "service_menu",
            "pickup_item": "pickup",
            "use_item": "inventory_use",
            "zoom_overworld": "map",
            "overworld_travel": "vehicle_travel",
            "toggle_cover": "cover",
            "cover_hop": "cover",
            "fire_weapon": "safe_aim",
        }
        gate = gate_by_action.get(action)
        if gate:
            record_tutorial_gate(self.sim, gate)

    def on_dialog_topic_request(self, event):
        if not self._matches_player(event):
            return
        if str(event.data.get("topic_id", "") or "").strip().lower() == "tutorial_next":
            record_tutorial_gate(self.sim, "guide_dialogue")

    def on_inventory_panel_toggled(self, event):
        if self._matches_player(event) and bool(event.data.get("open")):
            record_tutorial_gate(self.sim, "inventory")

    def on_trade_panel_toggled(self, event):
        if self._matches_player(event) and bool(event.data.get("open")):
            record_tutorial_gate(self.sim, "trade")

    def on_item_picked_up(self, event):
        if not self._matches_player(event):
            return
        record_tutorial_gate(self.sim, "pickup")
        state = tutorial_state(self.sim)
        target_instance_id = str(state.get("target_item_instance_id", "") or "").strip()
        if target_instance_id and str(event.data.get("instance_id", "") or "").strip() == target_instance_id:
            record_tutorial_gate(self.sim, "final_retrieval")

    def on_item_used(self, event):
        if self._matches_player(event):
            record_tutorial_gate(self.sim, "inventory_use")

    def on_vehicle_exited(self, event):
        if self._matches_player(event):
            record_tutorial_gate(self.sim, "vehicle_exit")

    def on_final_operation_completed(self, event):
        if not self._matches_player(event):
            return
        record_tutorial_gate(self.sim, "final_retrieval")
        record_tutorial_gate(self.sim, "tutorial_complete")
        state = tutorial_state(self.sim)
        state["completed"] = True
        state["hint"] = "Tutorial complete. This practice run will not affect future runs."
        state["current_hint"] = state["hint"]

    def update(self):
        if not is_tutorial_run(self.sim):
            return
        look_ui = getattr(self.sim, "look_ui", {}) if isinstance(getattr(self.sim, "look_ui", None), dict) else {}
        if bool(look_ui.get("active")):
            purpose = str(look_ui.get("purpose", "") or "").strip().lower()
            if purpose == "inspect":
                record_tutorial_gate(self.sim, "look")
            elif purpose == "interact":
                record_tutorial_gate(self.sim, "interact_targeting")
            elif purpose == "talk":
                record_tutorial_gate(self.sim, "talk_targeting")
            elif purpose == "aim":
                record_tutorial_gate(self.sim, "safe_aim")

        dialog_ui = getattr(self.sim, "dialog_ui", {}) if isinstance(getattr(self.sim, "dialog_ui", None), dict) else {}
        state = tutorial_state(self.sim)
        if bool(dialog_ui.get("open")) and dialog_ui.get("npc_eid") == state.get("guide_eid"):
            record_tutorial_gate(self.sim, "talk_targeting")

        report_ui = getattr(self.sim, "report_ui", {}) if isinstance(getattr(self.sim, "report_ui", None), dict) else {}
        if bool(report_ui.get("open")):
            kind = str(report_ui.get("kind", "progress") or "progress").strip().lower()
            if kind == "progress":
                record_tutorial_gate(self.sim, "operations_report")
            elif kind == "known_locations":
                record_tutorial_gate(self.sim, "places_notebook")
            elif kind == "known_people":
                record_tutorial_gate(self.sim, "people_notebook")

        if bool(getattr(self.sim, "character_ui", {}).get("open")):
            record_tutorial_gate(self.sim, "character_sheet")
        if bool(getattr(self.sim, "inventory_ui", {}).get("open")):
            record_tutorial_gate(self.sim, "inventory")
        if bool(getattr(self.sim, "trade_ui", {}).get("open")):
            record_tutorial_gate(self.sim, "trade")
        if bool(getattr(self.sim, "log_ui", {}).get("open")) or bool(getattr(self.sim, "help_ui", {}).get("open")):
            record_tutorial_gate(self.sim, "log_help")
        if str(getattr(self.sim, "zoom_mode", "city")).strip().lower() == "overworld":
            record_tutorial_gate(self.sim, "map")
