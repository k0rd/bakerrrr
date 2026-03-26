import random

from .buildings import layout_chunk_building, world_building_id
from .ecs import ECS
from .events import EventBus
from .sites import layout_chunk_site
from .world import World
from .eventlog import EventLog
from .tilemap import Tile, TileMap

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
        self.chunk_saved_states = {}
        self.property_registry_dirty = False
        self.properties = {}
        self.property_anchor_index = {}
        self.property_cover_index = {}
        self.property_order = {}
        self.next_property_order = 0
        self.structure_cells = {}
        self.next_property_id = 1
        self.ground_items = {}
        self.ground_item_index = {}
        self.ground_item_order = {}
        self.next_ground_item_order = 0
        self.next_ground_item_id = 1
        self.next_item_instance_id = 1
        self.projectiles = {}
        self.next_projectile_id = 1
        self.stores = {}
        self.quests = {
            "available": [],
            "active": [],
            "completed": [],
            "failed": [],
            "history_templates": [],
        }
        self.next_quest_id = 1
        self.turn_based = False
        self.turn_advance_requested = False
        self.zoom_mode = "city"
        self.city_anchor_by_chunk = {}
        self.npc_move_tick_stride = 2
        self.world_traits = {}
        self.organization_index = {}
        self.world_rumors = []
        self.overworld_markers_by_eid = {}
        self.next_overworld_marker_id_by_eid = {}
        self.pause_reasons = set()
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

    def set_time_paused(self, active=True, *, reason="modal"):
        reason_key = str(reason or "modal").strip().lower() or "modal"
        if active:
            self.pause_reasons.add(reason_key)
        else:
            self.pause_reasons.discard(reason_key)
        return bool(self.pause_reasons)

    def is_time_paused(self):
        return bool(self.pause_reasons)

    def chunk_coords(self, x, y):
        return (x // self.chunk_size, y // self.chunk_size)

    def stream_world(self, focus_x, focus_y):
        cx, cy = self.chunk_coords(focus_x, focus_y)
        report = self.world.stream_chunks(
            cx,
            cy,
            active_radius=self.active_chunk_radius,
            loaded_radius=self.loaded_chunk_radius,
        )

        self.active_chunk_coord = (cx, cy)
        self.active_chunk = self.world.get_chunk(cx, cy)
        self.chunk_detail = {
            key: data["detail"]
            for key, data in self.world.loaded_chunks.items()
        }

        return report

    def detail_for_xy(self, x, y):
        coord = self.chunk_coords(x, y)
        return self.chunk_detail.get(coord, "unloaded")

    def chunk_origin(self, cx, cy):
        return (cx * self.chunk_size, cy * self.chunk_size)

    def _coord_key(self, x, y, z=0):
        try:
            return (int(x), int(y), int(z))
        except (TypeError, ValueError):
            return None

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

        coords = []
        for cell_z in range(base_z - basement_levels, base_z + floors):
            for cell_y in range(top, bottom + 1):
                for cell_x in range(left, right + 1):
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
        self._index_property_record(property_id, prop)
        return True

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
            return tuple(reversed(labels[-window:]))
        start = min(max_start, int(max(0, floor)))
        return tuple(labels[start:start + window])

    def _room_plan_for_shell(self, rooms, left, right, top, bottom, floor=0, floors=1, basement_levels=0):
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

        width = interior_right - interior_left + 1
        height = interior_bottom - interior_top + 1
        floor_rooms = self._floor_room_sequence(
            rooms,
            floor=floor,
            floors=floors,
            basement_levels=basement_levels,
            max_rooms=3,
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
                else:
                    edge = (x in (left, right)) or (y in (top, bottom))
                interior_wall = (int(x), int(y), int(z)) in interior_wall_cells
                wall = edge or interior_wall
                glyph = "B" if edge else "b"
                walkable = not wall
                transparent = not wall
                if interior_wall:
                    glyph = "B"

                aperture = aperture_map.get((int(x), int(y), int(z)))
                if aperture:
                    kind = aperture.get("kind", "door")
                    ordinary = bool(aperture.get("ordinary"))
                    glyph = '"' if kind in {"window", "skylight"} else "+"
                    walkable = ordinary and kind == "door"
                    transparent = walkable

                self.tilemap.set_tile(
                    x,
                    y,
                    Tile(
                        walkable=walkable,
                        transparent=transparent,
                        glyph=glyph,
                    ),
                    z=z,
                )

    def _mark_structure_area(self, left, right, top, bottom, z, info, room_plan=None, excluded=None):
        excluded = excluded or frozenset()
        stamped = dict(info or {})
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
            reserved_footprints.append(dict(layout.get("footprint", {})))

            left = int(layout["left"])
            right = int(layout["right"])
            top = int(layout["top"])
            bottom = int(layout["bottom"])
            entry = dict(layout.get("entry", {}))
            structure_id = f"{chunk.get('cx', 0)}:{chunk.get('cy', 0)}:{site.get('site_id', idx)}"
            structure_info = {
                "building_id": structure_id,
                "name": str(site.get("name", site.get("kind", "site"))),
                "archetype": str(site.get("kind", "")).strip().lower(),
                "is_storefront": False,
                "floor": 0,
                "floors": 1,
                "entry": entry,
                "apertures": tuple(dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)),
                "footprint": dict(layout.get("footprint", {})),
                "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                "site_kind": str(site.get("kind", "")).strip().lower(),
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
            if terrain in {"forest"}:
                self._scatter_local_tiles(ox, oy, size, rng, "#", count=max(3, size // 6), walkable=False, transparent=False)
        elif area_type == "coastal":
            self._stamp_local_band(ox, oy, size, rng, "~", width=3, walkable=False, transparent=True)
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
                        basement_depth = max(basement_depth, int(max(0, building.get("basement_levels", 0))))
                    except (TypeError, ValueError, AttributeError):
                        continue

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
                    floors = int(max(1, min(self.tilemap.max_floors, building.get("floors", 1))))
                    basement_levels = int(max(0, building.get("basement_levels", 0)))
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
                        )
                        structure_info = {
                            "building_id": chunk_building_id,
                            "local_building_id": local_building_id or None,
                            "name": str(building.get("business_name") or building.get("archetype") or "building"),
                            "archetype": str(building.get("archetype", "")).strip().lower(),
                            "is_storefront": bool(building.get("is_storefront")),
                            "floor": z,
                            "floors": floors,
                            "basement_levels": basement_levels,
                            "total_levels": floors + basement_levels,
                            "rooms": tuple(room.get("kind", "room") for room in room_plan.get("rooms", ())) or tuple(building.get("rooms", ())),
                            "entry": entry,
                            "apertures": tuple(dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)),
                            "footprint": dict(layout.get("footprint", {})),
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
                        connector_x = right - 1 if connector_kind == "elevator" else left + 1
                        connector_y = top + 1
                        self._add_vertical_link_stack(
                            connector_x,
                            connector_y,
                            top_floor=floors - 1,
                            kind=connector_kind,
                            bottom_floor=-basement_levels,
                        )

            obstacle_count = 0
            for _ in range(obstacle_count):
                x = rng.randint(ox + 1, ox + size - 2)
                y = rng.randint(oy + 1, oy + size - 2)
                tile = self.tilemap.tile_at(x, y, 0)
                if tile and tile.walkable and tile.glyph == ".":
                    self.tilemap.set_tile(x, y, Tile(walkable=False, transparent=False, glyph="#"), z=0)
        else:
            self._realize_non_city_chunk(chunk, rng, ox, oy, size)

        self.realized_chunks.add(key)
        return True

    def ensure_loaded_chunk_terrain(self):
        changed = False
        for cx, cy in self.world.loaded_chunks.keys():
            if self.ensure_chunk_terrain(cx, cy):
                changed = True
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
            "metadata": metadata or {},
        }
        self._index_ground_item_record(ground_item_id, self.ground_items[ground_item_id])
        return ground_item_id

    def remove_ground_item(self, ground_item_id):
        removed = self.ground_items.pop(ground_item_id, None)
        if removed is not None:
            self._unindex_ground_item_record(ground_item_id, removed, drop_order=True)
        return removed

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
        position = None
        for bucket in self.ecs.components.values():
            component = bucket.get(eid)
            if component is not None and all(hasattr(component, attr) for attr in ("x", "y", "z")):
                position = component
                break

        if position is not None:
            self.tilemap.remove_entity(eid, position.x, position.y, position.z)

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

    def update(self):
        if not self.systems:
            return

        if self.is_time_paused():
            for system in self.systems:
                if getattr(system, "runs_while_paused", False):
                    system.update()
            return

        if self.turn_based:
            self.turn_advance_requested = False

            # Input system is registered first and decides whether a turn advances.
            self.systems[0].update()

            if not self.turn_advance_requested:
                for system in self.systems[1:]:
                    if getattr(system, "runs_without_turn", False):
                        system.update()
                return

            systems_to_run = self.systems[1:]
        else:
            systems_to_run = self.systems

        for system in systems_to_run:
            system.update()

        for m in self.mutators:
            m.on_tick(self)

        self.tick += 1
