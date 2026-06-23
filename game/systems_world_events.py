"""World-event runtime extracted from ``game/systems.py``.

This seam keeps the public import surface stable by letting
``game/systems.py`` re-export the helpers and ``WorldEventsSystem`` while the
ambient-event runtime evolves outside the monolith.
"""

import random

from engine.events import Event
from engine.systems import System
from game.components import (
    CreatureIdentity,
    HumanWildlifePresence,
    Inventory,
    Vitality,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.hunting_runtime import (
    FIELD_KNIFE_ITEM_ID,
    KILL_BAG_ITEM_ID,
    field_dress_carcass,
    hunting_yield_profile,
)
from game.items import ITEM_CATALOG
from game.weapons import weapon_by_id
from game.world_event_presentation import world_event_effect_summary
from game import systems as _systems

AI = _systems.AI
LOG_PRIORITY_HIGH = _systems.LOG_PRIORITY_HIGH
LOG_PRIORITY_NORMAL = _systems.LOG_PRIORITY_NORMAL
NPCSettlement = _systems.NPCSettlement
NPCWill = _systems.NPCWill
Position = _systems.Position
_WORLD_EVENT_CATALOG = _systems._WORLD_EVENT_CATALOG
_WORLD_EVENT_COOLDOWN_PER_CHUNK = _systems._WORLD_EVENT_COOLDOWN_PER_CHUNK
_WORLD_EVENT_DURATION_SCALE = _systems._WORLD_EVENT_DURATION_SCALE
_WORLD_EVENT_MAX_ACTIVE = _systems._WORLD_EVENT_MAX_ACTIVE
_WORLD_EVENT_PLAYER_REVEAL_RADIUS = _systems._WORLD_EVENT_PLAYER_REVEAL_RADIUS
_WORLD_EVENT_ROLL_INTERVAL = _systems._WORLD_EVENT_ROLL_INTERVAL
_apply_pressure_delta = _systems._apply_pressure_delta
_ensure_newcomer_component = _systems._ensure_newcomer_component
_manhattan = _systems._manhattan
_release_actor_to_newcomer = _systems._release_actor_to_newcomer
_spawn_human = _systems._spawn_human
_path_next_step = _systems._path_next_step
_try_move_entity = _systems.try_move_entity
_weapon_target_viability = _systems._weapon_target_viability

HUNTER_PARTY_MAX_KILLS = 2
HUNTER_PARTY_TARGET_RADIUS = 16
HUNTER_PARTY_ACTION_COOLDOWN = 2


def _normalize_chunk_coord(value):
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _world_event_chunk_coord(event):
    if not isinstance(event, dict):
        return None
    try:
        return (int(event.get("cx", 0)), int(event.get("cy", 0)))
    except (TypeError, ValueError):
        return None


def _chunk_chebyshev_distance(first, second):
    first_chunk = _normalize_chunk_coord(first)
    second_chunk = _normalize_chunk_coord(second)
    if first_chunk is None or second_chunk is None:
        return None
    return max(abs(first_chunk[0] - second_chunk[0]), abs(first_chunk[1] - second_chunk[1]))


def _viewer_chunk_coord(sim, viewer_eid=None):
    target_eid = viewer_eid if viewer_eid is not None else getattr(sim, "player_eid", None)
    if target_eid is not None:
        pos = sim.ecs.get(Position).get(target_eid)
        if pos is not None:
            try:
                cx, cy = sim.chunk_coords(pos.x, pos.y)
                return (int(cx), int(cy))
            except (TypeError, ValueError):
                pass
    return _normalize_chunk_coord(getattr(sim, "active_chunk_coord", None))


def active_world_events_near_chunk(sim, chunk, radius=_WORLD_EVENT_PLAYER_REVEAL_RADIUS):
    center_chunk = _normalize_chunk_coord(chunk)
    if center_chunk is None:
        return []
    state = _world_events_state(sim)
    nearby = []
    max_radius = max(0, int(radius))
    for event in state["active"]:
        event_chunk = _world_event_chunk_coord(event)
        if event_chunk is None:
            continue
        distance = _chunk_chebyshev_distance(center_chunk, event_chunk)
        if distance is None or distance > max_radius:
            continue
        nearby.append((distance, int(event_chunk[1]), int(event_chunk[0]), str(event.get("label", "")), event))
    nearby.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return [row[-1] for row in nearby]


def world_event_visible_to_viewer(sim, event, viewer_eid=None, radius=_WORLD_EVENT_PLAYER_REVEAL_RADIUS):
    viewer_chunk = _viewer_chunk_coord(sim, viewer_eid=viewer_eid)
    if viewer_chunk is None:
        return False
    event_chunk = _world_event_chunk_coord(event)
    if event_chunk is None:
        return False
    distance = _chunk_chebyshev_distance(viewer_chunk, event_chunk)
    return distance is not None and distance <= max(0, int(radius))


def _world_event_revealed_ids(sim):
    state = _world_events_state(sim)
    revealed = []
    seen = set()
    for raw_event_id in state.get("revealed_event_ids", ()):
        try:
            event_id = int(raw_event_id)
        except (TypeError, ValueError):
            continue
        if event_id <= 0 or event_id in seen:
            continue
        seen.add(event_id)
        revealed.append(event_id)
    state["revealed_event_ids"] = revealed
    return set(revealed)


def _mark_world_event_revealed(sim, event_id):
    try:
        clean_event_id = int(event_id)
    except (TypeError, ValueError):
        return
    if clean_event_id <= 0:
        return
    state = _world_events_state(sim)
    revealed = _world_event_revealed_ids(sim)
    if clean_event_id in revealed:
        return
    state["revealed_event_ids"] = list(state.get("revealed_event_ids", [])) + [clean_event_id]


def _clear_world_event_revealed(sim, event_id):
    try:
        clean_event_id = int(event_id)
    except (TypeError, ValueError):
        return
    if clean_event_id <= 0:
        return
    state = _world_events_state(sim)
    kept_ids = []
    for raw_existing_id in state.get("revealed_event_ids", ()):
        try:
            existing_id = int(raw_existing_id)
        except (TypeError, ValueError):
            continue
        if existing_id == clean_event_id:
            continue
        kept_ids.append(existing_id)
    state["revealed_event_ids"] = kept_ids


def _world_events_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("world_events")
    if not isinstance(state, dict):
        state = {
            "active": [],
            "history": [],
            "next_roll_tick": 0,
            "next_event_id": 1,
            "revealed_event_ids": [],
        }
        traits["world_events"] = state
    if not isinstance(state.get("revealed_event_ids"), list):
        raw_revealed = state.get("revealed_event_ids", ())
        if isinstance(raw_revealed, (tuple, set)):
            state["revealed_event_ids"] = list(raw_revealed)
        else:
            state["revealed_event_ids"] = []
    return state


def active_world_events_for_chunk(sim, chunk):
    """Return list of active world event dicts affecting *chunk*."""
    state = _world_events_state(sim)
    cx, cy = int(chunk[0]), int(chunk[1])
    return [
        e for e in state["active"]
        if isinstance(e, dict) and int(e.get("cx", -999)) == cx and int(e.get("cy", -999)) == cy
    ]


def world_event_trade_multipliers(sim, chunk):
    """Return aggregate (buy_mult, sell_mult) from active events on *chunk*."""
    events = active_world_events_for_chunk(sim, chunk)
    buy = 1.0
    sell = 1.0
    for event in events:
        buy *= float(event.get("trade_buy_mult", 1.0))
        sell *= float(event.get("trade_sell_mult", 1.0))
    return buy, sell


def world_event_observer_notice_delta(sim, chunk):
    """Return aggregate observer notice-radius delta for active events on *chunk*."""
    events = active_world_events_for_chunk(sim, chunk)
    delta = 0
    for event in events:
        try:
            delta += int(event.get("observer_notice_delta", 0))
        except (TypeError, ValueError):
            continue
    return max(-3, min(4, delta))


class WorldEventsSystem(System):
    """Fires ambient world events on a tick schedule."""

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.rng = random.Random(f"{sim.seed}:world-events")
        self.runs_without_turn = True
        self.sim.events.subscribe("world_event_started", self.on_world_event_started)
        self.sim.events.subscribe("world_event_ended", self.on_world_event_ended)

    def on_world_event_started(self, event):
        if not world_event_visible_to_viewer(self.sim, event.data, self.player_eid):
            return
        label = event.data.get("label", "World Event")
        text = event.data.get("flavor") or f"World event started: {label}"
        effect = world_event_effect_summary(event.data)
        if effect:
            text = f"{text} Effect: {effect}."
        self.sim.log.add(text, channel="status", priority=LOG_PRIORITY_HIGH)
        self.sim.log.add(f"[{label}] event started", channel="status", priority=LOG_PRIORITY_NORMAL)

    def on_world_event_ended(self, event):
        if not world_event_visible_to_viewer(self.sim, event.data, self.player_eid):
            return
        label = event.data.get("label", "World Event")
        text = event.data.get("flavor") or f"World event ended: {label}"
        effect = world_event_effect_summary(event.data, ending=True)
        if effect:
            text = f"{text} Effect: {effect}."
        self.sim.log.add(text, channel="status", priority=LOG_PRIORITY_HIGH)
        self.sim.log.add(f"[{label}] event ended", channel="status", priority=LOG_PRIORITY_NORMAL)

    def _normalize_event_runtime_state(self, event):
        if not isinstance(event, dict):
            return
        if not isinstance(event.get("spawned_entity_ids"), list):
            event["spawned_entity_ids"] = []
        if not isinstance(event.get("spawned_property_ids"), list):
            event["spawned_property_ids"] = []
        event["materialized"] = bool(event.get("materialized", False))
        if str(event.get("key", "")).strip().lower() == "hunter_party":
            if not isinstance(event.get("hunter_actor_ids"), list):
                event["hunter_actor_ids"] = []
            if not isinstance(event.get("hunter_task"), dict):
                event["hunter_task"] = {}
            try:
                event["hunter_kills"] = max(0, int(event.get("hunter_kills", 0) or 0))
            except (TypeError, ValueError):
                event["hunter_kills"] = 0
            try:
                event["hunter_kill_cap"] = max(0, int(event.get("hunter_kill_cap", HUNTER_PARTY_MAX_KILLS) or HUNTER_PARTY_MAX_KILLS))
            except (TypeError, ValueError):
                event["hunter_kill_cap"] = HUNTER_PARTY_MAX_KILLS
        try:
            event["spawn_seed"] = int(event.get("spawn_seed", event.get("id", 0)))
        except (TypeError, ValueError):
            event["spawn_seed"] = int(event.get("id", 0) or 0)

    def _active_chunk_coord(self):
        coord = getattr(self.sim, "active_chunk_coord", None)
        if not isinstance(coord, (tuple, list)) or len(coord) != 2:
            return None
        try:
            return (int(coord[0]), int(coord[1]))
        except (TypeError, ValueError):
            return None

    def _event_chunk_is_active(self, event):
        active = self._active_chunk_coord()
        if active is None or not isinstance(event, dict):
            return False
        try:
            return active == (int(event.get("cx", -9999)), int(event.get("cy", -9999)))
        except (TypeError, ValueError):
            return False

    def _event_has_physical_manifestation(self, event):
        if not isinstance(event, dict):
            return False
        try:
            guard_count = int(event.get("guard_count", 0))
        except (TypeError, ValueError):
            guard_count = 0
        event_key = str(event.get("key", "")).strip().lower()
        return (
            guard_count > 0
            or bool(event.get("spawn_market_stall"))
            or event_key in {"hunter_party", "campout"}
        )

    def _event_rng(self, event, salt):
        event_id = event.get("id", 0) if isinstance(event, dict) else 0
        seed = event.get("spawn_seed", event_id) if isinstance(event, dict) else event_id
        return random.Random(f"{self.sim.seed}:world-event:{event_id}:{seed}:{salt}")

    def _add_event_actor_item(self, eid, item_id, *, metadata=None):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if inventory is None:
            inventory = Inventory(capacity=10)
            self.sim.ecs.add(eid, inventory)
        inventory.capacity = max(int(getattr(inventory, "capacity", 0) or 0), 10)
        item_id = str(item_id or "").strip().lower()
        item_def = ITEM_CATALOG.get(item_id, {})
        if not item_def:
            return None
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="npc",
            metadata=metadata or {"source": "hunter_party"},
        )
        return instance_id if added else None

    def _equip_event_hunter(self, eid, rng, *, career="hunter"):
        weapon_item_id = "hunting_rifle" if str(career or "").strip().lower() == "hunter" else "varmint_rifle"
        instance_id = self._add_event_actor_item(
            eid,
            weapon_item_id,
            metadata={"source": "hunter_party", "equipped": True},
        )
        self._add_event_actor_item(eid, FIELD_KNIFE_ITEM_ID, metadata={"source": "hunter_party", "field_kit": True})
        self._add_event_actor_item(eid, KILL_BAG_ITEM_ID, metadata={"source": "hunter_party", "field_kit": True})

        item_def = ITEM_CATALOG.get(weapon_item_id, {})
        weapon_id = str(item_def.get("weapon_id", "") or "").strip()
        if weapon_id:
            loadout = self.sim.ecs.get(WeaponLoadout).get(eid)
            if loadout is None:
                loadout = WeaponLoadout()
                self.sim.ecs.add(eid, loadout)
            loadout.add_weapon(weapon_id, instance={"inventory_instance_id": instance_id, "source": "hunter_party"})
            loadout.equip(weapon_id)
            loadout.set_reserve_ammo_value(weapon_id, 18)

        self.sim.ecs.add(
            eid,
            WeaponUseProfile(
                aggression=0.86,
                aim_bias=0.72,
                min_range=1,
                max_range=14,
                cooldown_jitter=0,
                allow_explosives=False,
            ),
        )
        presence = self.sim.ecs.get(HumanWildlifePresence).get(eid)
        if presence is not None:
            presence.hunting_intent = True
            presence.firearm_threat_bonus = max(float(getattr(presence, "firearm_threat_bonus", 0.0) or 0.0), 44.0)
            presence.perceived_predator_score = max(float(getattr(presence, "perceived_predator_score", 0.0) or 0.0), 78.0)
        return True

    def _hunter_actor_ids(self, event):
        ids = []
        seen = set()
        raw_ids = event.get("hunter_actor_ids")
        if not isinstance(raw_ids, list):
            raw_ids = []
        identities = self.sim.ecs.get(CreatureIdentity)
        for raw_eid in list(raw_ids) + list(event.get("spawned_entity_ids", ()) or ()):
            try:
                eid = int(raw_eid)
            except (TypeError, ValueError):
                continue
            if eid in seen:
                continue
            identity = identities.get(eid)
            common = str(getattr(identity, "common_name", "") or "").strip().lower()
            if common not in {"hunter", "trapper"}:
                continue
            if self.sim.ecs.get(Position).get(eid) is None:
                continue
            seen.add(eid)
            ids.append(eid)
        event["hunter_actor_ids"] = ids
        return ids

    def _event_anchor(self, event):
        for property_id in tuple(event.get("spawned_property_ids", ()) or ()):
            prop = self.sim.properties.get(property_id)
            if prop:
                return (
                    int(prop.get("x", 0) or 0),
                    int(prop.get("y", 0) or 0),
                    int(prop.get("z", 0) or 0),
                    str(prop.get("id", "") or "").strip() or None,
                    str(prop.get("name", "") or "").strip() or "hunter party",
                )
        try:
            origin_x, origin_y = self.sim.chunk_origin(int(event.get("cx", 0)), int(event.get("cy", 0)))
            return (
                origin_x + self.sim.chunk_size // 2,
                origin_y + self.sim.chunk_size // 2,
                0,
                None,
                "hunter party",
            )
        except Exception:
            return (0, 0, 0, None, "hunter party")

    def _event_chunk_contains_pos(self, event, pos):
        if pos is None:
            return False
        try:
            return tuple(self.sim.chunk_coords(int(pos.x), int(pos.y))) == (int(event.get("cx", 0)), int(event.get("cy", 0)))
        except (TypeError, ValueError):
            return False

    def _eligible_hunter_target_rows(self, event, hunter_eid):
        hunter_pos = self.sim.ecs.get(Position).get(hunter_eid)
        if hunter_pos is None:
            return []
        anchor_x, anchor_y, anchor_z, _anchor_prop_id, _anchor_name = self._event_anchor(event)
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)
        rows = []
        for target_eid, ai in ais.items():
            if target_eid == hunter_eid:
                continue
            if str(getattr(ai, "role", "") or "").strip().lower() != "wildlife":
                continue
            target_pos = positions.get(target_eid)
            if target_pos is None or int(target_pos.z) != int(hunter_pos.z):
                continue
            if not self._event_chunk_contains_pos(event, target_pos):
                continue
            if self.sim.property_covering(int(target_pos.x), int(target_pos.y), int(target_pos.z)):
                continue
            vitality = vitalities.get(target_eid)
            if vitality is not None and bool(getattr(vitality, "downed", False)):
                continue
            if hunting_yield_profile(self.sim, animal_eid=target_eid) is None:
                continue
            anchor_dist = _manhattan(anchor_x, anchor_y, int(target_pos.x), int(target_pos.y))
            hunter_dist = _manhattan(int(hunter_pos.x), int(hunter_pos.y), int(target_pos.x), int(target_pos.y))
            if anchor_dist > HUNTER_PARTY_TARGET_RADIUS and hunter_dist > HUNTER_PARTY_TARGET_RADIUS:
                continue
            rows.append((hunter_dist, anchor_dist, int(target_eid), target_pos))
        rows.sort(key=lambda row: (row[0], row[1], row[2]))
        return rows

    def _claim_event_carcasses(self, event):
        state = getattr(self.sim, "hunting_carcasses", None)
        if not isinstance(state, dict):
            return []
        hunter_ids = set(self._hunter_actor_ids(event))
        if not hunter_ids:
            return []
        anchor_x, anchor_y, anchor_z, anchor_prop_id, anchor_name = self._event_anchor(event)
        claimed = []
        for record in state.values():
            if not isinstance(record, dict):
                continue
            try:
                source_eid = int(record.get("source_eid"))
            except (TypeError, ValueError):
                continue
            if source_eid not in hunter_ids:
                continue
            record["claimed_by_event_id"] = int(event.get("id", 0) or 0)
            record["claimed_by_hunter_eid"] = source_eid
            record["claimed_by_org"] = "hunter_party"
            record["claimed_property_id"] = anchor_prop_id
            record["claim_label"] = anchor_name
            claimed.append(record)
        return claimed

    def _move_event_actor_toward(self, eid, target, *, reason="event_hunt"):
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None or not isinstance(target, (tuple, list)) or len(target) < 3:
            return False
        try:
            tx, ty, tz = int(target[0]), int(target[1]), int(target[2])
        except (TypeError, ValueError):
            return False
        if int(pos.z) != tz or (int(pos.x), int(pos.y)) == (tx, ty):
            return False
        step = _path_next_step(
            self.sim,
            eid,
            sx=int(pos.x),
            sy=int(pos.y),
            tx=tx,
            ty=ty,
            z=int(pos.z),
            max_nodes=256,
        )
        if not step:
            return False
        moved, _blocked_reason = _try_move_entity(
            self.sim,
            eid=eid,
            new_x=int(step[0]),
            new_y=int(step[1]),
            new_z=int(pos.z),
            reason=reason,
        )
        if moved:
            self.sim.emit(Event(
                "noise",
                source_eid=eid,
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
                radius=2,
                cause="move",
            ))
        return bool(moved)

    def _hunter_can_fire_at(self, hunter_eid, target_eid):
        positions = self.sim.ecs.get(Position)
        loadout = self.sim.ecs.get(WeaponLoadout).get(hunter_eid)
        hunter_pos = positions.get(hunter_eid)
        target_pos = positions.get(target_eid)
        if hunter_pos is None or target_pos is None or int(hunter_pos.z) != int(target_pos.z):
            return False
        if loadout is None or not loadout.current_weapon():
            return False
        if int(getattr(self.sim, "tick", 0) or 0) < int(getattr(loadout, "cooldown_until_tick", 0) or 0):
            return False
        weapon = weapon_by_id(loadout.current_weapon())
        if not weapon or "melee" in {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}:
            return False
        profile = self.sim.ecs.get(WeaponUseProfile).get(hunter_eid)
        max_range = int(getattr(profile, "max_range", weapon.get("range", 1)) if profile else weapon.get("range", 1))
        if _manhattan(int(hunter_pos.x), int(hunter_pos.y), int(target_pos.x), int(target_pos.y)) > max_range:
            return False
        viability = _weapon_target_viability(
            self.sim,
            source_eid=hunter_eid,
            source_pos=hunter_pos,
            weapon=weapon,
            target_x=int(target_pos.x),
            target_y=int(target_pos.y),
            target_z=int(target_pos.z),
            target_eid=target_eid,
        )
        return bool(viability.get("ok"))

    def _set_hunter_task_intent(self, hunter_eid, *, target=None, target_eid=None, state="hunting"):
        ai = self.sim.ecs.get(AI).get(hunter_eid)
        will = self.sim.ecs.get(NPCWill).get(hunter_eid)
        if ai is not None:
            ai.state = str(state or "hunting").strip().lower() or "hunting"
            ai.target = target
            ai.target_eid = target_eid
        if will is not None:
            will.intent = str(state or "hunting").strip().lower() or "hunting"
            will.score = max(46.0, float(getattr(will, "score", 0.0) or 0.0))
            will.target = target
            will.target_eid = target_eid

    def _candidate_street_tiles(self, cx, cy, *, reserved=None, min_player_distance=3):
        reserved = {
            (int(pos[0]), int(pos[1]), int(pos[2]))
            for pos in (reserved or ())
            if isinstance(pos, (tuple, list)) and len(pos) >= 3
        }
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        origin_x, origin_y = self.sim.chunk_origin(cx, cy)
        center_x = origin_x + max(2, self.sim.chunk_size // 2)
        center_y = origin_y + max(2, self.sim.chunk_size // 2)
        candidates = []
        for y in range(origin_y + 1, origin_y + self.sim.chunk_size - 1):
            for x in range(origin_x + 1, origin_x + self.sim.chunk_size - 1):
                pos = (x, y, 0)
                if pos in reserved:
                    continue
                if not self.sim.tilemap.is_walkable(x, y, 0):
                    continue
                if self.sim.structure_at(x, y, 0):
                    continue
                if self.sim.property_covering(x, y, 0):
                    continue
                if self.sim.tilemap.entities_at(x, y, 0):
                    continue
                if player_pos and _manhattan(player_pos.x, player_pos.y, x, y) < int(min_player_distance):
                    continue
                dist_center = _manhattan(x, y, center_x, center_y)
                candidates.append((dist_center, x, y, 0))
        candidates.sort(key=lambda row: (row[0], row[2], row[1]))
        return [(x, y, z) for _dist, x, y, z in candidates]

    def _pick_event_tile(self, event, rng, *, reserved=None, prefer_center=True, min_player_distance=3):
        try:
            cx = int(event.get("cx", 0))
            cy = int(event.get("cy", 0))
        except (TypeError, ValueError):
            return None
        candidates = self._candidate_street_tiles(
            cx,
            cy,
            reserved=reserved,
            min_player_distance=min_player_distance,
        )
        if not candidates:
            return None
        if prefer_center:
            pool = candidates[: min(len(candidates), 18)]
        else:
            limit = max(12, min(len(candidates), max(18, len(candidates) // 2)))
            pool = candidates[:limit]
        return pool[rng.randrange(len(pool))]

    def _pick_adjacent_street_tile(self, anchor, *, reserved=None):
        if not isinstance(anchor, (tuple, list)) or len(anchor) < 3:
            return None
        reserved = {
            (int(pos[0]), int(pos[1]), int(pos[2]))
            for pos in (reserved or ())
            if isinstance(pos, (tuple, list)) and len(pos) >= 3
        }
        ax, ay, az = int(anchor[0]), int(anchor[1]), int(anchor[2])
        candidates = []
        for radius in (1, 2):
            for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                nx, ny = ax + dx, ay + dy
                pos = (nx, ny, az)
                if pos in reserved:
                    continue
                if not self.sim.tilemap.is_walkable(nx, ny, az):
                    continue
                if self.sim.structure_at(nx, ny, az):
                    continue
                if self.sim.property_covering(nx, ny, az):
                    continue
                if self.sim.tilemap.entities_at(nx, ny, az):
                    continue
                candidates.append(pos)
        return candidates[0] if candidates else None

    def _spawn_guard_patrols(self, event):
        try:
            guard_count = int(event.get("guard_count", 0))
        except (TypeError, ValueError):
            guard_count = 0
        if guard_count <= 0:
            return

        rng = self._event_rng(event, "guards")
        reserved = set()
        for guard_index in range(guard_count):
            patrol_target = self._pick_event_tile(
                event,
                rng,
                reserved=reserved,
                prefer_center=False,
                min_player_distance=4,
            )
            if not patrol_target:
                break
            reserved.add(patrol_target)
            spawn_pos = self._pick_event_tile(
                event,
                rng,
                reserved=reserved,
                prefer_center=False,
                min_player_distance=4,
            ) or patrol_target
            reserved.add(spawn_pos)

            guard_rng = self._event_rng(event, f"guard:{guard_index}:{spawn_pos[0]}:{spawn_pos[1]}")
            guard_eid = _spawn_human(
                self.sim,
                guard_rng,
                "guard",
                spawn_pos,
                career="security_patrol",
                work=patrol_target,
                shift_window=(0, 0),
            )
            ai = self.sim.ecs.get(AI).get(guard_eid)
            if ai:
                ai.state = "patrolling"
                ai.target = patrol_target
                ai.target_eid = None
            will = self.sim.ecs.get(NPCWill).get(guard_eid)
            if will:
                will.intent = "patrolling"
                will.score = 42.0
                will.target = patrol_target
                will.target_eid = None
            event["spawned_entity_ids"].append(guard_eid)

    def _spawn_market_stall(self, event):
        rng = self._event_rng(event, "stall")
        anchor = self._pick_event_tile(
            event,
            rng,
            prefer_center=True,
            min_player_distance=5,
        )
        if not anchor:
            return

        if str(event.get("key", "")).strip().lower() == "black_market_window":
            stall_name = "Back-Alley Stall"
            stall_glyph = "b"
        else:
            stall_name = "Pop-Up Market"
            stall_glyph = "m"

        ax, ay, az = anchor
        property_id = self.sim.register_property(
            name=stall_name,
            kind="fixture",
            x=ax,
            y=ay,
            z=az,
            owner_eid=None,
            owner_tag="public",
            metadata={
                "archetype": "junk_market",
                "fixture_type": "market_stall",
                "is_storefront": True,
                "public": True,
                "storefront_service_mode": "staffed",
                "entry": {"x": ax, "y": ay, "z": az, "kind": "stall", "ordinary": True},
                "apertures": [{"x": ax, "y": ay, "z": az, "kind": "stall", "ordinary": True}],
                "display_glyph": stall_glyph,
                "display_color": "building_roof_storefront",
                "world_event_id": int(event.get("id", 0)),
                "world_event_key": str(event.get("key", "")).strip().lower(),
            },
        )
        event["spawned_property_ids"].append(property_id)

        prop = self.sim.properties.get(property_id)
        if not prop:
            return

        vendor_pos = self._pick_adjacent_street_tile(anchor, reserved={anchor}) or anchor
        vendor_rng = self._event_rng(event, f"vendor:{vendor_pos[0]}:{vendor_pos[1]}")
        vendor_eid = _spawn_human(
            self.sim,
            vendor_rng,
            "worker",
            vendor_pos,
            career="market_vendor",
            workplace={"property_id": property_id},
            work=anchor,
            shift_window=(0, 0),
            workplace_prop=prop,
        )
        self.sim.assign_property_owner(property_id, owner_eid=vendor_eid, owner_tag="public")
        _ensure_newcomer_component(
            self.sim,
            vendor_eid,
            origin=f"world_event:{str(event.get('key', '') or '').strip().lower()}",
            arrived_tick=self.sim.tick,
            phase="working",
            housing_status="unhoused",
            employment_status="employed",
        )
        event["spawned_entity_ids"].append(vendor_eid)

    def _set_event_actor_intent(self, eid, intent, target, *, score=32.0):
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            return
        hold_target = (int(target[0]), int(target[1]), int(target[2]))
        ai = self.sim.ecs.get(AI).get(eid)
        if ai:
            ai.state = str(intent or "holding").strip().lower() or "holding"
            ai.target = hold_target
            ai.target_eid = None
        will = self.sim.ecs.get(NPCWill).get(eid)
        if will:
            will.intent = str(intent or "holding").strip().lower() or "holding"
            will.score = float(score)
            will.target = hold_target
            will.target_eid = None

    def _spawn_event_fixture(
        self,
        event,
        anchor,
        *,
        name,
        fixture_type,
        glyph,
        color,
        light_enabled=False,
        light_radius=0,
        light_intensity=0.0,
        light_phases=None,
    ):
        if not isinstance(anchor, (tuple, list)) or len(anchor) < 3:
            return None
        ax, ay, az = int(anchor[0]), int(anchor[1]), int(anchor[2])
        metadata = {
            "archetype": "world_event_fixture",
            "fixture_type": str(fixture_type or "world_event_fixture").strip().lower() or "world_event_fixture",
            "public": True,
            "display_glyph": str(glyph or "*")[:1] or "*",
            "display_color": str(color or "item_tool").strip() or "item_tool",
            "world_event_id": int(event.get("id", 0)),
            "world_event_key": str(event.get("key", "")).strip().lower(),
        }
        if light_enabled:
            metadata.update({
                "light_enabled": True,
                "light_radius": max(1, int(light_radius or 1)),
                "light_intensity": max(0.1, float(light_intensity or 0.1)),
                "light_phases": list(light_phases or ("dusk", "night")),
            })
        property_id = self.sim.register_property(
            name=str(name or "Event Fixture").strip() or "Event Fixture",
            kind="fixture",
            x=ax,
            y=ay,
            z=az,
            owner_eid=None,
            owner_tag="public",
            metadata=metadata,
        )
        event["spawned_property_ids"].append(property_id)
        return self.sim.properties.get(property_id)

    def _spawn_wilderness_party(self, event):
        event_key = str(event.get("key", "")).strip().lower()
        if event_key not in {"hunter_party", "campout"}:
            return
        rng = self._event_rng(event, event_key)
        anchor = self._pick_event_tile(
            event,
            rng,
            prefer_center=False,
            min_player_distance=5,
        )
        if not anchor:
            return

        if event_key == "hunter_party":
            self._spawn_event_fixture(
                event,
                anchor,
                name="Game Rack",
                fixture_type="game_rack",
                glyph="r",
                color="item_tool",
            )
            crew = (
                ("worker", "hunter"),
                ("worker", "trapper"),
                ("civilian", "trail_guide"),
            )
        else:
            self._spawn_event_fixture(
                event,
                anchor,
                name="Campfire Ring",
                fixture_type="campfire_ring",
                glyph="f",
                color="cat_orange",
                light_enabled=True,
                light_radius=3,
                light_intensity=0.62,
                light_phases=("dusk", "night"),
            )
            crew = (
                ("civilian", "camper"),
                ("civilian", "camper"),
                ("civilian", "trail_guide"),
            )

        reserved = {tuple(anchor)}
        for actor_index, (role, career) in enumerate(crew):
            hold_spot = self._pick_adjacent_street_tile(anchor, reserved=reserved)
            if hold_spot is None:
                hold_spot = self._pick_event_tile(
                    event,
                    rng,
                    reserved=reserved,
                    prefer_center=False,
                    min_player_distance=4,
                )
            if hold_spot is None:
                continue
            reserved.add(tuple(hold_spot))
            actor_rng = self._event_rng(
                event,
                f"{event_key}:{actor_index}:{hold_spot[0]}:{hold_spot[1]}",
            )
            eid = _spawn_human(
                self.sim,
                actor_rng,
                str(role or "civilian").strip().lower() or "civilian",
                hold_spot,
                career=str(career or "resident").strip().lower() or "resident",
                work=anchor,
                shift_window=(0, 0),
            )
            self._set_event_actor_intent(eid, "holding", hold_spot, score=34.0)
            if event_key == "hunter_party" and str(career or "").strip().lower() in {"hunter", "trapper"}:
                self._equip_event_hunter(eid, actor_rng, career=career)
                event.setdefault("hunter_actor_ids", []).append(eid)
            event["spawned_entity_ids"].append(eid)

    def _release_event_entity(self, event, eid):
        newcomer = self.sim.ecs.get(NPCSettlement).get(eid)
        if newcomer is None:
            return False
        released = _release_actor_to_newcomer(
            self.sim,
            eid,
            origin=f"released:{str(event.get('key', '') or '').strip().lower()}",
            arrived_tick=self.sim.tick,
            drift_preferred=bool(newcomer.drift_preferred),
        )
        return released is not None

    def _materialize_event(self, event):
        self._normalize_event_runtime_state(event)
        if event.get("materialized"):
            return
        if not self._event_chunk_is_active(event):
            return

        if int(event.get("guard_count", 0) or 0) > 0:
            self._spawn_guard_patrols(event)
        if bool(event.get("spawn_market_stall")):
            self._spawn_market_stall(event)
        if str(event.get("key", "")).strip().lower() in {"hunter_party", "campout"}:
            self._spawn_wilderness_party(event)

        if not self._event_has_physical_manifestation(event):
            event["materialized"] = True
            return
        if event["spawned_entity_ids"] or event["spawned_property_ids"]:
            event["materialized"] = True

    def _dematerialize_event(self, event):
        self._normalize_event_runtime_state(event)
        for property_id in list(event.get("spawned_property_ids", ())):
            self.sim.remove_property(property_id)
        kept = []
        for eid in list(event.get("spawned_entity_ids", ())):
            if self._release_event_entity(event, eid):
                kept.append(eid)
                continue
            self.sim.remove_entity(eid)
        event["spawned_property_ids"] = []
        event["spawned_entity_ids"] = kept
        if str(event.get("key", "")).strip().lower() == "hunter_party":
            event["hunter_actor_ids"] = []
            event["hunter_task"] = {}
        event["materialized"] = False

    def _update_guard_patrols(self, event):
        if str(event.get("key", "")).strip().lower() != "security_sweep":
            return
        if not self._event_chunk_is_active(event):
            return

        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        positions = self.sim.ecs.get(Position)

        for eid in list(event.get("spawned_entity_ids", ())):
            ai = ais.get(eid)
            pos = positions.get(eid)
            if not ai or not pos:
                continue
            if str(getattr(ai, "role", "") or "").strip().lower() != "guard":
                continue
            if ai.target is not None or ai.state not in {"idle", "patrolling"}:
                continue

            patrol_rng = self._event_rng(event, f"patrol:{eid}:{self.sim.tick // 6}")
            patrol_target = self._pick_event_tile(
                event,
                patrol_rng,
                reserved={(pos.x, pos.y, pos.z)},
                prefer_center=False,
                min_player_distance=2,
            )
            if not patrol_target:
                continue

            ai.state = "patrolling"
            ai.target = patrol_target
            ai.target_eid = None
            will = wills.get(eid)
            if will:
                will.intent = "patrolling"
                will.score = max(20.0, float(getattr(will, "score", 0.0) or 0.0))
                will.target = patrol_target
                will.target_eid = None

    def _task_carcass_for_hunter_event(self, event, task):
        if not isinstance(task, dict):
            return None
        state = getattr(self.sim, "hunting_carcasses", None)
        if not isinstance(state, dict):
            return None
        carcass_id = str(task.get("carcass_id", "") or "").strip()
        if carcass_id and isinstance(state.get(carcass_id), dict):
            return state[carcass_id]
        try:
            target_eid = int(task.get("target_eid"))
        except (TypeError, ValueError):
            target_eid = None
        try:
            hunter_eid = int(task.get("hunter_eid"))
        except (TypeError, ValueError):
            hunter_eid = None
        for record in state.values():
            if not isinstance(record, dict):
                continue
            try:
                animal_eid = int(record.get("animal_eid"))
            except (TypeError, ValueError):
                animal_eid = None
            try:
                source_eid = int(record.get("source_eid"))
            except (TypeError, ValueError):
                source_eid = None
            if target_eid is not None and animal_eid == target_eid:
                return record
            if hunter_eid is not None and source_eid == hunter_eid and not bool(record.get("harvested")):
                return record
        return None

    def _clear_hunter_task(self, event):
        event["hunter_task"] = {}

    def _begin_hunter_task(self, event):
        if int(event.get("hunter_kills", 0) or 0) >= int(event.get("hunter_kill_cap", HUNTER_PARTY_MAX_KILLS) or HUNTER_PARTY_MAX_KILLS):
            return None
        for hunter_eid in self._hunter_actor_ids(event):
            rows = self._eligible_hunter_target_rows(event, hunter_eid)
            if not rows:
                continue
            _hunter_dist, _anchor_dist, target_eid, target_pos = rows[0]
            task = {
                "status": "hunting",
                "hunter_eid": int(hunter_eid),
                "target_eid": int(target_eid),
                "started_tick": int(getattr(self.sim, "tick", 0) or 0),
                "last_action_tick": -10_000,
            }
            event["hunter_task"] = task
            self._set_hunter_task_intent(
                hunter_eid,
                target=(int(target_pos.x), int(target_pos.y), int(target_pos.z)),
                target_eid=int(target_eid),
                state="hunting",
            )
            self.sim.emit(Event(
                "hunter_party_targeted_wildlife",
                event_id=int(event.get("id", 0) or 0),
                hunter_eid=int(hunter_eid),
                target_eid=int(target_eid),
                x=int(target_pos.x),
                y=int(target_pos.y),
                z=int(target_pos.z),
            ))
            return task
        return None

    def _update_hunter_task_carcass(self, event, task, hunter_eid, record):
        if not isinstance(record, dict):
            return False
        task["status"] = "field_dressing"
        task["carcass_id"] = str(record.get("carcass_id", "") or "").strip()
        record["claimed_by_event_id"] = int(event.get("id", 0) or 0)
        record["claimed_by_hunter_eid"] = int(hunter_eid)
        record["claimed_by_org"] = "hunter_party"
        _anchor_x, _anchor_y, _anchor_z, anchor_prop_id, anchor_name = self._event_anchor(event)
        record["claimed_property_id"] = anchor_prop_id
        record["claim_label"] = anchor_name

        if bool(record.get("harvested")):
            if record.get("harvested_by_eid") == hunter_eid:
                event["hunter_kills"] = int(event.get("hunter_kills", 0) or 0) + 1
            self._clear_hunter_task(event)
            return True

        target = (
            int(record.get("x", 0) or 0),
            int(record.get("y", 0) or 0),
            int(record.get("z", 0) or 0),
        )
        hunter_pos = self.sim.ecs.get(Position).get(hunter_eid)
        if hunter_pos is None:
            self._clear_hunter_task(event)
            return False
        self._set_hunter_task_intent(hunter_eid, target=target, target_eid=None, state="hunting")
        if int(hunter_pos.z) != target[2] or _manhattan(int(hunter_pos.x), int(hunter_pos.y), target[0], target[1]) > 1:
            self._move_event_actor_toward(hunter_eid, target, reason="hunter_party_carcass")
            return True

        if field_dress_carcass(self.sim, hunter_eid, record.get("carcass_id")):
            event["hunter_kills"] = int(event.get("hunter_kills", 0) or 0) + 1
            self.sim.emit(Event(
                "hunter_party_carcass_dressed",
                event_id=int(event.get("id", 0) or 0),
                hunter_eid=int(hunter_eid),
                carcass_id=record.get("carcass_id"),
                animal_name=record.get("animal_name") or record.get("species_label"),
                x=target[0],
                y=target[1],
                z=target[2],
            ))
            self._clear_hunter_task(event)
            return True
        task["status"] = "blocked"
        task["last_action_tick"] = int(getattr(self.sim, "tick", 0) or 0)
        return False

    def _update_hunter_party(self, event):
        if str(event.get("key", "")).strip().lower() != "hunter_party":
            return
        if not self._event_chunk_is_active(event) or not bool(event.get("materialized")):
            return
        self._claim_event_carcasses(event)
        if int(event.get("hunter_kills", 0) or 0) >= int(event.get("hunter_kill_cap", HUNTER_PARTY_MAX_KILLS) or HUNTER_PARTY_MAX_KILLS):
            return

        task = event.get("hunter_task") if isinstance(event.get("hunter_task"), dict) else {}
        if not task:
            task = self._begin_hunter_task(event)
            if not task:
                return

        try:
            hunter_eid = int(task.get("hunter_eid"))
        except (TypeError, ValueError):
            self._clear_hunter_task(event)
            return
        hunter_pos = self.sim.ecs.get(Position).get(hunter_eid)
        hunter_vitality = self.sim.ecs.get(Vitality).get(hunter_eid)
        if hunter_pos is None or (hunter_vitality is not None and bool(getattr(hunter_vitality, "downed", False))):
            self._clear_hunter_task(event)
            return

        carcass = self._task_carcass_for_hunter_event(event, task)
        if carcass is not None:
            self._update_hunter_task_carcass(event, task, hunter_eid, carcass)
            return

        try:
            target_eid = int(task.get("target_eid"))
        except (TypeError, ValueError):
            self._clear_hunter_task(event)
            return
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        target_vitality = self.sim.ecs.get(Vitality).get(target_eid)
        if target_pos is None:
            self._clear_hunter_task(event)
            return
        target_tuple = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
        self._set_hunter_task_intent(hunter_eid, target=target_tuple, target_eid=target_eid, state="hunting")
        if target_vitality is not None and bool(getattr(target_vitality, "downed", False)):
            if _manhattan(int(hunter_pos.x), int(hunter_pos.y), int(target_pos.x), int(target_pos.y)) > 1:
                self._move_event_actor_toward(hunter_eid, target_tuple, reason="hunter_party_downed_target")
            return

        tick = int(getattr(self.sim, "tick", 0) or 0)
        last_action = int(task.get("last_action_tick", -10_000) or -10_000)
        if tick - last_action >= HUNTER_PARTY_ACTION_COOLDOWN and self._hunter_can_fire_at(hunter_eid, target_eid):
            task["last_action_tick"] = tick
            self.sim.emit(Event(
                "weapon_fire_request",
                eid=hunter_eid,
                target_eid=target_eid,
                reason="hunter_party",
            ))
            return

        self._move_event_actor_toward(hunter_eid, target_tuple, reason="hunter_party_stalk")

    def _sync_event_materialization(self, event):
        self._normalize_event_runtime_state(event)
        if self._event_chunk_is_active(event):
            if not event.get("materialized"):
                self._materialize_event(event)
            if event.get("materialized"):
                self._update_guard_patrols(event)
                self._update_hunter_party(event)
            return

        if event.get("materialized"):
            self._dematerialize_event(event)

    def _pick_target_chunk(self, state):
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not pos:
            return None
        player_chunk = self.sim.chunk_coords(pos.x, pos.y)
        px, py = int(player_chunk[0]), int(player_chunk[1])
        player_desc = self.sim.world.overworld_descriptor(px, py)
        player_area_type = str(player_desc.get("area_type", "city")).strip().lower() or "city"
        supported_area_types = set()
        for template in _WORLD_EVENT_CATALOG.values():
            for area_type in template.get("area_types", {"city"}):
                clean_area = str(area_type).strip().lower()
                if clean_area:
                    supported_area_types.add(clean_area)
        if not supported_area_types:
            return None
        tick = int(getattr(self.sim, "tick", 0))

        candidates = []
        same_area_candidates = []
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                cx, cy = px + dx, py + dy
                desc = self.sim.world.overworld_descriptor(cx, cy)
                area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
                if area_type not in supported_area_types:
                    continue
                if self._chunk_on_cooldown(state, cx, cy, tick):
                    continue
                dist = abs(dx) + abs(dy)
                candidate = (cx, cy, dist, area_type)
                candidates.append(candidate)
                if area_type == player_area_type:
                    same_area_candidates.append(candidate)
        if same_area_candidates:
            candidates = same_area_candidates
        if not candidates:
            return None

        weights = [max(1, 8 - candidate[2]) for candidate in candidates]
        chosen = self.rng.choices(candidates, weights=weights, k=1)[0]
        return (chosen[0], chosen[1])

    def _chunk_on_cooldown(self, state, cx, cy, tick):
        for entry in state.get("history", []):
            if int(entry.get("cx", -999)) == cx and int(entry.get("cy", -999)) == cy:
                if tick - int(entry.get("end_tick", 0)) < _WORLD_EVENT_COOLDOWN_PER_CHUNK:
                    return True
        for entry in state["active"]:
            if int(entry.get("cx", -999)) == cx and int(entry.get("cy", -999)) == cy:
                return True
        return False

    def _roll_event(self, state, tick):
        target = self._pick_target_chunk(state)
        if not target:
            return None
        cx, cy = target
        if self._chunk_on_cooldown(state, cx, cy, tick):
            return None

        desc = self.sim.world.overworld_descriptor(cx, cy)
        area_type = str(desc.get("area_type", "city")).strip().lower()
        district_type = str(desc.get("district_type", "unknown")).strip().lower()

        eligible = []
        weights = []
        for key, template in _WORLD_EVENT_CATALOG.items():
            if area_type not in template.get("area_types", {"city"}):
                continue
            eligible.append(key)
            weights.append(template["weight"])

        if not eligible:
            return None

        event_key = self.rng.choices(eligible, weights=weights, k=1)[0]
        template = _WORLD_EVENT_CATALOG[event_key]
        duration = self.rng.randint(template["duration_lo"], template["duration_hi"]) * _WORLD_EVENT_DURATION_SCALE
        event_id = int(state.get("next_event_id", 1))
        state["next_event_id"] = event_id + 1

        flavor = self.rng.choice(template["flavor_start"])
        guard_count = 0
        if "guard_count_lo" in template:
            guard_count = self.rng.randint(
                int(template.get("guard_count_lo", 0)),
                int(template.get("guard_count_hi", template.get("guard_count_lo", 0))),
            )

        return {
            "id": event_id,
            "key": event_key,
            "label": template["label"],
            "cx": cx,
            "cy": cy,
            "area_type": area_type,
            "district_type": district_type,
            "start_tick": tick,
            "end_tick": tick + duration,
            "trade_buy_mult": template.get("trade_buy_mult", 1.0),
            "trade_sell_mult": template.get("trade_sell_mult", 1.0),
            "pressure_delta": template.get("pressure_delta", 0),
            "observer_notice_delta": template.get("observer_notice_delta", 0),
            "fixture_light_mult": template.get("fixture_light_mult", 1.0),
            "spawn_market_stall": bool(template.get("spawn_market_stall")),
            "guard_count": guard_count,
            "spawn_seed": self.rng.randrange(1, 2_147_483_648),
            "spawned_entity_ids": [],
            "spawned_property_ids": [],
            "materialized": False,
            "flavor_start": flavor,
            "flavor_end": self.rng.choice(template["flavor_end"]),
        }

    def update(self):
        sim = self.sim
        tick = sim.tick
        state = _world_events_state(sim)

        still_active = []
        for event in state["active"]:
            self._normalize_event_runtime_state(event)
            if tick >= int(event.get("end_tick", 0)):
                self._dematerialize_event(event)
                sim.emit(Event(
                    "world_event_ended",
                    event_id=event["id"],
                    key=event["key"],
                    label=event["label"],
                    cx=event["cx"],
                    cy=event["cy"],
                    district_type=event.get("district_type", "unknown"),
                    flavor=event.get("flavor_end", ""),
                    trade_buy_mult=event.get("trade_buy_mult", 1.0),
                    trade_sell_mult=event.get("trade_sell_mult", 1.0),
                    pressure_delta=event.get("pressure_delta", 0),
                    observer_notice_delta=event.get("observer_notice_delta", 0),
                    fixture_light_mult=event.get("fixture_light_mult", 1.0),
                    spawn_market_stall=bool(event.get("spawn_market_stall")),
                    guard_count=event.get("guard_count", 0),
                ))
                pdelta = int(event.get("pressure_delta", 0))
                if pdelta != 0:
                    _apply_pressure_delta(
                        sim,
                        delta=-(pdelta // 2),
                        source="world_event_end",
                        reason=f"{event['label']} ended",
                        source_event=event["key"],
                    )
                state["history"].append({
                    "id": event["id"],
                    "key": event["key"],
                    "cx": event["cx"],
                    "cy": event["cy"],
                    "end_tick": tick,
                })
                if len(state["history"]) > 32:
                    del state["history"][:-32]
            else:
                self._sync_event_materialization(event)
                still_active.append(event)
        state["active"] = still_active

        if tick < int(state.get("next_roll_tick", 0)):
            return
        state["next_roll_tick"] = tick + _WORLD_EVENT_ROLL_INTERVAL

        if len(state["active"]) >= _WORLD_EVENT_MAX_ACTIVE:
            return

        event = self._roll_event(state, tick)
        if not event:
            return

        state["active"].append(event)

        pdelta = int(event.get("pressure_delta", 0))
        if pdelta != 0:
            _apply_pressure_delta(
                sim,
                delta=pdelta,
                source="world_event_start",
                reason=f"{event['label']} in {event.get('district_type', 'district')} district",
                source_event=event["key"],
            )

        sim.emit(Event(
            "world_event_started",
            event_id=event["id"],
            key=event["key"],
            label=event["label"],
            cx=event["cx"],
            cy=event["cy"],
            district_type=event.get("district_type", "unknown"),
            flavor=event.get("flavor_start", ""),
            duration=int(event["end_tick"]) - int(event["start_tick"]),
            trade_buy_mult=event.get("trade_buy_mult", 1.0),
            trade_sell_mult=event.get("trade_sell_mult", 1.0),
            pressure_delta=pdelta,
            observer_notice_delta=event.get("observer_notice_delta", 0),
            fixture_light_mult=event.get("fixture_light_mult", 1.0),
            spawn_market_stall=bool(event.get("spawn_market_stall")),
            guard_count=event.get("guard_count", 0),
        ))
        self._sync_event_materialization(event)
