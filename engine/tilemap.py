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
        # Monotonic, persistence-safe appearance generation.  Render caches can
        # retain a tile snapshot while this value is unchanged without storing
        # callbacks or runtime renderer objects on the tile itself.
        self.visual_revision = 0

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
        changed = False

        if glyph is not _UNCHANGED:
            value = str(glyph)[:1] or "."
            if value != self.glyph:
                self.glyph = value
                changed = True
        if color is not _UNCHANGED and color != self.color:
            self.color = color
            changed = True
        if semantic_id is not _UNCHANGED:
            semantic_text = str(semantic_id).strip()
            value = semantic_text or None
            if value != self.semantic_id:
                self.semantic_id = value
                changed = True
        if layer is not _UNCHANGED:
            layer_text = str(layer).strip().lower()
            value = layer_text or None
            if value != self.layer:
                self.layer = value
                changed = True
        if priority is not _UNCHANGED:
            value = None if priority is None else int(priority)
            if value != self.priority:
                self.priority = value
                changed = True
        if effects is not _UNCHANGED:
            value = tuple(
                dict.fromkeys(
                    str(effect).strip().lower()
                    for effect in effects
                    if str(effect).strip()
                )
            )
            if value != self.effects:
                self.effects = value
                changed = True
        if overlays is not _UNCHANGED:
            value = tuple(overlay for overlay in overlays if isinstance(overlay, dict))
            if value != self.overlays:
                self.overlays = value
                changed = True
        if attrs is not _UNCHANGED:
            value = int(attrs or 0)
            if value != self.attrs:
                self.attrs = value
                changed = True
        if visible is not _UNCHANGED:
            value = bool(visible)
            if value != self.visible:
                self.visible = value
                changed = True

        if changed:
            self.visual_revision = int(getattr(self, "visual_revision", 0) or 0) + 1
        return changed


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
        self.visibility_revision = 0
        self.visibility_global_revision = 0
        self.visibility_chunk_size = 16
        self.visibility_chunk_revisions = {}
        self.visual_revision = 0
        self.visual_global_revision = 0
        self.visual_chunk_size = 16
        self.visual_chunk_revisions = {}
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
        key = (int(x), int(y))
        previous = floor.get(key)
        previous_transparent = True if previous is None else bool(getattr(previous, "transparent", True))
        floor[key] = tile
        self.mark_visual_changed(x, y, z)
        if previous_transparent != bool(getattr(tile, "transparent", True)):
            self.mark_visibility_changed(x, y, z)

    def mark_visual_changed(self, x=None, y=None, z=0):
        """Advance render-only revisions without disturbing FOV caches."""

        self.visual_revision = int(getattr(self, "visual_revision", 0) or 0) + 1
        if x is None or y is None:
            self.visual_global_revision = self.visual_revision
            return self.visual_revision
        try:
            x = int(x)
            y = int(y)
            z = int(z)
            size = max(1, int(getattr(self, "visual_chunk_size", 16) or 16))
        except (TypeError, ValueError):
            self.visual_global_revision = self.visual_revision
            return self.visual_revision

        chunk_revisions = getattr(self, "visual_chunk_revisions", None)
        if not isinstance(chunk_revisions, dict):
            chunk_revisions = {}
            self.visual_chunk_revisions = chunk_revisions
        chunk_revisions[(x // size, y // size, z)] = self.visual_revision
        return self.visual_revision

    def visual_revision_at(self, x, y, z=0):
        try:
            tile = self.tile_at(int(x), int(y), int(z))
        except (TypeError, ValueError):
            return 0
        return int(getattr(tile, "visual_revision", 0) or 0) if tile is not None else 0

    def set_tile_appearance(self, x, y, z=0, **appearance):
        """Mutate a tile appearance and notify retained render caches once."""

        tile = self.tile_at(x, y, z)
        if tile is None or not hasattr(tile, "set_appearance"):
            return False
        changed = bool(tile.set_appearance(**appearance))
        if changed:
            self.mark_visual_changed(x, y, z)
        return changed

    def mark_visibility_changed(self, x=None, y=None, z=0):
        self.visibility_revision = int(getattr(self, "visibility_revision", 0) or 0) + 1
        if x is None or y is None:
            self.visibility_global_revision = self.visibility_revision
            return self.visibility_revision
        try:
            size = max(1, int(getattr(self, "visibility_chunk_size", 16) or 16))
            key = (int(x) // size, int(y) // size, int(z))
        except (TypeError, ValueError):
            self.visibility_global_revision = self.visibility_revision
            return self.visibility_revision
        revisions = getattr(self, "visibility_chunk_revisions", None)
        if not isinstance(revisions, dict):
            revisions = {}
            self.visibility_chunk_revisions = revisions
        revisions[key] = self.visibility_revision
        return self.visibility_revision

    def visibility_signature_for_region(self, x, y, z, radius):
        try:
            x = int(x)
            y = int(y)
            z = int(z)
            radius = max(0, int(radius))
            size = max(1, int(getattr(self, "visibility_chunk_size", 16) or 16))
        except (TypeError, ValueError):
            return (int(getattr(self, "visibility_revision", 0) or 0), ())
        revisions = getattr(self, "visibility_chunk_revisions", None)
        if not isinstance(revisions, dict):
            revisions = {}
        local = []
        for chunk_y in range((y - radius) // size, ((y + radius) // size) + 1):
            for chunk_x in range((x - radius) // size, ((x + radius) // size) + 1):
                local.append(int(revisions.get((chunk_x, chunk_y, z), 0) or 0))
        return (
            int(getattr(self, "visibility_global_revision", 0) or 0),
            tuple(local),
        )

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
        self.mark_visual_changed(x, y, from_z)
        self.mark_visual_changed(x, y, to_z)

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
