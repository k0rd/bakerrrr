import random

from .buildings import layout_chunk_building, world_building_id
from .ecs import ECS
from .events import Event, EventBus
from .underground import chunk_underground_site_plans
from .sites import layout_chunk_site, site_entry_front_cell, site_layout_reserved_footprints
from .world import World, normalize_building_levels
from .eventlog import EventLog
from .tilemap import Tile, TileMap
from game.appearance import AppearanceManager
from game.components import AI, CreatureIdentity, PlayerAssets, Position
from game.items import prepare_ground_item_stack_metadata
from game.property_access import COMMON_AREA_ROOM_KINDS
from game.system_support.actor_attention_runtime import actor_attention_state, warmth_protected_chunks
from game.system_support.fire_runtime import fire_protected_chunks

class Simulation:

    def __init__(
        self,
        seed,
        mutators=None,
        map_width=64,
        map_height=32,
        max_floors=3,
        chunk_size=16,
        active_chunk_radius=1,
        loaded_chunk_radius=2,
    ):

        self.seed = seed
        self.log = EventLog()
        self.ecs = ECS()
        self.events = EventBus()
        self.world = World(seed)
        self.tilemap = TileMap(map_width, map_height, max_floors=max_floors)
        self.chunk_size = chunk_size
        self.active_chunk_radius = active_chunk_radius
        self.loaded_chunk_radius = loaded_chunk_radius
        self.active_chunk = None
        self.active_chunk_coord = None
        self.chunk_detail = {}
        self.realized_chunks = set()
        self.chunk_property_records = {}
        self.chunk_ground_item_records = {}
        self.chunk_population_records = {}
        self.chunk_flora_records = {}
        self.chunk_population_membership = {}
        self.chunk_saved_states = {}
        self._pending_stream_unloads = set()
        self._stream_unload_flush_active = False
        self.chunk_entity_index = {}
        self.entity_chunk_membership = {}
        self.entity_identity_records = {}
        self.property_registry_dirty = False
        self.properties = {}
        self.property_anchor_index = {}
        self.property_cover_index = {}
        self.property_order = {}
        self.next_property_order = 0
        self.door_states = {}
        self.fixture_power_cuts = {}
        self.camera_disabled = {}
        self.contractors = {}
        self.fire_state = {}
        self.disguise_state = None
        self.structure_cells = {}
        self.next_property_id = 1
        self.ground_items = {}
        self.ground_item_index = {}
        self.ground_item_order = {}
        self.next_ground_item_order = 0
        self.next_ground_item_id = 1
        self.next_item_instance_id = 1
        self.flora_patches = {}
        self.cultivation_records = {}
        self.next_cultivation_id = 1
        self.cultivation_gardener_cooldowns = {}
        self.meaningful_objects = {"objects": {}, "actor_index": {}, "place_index": {}, "player_knowledge": {}}
        self.next_meaningful_object_id = 1
        self.projectiles = {}
        self.next_projectile_id = 1
        self.stores = {}
        self.turn_based = False
        self.turn_advance_requested = False
        self.zoom_mode = "city"
        self.city_anchor_by_chunk = {}
        self.npc_move_tick_stride = 2
        self.world_traits = {}
        self.organization_index = {}
        self.world_rumors = []
        self.active_ejections = {}
        self.overworld_markers_by_eid = {}
        self.next_overworld_marker_id_by_eid = {}
        self.pause_reasons = set()
        self.live_timeskip = {}
        self.look_ui = {
            "active": False,
            "mode": "city",
            "purpose": "inspect",
            "x": 0,
            "y": 0,
            "z": 0,
            "chunk_x": 0,
            "chunk_y": 0,
            "inspect_text": "",
        }
        self.visibility_state = {
            "tick": -1,
            "observers": {},
            "player_eid": None,
            "player_origin": None,
            "player_radius": 0,
            "player_visible": set(),
            "player_explored": set(),
        }

        self.systems = []
        self.appearance = AppearanceManager(self)

        self.mutators = mutators or []

        self.tick = 0
        self._bind_runtime_state()
        self.running = True
        self.character_name = None

    def _log_tick(self):
        return int(getattr(self, "tick", 0))

    def _bind_runtime_state(self):
        if isinstance(getattr(self, "log", None), EventLog):
            self.log.default_tick_source = self._log_tick
        if not isinstance(getattr(self, "door_states", None), dict):
            self.door_states = {}
        if not isinstance(getattr(self, "fixture_power_cuts", None), dict):
            self.fixture_power_cuts = {}
        if not isinstance(getattr(self, "camera_disabled", None), dict):
            self.camera_disabled = {}
        if not isinstance(getattr(self, "contractors", None), dict):
            self.contractors = {}
        if not isinstance(getattr(self, "fire_state", None), dict):
            self.fire_state = {}
        if not isinstance(getattr(self, "live_timeskip", None), dict):
            self.live_timeskip = {}
        if not isinstance(getattr(self, "active_ejections", None), dict):
            self.active_ejections = {}
        if not hasattr(self, "disguise_state"):
            self.disguise_state = None
        if not hasattr(self, "equipped_container"):
            self.equipped_container = None
        if not isinstance(getattr(self, "cache_inventories", None), dict):
            self.cache_inventories = {}
        if not isinstance(getattr(self, "chunk_population_membership", None), dict):
            self.chunk_population_membership = {}
        if not isinstance(getattr(self, "_pending_stream_unloads", None), set):
            self._pending_stream_unloads = set()
        if not isinstance(getattr(self, "_stream_unload_flush_active", None), bool):
            self._stream_unload_flush_active = False
        if not isinstance(getattr(self, "chunk_entity_index", None), dict):
            self.chunk_entity_index = {}
        if not isinstance(getattr(self, "entity_chunk_membership", None), dict):
            self.entity_chunk_membership = {}
        if not isinstance(getattr(self, "entity_identity_records", None), dict):
            self.entity_identity_records = {}
        if not isinstance(getattr(self, "flora_patches", None), dict):
            self.flora_patches = {}
        if not isinstance(getattr(self, "chunk_flora_records", None), dict):
            self.chunk_flora_records = {}
        if not isinstance(getattr(self, "cultivation_records", None), dict):
            self.cultivation_records = {}
        if not hasattr(self, "next_cultivation_id"):
            self.next_cultivation_id = 1
        if not isinstance(getattr(self, "cultivation_gardener_cooldowns", None), dict):
            self.cultivation_gardener_cooldowns = {}
        if not isinstance(getattr(self, "hunting_carcasses", None), dict):
            self.hunting_carcasses = {}
        if not hasattr(self, "next_hunting_carcass_id"):
            self.next_hunting_carcass_id = 1
        if not isinstance(getattr(self, "npc_relationships", None), dict):
            self.npc_relationships = {}
        if not isinstance(getattr(self, "npc_relationship_tastes", None), dict):
            self.npc_relationship_tastes = {}
        if not isinstance(getattr(self, "meaningful_objects", None), dict):
            self.meaningful_objects = {"objects": {}, "actor_index": {}, "place_index": {}, "player_knowledge": {}}
        else:
            self.meaningful_objects.setdefault("objects", {})
            self.meaningful_objects.setdefault("actor_index", {})
            self.meaningful_objects.setdefault("place_index", {})
            self.meaningful_objects.setdefault("player_knowledge", {})
        if not hasattr(self, "next_meaningful_object_id"):
            self.next_meaningful_object_id = 1
        if not isinstance(getattr(self, "local_trade_pressures", None), dict):
            self.local_trade_pressures = {"properties": {}, "chunks": {}}
        else:
            self.local_trade_pressures.setdefault("properties", {})
            self.local_trade_pressures.setdefault("chunks", {})
        self._bind_tilemap_runtime_state()

    def _bind_tilemap_runtime_state(self):
        tilemap = getattr(self, "tilemap", None)
        if tilemap is None:
            return
        tilemap.on_add_entity = self._on_tilemap_add_entity
        tilemap.on_move_entity = self._on_tilemap_move_entity
        tilemap.on_remove_entity = self._on_tilemap_remove_entity

    def _normalize_chunk_key(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return None
        try:
            return (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            return None

    def _track_chunk_entity(self, eid, chunk):
        key = self._normalize_chunk_key(chunk)
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            return None
        if key is None:
            return None

        previous = self._normalize_chunk_key(self.entity_chunk_membership.get(int_eid))
        if previous is not None and previous != key:
            bucket = self.chunk_entity_index.get(previous)
            if bucket:
                bucket.discard(int_eid)
                if not bucket:
                    self.chunk_entity_index.pop(previous, None)

        bucket = self.chunk_entity_index.setdefault(key, set())
        bucket.add(int_eid)
        self.entity_chunk_membership[int_eid] = key
        return key

    def _untrack_chunk_entity(self, eid, *, chunk=None):
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            return None

        key = self._normalize_chunk_key(chunk)
        if key is None:
            key = self._normalize_chunk_key(self.entity_chunk_membership.pop(int_eid, None))
        else:
            self.entity_chunk_membership.pop(int_eid, None)

        if key is None:
            return None

        bucket = self.chunk_entity_index.get(key)
        if bucket:
            bucket.discard(int_eid)
            if not bucket:
                self.chunk_entity_index.pop(key, None)
        return key

    def _on_tilemap_add_entity(self, eid, x, y, z=0):
        self._track_chunk_entity(eid, self.chunk_coords(int(x), int(y)))

    def _on_tilemap_move_entity(self, eid, oldx, oldy, newx, newy, oldz=0, newz=0):
        old_chunk = self.chunk_coords(int(oldx), int(oldy))
        new_chunk = self.chunk_coords(int(newx), int(newy))
        if old_chunk != new_chunk:
            self._untrack_chunk_entity(eid, chunk=old_chunk)
        self._track_chunk_entity(eid, new_chunk)
        if old_chunk != new_chunk:
            self.flush_stream_unloads()

    def _on_tilemap_remove_entity(self, eid, x, y, z=0):
        self._untrack_chunk_entity(eid, chunk=self.chunk_coords(int(x), int(y)))

    def entity_ids_in_chunk(self, chunk):
        key = self._normalize_chunk_key(chunk)
        if key is None:
            return ()
        return tuple(sorted(self.chunk_entity_index.get(key, ())))

    def rebuild_chunk_entity_index(self):
        self.chunk_entity_index = {}
        self.entity_chunk_membership = {}
        positions = self.ecs.get(Position)
        for eid, pos in positions.items():
            try:
                key = self.chunk_coords(int(pos.x), int(pos.y))
            except (TypeError, ValueError):
                continue
            self._track_chunk_entity(eid, key)

    def _entity_identity_record_from_components(self, eid, component_map=None):
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            int_eid = eid
        identity = None
        ai = None
        if isinstance(component_map, dict):
            identity = component_map.get(CreatureIdentity)
            ai = component_map.get(AI)
            if identity is None or ai is None:
                for component_type, component in component_map.items():
                    name = str(getattr(component_type, "__name__", component_type) or "")
                    if identity is None and name == "CreatureIdentity":
                        identity = component
                    elif ai is None and name == "AI":
                        ai = component
        else:
            identity = self.ecs.get(CreatureIdentity).get(eid)
            ai = self.ecs.get(AI).get(eid)

        record = {"eid": int_eid}
        if identity is not None:
            display_name = str(identity.display_name() or "").replace("_", " ").strip()
            fields = {
                "display_name": display_name,
                "personal_name": getattr(identity, "personal_name", ""),
                "common_name": getattr(identity, "common_name", ""),
                "species": getattr(identity, "species", ""),
                "creature_type": getattr(identity, "creature_type", ""),
                "taxonomy_class": getattr(identity, "taxonomy_class", ""),
                "gender_identity": getattr(identity, "gender_identity", ""),
                "pronoun_set": getattr(identity, "pronoun_set", ""),
            }
            for key, value in fields.items():
                text = str(value or "").replace("_", " ").strip()
                if text:
                    record[key] = text
        if ai is not None:
            role = str(getattr(ai, "role", "") or "").replace("_", " ").strip()
            if role:
                record["role"] = role
        if len(record) <= 1:
            return None
        return record

    def remember_entity_identity(self, eid, *, reason=""):
        record = self._entity_identity_record_from_components(eid)
        if not record:
            return None
        try:
            key = int(eid)
        except (TypeError, ValueError):
            key = eid
        existing = self.entity_identity_records.get(key)
        if isinstance(existing, dict):
            merged = dict(existing)
            merged.update({k: v for k, v in record.items() if v not in (None, "")})
            record = merged
        reason_text = str(reason or "").strip().lower()
        if reason_text:
            record["last_reason"] = reason_text
        record["last_seen_tick"] = int(getattr(self, "tick", 0) or 0)
        self.entity_identity_records[key] = dict(record)
        return dict(record)

    def _saved_entity_identity_record(self, eid):
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            int_eid = eid
        for snapshot in tuple(getattr(self, "chunk_saved_states", {}).values()):
            if not isinstance(snapshot, dict):
                continue
            entities = snapshot.get("entities", {})
            if not isinstance(entities, dict):
                continue
            component_map = entities.get(int_eid)
            if component_map is None:
                component_map = entities.get(str(int_eid))
            record = self._entity_identity_record_from_components(int_eid, component_map=component_map)
            if record:
                return record
        return None

    def entity_identity_record(self, eid):
        try:
            key = int(eid)
        except (TypeError, ValueError):
            key = eid
        live = self._entity_identity_record_from_components(eid)
        if live:
            self.entity_identity_records[key] = dict(live)
            return live
        record = self.entity_identity_records.get(key)
        if isinstance(record, dict):
            return dict(record)
        record = self._saved_entity_identity_record(eid)
        if record:
            self.entity_identity_records[key] = dict(record)
            return record
        return None

    def track_population_entity(self, eid, *, chunk=None):
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            return None

        if chunk is None:
            pos = self.ecs.get(Position).get(int_eid)
            if pos is None:
                return None
            try:
                chunk = self.chunk_coords(int(pos.x), int(pos.y))
            except (TypeError, ValueError):
                return None
        key = self._normalize_chunk_key(chunk)
        if key is None:
            return None

        previous = self._normalize_chunk_key(self.chunk_population_membership.get(int_eid))
        if previous is not None and previous != key:
            roster = [
                int(value)
                for value in tuple(self.chunk_population_records.get(previous, ()) or ())
                if int(value) != int_eid
            ]
            if roster:
                self.chunk_population_records[previous] = roster
            else:
                self.chunk_population_records.pop(previous, None)

        roster = [
            int(value)
            for value in tuple(self.chunk_population_records.get(key, ()) or ())
            if int(value) != int_eid
        ]
        roster.append(int_eid)
        self.chunk_population_records[key] = roster
        self.chunk_population_membership[int_eid] = key
        return key

    def untrack_population_entity(self, eid, *, chunk=None):
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            return None

        key = self._normalize_chunk_key(chunk)
        if key is None:
            key = self._normalize_chunk_key(self.chunk_population_membership.pop(int_eid, None))
            if key is None:
                pos = self.ecs.get(Position).get(int_eid)
                if pos is not None:
                    try:
                        key = self.chunk_coords(int(pos.x), int(pos.y))
                    except (TypeError, ValueError):
                        key = None
        else:
            self.chunk_population_membership.pop(int_eid, None)

        if key is None:
            return None

        roster = [
            int(value)
            for value in tuple(self.chunk_population_records.get(key, ()) or ())
            if int(value) != int_eid
        ]
        if roster:
            self.chunk_population_records[key] = roster
        else:
            self.chunk_population_records.pop(key, None)
        return key

    def door_state_at(self, x, y, z=0):
        key = self._coord_key(x, y, z)
        if key is None:
            return None
        state = self.door_states.get(key)
        return state if isinstance(state, dict) else None

    def set_door_state(
        self,
        x,
        y,
        z=0,
        *,
        open=None,
        locked=None,
        kind=None,
        ordinary=None,
        property_id=None,
        auto_managed=None,
        broken=None,
    ):
        key = self._coord_key(x, y, z)
        if key is None:
            return None

        state = self.door_states.get(key)
        if not isinstance(state, dict):
            state = {}

        if open is not None:
            state["open"] = bool(open)
        if locked is not None:
            state["locked"] = bool(locked)
        if kind is not None:
            state["kind"] = str(kind or "door").strip().lower() or "door"
        if ordinary is not None:
            state["ordinary"] = bool(ordinary)
        if property_id is not None:
            state["property_id"] = str(property_id).strip() or None
        if auto_managed is not None:
            state["auto_managed"] = bool(auto_managed)
        if broken is not None:
            state["broken"] = bool(broken)

        self.door_states[key] = state
        tile = self.tilemap.tile_at(x, y, z)
        if tile is not None:
            self.apply_door_state(x, y, z)
        return state

    def apply_door_state(self, x, y, z=0):
        state = self.door_state_at(x, y, z)
        tile = self.tilemap.tile_at(x, y, z)
        if not state or tile is None:
            return False

        structure = self.structure_at(int(x), int(y), int(z))
        property_id = str((state or {}).get("property_id", "") or "").strip()
        if (
            not isinstance(structure, dict)
            and not (property_id and property_id in getattr(self, "properties", {}))
            and not self._door_aperture_context_valid(int(x), int(y), int(z), tile=tile)
        ):
            return False

        kind = str(state.get("kind", "door") or "door").strip().lower() or "door"
        if kind not in {"door", "side_door", "service_door", "employee_door"}:
            return False

        if bool(state.get("broken", False)):
            tile.walkable = True
            tile.transparent = True
            tile.set_appearance(
                glyph="/",
                color="feature_breach",
                semantic_id="feature_breach",
            )
            return True

        is_open = bool(state.get("open", False))
        tile.walkable = bool(is_open)
        tile.transparent = bool(is_open)
        tile.set_appearance(
            glyph="'" if is_open else "+",
            color="feature_door",
            semantic_id="feature_door",
        )
        return True

    def _door_aperture_context_valid(self, x, y, z=0, *, tile=None):
        door_tile = tile if tile is not None else self.tilemap.tile_at(int(x), int(y), int(z))
        if door_tile is None:
            return False

        def _looks_like_wall(cx, cy):
            neighbor = self.tilemap.tile_at(int(cx), int(cy), int(z))
            if neighbor is None:
                return False
            semantic = str(getattr(neighbor, "semantic_id", "") or "").strip().lower()
            glyph = str(getattr(neighbor, "glyph", "") or "").strip()
            return semantic == "wall_building" or glyph == "#"

        def _looks_like_floor(cx, cy):
            neighbor = self.tilemap.tile_at(int(cx), int(cy), int(z))
            if neighbor is None:
                return False
            semantic = str(getattr(neighbor, "semantic_id", "") or "").strip().lower()
            glyph = str(getattr(neighbor, "glyph", "") or "").strip()
            if semantic == "floor_building_fill":
                return True
            return glyph in {".", "'", ","} and bool(getattr(neighbor, "walkable", False))

        return (
            _looks_like_wall(x, y - 1)
            and _looks_like_wall(x, y + 1)
            and _looks_like_floor(x - 1, y)
            and _looks_like_floor(x + 1, y)
        ) or (
            _looks_like_wall(x - 1, y)
            and _looks_like_wall(x + 1, y)
            and _looks_like_floor(x, y - 1)
            and _looks_like_floor(x, y + 1)
        )

    def reapply_door_states(self, *, chunk=None):
        target_chunk = self._normalize_chunk_key(chunk) if chunk is not None else None
        count = 0
        for key in tuple(sorted(getattr(self, "door_states", {}).keys())):
            if not isinstance(key, (tuple, list)) or len(key) < 3:
                continue
            try:
                x = int(key[0])
                y = int(key[1])
                z = int(key[2])
            except (TypeError, ValueError):
                continue
            if target_chunk is not None and self.chunk_coords(x, y) != target_chunk:
                continue
            if self.apply_door_state(x, y, z):
                count += 1
        return count

    def set_time_paused(self, active=True, *, reason="modal"):
        reason_key = str(reason or "modal").strip().lower() or "modal"
        if active:
            self.pause_reasons.add(reason_key)
        else:
            self.pause_reasons.discard(reason_key)
        return bool(self.pause_reasons)

    def is_time_paused(self):
        return bool(self.pause_reasons)

    def advance_time(self, ticks, *, reason="time_skip", emit_event=True, **event_data):
        try:
            delta = int(ticks)
        except (TypeError, ValueError):
            delta = 0
        delta = max(0, delta)
        if delta <= 0:
            return 0

        start_tick = int(self.tick)
        end_tick = start_tick + delta
        self.tick = end_tick

        if emit_event:
            payload = {
                "ticks": delta,
                "from_tick": start_tick,
                "to_tick": end_tick,
                "reason": str(reason or "time_skip").strip().lower() or "time_skip",
            }
            payload.update(event_data)
            self.emit(Event("time_advanced", **payload))
        return delta

    def chunk_coords(self, x, y):
        return (x // self.chunk_size, y // self.chunk_size)

    def stream_world(self, focus_x, focus_y, *, manage_unloads=True):
        cx, cy = self.chunk_coords(focus_x, focus_y)
        previous_loaded = dict(getattr(self.world, "loaded_chunks", {}) or {})
        report = self.world.stream_chunks(
            cx,
            cy,
            active_radius=self.active_chunk_radius,
            loaded_radius=self.loaded_chunk_radius,
        )

        protected_chunks = set(fire_protected_chunks(self))
        if protected_chunks and isinstance(report, dict):
            unloaded = []
            for raw_chunk in tuple(report.get("unloaded", ()) or ()):
                try:
                    chunk = (int(raw_chunk[0]), int(raw_chunk[1]))
                except (TypeError, ValueError, IndexError):
                    continue
                if chunk not in protected_chunks:
                    unloaded.append(chunk)
                    continue
                previous = previous_loaded.get(chunk)
                if isinstance(previous, dict):
                    self.world.loaded_chunks[chunk] = dict(previous)
                else:
                    detail = "active" if chunk == (cx, cy) else "coarse"
                    self.world.loaded_chunks[chunk] = {
                        "chunk": self.world.get_chunk(chunk[0], chunk[1]),
                        "detail": detail,
                    }
            report["unloaded"] = tuple(unloaded)

        if isinstance(report, dict):
            warmth_protected = set(warmth_protected_chunks(self, report.get("unloaded", ())))
            attention_state = actor_attention_state(self)
            social_warmth_protected = set(attention_state.get("social_warmth_protected_chunks", set()) or ())
            area_warmth_protected = set(attention_state.get("area_warmth_protected_chunks", set()) or ())
            if warmth_protected:
                unloaded = []
                detail_changed = list(report.get("detail_changed", ()) or ())
                for raw_chunk in tuple(report.get("unloaded", ()) or ()):
                    try:
                        chunk = (int(raw_chunk[0]), int(raw_chunk[1]))
                    except (TypeError, ValueError, IndexError):
                        continue
                    if chunk not in warmth_protected:
                        unloaded.append(chunk)
                        continue
                    previous = previous_loaded.get(chunk)
                    if isinstance(previous, dict):
                        retained = dict(previous)
                        retained["detail"] = "coarse"
                        self.world.loaded_chunks[chunk] = retained
                    else:
                        self.world.loaded_chunks[chunk] = {
                            "chunk": self.world.get_chunk(chunk[0], chunk[1]),
                            "detail": "coarse",
                        }
                    if isinstance(previous, dict) and previous.get("detail") != "coarse" and chunk not in detail_changed:
                        detail_changed.append(chunk)
                report["unloaded"] = tuple(unloaded)
                report["detail_changed"] = sorted(detail_changed)
            report["warmth_protected"] = tuple(sorted(warmth_protected))
            report["social_warmth_protected"] = tuple(sorted(social_warmth_protected))
            report["area_warmth_protected"] = tuple(sorted(area_warmth_protected))
            report["loaded_count"] = len(self.world.loaded_chunks)
            report["active_count"] = sum(1 for data in self.world.loaded_chunks.values() if data.get("detail") == "active")
            report["changed"] = bool(report.get("changed")) or bool(warmth_protected)

        self.active_chunk_coord = (cx, cy)
        self.active_chunk = self.world.get_chunk(cx, cy)
        self.chunk_detail = {
            key: data["detail"]
            for key, data in self.world.loaded_chunks.items()
        }

        if manage_unloads:
            self.flush_stream_unloads(report)

        return report

    def detail_for_xy(self, x, y):
        coord = self.chunk_coords(x, y)
        return self.chunk_detail.get(coord, "unloaded")

    def _managed_stream_unload_candidates(self):
        candidates = set()
        for source_name in (
            "chunk_population_records",
            "chunk_ground_item_records",
            "chunk_property_records",
            "chunk_entity_index",
        ):
            source = getattr(self, source_name, None)
            if not isinstance(source, dict):
                continue
            for raw_key in tuple(source.keys()):
                key = self._normalize_chunk_key(raw_key)
                if key is not None:
                    candidates.add(key)
        return candidates

    def _stream_unload_blockers(self, key):
        key = self._normalize_chunk_key(key)
        if key is None:
            return ("invalid_chunk",)

        loaded = getattr(getattr(self, "world", None), "loaded_chunks", {}) or {}
        if key in loaded:
            return ("loaded",)
        memberships = getattr(self, "chunk_population_membership", {}) or {}
        population_records = getattr(self, "chunk_population_records", {}) or {}
        chunk_roster = set()
        if isinstance(population_records, dict):
            for raw_eid in tuple(population_records.get(key, ()) or ()):
                try:
                    chunk_roster.add(int(raw_eid))
                except (TypeError, ValueError):
                    continue
        player_eid = getattr(self, "player_eid", None)
        try:
            player_eid = int(player_eid) if player_eid is not None else None
        except (TypeError, ValueError):
            player_eid = None
        player_assets = self.ecs.get(PlayerAssets) if getattr(self, "ecs", None) is not None else {}
        blockers = []
        for eid in tuple(self.entity_ids_in_chunk(key) or ()):
            try:
                int_eid = int(eid)
            except (TypeError, ValueError):
                blockers.append(eid)
                continue
            if int_eid == player_eid or int_eid in player_assets:
                blockers.append(int_eid)
                continue
            if memberships.get(int_eid) == key or int_eid in chunk_roster:
                continue
        return tuple(blockers)

    def flush_stream_unloads(self, report=None):
        if bool(getattr(self, "_stream_unload_flush_active", False)):
            return {
                "persisted": (),
                "dropped": (),
                "deferred": tuple(sorted(getattr(self, "_pending_stream_unloads", set()) or set())),
                "merged_saved": (),
            }

        pending = getattr(self, "_pending_stream_unloads", None)
        if not isinstance(pending, set):
            pending = set()
            self._pending_stream_unloads = pending

        loaded = getattr(getattr(self, "world", None), "loaded_chunks", {}) or {}
        candidates = set()
        explicit_unloaded = set()
        if isinstance(report, dict):
            for raw_key in tuple(report.get("unloaded", ()) or ()):
                key = self._normalize_chunk_key(raw_key)
                if key is not None:
                    explicit_unloaded.add(key)
        candidates.update(explicit_unloaded)
        candidates.update(pending)
        candidates.update(
            key
            for key in self._managed_stream_unload_candidates()
            if key not in loaded
        )

        persisted = []
        dropped = []
        deferred = []
        merged_saved = []
        attempted_unload = False
        self._stream_unload_flush_active = True
        try:
            pending.clear()
            if candidates:
                from .persistence import merge_unload_chunk_state, unload_chunk_state

                saved_states = getattr(self, "chunk_saved_states", {}) or {}
                for key in sorted(candidates):
                    if key in loaded:
                        continue
                    blockers = self._stream_unload_blockers(key)
                    if blockers:
                        pending.add(key)
                        deferred.append(key)
                        continue
                    if isinstance(saved_states, dict) and key in saved_states:
                        snapshot = merge_unload_chunk_state(self, key, rebuild_indexes=False)
                        merged_saved.append(key)
                    else:
                        snapshot = unload_chunk_state(self, key, rebuild_indexes=False)
                    attempted_unload = True
                    if snapshot is None:
                        dropped.append(key)
                    else:
                        persisted.append(key)
            if attempted_unload and hasattr(self, "rebuild_spatial_indexes"):
                self.rebuild_spatial_indexes()
        finally:
            self._stream_unload_flush_active = False

        result = {
            "persisted": tuple(sorted(persisted)),
            "dropped": tuple(sorted(dropped)),
            "deferred": tuple(sorted(deferred)),
            "merged_saved": tuple(sorted(merged_saved)),
        }
        if isinstance(report, dict):
            report["unloaded_persisted"] = result["persisted"]
            report["unloaded_dropped"] = result["dropped"]
            report["unloaded_deferred"] = result["deferred"]
            report["unloaded_merged_saved"] = result["merged_saved"]
            if persisted or dropped or merged_saved:
                report["managed_unload_changed"] = True
        return result

    def chunk_origin(self, cx, cy):
        return (cx * self.chunk_size, cy * self.chunk_size)

    def _coord_key(self, x, y, z=0):
        try:
            return (int(x), int(y), int(z))
        except (TypeError, ValueError):
            return None

    def _property_footprint_excluded_cells(self, prop):
        if not isinstance(prop, dict):
            return frozenset()

        metadata = prop.get("metadata")
        if not isinstance(metadata, dict):
            return frozenset()

        configured = metadata.get("footprint_excluded_cells")
        excluded = set()
        if isinstance(configured, (list, tuple, set, frozenset)):
            for cell in configured:
                if isinstance(cell, dict):
                    try:
                        excluded.add((int(cell.get("x")), int(cell.get("y"))))
                    except (TypeError, ValueError):
                        continue
                elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
                    try:
                        excluded.add((int(cell[0]), int(cell[1])))
                    except (TypeError, ValueError):
                        continue
            if excluded or configured == []:
                return frozenset(excluded)

        footprint = metadata.get("footprint")
        building_id = str(metadata.get("building_id", "") or "").strip()
        if not isinstance(footprint, dict) or not building_id:
            return frozenset()

        try:
            left = int(footprint.get("left"))
            right = int(footprint.get("right"))
            top = int(footprint.get("top"))
            bottom = int(footprint.get("bottom"))
            base_z = int(prop.get("z", 0))
            floors = max(1, int(metadata.get("floors", 1)))
            basement_levels = max(0, int(metadata.get("basement_levels", 0)))
        except (TypeError, ValueError):
            return frozenset()

        covered_xy = set()
        for (cell_x, cell_y, cell_z), info in getattr(self, "structure_cells", {}).items():
            if str((info or {}).get("building_id", "")).strip() != building_id:
                continue
            if not (base_z - basement_levels <= int(cell_z) < base_z + floors):
                continue
            covered_xy.add((int(cell_x), int(cell_y)))

        if not covered_xy:
            return frozenset()

        for cell_y in range(top, bottom + 1):
            for cell_x in range(left, right + 1):
                if (int(cell_x), int(cell_y)) not in covered_xy:
                    excluded.add((int(cell_x), int(cell_y)))

        metadata["footprint_excluded_cells"] = [
            {"x": int(cell_x), "y": int(cell_y)}
            for cell_x, cell_y in sorted(excluded)
        ]
        return frozenset(excluded)

    def _property_explicit_footprint_cells(self, prop):
        if not isinstance(prop, dict):
            return frozenset()

        metadata = prop.get("metadata")
        if not isinstance(metadata, dict):
            return frozenset()

        configured = metadata.get("footprint_cells")
        cells = set()
        if isinstance(configured, (list, tuple, set, frozenset)):
            for cell in configured:
                if isinstance(cell, dict):
                    try:
                        cells.add((int(cell.get("x")), int(cell.get("y"))))
                    except (TypeError, ValueError):
                        continue
                elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
                    try:
                        cells.add((int(cell[0]), int(cell[1])))
                    except (TypeError, ValueError):
                        continue
            if cells or configured == []:
                return frozenset(cells)

        building_id = str(metadata.get("building_id", "") or "").strip()
        if not building_id:
            return frozenset()

        footprint = metadata.get("footprint")
        if not isinstance(footprint, dict):
            return frozenset()

        try:
            left = int(footprint.get("left"))
            right = int(footprint.get("right"))
            top = int(footprint.get("top"))
            bottom = int(footprint.get("bottom"))
            base_z = int(prop.get("z", 0))
            floors = max(1, int(metadata.get("floors", 1)))
            basement_levels = max(0, int(metadata.get("basement_levels", 0)))
        except (TypeError, ValueError):
            return frozenset()

        for (cell_x, cell_y, cell_z), info in getattr(self, "structure_cells", {}).items():
            if str((info or {}).get("building_id", "")).strip() != building_id:
                continue
            if not (base_z - basement_levels <= int(cell_z) < base_z + floors):
                continue
            if not (left <= int(cell_x) <= right and top <= int(cell_y) <= bottom):
                continue
            cells.add((int(cell_x), int(cell_y)))

        if not cells:
            return frozenset()

        metadata["footprint_cells"] = [
            {"x": int(cell_x), "y": int(cell_y)}
            for cell_x, cell_y in sorted(cells)
        ]
        return frozenset(cells)

    def _property_cover_coords(self, prop):
        if not isinstance(prop, dict):
            return ()

        if str(prop.get("kind", "")).strip().lower() != "building":
            return ()

        metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
        footprint = metadata.get("footprint")
        if not isinstance(footprint, dict):
            return ()

        try:
            left = int(footprint.get("left"))
            right = int(footprint.get("right"))
            top = int(footprint.get("top"))
            bottom = int(footprint.get("bottom"))
            base_z = int(prop.get("z", 0))
            floors = max(1, int(metadata.get("floors", 1)))
            basement_levels = max(0, int(metadata.get("basement_levels", 0)))
        except (TypeError, ValueError):
            return ()

        explicit_cells = self._property_explicit_footprint_cells(prop)
        excluded = self._property_footprint_excluded_cells(prop)
        coords = []
        for cell_z in range(base_z - basement_levels, base_z + floors):
            if explicit_cells:
                for cell_x, cell_y in explicit_cells:
                    coords.append((int(cell_x), int(cell_y), int(cell_z)))
                continue
            for cell_y in range(top, bottom + 1):
                for cell_x in range(left, right + 1):
                    if (int(cell_x), int(cell_y)) in excluded:
                        continue
                    coords.append((cell_x, cell_y, cell_z))
        return coords

    def _index_property_record(self, property_id, prop):
        key = self._coord_key(prop.get("x"), prop.get("y"), prop.get("z", 0)) if isinstance(prop, dict) else None
        if key is None:
            return
        if property_id not in self.property_order:
            self.property_order[property_id] = int(self.next_property_order)
            self.next_property_order += 1

        anchor_bucket = self.property_anchor_index.setdefault(key, [])
        if property_id not in anchor_bucket:
            anchor_bucket.append(property_id)

        for cover_key in self._property_cover_coords(prop):
            cover_bucket = self.property_cover_index.setdefault(cover_key, [])
            if property_id not in cover_bucket:
                cover_bucket.append(property_id)

    def _unindex_property_record(self, property_id, prop):
        key = self._coord_key(prop.get("x"), prop.get("y"), prop.get("z", 0)) if isinstance(prop, dict) else None
        if key is not None:
            bucket = self.property_anchor_index.get(key)
            if bucket:
                self.property_anchor_index[key] = [pid for pid in bucket if pid != property_id]
                if not self.property_anchor_index[key]:
                    self.property_anchor_index.pop(key, None)

        for cover_key in self._property_cover_coords(prop):
            bucket = self.property_cover_index.get(cover_key)
            if bucket:
                self.property_cover_index[cover_key] = [pid for pid in bucket if pid != property_id]
                if not self.property_cover_index[cover_key]:
                    self.property_cover_index.pop(cover_key, None)

    def _index_ground_item_record(self, ground_item_id, item):
        key = self._coord_key(item.get("x"), item.get("y"), item.get("z", 0)) if isinstance(item, dict) else None
        if key is None:
            return
        if ground_item_id not in self.ground_item_order:
            self.ground_item_order[ground_item_id] = int(self.next_ground_item_order)
            self.next_ground_item_order += 1
        bucket = self.ground_item_index.setdefault(key, [])
        if ground_item_id not in bucket:
            bucket.append(ground_item_id)

    def _unindex_ground_item_record(self, ground_item_id, item, drop_order=False):
        key = self._coord_key(item.get("x"), item.get("y"), item.get("z", 0)) if isinstance(item, dict) else None
        if key is not None:
            bucket = self.ground_item_index.get(key)
            if bucket:
                self.ground_item_index[key] = [gid for gid in bucket if gid != ground_item_id]
                if not self.ground_item_index[key]:
                    self.ground_item_index.pop(key, None)
        if drop_order:
            self.ground_item_order.pop(ground_item_id, None)

    def rebuild_spatial_indexes(self):
        self.rebuild_chunk_entity_index()
        self.property_anchor_index = {}
        self.property_cover_index = {}
        self.property_order = {}
        self.next_property_order = 0
        for property_id, prop in self.properties.items():
            self._index_property_record(str(property_id), prop)

        self.ground_item_index = {}
        self.ground_item_order = {}
        self.next_ground_item_order = 0
        for ground_item_id, item in self.ground_items.items():
            self._index_ground_item_record(str(ground_item_id), item)

    def move_property(self, property_id, x, y, z=0):
        prop = self.properties.get(property_id)
        if not isinstance(prop, dict):
            return False

        self._unindex_property_record(property_id, prop)
        try:
            prop["x"] = int(x)
            prop["y"] = int(y)
            prop["z"] = int(z)
        except (TypeError, ValueError):
            self._index_property_record(property_id, prop)
            return False
        metadata = prop.get("metadata")
        if isinstance(metadata, dict):
            metadata["chunk"] = self.chunk_coords(int(prop["x"]), int(prop["y"]))
        self._index_property_record(property_id, prop)
        self._sync_property_chunk_record(property_id, prop)
        return True

    def _property_record_chunk_key(self, prop):
        if not isinstance(prop, dict):
            return None
        metadata = prop.get("metadata")
        if isinstance(metadata, dict):
            raw_chunk = metadata.get("chunk")
            if isinstance(raw_chunk, (list, tuple)) and len(raw_chunk) == 2:
                try:
                    return (int(raw_chunk[0]), int(raw_chunk[1]))
                except (TypeError, ValueError):
                    pass
        try:
            return self.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            return None

    def _property_chunk_record(self, property_id, prop, existing=None):
        record = dict(existing or {})
        metadata = prop.get("metadata", {}) if isinstance(prop, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        record.update({
            "id": str(property_id),
            "kind": str(prop.get("kind", "property")).strip().lower() or "property",
            "x": int(prop.get("x", 0) or 0),
            "y": int(prop.get("y", 0) or 0),
            "z": int(prop.get("z", 0) or 0),
            "archetype": metadata.get("archetype", record.get("archetype")),
            "building_id": metadata.get("building_id", record.get("building_id")),
        })
        return record

    def _sync_property_chunk_record(self, property_id, prop):
        if not isinstance(getattr(self, "chunk_property_records", None), dict):
            return None
        if not isinstance(prop, dict):
            return None
        property_id = str(property_id)
        found_record = None
        for key, records in tuple(self.chunk_property_records.items()):
            kept = []
            removed = False
            for record in tuple(records or ()):
                if isinstance(record, dict) and str(record.get("id", "")).strip() == property_id:
                    if found_record is None:
                        found_record = dict(record)
                    removed = True
                    continue
                kept.append(record)
            if removed:
                if kept:
                    self.chunk_property_records[key] = kept
                else:
                    self.chunk_property_records.pop(key, None)

        new_chunk = self._property_record_chunk_key(prop)
        if new_chunk is None:
            return None
        record = self._property_chunk_record(property_id, prop, existing=found_record)
        bucket = [
            row
            for row in tuple(self.chunk_property_records.get(new_chunk, ()) or ())
            if not (isinstance(row, dict) and str(row.get("id", "")).strip() == property_id)
        ]
        bucket.append(record)
        self.chunk_property_records[new_chunk] = bucket
        return new_chunk

    def _ordered_property_ids(self, property_ids):
        return sorted(
            set(str(property_id) for property_id in property_ids),
            key=lambda property_id: self.property_order.get(property_id, 10**9),
        )

    def _ordered_ground_item_ids(self, ground_item_ids):
        return sorted(
            set(str(ground_item_id) for ground_item_id in ground_item_ids),
            key=lambda ground_item_id: self.ground_item_order.get(ground_item_id, 10**9),
        )

    def structure_at(self, x, y, z=0):
        return self.structure_cells.get((int(x), int(y), int(z)))

    def _floor_room_sequence(self, rooms, floor, floors, basement_levels=0, max_rooms=3):
        labels = [str(room).strip().lower() for room in rooms or () if str(room).strip()]
        if not labels:
            labels = ["room"]
        window = max(1, min(int(max_rooms), len(labels)))
        floor = int(floor)
        max_start = max(0, len(labels) - window)
        if floor < 0:
            basement_levels = max(0, int(basement_levels))
            basement_index = max(0, abs(floor) - 1)
            basement_shift = min(max_start, basement_index, max(0, basement_levels - 1))
            start = max(0, max_start - basement_shift)
            return tuple(reversed(labels[start:start + window]))
        start = min(max_start, int(max(0, floor)))
        return tuple(labels[start:start + window])

    def _split_span(self, start, end, parts):
        start = int(start)
        end = int(end)
        parts = max(1, int(parts))
        length = end - start + 1
        if length <= 0:
            return ()
        parts = max(1, min(parts, length))
        base = length // parts
        extra = length % parts
        spans = []
        cursor = start
        for index in range(parts):
            span = base + (1 if index < extra else 0)
            span_end = cursor + span - 1
            spans.append((int(cursor), int(span_end)))
            cursor = span_end + 1
        return tuple(spans)

    def _room_plan_for_interior_bounds(self, rooms, left, right, top, bottom, floor=0, floors=1, basement_levels=0):
        interior_left = int(left)
        interior_right = int(right)
        interior_top = int(top)
        interior_bottom = int(bottom)
        if interior_left > interior_right or interior_top > interior_bottom:
            return {
                "rooms": (),
                "walls": (),
                "doors": (),
            }

        width = interior_right - interior_left + 1
        height = interior_bottom - interior_top + 1
        max_rooms = 3
        if width >= 9 and height >= 7:
            max_rooms = 5
        elif width >= 7 and height >= 7:
            max_rooms = 4
        floor_rooms = self._floor_room_sequence(
            rooms,
            floor=floor,
            floors=floors,
            basement_levels=basement_levels,
            max_rooms=max_rooms,
        )

        if len(floor_rooms) <= 1 or width < 2 or height < 2:
            return {
                "rooms": (
                    {
                        "kind": floor_rooms[0],
                        "left": interior_left,
                        "right": interior_right,
                        "top": interior_top,
                        "bottom": interior_bottom,
                    },
                ),
                "walls": (),
                "doors": (),
            }

        if len(floor_rooms) >= 5 and width >= 9 and height >= 7:
            front_depth = 3 if height >= 9 else 2
            front_top = max(interior_top, interior_bottom - front_depth + 1)
            front_wall_y = front_top - 1
            back_top = interior_top
            back_bottom = max(interior_top, front_wall_y - 1)
            mid_x = interior_left + (width // 2)
            back_mid_y = back_top + max(1, ((back_bottom - back_top + 1) // 2))

            walls = [(x, front_wall_y) for x in range(interior_left, interior_right + 1)]
            if back_bottom >= back_top:
                for y in range(back_top, back_bottom + 1):
                    walls.append((mid_x, y))
            if back_mid_y <= back_bottom:
                for x in range(interior_left, interior_right + 1):
                    walls.append((x, back_mid_y))

            rooms_out = [
                {
                    "kind": floor_rooms[0],
                    "left": interior_left,
                    "right": interior_right,
                    "top": front_top,
                    "bottom": interior_bottom,
                },
                {
                    "kind": floor_rooms[1],
                    "left": interior_left,
                    "right": max(interior_left, mid_x - 1),
                    "top": interior_top,
                    "bottom": max(interior_top, back_mid_y - 1),
                },
                {
                    "kind": floor_rooms[2],
                    "left": min(interior_right, mid_x + 1),
                    "right": interior_right,
                    "top": interior_top,
                    "bottom": max(interior_top, back_mid_y - 1),
                },
                {
                    "kind": floor_rooms[3],
                    "left": interior_left,
                    "right": max(interior_left, mid_x - 1),
                    "top": min(back_bottom, back_mid_y + 1),
                    "bottom": back_bottom,
                },
                {
                    "kind": floor_rooms[4],
                    "left": min(interior_right, mid_x + 1),
                    "right": interior_right,
                    "top": min(back_bottom, back_mid_y + 1),
                    "bottom": back_bottom,
                },
            ]
            rooms_out = tuple(
                room for room in rooms_out
                if int(room["left"]) <= int(room["right"]) and int(room["top"]) <= int(room["bottom"])
            )
            doors = [
                (interior_left + (width // 2), front_wall_y),
                (mid_x, back_top + ((back_mid_y - back_top) // 2)) if back_mid_y > back_top else None,
                (mid_x, min(back_bottom, back_mid_y + max(1, (back_bottom - back_mid_y) // 2))) if back_bottom > back_mid_y else None,
                (interior_left + (max(1, width // 4)), back_mid_y) if back_mid_y <= back_bottom else None,
                (interior_right - (max(1, width // 4)), back_mid_y) if back_mid_y <= back_bottom else None,
            ]
            return {
                "rooms": rooms_out,
                "walls": tuple(dict.fromkeys(walls)),
                "doors": tuple(dict.fromkeys(door for door in doors if door is not None)),
            }

        if len(floor_rooms) >= 4 and width >= 7 and height >= 7:
            mid_x = interior_left + (width // 2)
            mid_y = interior_top + (height // 2)
            walls = [(x, mid_y) for x in range(interior_left, interior_right + 1)]
            walls.extend((mid_x, y) for y in range(interior_top, interior_bottom + 1))
            rooms_out = (
                {
                    "kind": floor_rooms[0],
                    "left": interior_left,
                    "right": max(interior_left, mid_x - 1),
                    "top": interior_top,
                    "bottom": max(interior_top, mid_y - 1),
                },
                {
                    "kind": floor_rooms[1],
                    "left": min(interior_right, mid_x + 1),
                    "right": interior_right,
                    "top": interior_top,
                    "bottom": max(interior_top, mid_y - 1),
                },
                {
                    "kind": floor_rooms[2],
                    "left": interior_left,
                    "right": max(interior_left, mid_x - 1),
                    "top": min(interior_bottom, mid_y + 1),
                    "bottom": interior_bottom,
                },
                {
                    "kind": floor_rooms[3],
                    "left": min(interior_right, mid_x + 1),
                    "right": interior_right,
                    "top": min(interior_bottom, mid_y + 1),
                    "bottom": interior_bottom,
                },
            )
            doors = (
                (interior_left + (width // 2), mid_y),
                (mid_x, interior_top + (height // 2)),
            )
            return {
                "rooms": tuple(
                    room for room in rooms_out
                    if int(room["left"]) <= int(room["right"]) and int(room["top"]) <= int(room["bottom"])
                ),
                "walls": tuple(dict.fromkeys(walls)),
                "doors": tuple(dict.fromkeys(doors)),
            }

        if len(floor_rooms) >= 3 and width >= 5 and height >= 4:
            front_depth = 2 if height >= 5 else 1
            front_top = max(interior_top, interior_bottom - front_depth + 1)
            split_y = front_top - 1
            split_x = interior_left + (width // 2)

            walls = []
            if split_y >= interior_top:
                for x in range(interior_left, interior_right + 1):
                    walls.append((x, split_y))
            if split_y > interior_top and split_x > interior_left and split_x <= interior_right:
                for y in range(interior_top, split_y):
                    walls.append((split_x, y))

            doors = []
            if split_y >= interior_top:
                doors.append((interior_left + (width // 2), split_y))
            if split_y > interior_top and split_x > interior_left and split_x <= interior_right:
                doors.append((split_x, interior_top + ((split_y - interior_top) // 2)))

            return {
                "rooms": (
                    {
                        "kind": floor_rooms[0],
                        "left": interior_left,
                        "right": interior_right,
                        "top": front_top,
                        "bottom": interior_bottom,
                    },
                    {
                        "kind": floor_rooms[1],
                        "left": interior_left,
                        "right": max(interior_left, split_x - 1),
                        "top": interior_top,
                        "bottom": max(interior_top, split_y - 1),
                    },
                    {
                        "kind": floor_rooms[2],
                        "left": min(interior_right, split_x + 1),
                        "right": interior_right,
                        "top": interior_top,
                        "bottom": max(interior_top, split_y - 1),
                    },
                ),
                "walls": tuple(dict.fromkeys(walls)),
                "doors": tuple(dict.fromkeys(doors)),
            }

        if height >= 3:
            split_y = interior_top + (height // 2)
            walls = [(x, split_y) for x in range(interior_left, interior_right + 1)]
            door = (interior_left + (width // 2), split_y)
            return {
                "rooms": (
                    {
                        "kind": floor_rooms[0],
                        "left": interior_left,
                        "right": interior_right,
                        "top": min(interior_bottom, split_y + 1),
                        "bottom": interior_bottom,
                    },
                    {
                        "kind": floor_rooms[1],
                        "left": interior_left,
                        "right": interior_right,
                        "top": interior_top,
                        "bottom": max(interior_top, split_y - 1),
                    },
                ),
                "walls": tuple(walls),
                "doors": (door,),
            }

        split_x = interior_left + (width // 2)
        walls = [(split_x, y) for y in range(interior_top, interior_bottom + 1)]
        door = (split_x, interior_top + (height // 2))
        return {
            "rooms": (
                {
                    "kind": floor_rooms[0],
                    "left": interior_left,
                    "right": max(interior_left, split_x - 1),
                    "top": interior_top,
                    "bottom": interior_bottom,
                },
                {
                    "kind": floor_rooms[1],
                    "left": min(interior_right, split_x + 1),
                    "right": interior_right,
                    "top": interior_top,
                    "bottom": interior_bottom,
                },
            ),
            "walls": tuple(walls),
            "doors": (door,),
        }

    def _room_plan_point_for_entry_side(
        self,
        local_x,
        local_y,
        *,
        interior_left,
        interior_right,
        interior_top,
        interior_bottom,
        entry_side,
    ):
        side = str(entry_side or "south").strip().lower() or "south"
        if side == "north":
            return (
                int(interior_left) + int(local_x),
                int(interior_bottom) - int(local_y),
            )
        if side == "east":
            return (
                int(interior_left) + int(local_y),
                int(interior_top) + int(local_x),
            )
        if side == "west":
            return (
                int(interior_right) - int(local_y),
                int(interior_top) + int(local_x),
            )
        return (
            int(interior_left) + int(local_x),
            int(interior_top) + int(local_y),
        )

    def _orient_room_plan_for_entry_side(
        self,
        room_plan,
        *,
        interior_left,
        interior_right,
        interior_top,
        interior_bottom,
        entry_side,
    ):
        side = str(entry_side or "south").strip().lower() or "south"
        if side not in {"north", "south", "east", "west"}:
            side = "south"

        def world_point(local_x, local_y):
            return self._room_plan_point_for_entry_side(
                local_x,
                local_y,
                interior_left=interior_left,
                interior_right=interior_right,
                interior_top=interior_top,
                interior_bottom=interior_bottom,
                entry_side=side,
            )

        rooms_out = []
        for room in (room_plan or {}).get("rooms", ()):
            if not isinstance(room, dict):
                continue
            corners = (
                world_point(room.get("left", 0), room.get("top", 0)),
                world_point(room.get("left", 0), room.get("bottom", 0)),
                world_point(room.get("right", 0), room.get("top", 0)),
                world_point(room.get("right", 0), room.get("bottom", 0)),
            )
            xs = [int(x) for x, _y in corners]
            ys = [int(y) for _x, y in corners]
            rooms_out.append({
                "kind": str(room.get("kind", "room") or "room").strip().lower() or "room",
                "left": min(xs),
                "right": max(xs),
                "top": min(ys),
                "bottom": max(ys),
            })

        walls_out = []
        for wall in (room_plan or {}).get("walls", ()):
            if not isinstance(wall, (list, tuple)) or len(wall) < 2:
                continue
            walls_out.append(world_point(wall[0], wall[1]))

        doors_out = []
        for door in (room_plan or {}).get("doors", ()):
            if not isinstance(door, (list, tuple)) or len(door) < 2:
                continue
            doors_out.append(world_point(door[0], door[1]))

        return {
            "rooms": tuple(rooms_out),
            "walls": tuple(dict.fromkeys((int(x), int(y)) for x, y in walls_out)),
            "doors": tuple(dict.fromkeys((int(x), int(y)) for x, y in doors_out)),
        }

    def _room_plan_for_shell(self, rooms, left, right, top, bottom, floor=0, floors=1, basement_levels=0, entry_side="south"):
        interior_left = int(left) + 1
        interior_right = int(right) - 1
        interior_top = int(top) + 1
        interior_bottom = int(bottom) - 1
        if interior_left > interior_right or interior_top > interior_bottom:
            return {
                "rooms": (),
                "walls": (),
                "doors": (),
            }

        side = str(entry_side or "south").strip().lower() or "south"
        if side not in {"north", "south", "east", "west"}:
            side = "south"

        interior_width = interior_right - interior_left + 1
        interior_height = interior_bottom - interior_top + 1
        if side in {"east", "west"}:
            local_right = max(0, interior_height - 1)
            local_bottom = max(0, interior_width - 1)
        else:
            local_right = max(0, interior_width - 1)
            local_bottom = max(0, interior_height - 1)

        local_room_plan = self._room_plan_for_interior_bounds(
            rooms,
            left=0,
            right=local_right,
            top=0,
            bottom=local_bottom,
            floor=floor,
            floors=floors,
            basement_levels=basement_levels,
        )
        return self._orient_room_plan_for_entry_side(
            local_room_plan,
            interior_left=interior_left,
            interior_right=interior_right,
            interior_top=interior_top,
            interior_bottom=interior_bottom,
            entry_side=side,
        )

    def _stamp_room_shell(self, left, right, top, bottom, z, door_x=None, door_y=None, apertures=None, room_plan=None, excluded=None):
        excluded = excluded or frozenset()
        aperture_map = {}
        if door_x is not None and door_y is not None:
            aperture_map[(int(door_x), int(door_y), int(z))] = {
                "kind": "door",
                "ordinary": True,
            }

        for aperture in apertures or ():
            if not isinstance(aperture, dict):
                continue
            try:
                ax = int(aperture.get("x"))
                ay = int(aperture.get("y"))
                az = int(aperture.get("z", z))
            except (TypeError, ValueError):
                continue
            if az != int(z):
                continue
            aperture_map[(ax, ay, az)] = {
                "kind": str(aperture.get("kind", "door") or "door").strip().lower(),
                "ordinary": bool(aperture.get("ordinary")),
            }

        interior_wall_cells = set()
        interior_room_doors = set()
        for wall in (room_plan or {}).get("walls", ()):
            if not isinstance(wall, (list, tuple)) or len(wall) < 2:
                continue
            try:
                wx = int(wall[0])
                wy = int(wall[1])
            except (TypeError, ValueError):
                continue
            interior_wall_cells.add((wx, wy, int(z)))

        for door in (room_plan or {}).get("doors", ()):
            if not isinstance(door, (list, tuple)) or len(door) < 2:
                continue
            try:
                dx = int(door[0])
                dy = int(door[1])
            except (TypeError, ValueError):
                continue
            interior_room_doors.add((dx, dy, int(z)))
            aperture_map[(dx, dy, int(z))] = {
                "kind": "door",
                "ordinary": True,
            }

        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if (x, y) in excluded:
                    continue
                if excluded:
                    edge = False
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if nx < left or nx > right or ny < top or ny > bottom or (nx, ny) in excluded:
                            edge = True
                            break
                    if not edge:
                        for nx, ny in (
                            (x - 1, y - 1),
                            (x + 1, y - 1),
                            (x + 1, y + 1),
                            (x - 1, y + 1),
                        ):
                            if (nx, ny) in excluded:
                                edge = True
                                break
                else:
                    edge = (x in (left, right)) or (y in (top, bottom))
                interior_wall = (int(x), int(y), int(z)) in interior_wall_cells
                wall = edge or interior_wall
                glyph = "#" if edge else "."
                walkable = not wall
                transparent = not wall
                if interior_wall:
                    glyph = "#"

                aperture = aperture_map.get((int(x), int(y), int(z)))
                tile_color = "building_edge" if wall else "building_fill"
                tile_semantic = "wall_building" if wall else "floor_building_fill"
                if aperture:
                    kind = aperture.get("kind", "door")
                    ordinary = bool(aperture.get("ordinary"))
                    interior_room_door = (int(x), int(y), int(z)) in interior_room_doors
                    if interior_room_door and kind == "door" and ordinary:
                        self.set_door_state(
                            x,
                            y,
                            z,
                            kind="door",
                            ordinary=True,
                        )
                        door_state = self.door_state_at(x, y, z) or {}
                        is_open = bool(door_state.get("open", False))
                        glyph = "'" if is_open else "+"
                        walkable = bool(is_open)
                        transparent = bool(is_open)
                        tile_color = "feature_door"
                        tile_semantic = "feature_door"
                    elif kind in {"window", "skylight"}:
                        glyph = '"'
                        walkable = False
                        transparent = True
                        tile_color = "feature_window"
                        tile_semantic = "feature_window"
                    else:
                        glyph = "+"
                        walkable = ordinary and kind == "door"
                        transparent = bool(walkable)
                        tile_color = "feature_door"
                        tile_semantic = "feature_door"

                self.tilemap.set_tile(
                    x,
                    y,
                    Tile(
                        walkable=walkable,
                        transparent=transparent,
                        glyph=glyph,
                        color=tile_color,
                        semantic_id=tile_semantic,
                    ),
                    z=z,
                )
                if aperture and str(aperture.get("kind", "door") or "door").strip().lower() in {"door", "side_door", "service_door", "employee_door"}:
                    self.apply_door_state(x, y, z)

    def _mark_structure_area(self, left, right, top, bottom, z, info, room_plan=None, excluded=None):
        excluded = excluded or frozenset()
        stamped = dict(info or {})
        common_area_room_kinds = {
            str(room_kind or "").strip().lower().replace("-", "_").replace(" ", "_")
            for room_kind in tuple(stamped.get("common_area_room_kinds", ()) or COMMON_AREA_ROOM_KINDS)
            if str(room_kind or "").strip()
        }
        room_cells = {}
        room_list = tuple((room_plan or {}).get("rooms", ()))
        for room_index, room in enumerate(room_list):
            if not isinstance(room, dict):
                continue
            room_kind = str(room.get("kind", "room") or "room").strip().lower() or "room"
            for y in range(int(room.get("top", top)), int(room.get("bottom", bottom)) + 1):
                for x in range(int(room.get("left", left)), int(room.get("right", right)) + 1):
                    room_cells[(int(x), int(y), int(z))] = {
                        "room_index": int(room_index),
                        "room_kind": room_kind,
                    }
        for y in range(int(top), int(bottom) + 1):
            for x in range(int(left), int(right) + 1):
                if (x, y) in excluded:
                    continue
                cell_info = dict(stamped)
                room_info = room_cells.get((int(x), int(y), int(z)))
                if room_info:
                    cell_info.update(room_info)
                    room_kind = str(room_info.get("room_kind", "") or "").strip().lower()
                    if room_kind in common_area_room_kinds:
                        cell_info["common_area_kind"] = room_kind
                self.structure_cells[(int(x), int(y), int(z))] = cell_info

    def _add_vertical_link_stack(self, x, y, top_floor, kind, bottom_floor=0):
        top_floor = int(max(0, min(self.tilemap.max_floors - 1, top_floor)))
        bottom_floor = int(min(0, bottom_floor))
        if top_floor <= bottom_floor:
            return 0

        glyph = "E" if str(kind).strip().lower() == "elevator" else "S"
        for z in range(bottom_floor, top_floor + 1):
            self.tilemap.set_tile(
                int(x),
                int(y),
                Tile(walkable=True, transparent=True, glyph=glyph),
                z=z,
            )

        for from_z in range(bottom_floor, top_floor):
            self.tilemap.add_floor_link(int(x), int(y), from_z=from_z, to_z=from_z + 1, kind=kind)
        return top_floor - bottom_floor

    def _building_shell_edge_cell(self, x, y, *, left, right, top, bottom, excluded=None):
        excluded = set(excluded or ())
        cell = (int(x), int(y))
        if cell in excluded:
            return False
        if int(x) in {int(left), int(right)} or int(y) in {int(top), int(bottom)}:
            return True
        for nx, ny in (
            (int(x) - 1, int(y)),
            (int(x) + 1, int(y)),
            (int(x), int(y) - 1),
            (int(x), int(y) + 1),
        ):
            if nx < int(left) or nx > int(right) or ny < int(top) or ny > int(bottom):
                return True
            if (nx, ny) in excluded:
                return True
        for nx, ny in (
            (int(x) - 1, int(y) - 1),
            (int(x) + 1, int(y) - 1),
            (int(x) + 1, int(y) + 1),
            (int(x) - 1, int(y) + 1),
        ):
            if (nx, ny) in excluded:
                return True
        return False

    def _pick_building_connector_cell(
        self,
        left,
        right,
        top,
        bottom,
        kind,
        excluded=None,
        *,
        building_id=None,
        bottom_floor=0,
        top_floor=0,
    ):
        excluded = set(excluded or ())
        interior_cells = []
        for y in range(int(top) + 1, int(bottom)):
            for x in range(int(left) + 1, int(right)):
                cell = (int(x), int(y))
                if cell in excluded:
                    continue
                if self._building_shell_edge_cell(
                    int(x),
                    int(y),
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    excluded=excluded,
                ):
                    continue

                walkable_levels = 0
                carved_levels = 0
                blocked = False
                for z in range(int(bottom_floor), int(top_floor) + 1):
                    info = self.structure_at(int(x), int(y), int(z))
                    if building_id is not None:
                        info_building_id = str((info or {}).get("building_id", "") or "").strip() if isinstance(info, dict) else ""
                        if info_building_id != str(building_id).strip():
                            blocked = True
                            break
                    tile = self.tilemap.tile_at(int(x), int(y), int(z))
                    if tile is None:
                        blocked = True
                        break
                    semantic = str(getattr(tile, "semantic_id", "") or "").strip().lower()
                    if semantic.startswith("feature_"):
                        blocked = True
                        break
                    if bool(getattr(tile, "walkable", False)):
                        walkable_levels += 1
                    elif semantic == "wall_building":
                        carved_levels += 1
                    else:
                        blocked = True
                        break
                if blocked:
                    continue
                interior_cells.append((int(x), int(y), int(walkable_levels), int(carved_levels)))

        if not interior_cells:
            return None

        kind_label = str(kind).strip().lower() or "stairs"
        if kind_label == "elevator":
            preferred_cells = (
                (int(right) - 1, int(top) + 1),
                (int(right) - 1, int(bottom) - 1),
                (int(left) + 1, int(top) + 1),
                (int(left) + 1, int(bottom) - 1),
            )
        else:
            preferred_cells = (
                (int(left) + 1, int(top) + 1),
                (int(left) + 1, int(bottom) - 1),
                (int(right) - 1, int(top) + 1),
                (int(right) - 1, int(bottom) - 1),
            )

        center_x = (int(left) + int(right)) // 2
        center_y = (int(top) + int(bottom)) // 2

        def _score(cell):
            cell_x, cell_y, walkable_levels, carved_levels = cell
            preferred_offsets = tuple(
                max(abs(cell_x - pref_x), abs(cell_y - pref_y))
                for pref_x, pref_y in preferred_cells
            )
            return (
                -int(walkable_levels),
                int(carved_levels),
            ) + preferred_offsets + (
                abs(cell_x - center_x) + abs(cell_y - center_y),
                cell_y,
                cell_x,
            )

        best_x, best_y, _walkable_levels, _carved_levels = min(interior_cells, key=_score)
        return int(best_x), int(best_y)

    def _core_area_clear(self, center_x, center_y, top_floor):
        left = int(center_x) - 1
        right = int(center_x) + 1
        top = int(center_y) - 1
        bottom = int(center_y) + 1
        for z in range(int(max(0, top_floor)) + 1):
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    if self.structure_at(x, y, z):
                        return False
        return True

    def _find_vertical_core_location(self, ox, oy, size, preferred_x, preferred_y, top_floor, max_radius=8):
        min_x = int(ox) + 2
        max_x = int(ox) + int(size) - 3
        min_y = int(oy) + 2
        max_y = int(oy) + int(size) - 3

        if min_x > max_x or min_y > max_y:
            return None

        px = max(min_x, min(max_x, int(preferred_x)))
        py = max(min_y, min(max_y, int(preferred_y)))
        max_radius = int(max(0, max_radius))

        for radius in range(max_radius + 1):
            if radius == 0:
                if self._core_area_clear(px, py, top_floor):
                    return (px, py)
                continue

            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    cx = px + dx
                    cy = py + dy
                    if cx < min_x or cx > max_x or cy < min_y or cy > max_y:
                        continue
                    if self._core_area_clear(cx, cy, top_floor):
                        return (cx, cy)

        return None

    def _stamp_vertical_core(self, center_x, center_y, top_floor, kind, door_side="south"):
        left = int(center_x) - 1
        right = int(center_x) + 1
        top = int(center_y) - 1
        bottom = int(center_y) + 1
        door_x = int(center_x)
        door_y = bottom if str(door_side).strip().lower() == "south" else top
        kind_label = str(kind).strip().lower() or "stairs"
        core_name = "Elevator Core" if kind_label == "elevator" else "Stair Core"
        core_id = f"core:{kind_label}:{int(center_x)}:{int(center_y)}"

        for z in range(top_floor + 1):
            self._stamp_room_shell(
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                z=z,
                door_x=door_x,
                door_y=door_y,
            )
            self._mark_structure_area(
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                z=z,
                info={
                    "building_id": core_id,
                    "name": core_name,
                    "archetype": f"{kind_label}_core",
                    "is_storefront": False,
                    "floor": int(z),
                    "floors": int(top_floor + 1),
                    "rooms": ("core",),
                    "entry": {
                        "x": int(door_x),
                        "y": int(door_y),
                        "z": int(z),
                        "side": "south" if int(door_y) == int(bottom) else "north",
                        "kind": "door",
                    },
                    "apertures": (
                        {
                            "x": int(door_x),
                            "y": int(door_y),
                            "z": int(z),
                            "side": "south" if int(door_y) == int(bottom) else "north",
                            "kind": "door",
                            "ordinary": True,
                        },
                    ),
                    "footprint": {
                        "left": int(left),
                        "right": int(right),
                        "top": int(top),
                        "bottom": int(bottom),
                    },
                    "signage": None,
                },
            )

        self._add_vertical_link_stack(center_x, center_y, top_floor=top_floor, kind=kind)

    def _place_local_tile(self, x, y, glyph, walkable=True, transparent=True, z=0, overwrite=False):
        existing = self.tilemap.tile_at(int(x), int(y), int(z))
        if existing and not overwrite and str(existing.glyph)[:1] not in {".", ","}:
            return False
        self.tilemap.set_tile(
            int(x),
            int(y),
            Tile(walkable=bool(walkable), transparent=bool(transparent), glyph=str(glyph)[:1] or "."),
            z=int(z),
        )
        return True

    def _stamp_local_route(self, ox, oy, size, path_kind, rng):
        path_kind = str(path_kind or "").strip().lower()
        if not path_kind:
            return

        horizontal = bool(rng.randint(0, 1))
        road_like = path_kind in {"road", "freeway"}
        glyph = "=" if road_like else ":"
        line = (oy + (size // 2)) if horizontal else (ox + (size // 2))

        if horizontal:
            for x in range(ox + 1, ox + size - 1):
                self._place_local_tile(x, line, glyph, walkable=True, transparent=True, z=0, overwrite=True)
                if road_like and line + 1 < oy + size - 1:
                    self._place_local_tile(x, line + 1, glyph, walkable=True, transparent=True, z=0, overwrite=True)
        else:
            for y in range(oy + 1, oy + size - 1):
                self._place_local_tile(line, y, glyph, walkable=True, transparent=True, z=0, overwrite=True)
                if road_like and line + 1 < ox + size - 1:
                    self._place_local_tile(line + 1, y, glyph, walkable=True, transparent=True, z=0, overwrite=True)

    def _scatter_local_tiles(self, ox, oy, size, rng, glyph, count, walkable=True, transparent=True):
        for _ in range(int(max(0, count))):
            x = rng.randint(ox + 1, ox + size - 2)
            y = rng.randint(oy + 1, oy + size - 2)
            self._place_local_tile(x, y, glyph, walkable=walkable, transparent=transparent, z=0, overwrite=False)

    def _stamp_local_band(self, ox, oy, size, rng, glyph, width, walkable=True, transparent=True):
        edge = rng.choice(("north", "south", "east", "west"))
        width = max(1, int(width))
        if edge == "north":
            for y in range(oy, min(oy + size, oy + width)):
                for x in range(ox, ox + size):
                    self._place_local_tile(x, y, glyph, walkable=walkable, transparent=transparent, z=0, overwrite=True)
        elif edge == "south":
            for y in range(max(oy, oy + size - width), oy + size):
                for x in range(ox, ox + size):
                    self._place_local_tile(x, y, glyph, walkable=walkable, transparent=transparent, z=0, overwrite=True)
        elif edge == "west":
            for x in range(ox, min(ox + size, ox + width)):
                for y in range(oy, oy + size):
                    self._place_local_tile(x, y, glyph, walkable=walkable, transparent=transparent, z=0, overwrite=True)
        else:
            for x in range(max(ox, ox + size - width), ox + size):
                for y in range(oy, oy + size):
                    self._place_local_tile(x, y, glyph, walkable=walkable, transparent=transparent, z=0, overwrite=True)

    def _custom_profile_water_safe(self, x, y):
        x = int(x)
        y = int(y)
        if self.structure_at(x, y, 0) is not None:
            return False
        tile = self.tilemap.tile_at(x, y, 0)
        if tile is None:
            return False
        glyph = str(getattr(tile, "glyph", "") or "")[:1]
        if glyph not in {".", ","}:
            return False
        for ny in range(y - 1, y + 2):
            for nx in range(x - 1, x + 2):
                if self.structure_at(nx, ny, 0) is not None:
                    return False
        return True

    def _place_custom_profile_water_tile(self, x, y, glyph):
        if not self._custom_profile_water_safe(x, y):
            return False
        return self._place_local_tile(
            int(x),
            int(y),
            glyph,
            walkable=str(glyph)[:1] == "_",
            transparent=True,
            z=0,
            overwrite=True,
        )

    def _apply_custom_world_profile_water(self, chunk, rng, ox, oy, size):
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        level = str(district.get("custom_water_level", "none") or "none").strip().lower()
        if level not in {"low", "medium", "high"}:
            return 0

        placed = 0
        if level == "low":
            target = max(3, int(size) // 4)
            for _ in range(target * 6):
                if placed >= target:
                    break
                x = rng.randint(ox + 1, ox + size - 2)
                y = rng.randint(oy + 1, oy + size - 2)
                if self._place_custom_profile_water_tile(x, y, "~"):
                    placed += 1
            return placed

        width = 2 if level == "medium" else max(3, int(size) // 5)
        edge = rng.choice(("north", "south", "east", "west"))
        cells = []
        if edge == "north":
            for y in range(oy, min(oy + size, oy + width)):
                cells.extend((x, y, "~") for x in range(ox, ox + size))
            shore_y = min(oy + size - 1, oy + width)
            cells.extend((x, shore_y, "_") for x in range(ox, ox + size))
        elif edge == "south":
            for y in range(max(oy, oy + size - width), oy + size):
                cells.extend((x, y, "~") for x in range(ox, ox + size))
            shore_y = max(oy, oy + size - width - 1)
            cells.extend((x, shore_y, "_") for x in range(ox, ox + size))
        elif edge == "west":
            for x in range(ox, min(ox + size, ox + width)):
                cells.extend((x, y, "~") for y in range(oy, oy + size))
            shore_x = min(ox + size - 1, ox + width)
            cells.extend((shore_x, y, "_") for y in range(oy, oy + size))
        else:
            for x in range(max(ox, ox + size - width), ox + size):
                cells.extend((x, y, "~") for y in range(oy, oy + size))
            shore_x = max(ox, ox + size - width - 1)
            cells.extend((shore_x, y, "_") for y in range(oy, oy + size))
        for x, y, glyph in cells:
            if self._place_custom_profile_water_tile(x, y, glyph):
                placed += 1
        return placed

    def _realize_non_city_sites(self, chunk, ox, oy, size):
        sites = chunk.get("sites", ())
        area_type = str(chunk.get("district", {}).get("area_type", "frontier")).strip().lower() or "frontier"
        reserved_footprints = []
        for idx, site in enumerate(sites):
            if not isinstance(site, dict):
                continue
            layout = layout_chunk_site(
                origin_x=ox,
                origin_y=oy,
                chunk_size=size,
                site_index=idx,
                site=site,
                reserved_footprints=reserved_footprints,
            )
            if not layout:
                continue
            reserved_footprints.extend(site_layout_reserved_footprints(layout))

            left = int(layout["left"])
            right = int(layout["right"])
            top = int(layout["top"])
            bottom = int(layout["bottom"])
            entry = dict(layout.get("entry", {}))
            structure_id = f"{chunk.get('cx', 0)}:{chunk.get('cy', 0)}:{site.get('site_id', idx)}"
            structure_info = {
                "building_id": structure_id,
                "name": str(site.get("span_name") or site.get("name", site.get("kind", "site"))),
                "archetype": str(site.get("kind", "")).strip().lower(),
                "is_storefront": False,
                "floor": 0,
                "floors": 1,
                "rooms": tuple(site.get("rooms", ("entry", "room")) or ("entry", "room")),
                "common_area_room_kinds": tuple(sorted(COMMON_AREA_ROOM_KINDS)),
                "entry": entry,
                "apertures": tuple(dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)),
                "footprint": dict(layout.get("footprint", {})),
                "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                "site_kind": str(site.get("kind", "")).strip().lower(),
                "span_id": str(site.get("span_id", "") or "").strip() or None,
                "span_kind": str(site.get("span_kind", "") or "").strip().lower() or None,
                "span_name": str(site.get("span_name", "") or "").strip() or None,
                "area_type": area_type,
            }
            room_plan = self._room_plan_for_shell(
                structure_info.get("rooms", ("entry", "room")),
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                floor=0,
                floors=1,
                entry_side=entry.get("side", "south"),
            )
            structure_info["rooms"] = tuple(room.get("kind", "room") for room in room_plan.get("rooms", ())) or ("entry", "room")
            self._stamp_room_shell(
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                z=0,
                door_x=int(entry.get("x", layout["anchor_x"])),
                door_y=int(entry.get("y", bottom)),
                apertures=layout.get("apertures", ()),
                room_plan=room_plan,
            )
            self._mark_structure_area(
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                z=0,
                info=structure_info,
                room_plan=room_plan,
            )
            self._clear_non_city_entry_front(entry)

    def _clear_non_city_entry_front(self, entry):
        front = site_entry_front_cell(entry)
        if front is None:
            return False

        x, y, z = front
        if self.structure_at(x, y, z) is not None:
            return False

        tile = self.tilemap.tile_at(x, y, z)
        if tile and tile.walkable and tile.transparent:
            return False

        self.tilemap.set_tile(
            int(x),
            int(y),
            Tile(walkable=True, transparent=True, glyph="."),
            z=int(z),
        )
        return True

    def _realize_non_city_chunk(self, chunk, rng, ox, oy, size):
        district = chunk.get("district", {})
        area_type = str(district.get("area_type", "frontier")).strip().lower() or "frontier"
        descriptor = self.world.overworld_descriptor(chunk.get("cx", 0), chunk.get("cy", 0))
        terrain = str(descriptor.get("terrain", "")).strip().lower()
        path_kind = str(descriptor.get("path", "")).strip().lower()

        if path_kind:
            self._stamp_local_route(ox, oy, size, path_kind, rng)

        if area_type == "frontier":
            self._scatter_local_tiles(ox, oy, size, rng, ",", count=max(6, size // 2), walkable=True, transparent=True)
            self._scatter_local_tiles(ox, oy, size, rng, "^", count=max(3, size // 5), walkable=False, transparent=False)
            if terrain in {"badlands", "dunes", "ruins"}:
                self._scatter_local_tiles(ox, oy, size, rng, "#", count=max(2, size // 6), walkable=False, transparent=False)
        elif area_type == "wilderness":
            self._scatter_local_tiles(ox, oy, size, rng, ",", count=max(10, (size * 2) // 3), walkable=True, transparent=True)
            self._scatter_local_tiles(ox, oy, size, rng, "^", count=max(4, size // 4), walkable=False, transparent=False)
            if terrain in {"marsh", "lake"}:
                self._scatter_local_tiles(ox, oy, size, rng, "~", count=max(8, size // 2), walkable=False, transparent=True)
            if terrain == "waterway":
                self._stamp_local_band(ox, oy, size, rng, "~", width=2, walkable=False, transparent=True)
                self._stamp_local_band(ox, oy, size, rng, "_", width=1, walkable=True, transparent=True)
            if terrain in {"forest"}:
                self._scatter_local_tiles(ox, oy, size, rng, "#", count=max(3, size // 6), walkable=False, transparent=False)
        elif area_type == "coastal":
            water_width = 3
            if terrain == "ocean":
                water_width = max(5, size // 3)
            elif terrain == "island":
                water_width = max(4, size // 4)
            self._stamp_local_band(ox, oy, size, rng, "~", width=water_width, walkable=False, transparent=True)
            self._stamp_local_band(ox, oy, size, rng, "_", width=1, walkable=True, transparent=True)
            self._scatter_local_tiles(ox, oy, size, rng, ",", count=max(4, size // 4), walkable=True, transparent=True)
            if terrain in {"cliffs"}:
                self._scatter_local_tiles(ox, oy, size, rng, "^", count=max(4, size // 5), walkable=False, transparent=False)

        self._realize_non_city_sites(chunk, ox, oy, size)

    def ensure_chunk_terrain(self, cx, cy):
        key = (int(cx), int(cy))
        if key in self.realized_chunks:
            return False

        chunk = self.world.get_chunk(key[0], key[1])
        district = chunk.get("district", {})
        area_type = str(district.get("area_type", "city")).strip().lower() or "city"
        size = int(max(8, self.chunk_size))
        ox, oy = self.chunk_origin(key[0], key[1])
        rng = random.Random(f"{self.seed}:chunk:{key[0]}:{key[1]}:terrain")

        basement_depth = 0
        if area_type == "city":
            for block in chunk.get("blocks", ()):
                for building in block.get("buildings", ()):
                    try:
                        _floors, normalized_basements = normalize_building_levels(
                            building.get("archetype"),
                            building.get("floors", 1),
                            building.get("basement_levels", 0),
                        )
                        basement_depth = max(basement_depth, int(normalized_basements))
                    except (TypeError, ValueError, AttributeError):
                        continue
            underground_plans = chunk_underground_site_plans(
                chunk,
                origin_x=ox,
                origin_y=oy,
                chunk_size=size,
            )
            for plan in underground_plans:
                try:
                    basement_depth = max(basement_depth, abs(int(plan.get("z", 0) or 0)))
                except (TypeError, ValueError, AttributeError):
                    continue
        else:
            underground_plans = ()

        for z in range(-int(basement_depth), 0):
            for y in range(oy, oy + size):
                for x in range(ox, ox + size):
                    if self.tilemap.tile_at(x, y, z) is None:
                        self.tilemap.set_tile(
                            x,
                            y,
                            Tile(
                                walkable=False,
                                transparent=False,
                                glyph=" ",
                            ),
                            z=z,
                        )

        for z in range(self.tilemap.max_floors):
            for y in range(oy, oy + size):
                for x in range(ox, ox + size):
                    if self.tilemap.tile_at(x, y, z) is None:
                        is_ground_floor = z == 0
                        self.tilemap.set_tile(
                            x,
                            y,
                            Tile(
                                walkable=is_ground_floor,
                                transparent=is_ground_floor,
                                glyph="." if is_ground_floor else " ",
                            ),
                            z=z,
                        )

        elevator_archetypes = {
            "bank",
            "biotech_clinic",
            "command_center",
            "co_working_hub",
            "courthouse",
            "data_center",
            "field_hospital",
            "hotel",
            "metro_exchange",
            "office",
            "server_hub",
            "tower",
        }

        if area_type == "city":
            for block in chunk.get("blocks", []):
                bx = int(block.get("grid_x", 0))
                by = int(block.get("grid_y", 0))
                building_count = len(block.get("buildings", []))

                for i, building in enumerate(block.get("buildings", [])):
                    layout = layout_chunk_building(
                        origin_x=ox,
                        origin_y=oy,
                        chunk_size=size,
                        block_grid_x=bx,
                        block_grid_y=by,
                        building_index=i,
                        building=building,
                        building_count=building_count,
                    )
                    if not layout:
                        continue

                    chunk_building_id = world_building_id(key[0], key[1], building)
                    local_building_id = str(building.get("building_id", "") or "").strip()
                    left = int(layout["left"])
                    right = int(layout["right"])
                    top = int(layout["top"])
                    bottom = int(layout["bottom"])
                    entry = dict(layout.get("entry", {}))
                    floors, basement_levels = normalize_building_levels(
                        building.get("archetype"),
                        building.get("floors", 1),
                        building.get("basement_levels", 0),
                    )
                    floors = int(max(1, min(self.tilemap.max_floors, floors)))
                    basement_levels = int(max(0, basement_levels))
                    door_x = int(entry.get("x", layout["anchor_x"]))
                    door_y = int(entry.get("y", bottom))
                    shape_excluded = layout.get("excluded", frozenset())
                    for z in range(-basement_levels, floors):
                        floor_excluded = shape_excluded
                        room_plan = self._room_plan_for_shell(
                            building.get("rooms", ()),
                            left=left,
                            right=right,
                            top=top,
                            bottom=bottom,
                            floor=z,
                            floors=floors,
                            basement_levels=basement_levels,
                            entry_side=entry.get("side", "south"),
                        )
                        structure_info = {
                            "building_id": chunk_building_id,
                            "local_building_id": local_building_id or None,
                            "name": str(building.get("span_name") or building.get("business_name") or building.get("archetype") or "building"),
                            "archetype": str(building.get("archetype", "")).strip().lower(),
                            "is_storefront": bool(building.get("is_storefront")) and not bool(building.get("span_kind")),
                            "large_parcel": bool(building.get("large_parcel")),
                            "parcel_span_x": int(building.get("parcel_span_x", 1) or 1),
                            "parcel_span_y": int(building.get("parcel_span_y", 1) or 1),
                            "span_id": str(building.get("span_id", "") or "").strip() or None,
                            "span_kind": str(building.get("span_kind", "") or "").strip().lower() or None,
                            "span_name": str(building.get("span_name", "") or "").strip() or None,
                            "floor": z,
                            "floors": floors,
                            "basement_levels": basement_levels,
                            "total_levels": floors + basement_levels,
                            "rooms": tuple(room.get("kind", "room") for room in room_plan.get("rooms", ())) or tuple(building.get("rooms", ())),
                            "common_area_room_kinds": tuple(sorted(COMMON_AREA_ROOM_KINDS)),
                            "entry": entry,
                            "apertures": tuple(dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)),
                            "footprint": dict(layout.get("footprint", {})),
                            "placement": dict(layout.get("placement", {})),
                            "placement_profile": dict(building.get("placement_profile", {})) if isinstance(building.get("placement_profile"), dict) else None,
                            "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                        }
                        self._stamp_room_shell(
                            left=left,
                            right=right,
                            top=top,
                            bottom=bottom,
                            z=z,
                            door_x=door_x if z == 0 else None,
                            door_y=door_y if z == 0 else None,
                            apertures=layout.get("apertures", ()) if z == 0 else (),
                            room_plan=room_plan,
                            excluded=floor_excluded,
                        )
                        self._mark_structure_area(
                            left=left,
                            right=right,
                            top=top,
                            bottom=bottom,
                            z=z,
                            info=structure_info,
                            room_plan=room_plan,
                            excluded=floor_excluded,
                        )

                    if floors + basement_levels > 1:
                        archetype = str(building.get("archetype", "")).strip().lower()
                        connector_kind = "elevator" if archetype in elevator_archetypes else "stairs"
                        connector_cell = self._pick_building_connector_cell(
                            left=left,
                            right=right,
                            top=top,
                            bottom=bottom,
                            kind=connector_kind,
                            excluded=shape_excluded,
                            building_id=chunk_building_id,
                            bottom_floor=-basement_levels,
                            top_floor=floors - 1,
                        )
                        if connector_cell is None:
                            continue
                        connector_x, connector_y = connector_cell
                        self._add_vertical_link_stack(
                            connector_x,
                            connector_y,
                            top_floor=floors - 1,
                            kind=connector_kind,
                            bottom_floor=-basement_levels,
                        )

            for plan in underground_plans:
                footprint = plan.get("footprint")
                entry = plan.get("entry")
                if not isinstance(footprint, dict) or not isinstance(entry, dict):
                    continue
                excluded = set()
                for cell in tuple(plan.get("footprint_excluded_cells", ()) or ()):
                    if isinstance(cell, dict):
                        try:
                            excluded.add((int(cell.get("x")), int(cell.get("y"))))
                        except (TypeError, ValueError):
                            continue
                    elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
                        try:
                            excluded.add((int(cell[0]), int(cell[1])))
                        except (TypeError, ValueError):
                            continue
                try:
                    left = int(footprint.get("left"))
                    right = int(footprint.get("right"))
                    top = int(footprint.get("top"))
                    bottom = int(footprint.get("bottom"))
                    z = int(plan.get("z", 0))
                    door_x = int(entry.get("x"))
                    door_y = int(entry.get("y"))
                except (TypeError, ValueError):
                    continue
                room_plan = self._room_plan_for_shell(
                    plan.get("rooms", ("maintenance_tunnel", "junction")),
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    floor=z,
                    floors=1,
                    basement_levels=0,
                    entry_side=entry.get("side", "south"),
                )
                structure_info = {
                    "building_id": str(plan.get("building_id", "")).strip() or str(plan.get("site_id", "")).strip() or "underground_site",
                    "name": str(plan.get("name", "Underground Site")).strip() or "Underground Site",
                    "archetype": str(plan.get("kind", "underground_site")).strip().lower() or "underground_site",
                    "is_storefront": False,
                    "floor": z,
                    "floors": 1,
                    "basement_levels": 0,
                    "total_levels": 1,
                    "rooms": tuple(room.get("kind", "room") for room in room_plan.get("rooms", ())) or tuple(plan.get("rooms", ("maintenance_tunnel",))),
                    "common_area_room_kinds": tuple(sorted(COMMON_AREA_ROOM_KINDS)),
                    "entry": dict(entry),
                    "apertures": tuple(
                        dict(aperture)
                        for aperture in plan.get("apertures", ())
                        if isinstance(aperture, dict)
                    ),
                    "footprint": dict(footprint),
                    "signage": None,
                }
                self._stamp_room_shell(
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    z=z,
                    door_x=door_x,
                    door_y=door_y,
                    apertures=plan.get("apertures", ()),
                    room_plan=room_plan,
                    excluded=frozenset(excluded),
                )
                self._mark_structure_area(
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    z=z,
                    info=structure_info,
                    room_plan=room_plan,
                    excluded=frozenset(excluded),
                )

        else:
            self._realize_non_city_chunk(chunk, rng, ox, oy, size)

        self._apply_custom_world_profile_water(chunk, rng, ox, oy, size)
        self.realized_chunks.add(key)
        return True

    def ensure_loaded_chunk_terrain(self):
        changed = False
        changed_chunks = []
        for cx, cy in self.world.loaded_chunks.keys():
            if self.ensure_chunk_terrain(cx, cy):
                changed = True
                changed_chunks.append((int(cx), int(cy)))
        if changed_chunks:
            for chunk in changed_chunks:
                self.reapply_door_states(chunk=chunk)
        return changed

    def register_property(
        self,
        name,
        kind,
        x,
        y,
        z=0,
        owner_eid=None,
        owner_tag=None,
        metadata=None,
    ):
        property_id = f"prop-{self.next_property_id}"
        self.next_property_id += 1

        self.properties[property_id] = {
            "id": property_id,
            "name": name,
            "kind": kind,
            "x": x,
            "y": y,
            "z": z,
            "owner_eid": owner_eid,
            "owner_tag": owner_tag,
            "metadata": metadata or {},
        }
        self._index_property_record(property_id, self.properties[property_id])
        self.property_registry_dirty = True

        return property_id

    def assign_property_owner(self, property_id, owner_eid=None, owner_tag=None):
        prop = self.properties.get(property_id)
        if not prop:
            return False

        prop["owner_eid"] = owner_eid
        prop["owner_tag"] = owner_tag
        self.property_registry_dirty = True
        return True

    def remove_property(self, property_id):
        removed = self.properties.pop(property_id, None)
        if removed is None:
            return None

        self._unindex_property_record(property_id, removed)
        self.property_order.pop(property_id, None)
        self.property_registry_dirty = True

        stores = getattr(self, "stores", None)
        if isinstance(stores, dict):
            stores.pop(property_id, None)

        trade_ui = getattr(self, "trade_ui", None)
        if isinstance(trade_ui, dict) and str(trade_ui.get("property_id", "")) == str(property_id):
            trade_ui.update({
                "open": False,
                "selected_index": 0,
                "rows": [],
                "inspect_text": "",
                "store_name": "",
                "property_id": None,
                "supply_note": "",
                "contact_note": "",
                "service_note": "",
                "service_eid": None,
            })

        return removed

    def property_at(self, x, y, z=0):
        key = self._coord_key(x, y, z)
        if key is None:
            return None
        for property_id in self.property_anchor_index.get(key, ()):
            prop = self.properties.get(property_id)
            if prop is not None:
                return prop
        return None

    def property_covering(self, x, y, z=0):
        exact = self.property_at(x, y, z)
        if exact:
            return exact

        try:
            x = int(x)
            y = int(y)
            z = int(z)
        except (TypeError, ValueError):
            return None

        key = (x, y, z)
        for property_id in self.property_cover_index.get(key, ()):
            prop = self.properties.get(property_id)
            if prop is not None:
                return prop

        return None

    def properties_in_radius(self, x, y, z=0, r=2):
        key = self._coord_key(x, y, z)
        if key is None:
            return []
        x, y, z = key
        matched_ids = []
        for dy in range(-int(r), int(r) + 1):
            for dx in range(-int(r), int(r) + 1):
                if abs(dx) + abs(dy) > int(r):
                    continue
                matched_ids.extend(self.property_anchor_index.get((x + dx, y + dy, z), ()))
        return [
            self.properties[property_id]
            for property_id in self._ordered_property_ids(matched_ids)
            if property_id in self.properties
        ]

    def new_item_instance_id(self):
        iid = f"item-{self.next_item_instance_id}"
        self.next_item_instance_id += 1
        return iid

    def register_ground_item(
        self,
        item_id,
        x,
        y,
        z=0,
        quantity=1,
        owner_eid=None,
        owner_tag=None,
        instance_id=None,
        metadata=None,
    ):
        ground_item_id = f"ground-{self.next_ground_item_id}"
        self.next_ground_item_id += 1

        if instance_id is None:
            instance_id = self.new_item_instance_id()

        self.ground_items[ground_item_id] = {
            "ground_item_id": ground_item_id,
            "instance_id": instance_id,
            "item_id": item_id,
            "quantity": int(max(1, quantity)),
            "x": x,
            "y": y,
            "z": z,
            "owner_eid": owner_eid,
            "owner_tag": owner_tag,
            "metadata": prepare_ground_item_stack_metadata(
                self,
                item_id,
                x,
                y,
                z,
                quantity=quantity,
                instance_id=instance_id,
                metadata=metadata,
            ),
        }
        self._index_ground_item_record(ground_item_id, self.ground_items[ground_item_id])
        return ground_item_id

    def remove_ground_item(self, ground_item_id):
        removed = self.ground_items.pop(ground_item_id, None)
        if removed is not None:
            self._unindex_ground_item_record(ground_item_id, removed, drop_order=True)
        return removed

    def rotate_ground_item_to_back(self, ground_item_id):
        ground_item_id = str(ground_item_id or "").strip()
        if not ground_item_id or ground_item_id not in self.ground_items:
            return False
        if not isinstance(getattr(self, "ground_item_order", None), dict):
            self.ground_item_order = {}
        try:
            next_order = int(getattr(self, "next_ground_item_order", 0))
        except (TypeError, ValueError):
            next_order = 0
        max_order = next_order - 1
        for order in self.ground_item_order.values():
            try:
                max_order = max(max_order, int(order))
            except (TypeError, ValueError):
                continue
        self.ground_item_order[ground_item_id] = max_order + 1
        self.next_ground_item_order = max_order + 2
        return True

    def ground_items_at(self, x, y, z=0):
        key = self._coord_key(x, y, z)
        if key is None:
            return []
        return [
            self.ground_items[ground_item_id]
            for ground_item_id in self._ordered_ground_item_ids(self.ground_item_index.get(key, ()))
            if ground_item_id in self.ground_items
        ]

    def ground_items_in_radius(self, x, y, z=0, r=1):
        key = self._coord_key(x, y, z)
        if key is None:
            return []
        x, y, z = key
        matched_ids = []
        for dy in range(-int(r), int(r) + 1):
            for dx in range(-int(r), int(r) + 1):
                if abs(dx) + abs(dy) > int(r):
                    continue
                matched_ids.extend(self.ground_item_index.get((x + dx, y + dy, z), ()))
        return [
            self.ground_items[ground_item_id]
            for ground_item_id in self._ordered_ground_item_ids(matched_ids)
            if ground_item_id in self.ground_items
        ]

    def register_projectile(self, projectile):
        projectile_id = f"proj-{self.next_projectile_id}"
        self.next_projectile_id += 1
        data = dict(projectile or {})
        data["projectile_id"] = projectile_id
        self.projectiles[projectile_id] = data
        return projectile_id

    def remove_projectile(self, projectile_id):
        return self.projectiles.pop(projectile_id, None)

    def remove_entity(self, eid):
        self.remember_entity_identity(eid, reason="remove")
        position = self.ecs.get(Position).get(eid)

        if position is not None:
            self.tilemap.remove_entity(eid, position.x, position.y, position.z)

        self.untrack_population_entity(eid)

        removed = False
        for bucket in self.ecs.components.values():
            if bucket.pop(eid, None) is not None:
                removed = True
        return removed

    def register_system(self, system):
        self.systems.append(system)

    def emit(self, event):

        self.events.emit(event)

        for m in self.mutators:
            m.on_event(event, self)

    def _system_runtime_tag(self, system):
        tag = str(getattr(system, "runtime_tag", "") or "").strip().lower()
        if tag:
            return tag
        name = system.__class__.__name__
        if name == "InputSystem":
            return "input"
        if name == "RenderSystem":
            return "render"
        return ""

    def _system_headless_stride(self, system, *, headless_profile=None):
        profile = str(headless_profile or "").strip().lower()
        if not profile:
            return 1
        raw = getattr(system, f"{profile}_tick_stride", None)
        try:
            stride = int(raw)
        except (TypeError, ValueError):
            return 1
        return max(0, stride)

    def _run_systems(self, systems, *, skip_runtime_tags=None, require_flag=None, headless_profile=None):
        skip_tags = {
            str(tag or "").strip().lower()
            for tag in (skip_runtime_tags or ())
            if str(tag or "").strip()
        }
        for system in systems:
            if skip_tags and self._system_runtime_tag(system) in skip_tags:
                continue
            if require_flag and not getattr(system, require_flag, False):
                continue
            stride = self._system_headless_stride(system, headless_profile=headless_profile)
            if stride == 0:
                continue
            if stride > 1 and (int(self.tick) % stride != 0):
                continue
            system.update()

    def _update_cycle(
        self,
        *,
        skip_runtime_tags=None,
        ignore_pause=False,
        force_full_tick=False,
        headless_profile=None,
    ):
        if not self.systems:
            return

        if not ignore_pause and self.is_time_paused():
            self._run_systems(
                self.systems,
                skip_runtime_tags=skip_runtime_tags,
                require_flag="runs_while_paused",
                headless_profile=headless_profile,
            )
            return

        if self.turn_based and not force_full_tick:
            self.turn_advance_requested = False

            # Input system is registered first and decides whether a turn advances.
            self._run_systems(
                self.systems[:1],
                skip_runtime_tags=skip_runtime_tags,
                headless_profile=headless_profile,
            )

            if not self.turn_advance_requested:
                self._run_systems(
                    self.systems[1:],
                    skip_runtime_tags=skip_runtime_tags,
                    require_flag="runs_without_turn",
                    headless_profile=headless_profile,
                )
                return

            systems_to_run = self.systems[1:]
        else:
            systems_to_run = self.systems

        self._run_systems(
            systems_to_run,
            skip_runtime_tags=skip_runtime_tags,
            headless_profile=headless_profile,
        )

        for m in self.mutators:
            m.on_tick(self)

        self.tick += 1

    def update(self):
        self._update_cycle()

    def run_headless_tick(self, *, headless_profile=None):
        profile = str(headless_profile or "").strip().lower()
        if not profile:
            live_timeskip = getattr(self, "live_timeskip", None)
            if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")):
                profile = "live_timeskip"
        self._update_cycle(
            skip_runtime_tags={"input", "render"},
            ignore_pause=True,
            force_full_tick=True,
            headless_profile=profile,
        )

    def render_frame(self):
        for system in self.systems:
            if self._system_runtime_tag(system) != "render":
                continue
            system.update()
