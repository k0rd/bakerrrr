"""World-event runtime extracted from ``game/systems.py``.

This seam keeps the public import surface stable by letting
``game/systems.py`` re-export the helpers and ``WorldEventsSystem`` while the
ambient-event runtime evolves outside the monolith.
"""

import random

from engine.events import Event
from engine.systems import System
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

    def _sync_event_materialization(self, event):
        self._normalize_event_runtime_state(event)
        if self._event_chunk_is_active(event):
            if not event.get("materialized"):
                self._materialize_event(event)
            if event.get("materialized"):
                self._update_guard_patrols(event)
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
