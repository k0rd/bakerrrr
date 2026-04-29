"""Tile and spatial indexing primitives.

The TileMap stores:
1. Tile data by grid coordinate
2. A spatial entity index

Entity components stay in ECS; this index mirrors their positions for
fast lookups used by gameplay systems.
"""


_UNCHANGED = object()


class Tile:

    def __init__(
        self,
        walkable=True,
        transparent=True,
        glyph=".",
        *,
        color=None,
        semantic_id=None,
        layer=None,
        priority=None,
        effects=None,
        overlays=None,
        attrs=0,
        visible=True,
    ):
        self.walkable = walkable
        self.transparent = transparent
        self.glyph = glyph
        self.color = color
        self.semantic_id = str(semantic_id).strip() if semantic_id else None
        self.layer = str(layer).strip().lower() if str(layer or "").strip() else None
        self.priority = None if priority is None else int(priority)
        self.effects = tuple(
            dict.fromkeys(
                str(effect).strip().lower()
                for effect in (effects or ())
                if str(effect).strip()
            )
        )
        self.overlays = tuple(overlay for overlay in (overlays or ()) if isinstance(overlay, dict))
        self.attrs = int(attrs or 0)
        self.visible = bool(visible)

    def set_appearance(
        self,
        *,
        glyph=_UNCHANGED,
        color=_UNCHANGED,
        semantic_id=_UNCHANGED,
        layer=_UNCHANGED,
        priority=_UNCHANGED,
        effects=_UNCHANGED,
        overlays=_UNCHANGED,
        attrs=_UNCHANGED,
        visible=_UNCHANGED,
    ):
        if glyph is not _UNCHANGED:
            self.glyph = str(glyph)[:1] or "."
        if color is not _UNCHANGED:
            self.color = color
        if semantic_id is not _UNCHANGED:
            semantic_text = str(semantic_id).strip()
            self.semantic_id = semantic_text or None
        if layer is not _UNCHANGED:
            layer_text = str(layer).strip().lower()
            self.layer = layer_text or None
        if priority is not _UNCHANGED:
            self.priority = None if priority is None else int(priority)
        if effects is not _UNCHANGED:
            self.effects = tuple(
                dict.fromkeys(
                    str(effect).strip().lower()
                    for effect in effects
                    if str(effect).strip()
                )
            )
        if overlays is not _UNCHANGED:
            self.overlays = tuple(overlay for overlay in overlays if isinstance(overlay, dict))
        if attrs is not _UNCHANGED:
            self.attrs = int(attrs or 0)
        if visible is not _UNCHANGED:
            self.visible = bool(visible)


class TileMap:

    def __init__(self, width, height, max_floors=1, world_coord_limit=1000000):

        self.width = width
        self.height = height
        self.max_floors = max_floors
        self.world_coord_limit = int(max(1024, world_coord_limit))

        self.tiles_by_floor = {}
        for z in range(max_floors):
            self.ensure_floor(z)

        # Backward compatibility for code that still reads tilemap.tiles.
        self.tiles = self.tiles_by_floor[0]

        # spatial index
        # maps (x,y,z) -> set(entity_ids)
        self.entities = {}
        self.on_add_entity = None
        self.on_move_entity = None
        self.on_remove_entity = None
        # floor transition index:
        # maps (x,y,z,dz) -> {"x":tx, "y":ty, "z":tz, "kind":kind}
        self.floor_links = {}

    def _key(self, x, y, z=0):
        return (x, y, z)

    def in_bounds(self, x, y):
        try:
            xi = int(x)
            yi = int(y)
        except (TypeError, ValueError):
            return False
        return abs(xi) <= self.world_coord_limit and abs(yi) <= self.world_coord_limit

    def ensure_floor(self, z):
        if z not in self.tiles_by_floor:
            self.tiles_by_floor[z] = {}
        return self.tiles_by_floor[z]

    def tile_at(self, x, y, z=0):
        if not self.in_bounds(x, y):
            return None

        floor = self.tiles_by_floor.get(z)
        if floor is None:
            return None

        return floor.get((int(x), int(y)))

    def set_tile(self, x, y, tile, z=0):
        if not self.in_bounds(x, y):
            return

        floor = self.ensure_floor(z)
        floor[(int(x), int(y))] = tile

    def is_walkable(self, x, y, z=0):
        tile = self.tile_at(x, y, z)
        return bool(tile and tile.walkable)

    def add_floor_link(self, x, y, from_z, to_z, kind):
        if from_z == to_z:
            return

        self.ensure_floor(from_z)
        self.ensure_floor(to_z)

        dz_up = 1 if to_z > from_z else -1
        dz_down = -dz_up

        self.floor_links[(x, y, from_z, dz_up)] = {
            "x": x,
            "y": y,
            "z": to_z,
            "kind": kind,
        }

        self.floor_links[(x, y, to_z, dz_down)] = {
            "x": x,
            "y": y,
            "z": from_z,
            "kind": kind,
        }

    def floor_transition(self, x, y, z, dz):
        return self.floor_links.get((x, y, z, dz))

    def add_entity(self, eid, x, y, z=0):

        key = self._key(x, y, z)

        if key not in self.entities:
            self.entities[key] = set()

        self.entities[key].add(eid)
        hook = self.on_add_entity
        if callable(hook):
            hook(eid, x, y, z)

    def move_entity(self, eid, oldx, oldy, newx, newy, oldz=0, newz=0):

        old = self._key(oldx, oldy, oldz)
        new = self._key(newx, newy, newz)

        if old in self.entities:
            self.entities[old].discard(eid)
            if not self.entities[old]:
                self.entities.pop(old)

        if new not in self.entities:
            self.entities[new] = set()

        self.entities[new].add(eid)
        hook = self.on_move_entity
        if callable(hook):
            hook(eid, oldx, oldy, newx, newy, oldz, newz)

    def remove_entity(self, eid, x, y, z=0):

        key = self._key(x, y, z)

        if key in self.entities:
            self.entities[key].discard(eid)
            if not self.entities[key]:
                self.entities.pop(key)
        hook = self.on_remove_entity
        if callable(hook):
            hook(eid, x, y, z)

    def entities_at(self, x, y, z=0):

        return self.entities.get(self._key(x, y, z), set())

    def entities_at_any_floor(self, x, y):
        results = {}

        for (ex, ey, ez), bucket in self.entities.items():
            if ex == x and ey == y and bucket:
                results[ez] = set(bucket)

        return results

    def occupied_floors_at(self, x, y):
        return sorted(self.entities_at_any_floor(x, y).keys())

    def entities_on_floor(self, z):
        results = set()

        for (_, _, ez), bucket in self.entities.items():
            if ez == z and bucket:
                results.update(bucket)

        return results

    def entities_in_radius(self, x, y, r, z=0):

        results = []

        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):

                px = x + dx
                py = y + dy

                key = self._key(px, py, z)

                if key in self.entities:
                    results.extend(self.entities[key])

        return results
