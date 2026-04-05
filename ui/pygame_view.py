import curses
import json
import time
from collections import deque
from pathlib import Path
from typing import Any

from game.semantic_catalog import DEFAULT_RUNTIME_MAP_PATH, get_runtime_semantic_catalog
from ui.input_keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP

_DEFAULT_ATLAS_PATH = Path(__file__).resolve().parents[1] / "assets" / "tiles" / "atlas" / "tileset.png"
_DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "assets" / "tiles" / "atlas" / "tileset.json"
_DEFAULT_RUNTIME_SEMANTIC_MAP_PATH = DEFAULT_RUNTIME_MAP_PATH


def _env_flag(name, default=False):
    raw = __import__("os").getenv(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def pygame_atlas_enabled():
    if _env_flag("BAKERRRR_PYGAME_DISABLE_ATLAS", False):
        return False
    return _env_flag("BAKERRRR_PYGAME_ENABLE_ATLAS", False)


def _resolve_atlas_image_path(atlas_path=None, manifest_path=None):
    """Resolve the best available atlas image for the current manifest/package."""
    explicit_path = Path(atlas_path) if atlas_path else None
    manifest = Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST_PATH

    candidates = []
    seen = set()

    def _push(path):
        if path is None:
            return
        resolved = Path(path)
        key = str(resolved)
        if key in seen:
            return
        seen.add(key)
        candidates.append(resolved)

    _push(explicit_path)
    _push(_DEFAULT_ATLAS_PATH)

    if manifest.exists():
        try:
            with manifest.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            atlas = raw.get("atlas", {}) if isinstance(raw, dict) else {}
            image_name = str(atlas.get("image", "") or "").strip()
            if image_name:
                _push(manifest.parent / image_name)
        except Exception:
            pass
        _push(manifest.parent / "tilesheet_unused.png")
        _push(manifest.parent / "none.png")
        try:
            for png_path in sorted(manifest.parent.glob("*.png")):
                _push(png_path)
        except Exception:
            pass

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return explicit_path or _DEFAULT_ATLAS_PATH


def atlas_manifest_tile_size(manifest_path=None, default=40, minimum=8):
    """Return the atlas cell size declared in the manifest, with safe fallback."""
    if not pygame_atlas_enabled():
        value = default
        if minimum is not None:
            value = max(int(minimum), int(value))
        return int(value)
    path = Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST_PATH
    value = default
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        atlas = raw.get("atlas", {}) if isinstance(raw, dict) else {}
        value = int(atlas.get("tile_size", default))
    except Exception:
        value = default
    if minimum is not None:
        value = max(int(minimum), int(value))
    return int(value)


class PygameView:
    """Grid-based pygame view implementing the same drawing/input surface as CursesView.

    Tile rendering:
    - Procedural/glyph rendering is the default path.
    - Atlas rendering is an explicit compatibility opt-in via
      BAKERRRR_PYGAME_ENABLE_ATLAS=1.
    - draw() / draw_text() look up a tile_id from the tile_map then blit the
      sprite; when no sprite is found they fall back to glyph text rendering.
    - Alpha channel in sprites is respected via per-pixel alpha blitting.
    - Set BAKERRRR_TILE_SIZE_PX / BAKERRRR_TILE_GRID_W / BAKERRRR_TILE_GRID_H
      env vars to override defaults at launch.
    """

    def __init__(self, width_cells=64, height_cells=40, cell_px=None, title="bakerrrr"):
        try:
            import pygame
        except ImportError as exc:
            raise RuntimeError("pygame backend requested but pygame is not installed") from exc

        self.pygame = pygame
        pygame.init()
        pygame.font.init()

        self.width_cells = max(24, int(width_cells))
        self.height_cells = max(14, int(height_cells))
        resolved_cell_px = atlas_manifest_tile_size(default=40, minimum=8) if cell_px is None else cell_px
        self.cell_px = max(8, int(resolved_cell_px))
        self.surface = pygame.display.set_mode((self.width_cells * self.cell_px, self.height_cells * self.cell_px))
        pygame.display.set_caption(str(title or "bakerrrr"))

        # Use a monospace system font so glyph-grid alignment remains predictable.
        self.font = pygame.font.SysFont("DejaVu Sans Mono", self.cell_px)
        ui_font_px = max(8, int(round(self.cell_px * 0.78)))
        self._ui_font = pygame.font.SysFont("DejaVu Sans Mono", ui_font_px)
        self._ui_bold_font = pygame.font.SysFont("DejaVu Sans Mono", ui_font_px, bold=True)
        marker_font_px = max(8, int(round(self.cell_px * 0.62)))
        self._marker_font = pygame.font.SysFont("DejaVu Sans Mono", marker_font_px, bold=True)
        self.key_queue = deque()
        self._animation_tick = 0
        self.uses_realtime_animation = True
        self._queued_draw_calls = []
        self._draw_sequence = 0
        self.atlas_enabled = pygame_atlas_enabled()

        # Atlas tile rendering. Populated by _load_atlas().
        self._atlas: Any = None            # pygame.Surface or None
        self._tile_rects: dict = {}        # tile_id -> pygame.Rect
        self._glyph_color_tiles: dict = {} # (glyph, asset_color) -> tile_id
        self._semantic_catalog = None
        self._tile_map: dict = {}          # glyph/category lookup table from semantic_map.json
        self._semantic_aliases: dict = {}  # semantic tile_id -> atlas tile_id
        self._runtime_color_asset_families: dict = {}
        self._load_atlas()
        self._load_tile_map()
        self._load_semantic_aliases()

        self.palette = {
            "default": (240, 240, 240),
            "player": (100, 220, 255),
            "human": (230, 230, 230),
            "guard": (95, 140, 255),
            "scout": (120, 220, 120),
            "feline": (255, 220, 90),
            "canine": (220, 220, 220),
            "avian": (220, 120, 220),
            "insect": (110, 200, 110),
            "rodent": (205, 170, 105),
            "reptile": (120, 185, 120),
            "amphibian": (100, 210, 190),
            "fish": (110, 185, 235),
            "ungulate": (200, 185, 120),
            "other": (205, 145, 205),
            "floor_coarse": (90, 90, 90),
            "floor_industrial": (120, 120, 120),
            "floor_residential": (170, 170, 170),
            "floor_downtown": (190, 190, 210),
            "floor_slums": (110, 95, 120),
            "floor_corporate": (120, 170, 220),
            "floor_military": (95, 150, 140),
            "floor_entertainment": (205, 170, 120),
            "floor_frontier": (180, 150, 100),
            "floor_wilderness": (95, 160, 95),
            "floor_coastal": (110, 180, 210),
            "building_fill": (110, 110, 110),
            "building_edge": (150, 150, 150),
            "terrain_block": (85, 85, 85),
            "terrain_brush": (120, 180, 120),
            "terrain_rock": (165, 165, 165),
            "terrain_water": (120, 170, 220),
            "terrain_salt": (230, 220, 190),
            "terrain_road": (205, 190, 110),
            "terrain_trail": (185, 140, 110),
            "building_roof": (100, 100, 100),
            "building_roof_residential": (180, 180, 180),
            "building_roof_storefront": (185, 155, 95),
            "building_roof_industrial": (125, 125, 125),
            "building_roof_corporate": (110, 160, 210),
            "building_roof_civic": (145, 190, 220),
            "building_roof_secure": (95, 150, 95),
            "building_roof_entertainment": (190, 145, 200),
            "feature_door": (205, 190, 110),
            "feature_window": (110, 180, 220),
            "feature_breach": (220, 100, 100),
            "transit": (220, 220, 140),
            "property_building": (220, 210, 190),
            "property_fixture": (130, 180, 235),
            "property_asset": (225, 190, 95),
            "property_service": (140, 200, 140),
            "vehicle_parked": (190, 190, 190),
            "vehicle_new": (235, 190, 95),
            "vehicle_player": (80, 210, 240),
            "vehicle_paint_red": (198, 90, 90),
            "vehicle_paint_blue": (92, 132, 208),
            "vehicle_paint_green": (96, 168, 104),
            "vehicle_paint_white": (215, 215, 215),
            "vehicle_paint_black": (96, 96, 104),
            "vehicle_paint_teal": (82, 170, 170),
            "vehicle_paint_rust": (156, 96, 64),
            "vehicle_paint_brown": (150, 118, 82),
            "vehicle_paint_yellow": (214, 186, 86),
            "item_ground": (225, 185, 95),
            "item_token": (240, 220, 110),
            "item_tool": (200, 170, 120),
            "item_medical": (120, 220, 140),
            "item_restricted": (230, 150, 100),
            "item_illegal": (220, 90, 90),
            "item_weapon": (210, 130, 110),
            "item_armor": (170, 190, 225),
            "item_food": (220, 185, 105),
            "item_drink": (120, 190, 235),
            "item_access": (200, 220, 160),
            "item_objective": (245, 220, 110),
            "projectile": (220, 110, 110),
            "objective": (245, 220, 110),
            "cat_orange": (230, 140, 70),
            "cat_black": (90, 90, 90),
            "cat_tabby": (190, 140, 100),
            "cat_calico": (235, 150, 110),
            "cat_white": (240, 240, 240),
            "cat_gray": (170, 170, 170),
            "cat_tuxedo": (215, 215, 215),
            "cat_purple": (175, 125, 220),
        }

    def prompt_text_input(
        self,
        prompt,
        *,
        detail="",
        initial_text="",
        max_length=40,
        title=None,
        banner="",
        subtitle="",
        invalid_message="Please enter a valid value.",
        normalizer=None,
        status_lines_callback=None,
    ):
        """Run a simple in-window text prompt and return the normalized result."""
        if title:
            self.pygame.display.set_caption(str(title))

        text = str(initial_text or "")[: max(1, int(max_length))]
        error_text = ""
        cursor_visible = True
        blink_deadline = time.monotonic() + 0.5
        clock = self.pygame.time.Clock()

        prompt = str(prompt or "")
        detail = str(detail or "")
        banner = str(banner or "")
        subtitle = str(subtitle or "")
        invalid_message = str(invalid_message or "Please enter a valid value.")
        normalize = normalizer if callable(normalizer) else (lambda value: str(value or "").strip())
        status_callback = status_lines_callback if callable(status_lines_callback) else None
        title_font = self.pygame.font.SysFont("DejaVu Sans Mono", max(18, int(self.cell_px * 1.7)), bold=True)
        subtitle_font = self.pygame.font.SysFont("DejaVu Sans Mono", max(12, int(self.cell_px * 0.85)))

        def _status_lines(current_text):
            if not status_callback:
                return []
            rows = []
            for raw in status_callback(current_text) or ():
                if isinstance(raw, dict):
                    text_value = str(raw.get("text", "")).strip()
                    color_value = raw.get("color")
                else:
                    text_value = str(raw).strip()
                    color_value = None
                if text_value:
                    rows.append({"text": text_value, "color": color_value})
            return rows

        while True:
            now = time.monotonic()
            if now >= blink_deadline:
                cursor_visible = not cursor_visible
                blink_deadline = now + 0.5

            self.surface.fill((12, 16, 22))
            stripe_color = (18, 24, 31)
            for row in range(0, self.height_cells * self.cell_px, self.cell_px * 2):
                self.surface.fill(stripe_color, (0, row, self.width_cells * self.cell_px, self.cell_px))

            panel_w = min(max(36, self.width_cells - 10), self.width_cells)
            panel_h = min(max(12, 16), self.height_cells)
            panel_x = max(0, (self.width_cells - panel_w) // 2)
            panel_y = max(0, (self.height_cells - panel_h) // 2)
            panel_px = panel_x * self.cell_px
            panel_py = panel_y * self.cell_px
            panel_pw = panel_w * self.cell_px
            panel_ph = panel_h * self.cell_px

            outer_rect = self.pygame.Rect(panel_px, panel_py, panel_pw, panel_ph)
            inner_rect = self.pygame.Rect(panel_px + self.cell_px, panel_py + self.cell_px, max(0, panel_pw - (self.cell_px * 2)), max(0, panel_ph - (self.cell_px * 2)))
            self.pygame.draw.rect(self.surface, (28, 36, 46), outer_rect)
            self.pygame.draw.rect(self.surface, (32, 41, 53), inner_rect)
            accent_rect = self.pygame.Rect(panel_px, panel_py, max(2, self.cell_px // 3), panel_ph)
            self.pygame.draw.rect(self.surface, self._color_value("player"), accent_rect)

            top = "+" + ("-" * max(0, panel_w - 2)) + "+"
            mid = "|" + (" " * max(0, panel_w - 2)) + "|"
            bot = "+" + ("-" * max(0, panel_w - 2)) + "+"
            self.draw_text(panel_x, panel_y, top, color="human")
            for row in range(1, max(1, panel_h - 1)):
                self.draw_text(panel_x, panel_y + row, mid, color="human")
            self.draw_text(panel_x, panel_y + panel_h - 1, bot, color="human")

            inner_w = max(1, panel_w - 4)
            text_px = panel_px + (self.cell_px * 2)
            text_py = panel_py + self.cell_px
            if banner:
                banner_surface = title_font.render(banner, True, self._color_value("objective"))
                self.surface.blit(banner_surface, (text_px, text_py))
            if subtitle:
                subtitle_surface = subtitle_font.render(subtitle[: max(1, inner_w * 2)], True, self._color_value("default"))
                subtitle_y = text_py + max(self.cell_px, title_font.get_height())
                self.surface.blit(subtitle_surface, (text_px, subtitle_y))

            prompt_y = panel_y + 4
            self.draw_text(panel_x + 2, prompt_y, prompt[:inner_w], color="objective")
            if detail:
                self.draw_text(panel_x + 2, prompt_y + 1, detail[:inner_w], color="default")

            field_y = prompt_y + 3
            field_rect = self.pygame.Rect(
                panel_px + (self.cell_px * 2),
                panel_py + (field_y * self.cell_px) - panel_py,
                max(self.cell_px * 8, (panel_w - 4) * self.cell_px),
                self.cell_px + max(6, self.cell_px // 3),
            )
            field_rect.y = panel_y * self.cell_px + (field_y * self.cell_px - panel_y * self.cell_px)
            self.pygame.draw.rect(self.surface, (18, 23, 30), field_rect)
            self.pygame.draw.rect(self.surface, self._color_value("building_edge"), field_rect, width=1)

            field_text = text
            if cursor_visible and len(field_text) < inner_w:
                field_text += "_"
            self.draw_text(panel_x + 2, field_y, field_text[:inner_w], color="player")

            status_rows = _status_lines(text)
            for idx, row in enumerate(status_rows[:2]):
                self.draw_text(panel_x + 2, field_y + 2 + idx, row["text"][:inner_w], color=row.get("color") or "scout")

            footer = "Enter confirm  Esc cancel"
            self.draw_text(panel_x + 2, panel_y + panel_h - 2, footer[:inner_w], color="scout")
            if error_text:
                self.draw_text(panel_x + 2, panel_y + panel_h - 3, error_text[:inner_w], color="feature_breach")

            self.refresh()

            for event in self.pygame.event.get():
                if event.type == self.pygame.QUIT:
                    return None
                if event.type != self.pygame.KEYDOWN:
                    continue

                if event.key == self.pygame.K_RETURN:
                    normalized = normalize(text)
                    if normalized:
                        return normalized
                    error_text = invalid_message
                    continue

                if event.key == self.pygame.K_ESCAPE:
                    return None

                if event.key == self.pygame.K_BACKSPACE:
                    text = text[:-1]
                    error_text = ""
                    continue

                if event.key == self.pygame.K_TAB:
                    continue

                raw = getattr(event, "unicode", "") or ""
                if not raw:
                    continue
                if raw in {"\r", "\n", "\t"}:
                    continue
                if ord(raw[0]) < 32:
                    continue
                if len(text) < max(1, int(max_length)):
                    text += raw[0]
                    error_text = ""

            clock.tick(30)

    def _load_atlas(self, atlas_path=None, manifest_path=None):
        """Load a packed atlas PNG + manifest JSON if they exist."""
        if not self.atlas_enabled:
            return
        manifest_path = Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST_PATH
        atlas_path = _resolve_atlas_image_path(atlas_path=atlas_path, manifest_path=manifest_path)

        if not atlas_path.exists() or not manifest_path.exists():
            return

        try:
            raw = self.pygame.image.load(str(atlas_path)).convert_alpha()
            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        except Exception:
            return

        rects = {}
        glyph_color_tiles = {}
        for entry in manifest.get("tiles", ()):
            tile_id = str(entry.get("id", "")).strip()
            if not tile_id:
                continue
            try:
                x = int(entry["x"])
                y = int(entry["y"])
                w = int(entry["w"])
                h = int(entry["h"])
            except (KeyError, TypeError, ValueError):
                continue
            rects[tile_id] = self.pygame.Rect(x, y, w, h)
            glyph = str(entry.get("glyph", ""))[:1]
            color = str(entry.get("color", "")).strip().lower()
            if glyph and color:
                glyph_color_tiles[(glyph, color)] = tile_id

        self._atlas = raw
        self._tile_rects = rects
        self._glyph_color_tiles = glyph_color_tiles

    def _load_tile_map(self, path=None):
        """Load the runtime semantic catalog used by renderer lookup."""
        catalog_path = Path(path) if path else _DEFAULT_RUNTIME_SEMANTIC_MAP_PATH
        try:
            self._semantic_catalog = get_runtime_semantic_catalog(str(catalog_path))
        except Exception:
            self._semantic_catalog = get_runtime_semantic_catalog()

        self._tile_map = dict(getattr(self._semantic_catalog, "categories", {}) or {})
        aliases = getattr(self._semantic_catalog, "color_aliases", {}) or {}
        runtime_to_asset = {}
        if isinstance(aliases, dict):
            for asset_family, runtime_colors in aliases.items():
                asset_key = str(asset_family or "").strip().lower()
                if not asset_key:
                    continue
                runtime_to_asset.setdefault(asset_key, []).append(asset_key)
                if not isinstance(runtime_colors, (list, tuple, set)):
                    continue
                for runtime_color in runtime_colors:
                    runtime_key = str(runtime_color or "").strip().lower()
                    if not runtime_key:
                        continue
                    runtime_to_asset.setdefault(runtime_key, [])
                    if asset_key not in runtime_to_asset[runtime_key]:
                        runtime_to_asset[runtime_key].append(asset_key)
        self._runtime_color_asset_families = runtime_to_asset

    def _load_semantic_aliases(self, path=None):
        """Load semantic tile aliases to atlas IDs if available."""
        if self._semantic_catalog is None:
            self._load_tile_map(path=path)
        semantics = getattr(self._semantic_catalog, "semantics", {}) if self._semantic_catalog is not None else {}
        if not isinstance(semantics, dict):
            self._semantic_aliases = {}
            return
        mapping = {}
        for semantic_id, entry in semantics.items():
            if not isinstance(entry, dict):
                continue
            atlas_id = str(entry.get("atlas_id", "") or "").strip()
            semantic_key = str(semantic_id or "").strip()
            if semantic_key and atlas_id:
                mapping[semantic_key] = atlas_id
        self._semantic_aliases = mapping

    def _category_order_for_color(self, color_key):
        """Return preferred tile-map category order for a given color key."""
        if self._semantic_catalog is not None:
            return list(self._semantic_catalog.category_order_for_color(color_key))
        key = str(color_key or "default").strip().lower()
        default_order = [
            "terrain",
            "features",
            "infrastructure",
            "properties",
            "vehicles",
            "items",
            "projectiles",
            "entities",
            "ui_markers",
        ]

        if key in {
            "player",
            "human",
            "guard",
            "scout",
            "feline",
            "canine",
            "avian",
            "insect",
            "rodent",
            "reptile",
            "amphibian",
            "fish",
            "ungulate",
            "other",
        } or key.startswith("cat_"):
            return ["entities"] + [name for name in default_order if name != "entities"]
        if key.startswith("item_"):
            return ["items"] + [name for name in default_order if name != "items"]
        if key.startswith("vehicle_"):
            return ["vehicles"] + [name for name in default_order if name != "vehicles"]
        if key.startswith("feature_"):
            return ["features"] + [name for name in default_order if name != "features"]
        if key.startswith("terrain_") or key.startswith("floor_") or key in {"building_edge", "building_fill"}:
            return ["terrain"] + [name for name in default_order if name != "terrain"]
        if key.startswith("property_") or key.startswith("building_roof_"):
            return ["properties"] + [name for name in default_order if name != "properties"]
        if key == "projectile":
            return ["projectiles"] + [name for name in default_order if name != "projectiles"]
        if key.startswith("ui_"):
            return ["ui_markers"] + [name for name in default_order if name != "ui_markers"]
        if key == "transit":
            return ["features", "terrain"] + [name for name in default_order if name not in {"features", "terrain"}]
        return default_order

    def _strict_categories_for_color(self, color_key):
        if self._semantic_catalog is not None:
            return tuple(self._semantic_catalog.strict_categories_for_color(color_key))
        key = str(color_key or "default").strip().lower()
        if key.startswith("item_"):
            return ("items",)
        if key.startswith("vehicle_"):
            return ("vehicles",)
        return ()

    def _preserve_background_for_color(self, color_key):
        key = str(color_key or "default").strip().lower()
        return key.startswith("item_") or key.startswith("vehicle_") or key == "feature_window"

    def _styled_overlay_color(self, color, attrs=0, *, bold_scale=1.15):
        frame = self._color_value(color)
        if self._has_attr(attrs, "A_DIM"):
            frame = (frame[0] // 2, frame[1] // 2, frame[2] // 2)
        if self._has_attr(attrs, "A_BOLD"):
            frame = (
                min(255, int(frame[0] * bold_scale)),
                min(255, int(frame[1] * bold_scale)),
                min(255, int(frame[2] * bold_scale)),
            )
        return frame

    def _draw_window_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs)

        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 8)
        inner_w = max(1, self.cell_px - (inset * 2))
        inner_h = max(1, self.cell_px - (inset * 2))
        frame_alpha = 188
        glass_alpha = 54

        glass = (frame[0], frame[1], frame[2], glass_alpha)
        stroke = (frame[0], frame[1], frame[2], frame_alpha)
        self.pygame.draw.rect(overlay, glass, (inset, inset, inner_w, inner_h))
        self.pygame.draw.rect(overlay, stroke, (inset, inset, inner_w, inner_h), max(1, self.cell_px // 12))

        mid_x = self.cell_px // 2
        self.pygame.draw.line(
            overlay,
            stroke,
            (mid_x, inset + 1),
            (mid_x, self.cell_px - inset - 2),
            max(1, self.cell_px // 12),
        )

        cross_y = max(inset + 2, self.cell_px // 3)
        self.pygame.draw.line(
            overlay,
            (frame[0], frame[1], frame[2], max(120, frame_alpha - 28)),
            (inset + 1, cross_y),
            (self.cell_px - inset - 2, cross_y),
            max(1, self.cell_px // 16),
        )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_door_overlay(self, x, y, color=None, attrs=0, *, is_open=False):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 8)
        stroke_w = max(1, self.cell_px // 12)
        panel_rect = (
            inset,
            inset,
            max(1, self.cell_px - (inset * 2)),
            max(1, self.cell_px - (inset * 2)),
        )
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 104), panel_rect)
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 196), panel_rect, stroke_w)

        if is_open:
            slab_w = max(2, self.cell_px // 3)
            slab_rect = self.pygame.Rect(inset + 1, inset + 1, slab_w, max(2, self.cell_px - (inset * 2) - 2))
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 130), slab_rect, max(1, stroke_w - 1))
            jamb_x = inset + slab_w + max(1, self.cell_px // 16)
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 172),
                (jamb_x, inset + 1),
                (jamb_x, self.cell_px - inset - 2),
                stroke_w,
            )
            swing_y = self.cell_px // 2
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 146),
                (jamb_x, swing_y),
                (self.cell_px - inset - 2, inset + 2),
                max(1, stroke_w - 1),
            )
        else:
            knob_r = max(1, self.cell_px // 18)
            knob_x = self.cell_px - inset - max(2, self.cell_px // 5)
            knob_y = self.cell_px // 2
            self.pygame.draw.circle(overlay, (255, 236, 170, 170), (int(knob_x), int(knob_y)), knob_r)
            threshold_y = self.cell_px - inset - stroke_w
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 152),
                (inset + 1, threshold_y),
                (self.cell_px - inset - 2, threshold_y),
                stroke_w,
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_breach_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        stroke_w = max(1, self.cell_px // 10)
        offset = max(2, self.cell_px // 7)
        self.pygame.draw.line(
            overlay,
            (frame[0], frame[1], frame[2], 188),
            (offset, self.cell_px - offset - 1),
            (self.cell_px - offset - 1, offset),
            stroke_w,
        )
        self.pygame.draw.line(
            overlay,
            (frame[0], frame[1], frame[2], 110),
            (offset + stroke_w, self.cell_px - offset - 1),
            (self.cell_px - offset - 1, offset + stroke_w),
            max(1, stroke_w - 1),
        )
        for px, py in (
            (offset + 1, self.cell_px - offset - 2),
            (self.cell_px // 2, self.cell_px // 2),
            (self.cell_px - offset - 2, offset + 1),
        ):
            self.pygame.draw.circle(overlay, (frame[0], frame[1], frame[2], 132), (px, py), max(1, stroke_w - 1))

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_wall_overlay(self, x, y, color=None, attrs=0, *, filled=False):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        if filled:
            inset = max(1, self.cell_px // 16)
            rect = self.pygame.Rect(inset, inset, max(1, self.cell_px - (inset * 2)), max(1, self.cell_px - (inset * 2)))
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 86), rect)
            seam = (
                min(255, int(frame[0] * 1.04)),
                min(255, int(frame[1] * 1.04)),
                min(255, int(frame[2] * 1.04)),
                124,
            )
            seam_w = max(1, self.cell_px // 20)
            mid_x = rect.left + (rect.w // 2)
            mid_y = rect.top + (rect.h // 2)
            self.pygame.draw.line(overlay, seam, (mid_x, rect.top), (mid_x, rect.bottom - 1), seam_w)
            self.pygame.draw.line(overlay, seam, (rect.left, mid_y), (rect.right - 1, mid_y), seam_w)
            dot = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 92)
            for px, py in (
                (rect.left + max(1, self.cell_px // 6), rect.top + max(1, self.cell_px // 6)),
                (rect.right - max(2, self.cell_px // 5), rect.top + max(1, self.cell_px // 6)),
                (rect.left + max(1, self.cell_px // 5), rect.bottom - max(2, self.cell_px // 5)),
            ):
                self.pygame.draw.circle(overlay, dot, (px, py), max(1, self.cell_px // 24))
        else:
            inset = max(1, self.cell_px // 12)
            rect = self.pygame.Rect(inset, inset, max(1, self.cell_px - (inset * 2)), max(1, self.cell_px - (inset * 2)))
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 116), rect)
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 224), rect, max(1, self.cell_px // 14))
            top = (
                min(255, int(frame[0] * 1.12)),
                min(255, int(frame[1] * 1.12)),
                min(255, int(frame[2] * 1.12)),
                146,
            )
            bottom = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 132)
            edge_w = max(1, self.cell_px // 18)
            self.pygame.draw.line(overlay, top, (rect.left, rect.top), (rect.right - 1, rect.top), edge_w)
            self.pygame.draw.line(overlay, top, (rect.left, rect.top), (rect.left, rect.bottom - 1), edge_w)
            self.pygame.draw.line(overlay, bottom, (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1), edge_w)
            self.pygame.draw.line(overlay, bottom, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom - 1), edge_w)
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 104),
                (rect.left + max(1, self.cell_px // 6), rect.top + max(2, self.cell_px // 4)),
                (rect.right - max(2, self.cell_px // 6), rect.top + max(2, self.cell_px // 4)),
                max(1, self.cell_px // 22),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_roof_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.06)
        color_key = str(color or "").strip().lower()
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 14)
        rect = self.pygame.Rect(inset, inset, max(1, self.cell_px - (inset * 2)), max(1, self.cell_px - (inset * 2)))
        parapet_w = max(1, self.cell_px // 16)
        seam_w = max(1, self.cell_px // 24)

        slab = (frame[0], frame[1], frame[2], 116)
        parapet = (
            min(255, int(frame[0] * 1.1)),
            min(255, int(frame[1] * 1.1)),
            min(255, int(frame[2] * 1.1)),
            208,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 126)
        seam = (
            min(255, int(frame[0] * 1.03)),
            min(255, int(frame[1] * 1.03)),
            min(255, int(frame[2] * 1.03)),
            118,
        )

        self.pygame.draw.rect(overlay, slab, rect)
        self.pygame.draw.rect(overlay, parapet, rect, parapet_w)
        self.pygame.draw.line(overlay, parapet, (rect.left, rect.top), (rect.right - 1, rect.top), parapet_w)
        self.pygame.draw.line(overlay, parapet, (rect.left, rect.top), (rect.left, rect.bottom - 1), parapet_w)
        self.pygame.draw.line(overlay, shadow, (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1), parapet_w)
        self.pygame.draw.line(overlay, shadow, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom - 1), parapet_w)

        vent_w = max(3, self.cell_px // 4)
        vent_h = max(2, self.cell_px // 8)
        vent_x = rect.left + max(2, self.cell_px // 5)
        vent_y = rect.top + max(2, self.cell_px // 5)
        vent_rect = self.pygame.Rect(
            vent_x,
            vent_y,
            min(vent_w, max(2, rect.w - max(3, self.cell_px // 4))),
            vent_h,
        )
        self.pygame.draw.rect(overlay, (shadow[0], shadow[1], shadow[2], 136), vent_rect)
        self.pygame.draw.rect(overlay, (parapet[0], parapet[1], parapet[2], 148), vent_rect, max(1, seam_w))

        hatch_y = rect.top + max(2, self.cell_px // 3)
        self.pygame.draw.line(
            overlay,
            seam,
            (rect.left + max(2, self.cell_px // 5), hatch_y),
            (rect.right - max(2, self.cell_px // 5), hatch_y),
            seam_w,
        )
        diag_start_x = rect.left + max(1, self.cell_px // 4)
        diag_start_y = rect.bottom - max(2, self.cell_px // 4)
        diag_end_x = rect.right - max(2, self.cell_px // 6)
        diag_end_y = rect.top + max(2, self.cell_px // 4)
        self.pygame.draw.line(
            overlay,
            (shadow[0], shadow[1], shadow[2], 96),
            (diag_start_x, diag_start_y),
            (diag_end_x, diag_end_y),
            seam_w,
        )

        if color_key == "building_roof_entertainment":
            neon_specs = (
                ((72, 215, 220, 182), rect.top + max(2, self.cell_px // 5)),
                ((230, 120, 220, 176), rect.centery),
                ((245, 196, 92, 170), rect.bottom - max(3, self.cell_px // 5)),
            )
            bar_inset = max(2, self.cell_px // 6)
            bar_w = max(1, self.cell_px // 24)
            for neon_color, band_y in neon_specs:
                self.pygame.draw.line(
                    overlay,
                    neon_color,
                    (rect.left + bar_inset, band_y),
                    (rect.right - bar_inset, band_y),
                    bar_w,
                )
            light_r = max(1, self.cell_px // 14)
            marquee_y = rect.top + max(2, self.cell_px // 7)
            marquee_step = max(4, self.cell_px // 4)
            marquee_colors = (
                (72, 215, 220, 170),
                (230, 120, 220, 168),
                (245, 196, 92, 162),
            )
            idx = 0
            for px in range(rect.left + bar_inset, rect.right - bar_inset, marquee_step):
                self.pygame.draw.circle(overlay, marquee_colors[idx % len(marquee_colors)], (px, marquee_y), light_r)
                idx += 1

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_block_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 14)
        rect = self.pygame.Rect(inset, inset, max(1, self.cell_px - (inset * 2)), max(1, self.cell_px - (inset * 2)))
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 184), rect)
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 220), rect, max(1, self.cell_px // 16))
        crack = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 128)
        self.pygame.draw.line(
            overlay,
            crack,
            (rect.left + max(1, self.cell_px // 5), rect.top + 1),
            (rect.centerx, rect.centery),
            max(1, self.cell_px // 18),
        )
        self.pygame.draw.line(
            overlay,
            crack,
            (rect.centerx, rect.centery),
            (rect.right - max(1, self.cell_px // 6), rect.bottom - 2),
            max(1, self.cell_px // 18),
        )
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_brush_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        base_h = max(3, self.cell_px // 4)
        self.pygame.draw.rect(
            overlay,
            (frame[0], frame[1], frame[2], 74),
            (0, self.cell_px - base_h, self.cell_px, base_h),
        )
        stalk_w = max(1, self.cell_px // 16)
        for px, top_frac in (
            (self.cell_px // 5, 0.34),
            (self.cell_px // 2, 0.18),
            (self.cell_px - max(3, self.cell_px // 4), 0.28),
        ):
            top_y = max(1, int(self.cell_px * top_frac))
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 186),
                (px, self.cell_px - 2),
                (px, top_y),
                stalk_w,
            )
        leaf = (min(255, int(frame[0] * 1.08)), min(255, int(frame[1] * 1.08)), min(255, int(frame[2] * 1.08)), 154)
        for px, py, r in (
            (self.cell_px // 5, max(2, self.cell_px // 3), max(1, self.cell_px // 14)),
            (self.cell_px // 2, max(2, self.cell_px // 4), max(1, self.cell_px // 12)),
            (self.cell_px - max(3, self.cell_px // 4), max(2, self.cell_px // 3), max(1, self.cell_px // 14)),
        ):
            self.pygame.draw.circle(overlay, leaf, (px, py), r)
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_rock_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.06)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        points = [
            (max(1, self.cell_px // 6), self.cell_px - max(2, self.cell_px // 5)),
            (max(2, self.cell_px // 3), max(1, self.cell_px // 6)),
            (self.cell_px - max(2, self.cell_px // 4), max(2, self.cell_px // 4)),
            (self.cell_px - max(2, self.cell_px // 6), self.cell_px - max(3, self.cell_px // 10)),
            (self.cell_px // 2, self.cell_px - max(1, self.cell_px // 10)),
        ]
        self.pygame.draw.polygon(overlay, (frame[0], frame[1], frame[2], 172), points)
        self.pygame.draw.polygon(overlay, (frame[0], frame[1], frame[2], 220), points, max(1, self.cell_px // 18))
        highlight = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            136,
        )
        self.pygame.draw.line(
            overlay,
            highlight,
            (points[0][0] + 1, points[0][1] - 2),
            (points[2][0] - 1, points[2][1]),
            max(1, self.cell_px // 18),
        )
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_water_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 132), (0, 0, self.cell_px, self.cell_px))
        crest = (
            min(255, int(frame[0] * 1.18)),
            min(255, int(frame[1] * 1.18)),
            min(255, int(frame[2] * 1.18)),
            180,
        )
        stroke_w = max(1, self.cell_px // 18)
        bands = (
            max(2, self.cell_px // 4),
            self.cell_px // 2,
            self.cell_px - max(3, self.cell_px // 4),
        )
        for base_y in bands:
            points = []
            for idx, px in enumerate(range(0, self.cell_px + 1, max(2, self.cell_px // 5))):
                offset = -max(1, self.cell_px // 16) if idx % 2 == 0 else max(1, self.cell_px // 16)
                points.append((px, max(0, min(self.cell_px - 1, base_y + offset))))
            if len(points) >= 2:
                self.pygame.draw.lines(overlay, crest, False, points, stroke_w)
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_road_overlay(self, x, y, color=None, attrs=0, *, trail=False):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.04)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        road_h = max(4, self.cell_px // (4 if trail else 3))
        road_y = (self.cell_px - road_h) // 2
        fill_alpha = 138 if trail else 170
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], fill_alpha), (0, road_y, self.cell_px, road_h))
        if trail:
            dash_w = max(2, self.cell_px // 5)
            for px in range(max(1, self.cell_px // 10), self.cell_px, dash_w + max(1, self.cell_px // 12)):
                self.pygame.draw.rect(
                    overlay,
                    (min(255, int(frame[0] * 1.08)), min(255, int(frame[1] * 1.08)), min(255, int(frame[2] * 1.08)), 116),
                    (px, road_y + max(1, road_h // 3), dash_w, max(1, road_h // 3)),
                )
        else:
            stripe_y = road_y + (road_h // 2)
            stripe_w = max(1, self.cell_px // 18)
            for px in range(max(1, self.cell_px // 8), self.cell_px, max(3, self.cell_px // 4)):
                seg_w = max(2, self.cell_px // 6)
                self.pygame.draw.line(
                    overlay,
                    (245, 224, 144, 178),
                    (px, stripe_y),
                    (min(self.cell_px - 1, px + seg_w), stripe_y),
                    stripe_w,
                )
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_salt_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        pale = (
            min(255, int(frame[0] * 1.06)),
            min(255, int(frame[1] * 1.06)),
            min(255, int(frame[2] * 1.06)),
            144,
        )
        self.pygame.draw.rect(overlay, pale, (0, 0, self.cell_px, self.cell_px))
        speck = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 88)
        for px, py in (
            (self.cell_px // 5, self.cell_px // 4),
            (self.cell_px // 2, self.cell_px // 3),
            (self.cell_px - max(3, self.cell_px // 4), self.cell_px // 2),
            (self.cell_px // 3, self.cell_px - max(3, self.cell_px // 4)),
            (self.cell_px - max(4, self.cell_px // 3), self.cell_px - max(4, self.cell_px // 5)),
        ):
            self.pygame.draw.circle(overlay, speck, (px, py), max(1, self.cell_px // 18))
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_item_overlay(self, x, y, color=None, attrs=0, *, kind="ground"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 16)
        fill = (frame[0], frame[1], frame[2], 156)
        stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            210,
        )
        dark = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 132)

        if kind == "ground":
            points = [
                (mid_x, max(2, self.cell_px // 5)),
                (self.cell_px - max(3, self.cell_px // 5), mid_y),
                (mid_x, self.cell_px - max(3, self.cell_px // 5)),
                (max(2, self.cell_px // 5), mid_y),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
        elif kind == "medical":
            bar_w = max(2, self.cell_px // 5)
            arm = max(4, self.cell_px // 3)
            self.pygame.draw.rect(
                overlay,
                fill,
                (mid_x - (bar_w // 2), max(2, mid_y - arm // 2), bar_w, arm),
            )
            self.pygame.draw.rect(
                overlay,
                fill,
                (max(2, mid_x - arm // 2), mid_y - (bar_w // 2), arm, bar_w),
            )
            self.pygame.draw.rect(
                overlay,
                stroke,
                (mid_x - (bar_w // 2), max(2, mid_y - arm // 2), bar_w, arm),
                stroke_w,
            )
            self.pygame.draw.rect(
                overlay,
                stroke,
                (max(2, mid_x - arm // 2), mid_y - (bar_w // 2), arm, bar_w),
                stroke_w,
            )
        elif kind == "token":
            radius = max(3, self.cell_px // 4)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), radius)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, dark, (mid_x, mid_y), max(1, radius // 2), max(1, stroke_w - 1))
        elif kind == "tool":
            handle_x0 = max(2, self.cell_px // 4)
            handle_y0 = self.cell_px - max(4, self.cell_px // 3)
            handle_x1 = self.cell_px - max(4, self.cell_px // 4)
            handle_y1 = max(3, self.cell_px // 3)
            self.pygame.draw.line(overlay, stroke, (handle_x0, handle_y0), (handle_x1, handle_y1), max(2, stroke_w + 1))
            jaw_r = max(2, self.cell_px // 7)
            self.pygame.draw.circle(overlay, fill, (handle_x1, handle_y1), jaw_r)
            self.pygame.draw.circle(overlay, (0, 0, 0, 0), (handle_x1, handle_y1), max(1, jaw_r - 1))
        elif kind == "weapon":
            self.pygame.draw.line(
                overlay,
                stroke,
                (max(2, self.cell_px // 4), self.cell_px - max(3, self.cell_px // 4)),
                (self.cell_px - max(2, self.cell_px // 4), max(2, self.cell_px // 4)),
                max(2, stroke_w + 1),
            )
            grip_x = max(2, self.cell_px // 4)
            grip_y = self.cell_px - max(3, self.cell_px // 4)
            self.pygame.draw.line(
                overlay,
                dark,
                (grip_x - max(1, self.cell_px // 14), grip_y + max(1, self.cell_px // 12)),
                (grip_x + max(2, self.cell_px // 8), grip_y - max(1, self.cell_px // 10)),
                stroke_w,
            )
        elif kind == "armor":
            points = [
                (mid_x, max(2, self.cell_px // 5)),
                (self.cell_px - max(3, self.cell_px // 4), max(3, self.cell_px // 3)),
                (self.cell_px - max(3, self.cell_px // 4), self.cell_px - max(4, self.cell_px // 4)),
                (mid_x, self.cell_px - max(2, self.cell_px // 5)),
                (max(2, self.cell_px // 4), self.cell_px - max(4, self.cell_px // 4)),
                (max(2, self.cell_px // 4), max(3, self.cell_px // 3)),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
        elif kind == "food":
            bun_h = max(3, self.cell_px // 5)
            self.pygame.draw.ellipse(
                overlay,
                fill,
                (max(2, self.cell_px // 5), mid_y - bun_h, self.cell_px - max(4, self.cell_px // 2), bun_h + 1),
            )
            self.pygame.draw.rect(
                overlay,
                (100, 180, 90, 164),
                (max(2, self.cell_px // 4), mid_y - 1, self.cell_px - max(4, self.cell_px // 2), max(2, self.cell_px // 8)),
            )
            self.pygame.draw.ellipse(
                overlay,
                stroke,
                (max(2, self.cell_px // 5), mid_y - bun_h, self.cell_px - max(4, self.cell_px // 2), bun_h + 1),
                stroke_w,
            )
        elif kind == "drink":
            bottle_w = max(3, self.cell_px // 4)
            neck_w = max(2, self.cell_px // 8)
            neck_h = max(2, self.cell_px // 6)
            body_rect = (mid_x - (bottle_w // 2), mid_y - max(2, self.cell_px // 6), bottle_w, max(5, self.cell_px // 3))
            neck_rect = (mid_x - (neck_w // 2), body_rect[1] - neck_h + 1, neck_w, neck_h)
            self.pygame.draw.rect(overlay, fill, body_rect)
            self.pygame.draw.rect(overlay, fill, neck_rect)
            self.pygame.draw.rect(overlay, stroke, body_rect, stroke_w)
            self.pygame.draw.rect(overlay, stroke, neck_rect, stroke_w)
        elif kind == "access":
            ring_r = max(2, self.cell_px // 8)
            ring_x = max(3, self.cell_px // 3)
            self.pygame.draw.circle(overlay, stroke, (ring_x, mid_y), ring_r, stroke_w)
            self.pygame.draw.line(
                overlay,
                stroke,
                (ring_x + ring_r, mid_y),
                (self.cell_px - max(3, self.cell_px // 5), mid_y),
                stroke_w,
            )
            tooth_x = self.cell_px - max(3, self.cell_px // 5)
            self.pygame.draw.line(
                overlay,
                stroke,
                (tooth_x - max(1, self.cell_px // 10), mid_y),
                (tooth_x - max(1, self.cell_px // 10), mid_y + max(2, self.cell_px // 6)),
                stroke_w,
            )
            self.pygame.draw.line(
                overlay,
                stroke,
                (tooth_x - max(3, self.cell_px // 10), mid_y),
                (tooth_x - max(3, self.cell_px // 10), mid_y + max(1, self.cell_px // 8)),
                stroke_w,
            )
        elif kind == "restricted":
            points = [
                (mid_x, max(2, self.cell_px // 6)),
                (self.cell_px - max(3, self.cell_px // 6), mid_y),
                (mid_x, self.cell_px - max(3, self.cell_px // 6)),
                (max(2, self.cell_px // 6), mid_y),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.line(
                overlay,
                dark,
                (mid_x, max(3, self.cell_px // 4)),
                (mid_x, self.cell_px - max(3, self.cell_px // 4)),
                stroke_w,
            )
        elif kind == "illegal":
            self.pygame.draw.line(
                overlay,
                stroke,
                (max(2, self.cell_px // 4), max(2, self.cell_px // 4)),
                (self.cell_px - max(3, self.cell_px // 4), self.cell_px - max(3, self.cell_px // 4)),
                max(2, stroke_w + 1),
            )
            self.pygame.draw.line(
                overlay,
                stroke,
                (self.cell_px - max(3, self.cell_px // 4), max(2, self.cell_px // 4)),
                (max(2, self.cell_px // 4), self.cell_px - max(3, self.cell_px // 4)),
                max(2, stroke_w + 1),
            )
        elif kind == "objective":
            radius = max(3, self.cell_px // 4)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), max(1, radius // 3))

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_vehicle_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset_x = max(2, self.cell_px // 6)
        inset_y = max(1, self.cell_px // 8)
        body_rect = self.pygame.Rect(
            inset_x,
            inset_y,
            max(4, self.cell_px - (inset_x * 2)),
            max(6, self.cell_px - (inset_y * 2)),
        )
        corner_r = max(2, self.cell_px // 6)
        stroke_w = max(1, self.cell_px // 18)

        body_fill = (frame[0], frame[1], frame[2], 170)
        body_stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            220,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 132)
        glass = (
            min(255, int(frame[0] * 0.92) + 18),
            min(255, int(frame[1] * 1.02) + 20),
            min(255, int(frame[2] * 1.08) + 24),
            144,
        )

        self.pygame.draw.rect(overlay, body_fill, body_rect, border_radius=corner_r)
        self.pygame.draw.rect(overlay, body_stroke, body_rect, stroke_w, border_radius=corner_r)

        windshield_rect = self.pygame.Rect(
            body_rect.left + max(1, self.cell_px // 8),
            body_rect.top + max(1, self.cell_px // 6),
            max(2, body_rect.w - max(2, self.cell_px // 4)),
            max(2, self.cell_px // 5),
        )
        rear_window_rect = self.pygame.Rect(
            windshield_rect.left,
            body_rect.bottom - max(2, self.cell_px // 6) - max(2, self.cell_px // 5),
            windshield_rect.w,
            max(2, self.cell_px // 5),
        )
        self.pygame.draw.rect(overlay, glass, windshield_rect, border_radius=max(1, corner_r - 1))
        self.pygame.draw.rect(overlay, glass, rear_window_rect, border_radius=max(1, corner_r - 1))

        mid_y = body_rect.centery
        self.pygame.draw.line(
            overlay,
            shadow,
            (body_rect.left + max(1, self.cell_px // 7), mid_y),
            (body_rect.right - max(2, self.cell_px // 7), mid_y),
            max(1, self.cell_px // 22),
        )

        wheel_w = max(1, self.cell_px // 10)
        wheel_h = max(2, self.cell_px // 5)
        wheel_offsets = (
            (body_rect.left - max(1, wheel_w // 2), body_rect.top + max(1, self.cell_px // 7)),
            (body_rect.right - max(1, wheel_w // 2), body_rect.top + max(1, self.cell_px // 7)),
            (body_rect.left - max(1, wheel_w // 2), body_rect.bottom - wheel_h - max(1, self.cell_px // 7)),
            (body_rect.right - max(1, wheel_w // 2), body_rect.bottom - wheel_h - max(1, self.cell_px // 7)),
        )
        for wheel_x, wheel_y in wheel_offsets:
            wheel = self.pygame.Rect(wheel_x, wheel_y, wheel_w, wheel_h)
            self.pygame.draw.rect(overlay, shadow, wheel, border_radius=max(1, wheel_w // 2))

        nose_y = body_rect.top + max(1, self.cell_px // 16)
        self.pygame.draw.line(
            overlay,
            body_stroke,
            (body_rect.left + max(2, self.cell_px // 4), nose_y),
            (body_rect.right - max(2, self.cell_px // 4), nose_y),
            max(1, self.cell_px // 24),
        )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_infrastructure_overlay(self, x, y, color=None, attrs=0, *, kind="lamp"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.06)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 168)
        stroke = (
            min(255, int(frame[0] * 1.1)),
            min(255, int(frame[1] * 1.1)),
            min(255, int(frame[2] * 1.1)),
            224,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 132)
        glow = (
            min(255, int(frame[0] * 1.16) + 10),
            min(255, int(frame[1] * 1.16) + 10),
            min(255, int(frame[2] * 1.08) + 6),
            76,
        )
        accent = (
            min(255, int(frame[0] * 0.94) + 18),
            min(255, int(frame[1] * 1.02) + 24),
            min(255, int(frame[2] * 1.12) + 30),
            156,
        )

        if kind == "lamp":
            pole_top = max(2, self.cell_px // 5)
            pole_bottom = self.cell_px - max(2, self.cell_px // 7)
            self.pygame.draw.line(overlay, shadow, (mid_x, pole_top + 1), (mid_x, pole_bottom), max(1, stroke_w + 1))
            self.pygame.draw.line(overlay, stroke, (mid_x, pole_top), (mid_x, pole_bottom - 1), stroke_w)
            arm_y = pole_top + max(1, self.cell_px // 7)
            arm_x = mid_x + max(2, self.cell_px // 6)
            self.pygame.draw.line(overlay, stroke, (mid_x, arm_y), (arm_x, arm_y), stroke_w)
            head_r = max(2, self.cell_px // 8)
            lamp_center = (arm_x + head_r, arm_y + head_r)
            self.pygame.draw.circle(overlay, glow, lamp_center, head_r + max(2, self.cell_px // 7))
            self.pygame.draw.circle(overlay, fill, lamp_center, head_r)
            self.pygame.draw.circle(overlay, stroke, lamp_center, head_r, stroke_w)
        elif kind == "pole":
            top_y = max(2, self.cell_px // 6)
            bot_y = self.cell_px - max(2, self.cell_px // 8)
            self.pygame.draw.line(overlay, shadow, (mid_x, top_y), (mid_x, bot_y), max(1, stroke_w + 1))
            self.pygame.draw.line(overlay, stroke, (mid_x, top_y), (mid_x, bot_y), stroke_w)
            cross_y = top_y + max(2, self.cell_px // 5)
            arm_half = max(3, self.cell_px // 4)
            self.pygame.draw.line(overlay, stroke, (mid_x - arm_half, cross_y), (mid_x + arm_half, cross_y), stroke_w)
            brace_y = cross_y + max(2, self.cell_px // 5)
            self.pygame.draw.line(
                overlay,
                accent,
                (mid_x - max(1, arm_half - 1), cross_y + 1),
                (mid_x, brace_y),
                max(1, stroke_w - 1),
            )
            self.pygame.draw.line(
                overlay,
                accent,
                (mid_x + max(1, arm_half - 1), cross_y + 1),
                (mid_x, brace_y),
                max(1, stroke_w - 1),
            )
        elif kind == "hydrant":
            body_w = max(4, self.cell_px // 3)
            body_h = max(4, self.cell_px // 3)
            body = self.pygame.Rect(mid_x - (body_w // 2), mid_y - max(1, self.cell_px // 12), body_w, body_h)
            top = self.pygame.Rect(mid_x - max(2, self.cell_px // 10), body.top - max(2, self.cell_px // 8), max(4, self.cell_px // 5), max(3, self.cell_px // 6))
            left_cap = self.pygame.Rect(body.left - max(2, self.cell_px // 8), body.top + max(1, self.cell_px // 8), max(3, self.cell_px // 6), max(3, self.cell_px // 7))
            right_cap = self.pygame.Rect(body.right - max(1, self.cell_px // 18), body.top + max(1, self.cell_px // 8), max(3, self.cell_px // 6), max(3, self.cell_px // 7))
            self.pygame.draw.rect(overlay, fill, body, border_radius=max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, stroke, body, stroke_w, border_radius=max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, fill, top, border_radius=max(1, self.cell_px // 10))
            self.pygame.draw.rect(overlay, fill, left_cap, border_radius=max(1, self.cell_px // 10))
            self.pygame.draw.rect(overlay, fill, right_cap, border_radius=max(1, self.cell_px // 10))
            footing_y = body.bottom - max(1, self.cell_px // 16)
            self.pygame.draw.line(
                overlay,
                shadow,
                (body.left + 1, footing_y),
                (body.right - 2, footing_y),
                max(1, stroke_w + 1),
            )
        elif kind == "stop":
            post_top = max(2, self.cell_px // 6)
            post_bottom = self.cell_px - max(2, self.cell_px // 7)
            self.pygame.draw.line(overlay, shadow, (mid_x, post_top), (mid_x, post_bottom), max(1, stroke_w + 1))
            self.pygame.draw.line(overlay, stroke, (mid_x, post_top), (mid_x, post_bottom), stroke_w)
            sign = self.pygame.Rect(
                mid_x - max(3, self.cell_px // 5),
                post_top + max(1, self.cell_px // 10),
                max(6, self.cell_px // 2),
                max(4, self.cell_px // 3),
            )
            self.pygame.draw.rect(overlay, fill, sign, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, sign, stroke_w, border_radius=max(2, self.cell_px // 10))
            route_y = sign.centery
            self.pygame.draw.line(
                overlay,
                accent,
                (sign.left + max(2, self.cell_px // 8), route_y),
                (sign.right - max(2, self.cell_px // 8), route_y),
                max(1, stroke_w),
            )
        elif kind == "utility_a":
            box = self.pygame.Rect(
                max(2, self.cell_px // 6),
                max(2, self.cell_px // 5),
                max(6, self.cell_px - max(4, self.cell_px // 3)),
                max(7, self.cell_px - max(4, self.cell_px // 2)),
            )
            self.pygame.draw.rect(overlay, fill, box, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, box, stroke_w, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.line(
                overlay,
                accent,
                (box.left + max(2, self.cell_px // 6), box.centery),
                (box.right - max(2, self.cell_px // 6), box.centery),
                max(1, stroke_w),
            )
            for px, py in (
                (box.left + max(2, self.cell_px // 5), box.top + max(2, self.cell_px // 5)),
                (box.right - max(3, self.cell_px // 4), box.bottom - max(3, self.cell_px // 4)),
            ):
                self.pygame.draw.circle(overlay, shadow, (px, py), max(1, self.cell_px // 22))
        elif kind == "utility_b":
            box = self.pygame.Rect(
                max(2, self.cell_px // 5),
                max(2, self.cell_px // 6),
                max(6, self.cell_px - max(4, self.cell_px // 2)),
                max(8, self.cell_px - max(4, self.cell_px // 3)),
            )
            self.pygame.draw.rect(overlay, fill, box, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, box, stroke_w, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.line(
                overlay,
                accent,
                (box.left + max(2, self.cell_px // 6), box.bottom - max(3, self.cell_px // 4)),
                (box.right - max(2, self.cell_px // 6), box.top + max(3, self.cell_px // 4)),
                max(1, stroke_w),
            )
            slot_x = box.left + max(2, self.cell_px // 5)
            self.pygame.draw.line(
                overlay,
                shadow,
                (slot_x, box.top + max(2, self.cell_px // 4)),
                (slot_x, box.bottom - max(2, self.cell_px // 4)),
                max(1, stroke_w - 1),
            )
        elif kind == "atm":
            kiosk = self.pygame.Rect(
                max(2, self.cell_px // 5),
                max(1, self.cell_px // 10),
                max(7, self.cell_px - max(4, self.cell_px // 2)),
                max(10, self.cell_px - max(3, self.cell_px // 5)),
            )
            self.pygame.draw.rect(overlay, fill, kiosk, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, kiosk, stroke_w, border_radius=max(2, self.cell_px // 10))
            screen = self.pygame.Rect(
                kiosk.left + max(2, self.cell_px // 6),
                kiosk.top + max(2, self.cell_px // 6),
                max(3, kiosk.w - max(4, self.cell_px // 3)),
                max(3, self.cell_px // 5),
            )
            slot = self.pygame.Rect(
                kiosk.left + max(2, self.cell_px // 5),
                kiosk.bottom - max(3, self.cell_px // 3),
                max(4, kiosk.w - max(4, self.cell_px // 2)),
                max(1, self.cell_px // 16),
            )
            self.pygame.draw.rect(overlay, accent, screen, border_radius=max(1, self.cell_px // 12))
            self.pygame.draw.rect(overlay, shadow, slot, border_radius=max(1, self.cell_px // 20))
            self.pygame.draw.circle(
                overlay,
                shadow,
                (screen.right - max(2, self.cell_px // 8), kiosk.bottom - max(3, self.cell_px // 4)),
                max(1, self.cell_px // 20),
            )
        elif kind == "claim_terminal":
            kiosk = self.pygame.Rect(
                max(2, self.cell_px // 4),
                max(1, self.cell_px // 12),
                max(6, self.cell_px - max(4, self.cell_px // 2)),
                max(9, self.cell_px - max(3, self.cell_px // 5)),
            )
            self.pygame.draw.rect(overlay, fill, kiosk, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, kiosk, stroke_w, border_radius=max(2, self.cell_px // 10))
            slip = self.pygame.Rect(
                kiosk.left + max(2, self.cell_px // 6),
                kiosk.top + max(2, self.cell_px // 6),
                max(4, kiosk.w - max(4, self.cell_px // 3)),
                max(6, kiosk.h - max(5, self.cell_px // 2)),
            )
            self.pygame.draw.rect(overlay, accent, slip, border_radius=max(1, self.cell_px // 14))
            check_left = slip.left + max(2, self.cell_px // 7)
            check_mid = slip.left + max(3, self.cell_px // 4)
            check_right = slip.right - max(2, self.cell_px // 7)
            check_y = slip.centery
            self.pygame.draw.line(
                overlay,
                shadow,
                (check_left, check_y),
                (check_mid, check_y + max(2, self.cell_px // 8)),
                max(1, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                shadow,
                (check_mid, check_y + max(2, self.cell_px // 8)),
                (check_right, check_y - max(2, self.cell_px // 8)),
                max(1, stroke_w),
            )
        else:
            panel = self.pygame.Rect(
                max(2, self.cell_px // 4),
                max(2, self.cell_px // 7),
                max(5, self.cell_px - max(4, self.cell_px // 2)),
                max(8, self.cell_px - max(4, self.cell_px // 3)),
            )
            self.pygame.draw.rect(overlay, fill, panel, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, panel, stroke_w, border_radius=max(2, self.cell_px // 10))
            px = panel.left + max(2, self.cell_px // 6)
            py = panel.top + max(2, self.cell_px // 5)
            self.pygame.draw.circle(overlay, accent, (px, py), max(1, self.cell_px // 18))
            self.pygame.draw.line(
                overlay,
                accent,
                (px, py),
                (panel.right - max(2, self.cell_px // 6), py),
                max(1, stroke_w - 1),
            )
            self.pygame.draw.line(
                overlay,
                accent,
                (px, py),
                (panel.right - max(2, self.cell_px // 5), panel.bottom - max(2, self.cell_px // 5)),
                max(1, stroke_w - 1),
            )
            self.pygame.draw.circle(
                overlay,
                shadow,
                (panel.right - max(2, self.cell_px // 5), panel.bottom - max(2, self.cell_px // 5)),
                max(1, self.cell_px // 20),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_actor_token_overlay(self, x, y, glyph, color=None, attrs=0, *, kind="civilian"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        inset = max(1, self.cell_px // 8)
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 108)
        stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            220,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 128)
        accent = (
            min(255, int(frame[0] * 1.08) + 10),
            min(255, int(frame[1] * 1.02) + 8),
            min(255, int(frame[2] * 1.02) + 8),
            160,
        )

        if kind == "player":
            radius = max(4, (self.cell_px // 2) - inset)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), radius)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.arc(
                overlay,
                accent,
                (inset, inset, max(4, self.cell_px - (inset * 2)), max(4, self.cell_px - (inset * 2))),
                0.35,
                2.25,
                max(1, stroke_w),
            )
        elif kind == "guard":
            points = [
                (mid_x, inset),
                (self.cell_px - inset - 2, inset + max(2, self.cell_px // 4)),
                (self.cell_px - inset - 3, self.cell_px - inset - max(2, self.cell_px // 4)),
                (mid_x, self.cell_px - inset - 1),
                (inset + 2, self.cell_px - inset - max(2, self.cell_px // 4)),
                (inset + 1, inset + max(2, self.cell_px // 4)),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.line(
                overlay,
                accent,
                (mid_x - max(2, self.cell_px // 6), mid_y - max(1, self.cell_px // 8)),
                (mid_x + max(2, self.cell_px // 6), mid_y - max(1, self.cell_px // 8)),
                max(1, stroke_w),
            )
        elif kind == "scout":
            diamond = [
                (mid_x, inset),
                (self.cell_px - inset - 1, mid_y),
                (mid_x, self.cell_px - inset - 1),
                (inset, mid_y),
            ]
            self.pygame.draw.polygon(overlay, fill, diamond)
            self.pygame.draw.polygon(overlay, stroke, diamond, stroke_w)
            self.pygame.draw.line(
                overlay,
                accent,
                (mid_x - max(2, self.cell_px // 6), mid_y + max(1, self.cell_px // 6)),
                (mid_x, mid_y - max(2, self.cell_px // 6)),
                max(1, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                accent,
                (mid_x, mid_y - max(2, self.cell_px // 6)),
                (mid_x + max(2, self.cell_px // 6), mid_y + max(1, self.cell_px // 6)),
                max(1, stroke_w),
            )
        else:
            rect = self.pygame.Rect(
                inset,
                inset,
                max(4, self.cell_px - (inset * 2)),
                max(4, self.cell_px - (inset * 2)),
            )
            self.pygame.draw.rect(overlay, fill, rect, border_radius=max(2, self.cell_px // 7))
            self.pygame.draw.rect(overlay, stroke, rect, stroke_w, border_radius=max(2, self.cell_px // 7))
            self.pygame.draw.line(
                overlay,
                accent,
                (rect.left + max(2, self.cell_px // 6), rect.bottom - max(2, self.cell_px // 5)),
                (rect.right - max(2, self.cell_px // 6), rect.bottom - max(2, self.cell_px // 5)),
                max(1, stroke_w),
            )

        text_value = str(glyph or "@")[:1] or "@"
        brightness = (frame[0] * 0.299) + (frame[1] * 0.587) + (frame[2] * 0.114)
        text_rgb = (24, 28, 32) if brightness >= 150 else (245, 245, 245)
        text_surface = self._ui_bold_font.render(text_value, True, text_rgb)
        text_rect = text_surface.get_rect(center=(mid_x, mid_y))
        text_rect.y += max(-1, self.cell_px // 32)
        overlay.blit(text_surface, text_rect)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_service_security_fixture_overlay(self, x, y, color=None, attrs=0, *, kind="terminal"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.06)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 8)
        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 164)
        stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            224,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 132)
        screen = (
            min(255, int(frame[0] * 0.94) + 26),
            min(255, int(frame[1] * 1.02) + 30),
            min(255, int(frame[2] * 1.1) + 34),
            160,
        )
        accent = (
            min(255, int(frame[0] * 1.05) + 12),
            min(255, int(frame[1] * 1.05) + 12),
            min(255, int(frame[2] * 1.05) + 12),
            170,
        )

        if kind == "security_booth":
            booth = self.pygame.Rect(
                inset,
                max(1, self.cell_px // 6),
                max(6, self.cell_px - (inset * 2)),
                max(8, self.cell_px - max(3, self.cell_px // 3)),
            )
            roof = [
                (booth.left, booth.top + max(2, self.cell_px // 7)),
                (mid_x, max(1, self.cell_px // 10)),
                (booth.right - 1, booth.top + max(2, self.cell_px // 7)),
            ]
            self.pygame.draw.polygon(overlay, (shadow[0], shadow[1], shadow[2], 148), roof)
            self.pygame.draw.rect(overlay, fill, booth, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, booth, stroke_w, border_radius=max(2, self.cell_px // 10))
            window = self.pygame.Rect(
                booth.left + max(2, self.cell_px // 6),
                booth.top + max(2, self.cell_px // 6),
                max(3, booth.w - max(4, self.cell_px // 3)),
                max(3, self.cell_px // 4),
            )
            self.pygame.draw.rect(overlay, screen, window, border_radius=max(1, self.cell_px // 12))
            self.pygame.draw.line(
                overlay,
                shadow,
                (booth.left + max(2, self.cell_px // 5), booth.bottom - max(2, self.cell_px // 4)),
                (booth.right - max(2, self.cell_px // 5), booth.bottom - max(2, self.cell_px // 4)),
                max(1, stroke_w),
            )
        elif kind == "vending":
            body = self.pygame.Rect(
                inset + max(1, self.cell_px // 12),
                max(1, self.cell_px // 12),
                max(6, self.cell_px - max(4, self.cell_px // 3)),
                max(10, self.cell_px - max(2, self.cell_px // 6)),
            )
            self.pygame.draw.rect(overlay, fill, body, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, body, stroke_w, border_radius=max(2, self.cell_px // 10))
            display = self.pygame.Rect(
                body.left + max(2, self.cell_px // 6),
                body.top + max(2, self.cell_px // 6),
                max(3, body.w - max(4, self.cell_px // 3)),
                max(3, body.h // 2),
            )
            self.pygame.draw.rect(overlay, screen, display, border_radius=max(1, self.cell_px // 12))
            row_h = max(1, self.cell_px // 18)
            for idx in range(3):
                py = display.top + max(2, self.cell_px // 8) + (idx * max(2, self.cell_px // 8))
                self.pygame.draw.line(
                    overlay,
                    accent,
                    (display.left + max(2, self.cell_px // 7), py),
                    (display.right - max(2, self.cell_px // 7), py),
                    row_h,
                )
            slot = self.pygame.Rect(
                body.left + max(2, self.cell_px // 5),
                body.bottom - max(3, self.cell_px // 4),
                max(4, body.w - max(4, self.cell_px // 2)),
                max(1, self.cell_px // 16),
            )
            self.pygame.draw.rect(overlay, shadow, slot, border_radius=max(1, self.cell_px // 20))
        elif kind == "charging":
            pillar = self.pygame.Rect(
                mid_x - max(2, self.cell_px // 7),
                max(1, self.cell_px // 10),
                max(4, self.cell_px // 3),
                max(10, self.cell_px - max(3, self.cell_px // 6)),
            )
            self.pygame.draw.rect(overlay, fill, pillar, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, pillar, stroke_w, border_radius=max(2, self.cell_px // 10))
            display = self.pygame.Rect(
                pillar.left + max(1, self.cell_px // 10),
                pillar.top + max(2, self.cell_px // 6),
                max(2, pillar.w - max(2, self.cell_px // 5)),
                max(3, self.cell_px // 5),
            )
            self.pygame.draw.rect(overlay, screen, display, border_radius=max(1, self.cell_px // 14))
            cable_start = (pillar.right - max(1, self.cell_px // 16), pillar.centery)
            cable_mid = (self.cell_px - max(3, self.cell_px // 12), pillar.centery + max(2, self.cell_px // 7))
            cable_end = (self.cell_px - max(3, self.cell_px // 12), self.cell_px - max(3, self.cell_px // 8))
            self.pygame.draw.line(overlay, accent, cable_start, cable_mid, max(1, stroke_w))
            self.pygame.draw.line(overlay, accent, cable_mid, cable_end, max(1, stroke_w))
            plug = self.pygame.Rect(cable_end[0] - max(1, self.cell_px // 12), cable_end[1] - max(1, self.cell_px // 10), max(2, self.cell_px // 7), max(3, self.cell_px // 7))
            self.pygame.draw.rect(overlay, stroke, plug, border_radius=max(1, self.cell_px // 18))
        else:
            kiosk = self.pygame.Rect(
                inset,
                max(1, self.cell_px // 8),
                max(6, self.cell_px - (inset * 2)),
                max(9, self.cell_px - max(3, self.cell_px // 4)),
            )
            self.pygame.draw.rect(overlay, fill, kiosk, border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, stroke, kiosk, stroke_w, border_radius=max(2, self.cell_px // 10))
            display = self.pygame.Rect(
                kiosk.left + max(2, self.cell_px // 6),
                kiosk.top + max(2, self.cell_px // 6),
                max(3, kiosk.w - max(4, self.cell_px // 3)),
                max(3, self.cell_px // 4),
            )
            self.pygame.draw.rect(overlay, screen, display, border_radius=max(1, self.cell_px // 12))
            for idx in range(2):
                py = display.bottom + max(2, self.cell_px // 10) + (idx * max(2, self.cell_px // 8))
                self.pygame.draw.line(
                    overlay,
                    accent,
                    (kiosk.left + max(2, self.cell_px // 6), py),
                    (kiosk.right - max(2, self.cell_px // 6), py),
                    max(1, stroke_w - 1),
                )
            self.pygame.draw.circle(
                overlay,
                shadow,
                (kiosk.right - max(3, self.cell_px // 8), kiosk.bottom - max(3, self.cell_px // 8)),
                max(1, self.cell_px // 20),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_cover_fixture_overlay(self, x, y, color=None, attrs=0, *, kind="bench"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.04)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 9)
        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 156)
        stroke = (
            min(255, int(frame[0] * 1.1)),
            min(255, int(frame[1] * 1.1)),
            min(255, int(frame[2] * 1.1)),
            220,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 124)
        bright = (
            min(255, int(frame[0] * 1.02) + 16),
            min(255, int(frame[1] * 1.02) + 16),
            min(255, int(frame[2] * 1.02) + 16),
            170,
        )
        leaf = (96, 176, 108, 176)
        hazard = (228, 192, 88, 176)

        if kind == "bench":
            seat = self.pygame.Rect(
                inset + max(1, self.cell_px // 10),
                mid_y,
                max(6, self.cell_px - (inset * 2) - max(2, self.cell_px // 8)),
                max(2, self.cell_px // 6),
            )
            back = self.pygame.Rect(seat.left, seat.top - max(3, self.cell_px // 5), seat.w, max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, fill, back, border_radius=max(1, self.cell_px // 14))
            self.pygame.draw.rect(overlay, stroke, back, stroke_w, border_radius=max(1, self.cell_px // 14))
            self.pygame.draw.rect(overlay, fill, seat, border_radius=max(1, self.cell_px // 14))
            self.pygame.draw.rect(overlay, stroke, seat, stroke_w, border_radius=max(1, self.cell_px // 14))
            for leg_x in (seat.left + max(2, self.cell_px // 8), seat.right - max(2, self.cell_px // 8)):
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (leg_x, seat.bottom),
                    (leg_x, self.cell_px - inset - 1),
                    max(1, stroke_w),
                )
        elif kind == "shelter":
            roof = [
                (inset, inset + max(1, self.cell_px // 8)),
                (mid_x, inset),
                (self.cell_px - inset - 1, inset + max(1, self.cell_px // 8)),
                (self.cell_px - inset - 2, inset + max(3, self.cell_px // 5)),
                (inset + 1, inset + max(3, self.cell_px // 5)),
            ]
            self.pygame.draw.polygon(overlay, fill, roof)
            self.pygame.draw.polygon(overlay, stroke, roof, stroke_w)
            for post_x in (inset + max(2, self.cell_px // 8), self.cell_px - inset - max(3, self.cell_px // 8)):
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (post_x, inset + max(3, self.cell_px // 5)),
                    (post_x, self.cell_px - inset - 1),
                    max(1, stroke_w),
                )
            seat_y = self.cell_px - inset - max(3, self.cell_px // 6)
            self.pygame.draw.line(
                overlay,
                bright,
                (inset + max(2, self.cell_px // 7), seat_y),
                (self.cell_px - inset - max(2, self.cell_px // 7), seat_y),
                max(1, self.cell_px // 10),
            )
        elif kind == "planter":
            box = self.pygame.Rect(
                inset + max(1, self.cell_px // 10),
                mid_y,
                max(6, self.cell_px - (inset * 2) - max(2, self.cell_px // 8)),
                max(4, self.cell_px // 3),
            )
            self.pygame.draw.rect(overlay, fill, box, border_radius=max(1, self.cell_px // 14))
            self.pygame.draw.rect(overlay, stroke, box, stroke_w, border_radius=max(1, self.cell_px // 14))
            soil_y = box.top + max(1, self.cell_px // 14)
            self.pygame.draw.line(
                overlay,
                shadow,
                (box.left + max(2, self.cell_px // 8), soil_y),
                (box.right - max(2, self.cell_px // 8), soil_y),
                max(1, stroke_w),
            )
            for leaf_x, leaf_h in (
                (box.left + max(3, self.cell_px // 7), max(4, self.cell_px // 3)),
                (mid_x, max(5, self.cell_px // 2)),
                (box.right - max(3, self.cell_px // 7), max(4, self.cell_px // 3)),
            ):
                self.pygame.draw.line(
                    overlay,
                    leaf,
                    (leaf_x, box.top + max(1, self.cell_px // 10)),
                    (leaf_x, box.top - leaf_h + max(4, self.cell_px // 2)),
                    max(1, stroke_w),
                )
                self.pygame.draw.circle(
                    overlay,
                    leaf,
                    (leaf_x, box.top - max(1, self.cell_px // 14)),
                    max(1, self.cell_px // 10),
                )
        elif kind == "fence":
            rail_y_top = mid_y - max(2, self.cell_px // 8)
            rail_y_bottom = mid_y + max(2, self.cell_px // 8)
            for rail_y in (rail_y_top, rail_y_bottom):
                self.pygame.draw.line(
                    overlay,
                    bright,
                    (inset + 1, rail_y),
                    (self.cell_px - inset - 2, rail_y),
                    max(1, stroke_w),
                )
            for px in (inset + max(1, self.cell_px // 8), mid_x, self.cell_px - inset - max(2, self.cell_px // 8)):
                self.pygame.draw.line(
                    overlay,
                    stroke,
                    (px, rail_y_top - max(3, self.cell_px // 6)),
                    (px, rail_y_bottom + max(3, self.cell_px // 6)),
                    max(1, stroke_w),
                )
        elif kind == "transformer":
            box = self.pygame.Rect(
                inset,
                inset + max(1, self.cell_px // 12),
                max(7, self.cell_px - (inset * 2)),
                max(8, self.cell_px - max(3, self.cell_px // 3)),
            )
            self.pygame.draw.rect(overlay, fill, box, border_radius=max(2, self.cell_px // 12))
            self.pygame.draw.rect(overlay, stroke, box, stroke_w, border_radius=max(2, self.cell_px // 12))
            stripe_y = box.top + max(2, self.cell_px // 5)
            self.pygame.draw.line(
                overlay,
                hazard,
                (box.left + max(2, self.cell_px // 7), stripe_y),
                (box.right - max(2, self.cell_px // 7), stripe_y),
                max(1, self.cell_px // 10),
            )
            for px in (box.left + max(2, self.cell_px // 6), box.right - max(3, self.cell_px // 5)):
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (px, box.bottom - max(3, self.cell_px // 6)),
                    (px + max(2, self.cell_px // 8), box.bottom - max(1, self.cell_px // 8)),
                    max(1, stroke_w),
                )
        elif kind == "cache":
            crate = self.pygame.Rect(
                inset + max(1, self.cell_px // 10),
                mid_y - max(2, self.cell_px // 8),
                max(7, self.cell_px - (inset * 2) - max(2, self.cell_px // 8)),
                max(5, self.cell_px // 3),
            )
            self.pygame.draw.rect(overlay, fill, crate, border_radius=max(1, self.cell_px // 16))
            self.pygame.draw.rect(overlay, stroke, crate, stroke_w, border_radius=max(1, self.cell_px // 16))
            self.pygame.draw.line(
                overlay,
                shadow,
                (crate.left + max(2, self.cell_px // 8), crate.centery),
                (crate.right - max(2, self.cell_px // 8), crate.centery),
                max(1, stroke_w),
            )
            self.pygame.draw.circle(
                overlay,
                bright,
                (crate.centerx, crate.centery),
                max(1, self.cell_px // 18),
            )
        else:
            tank = self.pygame.Rect(
                inset + max(1, self.cell_px // 12),
                inset + max(1, self.cell_px // 14),
                max(7, self.cell_px - (inset * 2) - max(2, self.cell_px // 10)),
                max(6, self.cell_px // 2),
            )
            self.pygame.draw.ellipse(overlay, fill, tank)
            self.pygame.draw.ellipse(overlay, stroke, tank, stroke_w)
            for px in (tank.left + max(2, self.cell_px // 6), tank.right - max(3, self.cell_px // 5)):
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (px, tank.bottom - max(1, self.cell_px // 10)),
                    (px, self.cell_px - inset - 1),
                    max(1, stroke_w),
                )
            self.pygame.draw.line(
                overlay,
                bright,
                (mid_x, tank.top + max(1, self.cell_px // 10)),
                (mid_x, tank.bottom - max(1, self.cell_px // 10)),
                max(1, stroke_w),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_property_marker_overlay(self, x, y, glyph, color=None, attrs=0, *, kind="building"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.06)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(2, self.cell_px // 7)
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 164)
        stroke = (
            min(255, int(frame[0] * 1.1)),
            min(255, int(frame[1] * 1.1)),
            min(255, int(frame[2] * 1.1)),
            220,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 120)

        if kind == "service":
            radius = max(4, (self.cell_px // 2) - inset)
            self.pygame.draw.circle(overlay, fill, (self.cell_px // 2, self.cell_px // 2), radius)
            self.pygame.draw.circle(overlay, stroke, (self.cell_px // 2, self.cell_px // 2), radius, stroke_w)
        elif kind == "fixture":
            points = [
                (self.cell_px // 2, inset),
                (self.cell_px - inset - 1, self.cell_px // 2),
                (self.cell_px // 2, self.cell_px - inset - 1),
                (inset, self.cell_px // 2),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
        elif kind == "asset":
            rect = self.pygame.Rect(inset, inset, max(4, self.cell_px - (inset * 2)), max(4, self.cell_px - (inset * 2)))
            self.pygame.draw.rect(overlay, fill, rect, border_radius=max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, stroke, rect, stroke_w, border_radius=max(2, self.cell_px // 8))
        else:
            points = [
                (self.cell_px // 2, inset),
                (self.cell_px - inset - 2, inset + max(1, self.cell_px // 5)),
                (self.cell_px - inset - 2, self.cell_px - inset - 2),
                (inset + 1, self.cell_px - inset - 2),
                (inset, inset + max(1, self.cell_px // 3)),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)

        if kind != "service":
            self.pygame.draw.line(
                overlay,
                shadow,
                (inset + 1, self.cell_px - inset - 2),
                (self.cell_px - inset - 2, self.cell_px - inset - 2),
                max(1, self.cell_px // 26),
            )

        text_value = str(glyph or "P")[:1] or "P"
        brightness = (frame[0] * 0.299) + (frame[1] * 0.587) + (frame[2] * 0.114)
        text_rgb = (22, 26, 32) if brightness >= 150 else (245, 245, 245)
        text_surface = self._marker_font.render(text_value, True, text_rgb)
        text_rect = text_surface.get_rect(center=(self.cell_px // 2, self.cell_px // 2))
        overlay.blit(text_surface, text_rect)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_objective_marker_overlay(self, x, y, glyph, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(2, self.cell_px // 7)
        stroke_w = max(1, self.cell_px // 18)
        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        fill = (frame[0], frame[1], frame[2], 112)
        stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            224,
        )
        glow = (
            min(255, int(frame[0] * 1.2) + 14),
            min(255, int(frame[1] * 1.2) + 14),
            min(255, int(frame[2] * 1.1) + 8),
            82,
        )

        outer = [
            (mid_x, inset),
            (self.cell_px - inset - 1, mid_y),
            (mid_x, self.cell_px - inset - 1),
            (inset, mid_y),
        ]
        inner_inset = inset + max(2, self.cell_px // 9)
        inner = [
            (mid_x, inner_inset),
            (self.cell_px - inner_inset - 1, mid_y),
            (mid_x, self.cell_px - inner_inset - 1),
            (inner_inset, mid_y),
        ]
        self.pygame.draw.polygon(overlay, glow, outer)
        self.pygame.draw.polygon(overlay, fill, inner)
        self.pygame.draw.polygon(overlay, stroke, outer, stroke_w)

        tick_len = max(2, self.cell_px // 7)
        self.pygame.draw.line(overlay, stroke, (mid_x, inset - 1), (mid_x, inset + tick_len), stroke_w)
        self.pygame.draw.line(
            overlay,
            stroke,
            (mid_x, self.cell_px - inset - tick_len),
            (mid_x, self.cell_px - inset + 1),
            stroke_w,
        )
        self.pygame.draw.line(overlay, stroke, (inset - 1, mid_y), (inset + tick_len, mid_y), stroke_w)
        self.pygame.draw.line(
            overlay,
            stroke,
            (self.cell_px - inset - tick_len, mid_y),
            (self.cell_px - inset + 1, mid_y),
            stroke_w,
        )

        self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), max(2, self.cell_px // 9))
        text_value = str(glyph or "!")[:1] or "!"
        brightness = (frame[0] * 0.299) + (frame[1] * 0.587) + (frame[2] * 0.114)
        text_rgb = (24, 28, 32) if brightness >= 155 else (245, 245, 245)
        text_surface = self._marker_font.render(text_value, True, text_rgb)
        text_rect = text_surface.get_rect(center=(mid_x, mid_y))
        overlay.blit(text_surface, text_rect)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_projectile_overlay(self, x, y, glyph, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.1)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke = (
            min(255, int(frame[0] * 1.15)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            230,
        )
        tail = (frame[0], frame[1], frame[2], 126)
        glow = (
            min(255, int(frame[0] * 1.18) + 10),
            min(255, int(frame[1] * 1.1) + 6),
            min(255, int(frame[2] * 1.1) + 6),
            88,
        )
        stroke_w = max(1, self.cell_px // 15)
        trail = max(3, self.cell_px // 3)
        point_r = max(1, self.cell_px // 8)

        glyph_key = str(glyph or ".")[:1] or "."
        if glyph_key == "|":
            start = (mid_x, mid_y - trail)
            end = (mid_x, mid_y + trail)
        elif glyph_key == "/":
            start = (mid_x - trail, mid_y + trail)
            end = (mid_x + trail, mid_y - trail)
        elif glyph_key == "\\":
            start = (mid_x - trail, mid_y - trail)
            end = (mid_x + trail, mid_y + trail)
        else:
            start = (mid_x - trail, mid_y)
            end = (mid_x + trail, mid_y)

        self.pygame.draw.line(overlay, glow, start, end, max(2, stroke_w + 1))
        self.pygame.draw.line(overlay, tail, start, end, stroke_w)
        self.pygame.draw.circle(overlay, stroke, end, point_r + 1)
        self.pygame.draw.circle(overlay, glow, end, max(1, point_r // 2))

        if glyph_key in {"*", "o"}:
            burst = max(2, self.cell_px // 6)
            self.pygame.draw.line(overlay, stroke, (mid_x - burst, mid_y), (mid_x + burst, mid_y), stroke_w)
            self.pygame.draw.line(overlay, stroke, (mid_x, mid_y - burst), (mid_x, mid_y + burst), stroke_w)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_district_floor_overlay(self, x, y, color=None, attrs=0, *, kind="downtown"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.04)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 10)
        panel = self.pygame.Rect(inset, inset, max(4, self.cell_px - (inset * 2)), max(4, self.cell_px - (inset * 2)))
        base_fill = (frame[0], frame[1], frame[2], 56)
        edge = (
            min(255, int(frame[0] * 1.08)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            110,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 82)
        self.pygame.draw.rect(overlay, base_fill, panel, border_radius=max(1, self.cell_px // 9))
        self.pygame.draw.rect(overlay, edge, panel, max(1, self.cell_px // 24), border_radius=max(1, self.cell_px // 9))

        if kind == "downtown":
            pip_r = max(1, self.cell_px // 7)
            slash_w = max(1, self.cell_px // 18)
            p1 = (panel.left + max(2, self.cell_px // 4), panel.top + max(2, self.cell_px // 4))
            p2 = (panel.right - max(2, self.cell_px // 4), panel.bottom - max(2, self.cell_px // 4))
            glow = (
                min(255, int(frame[0] * 1.1) + 10),
                min(255, int(frame[1] * 1.1) + 10),
                min(255, int(frame[2] * 1.1) + 10),
                138,
            )
            self.pygame.draw.circle(overlay, glow, p1, pip_r + 1)
            self.pygame.draw.circle(overlay, glow, p2, pip_r + 1)
            self.pygame.draw.circle(overlay, shadow, p1, pip_r)
            self.pygame.draw.circle(overlay, shadow, p2, pip_r)
            self.pygame.draw.line(
                overlay,
                glow,
                (panel.left + max(2, self.cell_px // 3), panel.bottom - max(2, self.cell_px // 3)),
                (panel.right - max(2, self.cell_px // 3), panel.top + max(2, self.cell_px // 3)),
                slash_w,
            )
        else:
            sparkle = (
                min(255, int(frame[0] * 1.12) + 10),
                min(255, int(frame[1] * 1.06) + 8),
                min(255, int(frame[2] * 0.98) + 4),
                148,
            )
            dot = (frame[0], frame[1], frame[2], 176)
            mid_x = self.cell_px // 2
            mid_y = self.cell_px // 2
            burst = max(2, self.cell_px // 7)
            stroke_w = max(1, self.cell_px // 18)
            self.pygame.draw.line(overlay, sparkle, (mid_x - burst, mid_y), (mid_x + burst, mid_y), stroke_w)
            self.pygame.draw.line(overlay, sparkle, (mid_x, mid_y - burst), (mid_x, mid_y + burst), stroke_w)
            self.pygame.draw.line(
                overlay,
                sparkle,
                (mid_x - max(1, burst - 1), mid_y - max(1, burst - 1)),
                (mid_x + max(1, burst - 1), mid_y + max(1, burst - 1)),
                max(1, stroke_w - 1),
            )
            self.pygame.draw.line(
                overlay,
                sparkle,
                (mid_x - max(1, burst - 1), mid_y + max(1, burst - 1)),
                (mid_x + max(1, burst - 1), mid_y - max(1, burst - 1)),
                max(1, stroke_w - 1),
            )
            dot_r = max(1, self.cell_px // 10)
            confetti = (
                (panel.left + max(1, self.cell_px // 5), panel.top + max(1, self.cell_px // 4)),
                (panel.right - max(1, self.cell_px // 5), panel.top + max(2, self.cell_px // 3)),
                (panel.left + max(2, self.cell_px // 3), panel.bottom - max(1, self.cell_px // 5)),
                (panel.right - max(2, self.cell_px // 3), panel.bottom - max(2, self.cell_px // 3)),
            )
            for point in confetti:
                self.pygame.draw.circle(overlay, dot, point, dot_r)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _overworld_pattern_variant(self, x, y, mod=4):
        try:
            mod = max(1, int(mod))
        except (TypeError, ValueError):
            mod = 4
        ix = int(x)
        iy = int(y)
        return ((ix * 17) + (iy * 31) + ((ix + iy) * 7)) % mod

    def _draw_overworld_fill_overlay(self, x, y, color=None, attrs=0, *, kind="plains"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.04)
        kind_key = str(kind or "plains").strip().lower() or "plains"
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 18)
        rect = self.pygame.Rect(inset, inset, max(1, self.cell_px - (inset * 2)), max(1, self.cell_px - (inset * 2)))
        variant = self._overworld_pattern_variant(x, y, mod=5)
        base = (frame[0], frame[1], frame[2], 72)
        accent = (
            min(255, int(frame[0] * 1.08)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            136,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 86)
        self.pygame.draw.rect(overlay, base, rect)

        if kind_key.startswith("city_") or kind_key in {"urban", "city"}:
            district = kind_key[5:] if kind_key.startswith("city_") else kind_key
            block_w = max(3, self.cell_px // 4)
            block_h = max(3, self.cell_px // 4)
            gap = max(1, self.cell_px // 14)
            for row in range(2):
                for col in range(2):
                    bx = inset + gap + (col * (block_w + gap))
                    by = inset + gap + (row * (block_h + gap))
                    w = min(block_w, max(2, rect.right - bx - gap))
                    h = min(block_h, max(2, rect.bottom - by - gap))
                    if w <= 1 or h <= 1:
                        continue
                    block = self.pygame.Rect(bx, by, w, h)
                    self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 108), block, border_radius=max(1, self.cell_px // 12))
                    self.pygame.draw.rect(overlay, accent, block, max(1, self.cell_px // 26), border_radius=max(1, self.cell_px // 12))
            if district in {"downtown", "corporate"}:
                mid_x = self.cell_px // 2
                self.pygame.draw.line(overlay, accent, (mid_x, inset + 1), (mid_x, self.cell_px - inset - 2), max(1, self.cell_px // 26))
            elif district == "entertainment":
                dot_r = max(1, self.cell_px // 18)
                neon = (
                    (72, 215, 220, 150),
                    (230, 120, 220, 146),
                    (245, 196, 92, 140),
                )
                step = max(4, self.cell_px // 4)
                idx = 0
                for px in range(inset + gap, self.cell_px - inset - gap, step):
                    self.pygame.draw.circle(overlay, neon[idx % len(neon)], (px, inset + gap + dot_r), dot_r)
                    idx += 1
            elif district == "industrial":
                smoke_w = max(2, self.cell_px // 10)
                stack_x = rect.left + max(2, self.cell_px // 5)
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (stack_x, rect.top + max(2, self.cell_px // 4)),
                    (stack_x, rect.bottom - max(2, self.cell_px // 5)),
                    smoke_w,
                )
            elif district in {"slums", "residential"}:
                roof_y = rect.top + max(2, self.cell_px // 3)
                self.pygame.draw.line(overlay, accent, (rect.left + gap, roof_y), (rect.right - gap, roof_y), max(1, self.cell_px // 24))
            elif district == "military":
                band_y = rect.top + max(2, self.cell_px // 4)
                self.pygame.draw.line(
                    overlay,
                    accent,
                    (rect.left + gap, band_y),
                    (rect.right - gap, band_y + max(1, self.cell_px // 7)),
                    max(1, self.cell_px // 18),
                )
        elif kind_key in {"lake", "shore", "shoals", "coastal"}:
            water = (frame[0], frame[1], frame[2], 110)
            self.pygame.draw.rect(overlay, water, rect, border_radius=max(1, self.cell_px // 9))
            crest = (
                min(255, int(frame[0] * 1.16)),
                min(255, int(frame[1] * 1.16)),
                min(255, int(frame[2] * 1.16)),
                150,
            )
            for base_y in (
                rect.top + max(2, self.cell_px // 4),
                rect.centery,
                rect.bottom - max(3, self.cell_px // 4),
            ):
                points = []
                step = max(2, self.cell_px // 5)
                for idx, px in enumerate(range(rect.left, rect.right + 1, step)):
                    offset = -max(1, self.cell_px // 18) if ((idx + variant) % 2 == 0) else max(1, self.cell_px // 18)
                    points.append((px, max(rect.top, min(rect.bottom - 1, base_y + offset))))
                if len(points) >= 2:
                    self.pygame.draw.lines(overlay, crest, False, points, max(1, self.cell_px // 24))
            if kind_key in {"shore", "shoals"}:
                sand = (240, 214, 150, 88)
                lip_h = max(2, self.cell_px // 6)
                self.pygame.draw.rect(overlay, sand, (rect.left, rect.bottom - lip_h, rect.w, lip_h))
        elif kind_key in {"forest", "wilderness", "park"}:
            canopy = (
                min(255, int(frame[0] * 1.08)),
                min(255, int(frame[1] * 1.08)),
                min(255, int(frame[2] * 1.08)),
                130,
            )
            trunk = (max(50, frame[0] // 2), max(40, frame[1] // 3), max(30, frame[2] // 4), 118)
            trees = (
                (rect.left + max(2, self.cell_px // 4), rect.centery),
                (rect.centerx, rect.top + max(3, self.cell_px // 4)),
                (rect.right - max(3, self.cell_px // 4), rect.bottom - max(3, self.cell_px // 4)),
            )
            for tx, ty in trees:
                self.pygame.draw.circle(overlay, canopy, (tx, ty), max(2, self.cell_px // 6))
                self.pygame.draw.line(overlay, trunk, (tx, ty), (tx, min(rect.bottom - 1, ty + max(2, self.cell_px // 5))), max(1, self.cell_px // 26))
        elif kind_key in {"plains", "scrub", "frontier"}:
            blade_w = max(1, self.cell_px // 26)
            for px in (
                rect.left + max(2, self.cell_px // 5),
                rect.centerx,
                rect.right - max(3, self.cell_px // 5),
            ):
                base_y = rect.bottom - max(2, self.cell_px // 5)
                height = max(2, self.cell_px // (4 if kind_key == "scrub" else 5))
                self.pygame.draw.line(overlay, accent, (px, base_y), (px, base_y - height), blade_w)
                self.pygame.draw.line(overlay, accent, (px, base_y - max(1, height // 2)), (px - max(1, self.cell_px // 12), base_y - height), blade_w)
        elif kind_key == "marsh":
            puddle = (frame[0], frame[1], frame[2], 96)
            self.pygame.draw.ellipse(
                overlay,
                puddle,
                (rect.left + max(2, self.cell_px // 5), rect.centery - max(2, self.cell_px // 8), max(4, self.cell_px // 3), max(3, self.cell_px // 5)),
            )
            for px in (rect.left + max(2, self.cell_px // 5), rect.right - max(3, self.cell_px // 5)):
                self.pygame.draw.line(overlay, accent, (px, rect.bottom - max(2, self.cell_px // 6)), (px, rect.top + max(2, self.cell_px // 4)), max(1, self.cell_px // 26))
        elif kind_key in {"dunes", "salt_flats"}:
            bands = (
                rect.top + max(2, self.cell_px // 4),
                rect.centery,
                rect.bottom - max(3, self.cell_px // 4),
            )
            for base_y in bands:
                arc = self.pygame.Rect(rect.left + max(1, self.cell_px // 12), base_y - max(2, self.cell_px // 8), max(4, rect.w - max(2, self.cell_px // 6)), max(4, self.cell_px // 3))
                self.pygame.draw.arc(overlay, accent, arc, 0.2, 2.9, max(1, self.cell_px // 26))
        elif kind_key in {"hills", "badlands", "cliffs"}:
            stroke_w = max(1, self.cell_px // 24)
            ridges = (
                (rect.left + max(1, self.cell_px // 12), rect.bottom - max(3, self.cell_px // 5)),
                (rect.centerx, rect.top + max(2, self.cell_px // 5)),
                (rect.right - max(2, self.cell_px // 6), rect.bottom - max(4, self.cell_px // 7)),
            )
            self.pygame.draw.lines(overlay, accent, False, ridges, stroke_w)
            if kind_key == "cliffs":
                edge_x = rect.right - max(2, self.cell_px // 5)
                self.pygame.draw.line(overlay, shadow, (edge_x, rect.top + 1), (edge_x, rect.bottom - 1), max(1, self.cell_px // 20))
        elif kind_key in {"ruins", "industrial_waste"}:
            rubble = self.pygame.Rect(rect.left + max(2, self.cell_px // 5), rect.top + max(2, self.cell_px // 5), max(4, self.cell_px // 3), max(3, self.cell_px // 4))
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 96), rubble)
            self.pygame.draw.rect(overlay, shadow, rubble, max(1, self.cell_px // 26))
            self.pygame.draw.line(overlay, accent, (rubble.left, rubble.bottom - 1), (rubble.right - 1, rubble.top), max(1, self.cell_px // 24))
        else:
            dot_r = max(1, self.cell_px // 24)
            for px, py in (
                (rect.left + max(2, self.cell_px // 5), rect.top + max(2, self.cell_px // 5)),
                (rect.centerx, rect.centery),
                (rect.right - max(3, self.cell_px // 5), rect.bottom - max(3, self.cell_px // 5)),
            ):
                self.pygame.draw.circle(overlay, accent, (px, py), dot_r)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_overworld_path_overlay(self, x, y, color=None, attrs=0, *, kind="road"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.06)
        kind_key = str(kind or "road").strip().lower() or "road"
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        mid_y = self.cell_px // 2
        if kind_key == "freeway":
            band_h = max(5, self.cell_px // 3)
            top_y = max(1, mid_y - (band_h // 2))
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 176), (0, top_y, self.cell_px, band_h))
            divider_y = top_y + (band_h // 2)
            self.pygame.draw.line(overlay, (255, 244, 182, 180), (0, divider_y), (self.cell_px, divider_y), max(1, self.cell_px // 24))
            shoulder = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 128)
            self.pygame.draw.line(overlay, shoulder, (0, top_y), (self.cell_px, top_y), max(1, self.cell_px // 20))
            self.pygame.draw.line(overlay, shoulder, (0, top_y + band_h - 1), (self.cell_px, top_y + band_h - 1), max(1, self.cell_px // 20))
        elif kind_key == "trail":
            band_h = max(2, self.cell_px // 6)
            top_y = mid_y - (band_h // 2)
            dash_w = max(2, self.cell_px // 5)
            gap = max(1, self.cell_px // 10)
            for px in range(0, self.cell_px, dash_w + gap):
                self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 158), (px, top_y, dash_w, band_h))
        else:
            band_h = max(3, self.cell_px // 5)
            top_y = mid_y - (band_h // 2)
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 170), (0, top_y, self.cell_px, band_h))
            stripe_y = mid_y
            stripe_w = max(1, self.cell_px // 24)
            seg_w = max(2, self.cell_px // 6)
            step = max(seg_w + 1, self.cell_px // 4)
            for px in range(max(1, self.cell_px // 8), self.cell_px, step):
                self.pygame.draw.line(overlay, (245, 226, 150, 182), (px, stripe_y), (min(self.cell_px - 1, px + seg_w), stripe_y), stripe_w)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_overworld_boundary_overlay(self, x, y, color=None, attrs=0, *, kind="vertical"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.02)
        kind_key = str(kind or "vertical").strip().lower() or "vertical"
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        stroke = (
            min(255, int(frame[0] * 1.02)),
            min(255, int(frame[1] * 1.02)),
            min(255, int(frame[2] * 1.02)),
            86,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 48)
        stroke_w = max(1, self.cell_px // 30)
        if kind_key == "horizontal":
            y0 = self.cell_px - max(1, self.cell_px // 20) - 1
            self.pygame.draw.line(overlay, stroke, (0, y0), (self.cell_px, y0), stroke_w)
            self.pygame.draw.line(overlay, shadow, (0, max(0, y0 - 1)), (self.cell_px, max(0, y0 - 1)), stroke_w)
        else:
            x0 = self.cell_px - max(1, self.cell_px // 20) - 1
            self.pygame.draw.line(overlay, stroke, (x0, 0), (x0, self.cell_px), stroke_w)
            self.pygame.draw.line(overlay, shadow, (max(0, x0 - 1), 0), (max(0, x0 - 1), self.cell_px), stroke_w)
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_overworld_focus_overlay(self, x, y, color=None, attrs=0, *, kind="horizontal"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.12)
        kind_key = str(kind or "horizontal").strip().lower() or "horizontal"
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        stroke = (
            min(255, int(frame[0] * 1.16)),
            min(255, int(frame[1] * 1.16)),
            min(255, int(frame[2] * 1.12)),
            208,
        )
        glow = (
            min(255, int(frame[0] * 1.2) + 10),
            min(255, int(frame[1] * 1.2) + 10),
            min(255, int(frame[2] * 1.16) + 8),
            82,
        )
        stroke_w = max(1, self.cell_px // 16)
        inset = max(1, self.cell_px // 18)

        if kind_key == "horizontal":
            y0 = inset + max(1, self.cell_px // 18)
            self.pygame.draw.line(overlay, glow, (0, y0), (self.cell_px, y0), max(1, stroke_w + 1))
            self.pygame.draw.line(overlay, stroke, (0, y0), (self.cell_px, y0), stroke_w)
        elif kind_key == "vertical":
            x0 = inset + max(1, self.cell_px // 18)
            self.pygame.draw.line(overlay, glow, (x0, 0), (x0, self.cell_px), max(1, stroke_w + 1))
            self.pygame.draw.line(overlay, stroke, (x0, 0), (x0, self.cell_px), stroke_w)
        else:
            corner = kind_key.rsplit("_", 1)[-1]
            arm = max(3, self.cell_px // 3)
            x0 = inset
            y0 = inset
            if corner == "ne":
                x0 = self.cell_px - inset - 1
                self.pygame.draw.line(overlay, glow, (x0 - arm, y0), (x0, y0), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, glow, (x0, y0), (x0, y0 + arm), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, stroke, (x0 - arm, y0), (x0, y0), stroke_w)
                self.pygame.draw.line(overlay, stroke, (x0, y0), (x0, y0 + arm), stroke_w)
            elif corner == "sw":
                y0 = self.cell_px - inset - 1
                self.pygame.draw.line(overlay, glow, (x0, y0), (x0 + arm, y0), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, glow, (x0, y0 - arm), (x0, y0), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, stroke, (x0, y0), (x0 + arm, y0), stroke_w)
                self.pygame.draw.line(overlay, stroke, (x0, y0 - arm), (x0, y0), stroke_w)
            elif corner == "se":
                x0 = self.cell_px - inset - 1
                y0 = self.cell_px - inset - 1
                self.pygame.draw.line(overlay, glow, (x0 - arm, y0), (x0, y0), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, glow, (x0, y0 - arm), (x0, y0), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, stroke, (x0 - arm, y0), (x0, y0), stroke_w)
                self.pygame.draw.line(overlay, stroke, (x0, y0 - arm), (x0, y0), stroke_w)
            else:
                self.pygame.draw.line(overlay, glow, (x0, y0), (x0 + arm, y0), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, glow, (x0, y0), (x0, y0 + arm), max(1, stroke_w + 1))
                self.pygame.draw.line(overlay, stroke, (x0, y0), (x0 + arm, y0), stroke_w)
                self.pygame.draw.line(overlay, stroke, (x0, y0), (x0, y0 + arm), stroke_w)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_overworld_icon_overlay(self, x, y, color=None, attrs=0, *, kind="terrain_plains"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        kind_key = str(kind or "terrain_plains").strip().lower() or "terrain_plains"
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(2, self.cell_px // 7)
        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 156)
        stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            224,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 116)
        plate_fill = (12, 16, 22, 86)
        plate_stroke = (255, 255, 255, 22)
        plate_rect = self.pygame.Rect(
            inset,
            inset,
            max(5, self.cell_px - (inset * 2)),
            max(5, self.cell_px - (inset * 2)),
        )
        self.pygame.draw.rect(overlay, plate_fill, plate_rect, border_radius=max(2, self.cell_px // 6))
        self.pygame.draw.rect(overlay, plate_stroke, plate_rect, max(1, self.cell_px // 28), border_radius=max(2, self.cell_px // 6))

        if kind_key == "landmark":
            points = [
                (mid_x, inset),
                (self.cell_px - inset - 1, mid_y),
                (mid_x, self.cell_px - inset - 1),
                (inset, mid_y),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), max(1, self.cell_px // 10))
        elif kind_key == "interest":
            radius = max(3, self.cell_px // 4)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), max(1, radius // 2), max(1, stroke_w - 1))
            self.pygame.draw.line(overlay, stroke, (mid_x, inset), (mid_x, inset + max(2, self.cell_px // 6)), stroke_w)
            self.pygame.draw.line(overlay, stroke, (inset, mid_y), (inset + max(2, self.cell_px // 6), mid_y), stroke_w)
        elif kind_key in {"district_residential", "district_slums"}:
            body = self.pygame.Rect(mid_x - max(3, self.cell_px // 5), mid_y - max(1, self.cell_px // 10), max(6, self.cell_px // 3), max(5, self.cell_px // 3))
            roof = [(body.left - 1, body.top + 1), (mid_x, inset + 1), (body.right + 1, body.top + 1)]
            self.pygame.draw.polygon(overlay, fill, roof)
            self.pygame.draw.polygon(overlay, stroke, roof, stroke_w)
            self.pygame.draw.rect(overlay, fill, body)
            self.pygame.draw.rect(overlay, stroke, body, stroke_w)
            if kind_key == "district_slums":
                self.pygame.draw.line(overlay, shadow, (body.left, body.top + 1), (body.right - 1, body.top - max(1, self.cell_px // 12) + 2), max(1, stroke_w - 1))
        elif kind_key in {"district_downtown", "district_corporate", "area_city", "terrain_urban"}:
            towers = (
                self.pygame.Rect(mid_x - max(5, self.cell_px // 3), mid_y, max(3, self.cell_px // 6), max(4, self.cell_px // 4)),
                self.pygame.Rect(mid_x - max(2, self.cell_px // 10), mid_y - max(2, self.cell_px // 6), max(3, self.cell_px // 5), max(5, self.cell_px // 3)),
                self.pygame.Rect(mid_x + max(2, self.cell_px // 8), mid_y - max(1, self.cell_px // 12), max(3, self.cell_px // 6), max(4, self.cell_px // 4)),
            )
            for tower in towers:
                self.pygame.draw.rect(overlay, fill, tower)
                self.pygame.draw.rect(overlay, stroke, tower, max(1, stroke_w - 1))
        elif kind_key in {"district_industrial", "terrain_industrial_waste"}:
            base = self.pygame.Rect(inset, mid_y, max(6, self.cell_px - (inset * 2)), max(4, self.cell_px // 4))
            self.pygame.draw.rect(overlay, fill, base)
            self.pygame.draw.rect(overlay, stroke, base, stroke_w)
            for px in (base.left + max(2, self.cell_px // 5), base.centerx + max(1, self.cell_px // 10)):
                self.pygame.draw.line(overlay, stroke, (px, base.top), (px, inset + max(1, self.cell_px // 8)), max(1, self.cell_px // 10))
                self.pygame.draw.circle(overlay, shadow, (px, inset + max(1, self.cell_px // 7)), max(1, self.cell_px // 10))
        elif kind_key == "district_entertainment":
            burst = max(3, self.cell_px // 4)
            self.pygame.draw.line(overlay, stroke, (mid_x - burst, mid_y), (mid_x + burst, mid_y), stroke_w)
            self.pygame.draw.line(overlay, stroke, (mid_x, mid_y - burst), (mid_x, mid_y + burst), stroke_w)
            self.pygame.draw.line(overlay, stroke, (mid_x - burst + 1, mid_y - burst + 1), (mid_x + burst - 1, mid_y + burst - 1), max(1, stroke_w - 1))
            self.pygame.draw.line(overlay, stroke, (mid_x - burst + 1, mid_y + burst - 1), (mid_x + burst - 1, mid_y - burst + 1), max(1, stroke_w - 1))
        elif kind_key == "district_military":
            shield = [
                (mid_x, inset),
                (self.cell_px - inset - 1, inset + max(2, self.cell_px // 5)),
                (self.cell_px - inset - 2, mid_y),
                (mid_x, self.cell_px - inset - 1),
                (inset + 1, mid_y),
                (inset, inset + max(2, self.cell_px // 5)),
            ]
            self.pygame.draw.polygon(overlay, fill, shield)
            self.pygame.draw.polygon(overlay, stroke, shield, stroke_w)
        elif kind_key in {"area_frontier", "terrain_plains", "terrain_scrub"}:
            post_x = mid_x
            self.pygame.draw.line(overlay, stroke, (post_x, inset + 1), (post_x, self.cell_px - inset - 1), stroke_w)
            self.pygame.draw.polygon(
                overlay,
                fill,
                [
                    (post_x, inset + max(1, self.cell_px // 8)),
                    (post_x + max(3, self.cell_px // 4), inset + max(2, self.cell_px // 4)),
                    (post_x, inset + max(3, self.cell_px // 8)),
                ],
            )
        elif kind_key in {"area_wilderness", "terrain_forest", "terrain_park"}:
            canopy = [
                (mid_x, inset),
                (self.cell_px - inset - 1, mid_y),
                (mid_x + max(1, self.cell_px // 8), mid_y),
                (self.cell_px - inset - max(2, self.cell_px // 5), self.cell_px - inset - max(2, self.cell_px // 4)),
                (inset + max(2, self.cell_px // 5), self.cell_px - inset - max(2, self.cell_px // 4)),
                (mid_x - max(1, self.cell_px // 8), mid_y),
                (inset, mid_y),
            ]
            self.pygame.draw.polygon(overlay, fill, canopy)
            self.pygame.draw.polygon(overlay, stroke, canopy, stroke_w)
            self.pygame.draw.line(overlay, shadow, (mid_x, mid_y), (mid_x, self.cell_px - inset - 1), max(1, self.cell_px // 12))
        elif kind_key in {"area_coastal", "terrain_lake", "terrain_shore", "terrain_shoals", "terrain_coastal"}:
            step = max(2, self.cell_px // 5)
            points = []
            base_y = mid_y
            for idx, px in enumerate(range(inset, self.cell_px - inset + 1, step)):
                offset = -max(1, self.cell_px // 16) if idx % 2 == 0 else max(1, self.cell_px // 16)
                points.append((px, base_y + offset))
            if len(points) >= 2:
                self.pygame.draw.lines(overlay, stroke, False, points, stroke_w)
            if kind_key == "terrain_lake":
                self.pygame.draw.ellipse(
                    overlay,
                    fill,
                    (mid_x - max(3, self.cell_px // 5), mid_y - max(2, self.cell_px // 6), max(6, self.cell_px // 2), max(4, self.cell_px // 3)),
                )
        elif kind_key in {"terrain_hills", "terrain_badlands", "terrain_cliffs"}:
            ridge = [
                (inset, self.cell_px - inset - max(2, self.cell_px // 5)),
                (mid_x - max(1, self.cell_px // 8), inset + max(2, self.cell_px // 5)),
                (mid_x + max(1, self.cell_px // 8), mid_y),
                (self.cell_px - inset - 1, self.cell_px - inset - max(3, self.cell_px // 7)),
            ]
            self.pygame.draw.lines(overlay, stroke, False, ridge, stroke_w)
            if kind_key == "terrain_cliffs":
                edge_x = self.cell_px - inset - max(2, self.cell_px // 5)
                self.pygame.draw.line(overlay, shadow, (edge_x, inset), (edge_x, self.cell_px - inset - 1), max(1, self.cell_px // 12))
        elif kind_key in {"terrain_marsh"}:
            self.pygame.draw.ellipse(
                overlay,
                fill,
                (mid_x - max(3, self.cell_px // 5), mid_y - max(2, self.cell_px // 8), max(6, self.cell_px // 2), max(4, self.cell_px // 4)),
            )
            reeds_x = (mid_x - max(3, self.cell_px // 6), mid_x + max(2, self.cell_px // 6))
            for px in reeds_x:
                self.pygame.draw.line(overlay, stroke, (px, mid_y), (px, inset + max(2, self.cell_px // 4)), max(1, self.cell_px // 18))
        elif kind_key in {"terrain_dunes", "terrain_salt_flats"}:
            arc = self.pygame.Rect(inset, mid_y - max(2, self.cell_px // 5), max(6, self.cell_px - (inset * 2)), max(4, self.cell_px // 2))
            self.pygame.draw.arc(overlay, stroke, arc, 0.15, 2.85, stroke_w)
            self.pygame.draw.arc(overlay, shadow, arc.move(0, max(1, self.cell_px // 6)), 0.15, 2.85, max(1, stroke_w - 1))
        elif kind_key in {"terrain_ruins"}:
            ruin = self.pygame.Rect(mid_x - max(3, self.cell_px // 5), mid_y - max(2, self.cell_px // 6), max(6, self.cell_px // 2), max(5, self.cell_px // 3))
            self.pygame.draw.rect(overlay, fill, ruin)
            self.pygame.draw.rect(overlay, stroke, ruin, stroke_w)
            self.pygame.draw.line(overlay, shadow, (ruin.left, ruin.bottom - 1), (ruin.right - 1, ruin.top), max(1, stroke_w - 1))
        else:
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), max(2, self.cell_px // 5))
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), max(2, self.cell_px // 5), stroke_w)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_overworld_badge_overlay(self, x, y, glyph, color=None, attrs=0, *, kind="marker"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.1)
        kind_key = str(kind or "marker").strip().lower() or "marker"
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(2, self.cell_px // 7)
        stroke_w = max(1, self.cell_px // 18)
        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        fill = (frame[0], frame[1], frame[2], 164)
        stroke = (
            min(255, int(frame[0] * 1.14)),
            min(255, int(frame[1] * 1.14)),
            min(255, int(frame[2] * 1.14)),
            232,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 112)

        if kind_key == "player":
            radius = max(4, (self.cell_px // 2) - inset)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), radius)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, shadow, (mid_x, mid_y), max(1, radius // 3))
            self.pygame.draw.line(overlay, stroke, (mid_x, inset), (mid_x, inset + max(2, self.cell_px // 5)), stroke_w)
        elif kind_key == "cursor":
            rect = self.pygame.Rect(inset, inset, max(5, self.cell_px - (inset * 2)), max(5, self.cell_px - (inset * 2)))
            self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 78), rect)
            self.pygame.draw.rect(overlay, stroke, rect, stroke_w)
            arm = max(2, self.cell_px // 5)
            self.pygame.draw.line(overlay, stroke, (mid_x - arm, mid_y), (mid_x + arm, mid_y), stroke_w)
            self.pygame.draw.line(overlay, stroke, (mid_x, mid_y - arm), (mid_x, mid_y + arm), stroke_w)
        else:
            points = [
                (mid_x, inset),
                (self.cell_px - inset - 1, mid_y),
                (mid_x, self.cell_px - inset - 1),
                (inset, mid_y),
            ]
            if kind_key == "marker_nearest":
                glow = (
                    min(255, int(frame[0] * 1.18) + 10),
                    min(255, int(frame[1] * 1.18) + 10),
                    min(255, int(frame[2] * 1.1) + 6),
                    92,
                )
                self.pygame.draw.polygon(overlay, glow, points)
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            text_value = str(glyph or "!")[:1] or "!"
            brightness = (frame[0] * 0.299) + (frame[1] * 0.587) + (frame[2] * 0.114)
            text_rgb = (24, 28, 32) if brightness >= 155 else (245, 245, 245)
            text_surface = self._marker_font.render(text_value, True, text_rgb)
            text_rect = text_surface.get_rect(center=(mid_x, mid_y))
            overlay.blit(text_surface, text_rect)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_stairs_overlay(self, x, y, color=None, attrs=0, *, direction="up", landing=False):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(2, self.cell_px // 8)
        stroke_w = max(1, self.cell_px // 14)
        left_x = inset
        right_x = self.cell_px - inset - 1
        top_y = inset
        bottom_y = self.cell_px - inset - 1
        for idx in range(3):
            frac = (idx + 1) / 4.0
            y_pos = int(top_y + ((bottom_y - top_y) * frac))
            width = max(2, int((right_x - left_x) * (0.38 + (idx * 0.18))))
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 176),
                (left_x, y_pos),
                (left_x + width, y_pos),
                stroke_w,
            )
        if landing:
            mid_y = self.cell_px // 2
            self.pygame.draw.line(
                overlay,
                (frame[0], frame[1], frame[2], 152),
                (left_x, mid_y),
                (right_x, mid_y),
                stroke_w,
            )
        else:
            arrow_w = max(2, self.cell_px // 7)
            if direction == "up":
                points = [
                    (right_x - 1, top_y + 1),
                    (right_x - arrow_w, top_y + arrow_w + 1),
                    (right_x - max(7, self.cell_px // 3), top_y + arrow_w + 1),
                ]
            else:
                points = [
                    (right_x - 1, bottom_y - 1),
                    (right_x - arrow_w, bottom_y - arrow_w - 1),
                    (right_x - max(7, self.cell_px // 3), bottom_y - arrow_w - 1),
                ]
            self.pygame.draw.polygon(overlay, (frame[0], frame[1], frame[2], 210), points)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_elevator_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(2, self.cell_px // 8)
        stroke_w = max(1, self.cell_px // 14)
        rect = self.pygame.Rect(inset, inset, max(1, self.cell_px - (inset * 2)), max(1, self.cell_px - (inset * 2)))
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 112), rect)
        self.pygame.draw.rect(overlay, (frame[0], frame[1], frame[2], 196), rect, stroke_w)
        mid_x = self.cell_px // 2
        self.pygame.draw.line(
            overlay,
            (frame[0], frame[1], frame[2], 168),
            (mid_x, inset + 1),
            (mid_x, self.cell_px - inset - 2),
            stroke_w,
        )
        arrow_w = max(2, self.cell_px // 7)
        up = [(mid_x, inset + 2), (mid_x - arrow_w, inset + arrow_w + 2), (mid_x + arrow_w, inset + arrow_w + 2)]
        down = [
            (mid_x, self.cell_px - inset - 2),
            (mid_x - arrow_w, self.cell_px - inset - arrow_w - 2),
            (mid_x + arrow_w, self.cell_px - inset - arrow_w - 2),
        ]
        self.pygame.draw.polygon(overlay, (frame[0], frame[1], frame[2], 210), up)
        self.pygame.draw.polygon(overlay, (frame[0], frame[1], frame[2], 210), down)
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_procedural_shape(self, x, y, ch, color=None, attrs=0, semantic_id=None):
        glyph = str(ch)[:1] or " "
        color_key = str(color or "").strip().lower()
        semantic_key = str(semantic_id or "").strip().lower()

        if semantic_key.startswith("overworld_fill_city_"):
            self._draw_overworld_fill_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=f"city_{semantic_key.removeprefix('overworld_fill_city_') or 'residential'}",
            )
            return semantic_key
        if semantic_key.startswith("overworld_fill_terrain_"):
            self._draw_overworld_fill_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=semantic_key.removeprefix("overworld_fill_terrain_") or "plains",
            )
            return semantic_key
        if semantic_key.startswith("overworld_path_"):
            self._draw_overworld_path_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=semantic_key.removeprefix("overworld_path_") or "road",
            )
            return semantic_key
        if semantic_key == "overworld_boundary_vertical":
            self._draw_overworld_boundary_overlay(x, y, color=color, attrs=attrs, kind="vertical")
            return semantic_key
        if semantic_key == "overworld_boundary_horizontal":
            self._draw_overworld_boundary_overlay(x, y, color=color, attrs=attrs, kind="horizontal")
            return semantic_key
        if semantic_key == "overworld_focus_horizontal":
            self._draw_overworld_focus_overlay(x, y, color=color, attrs=attrs, kind="horizontal")
            return semantic_key
        if semantic_key == "overworld_focus_vertical":
            self._draw_overworld_focus_overlay(x, y, color=color, attrs=attrs, kind="vertical")
            return semantic_key
        if semantic_key.startswith("overworld_focus_corner_"):
            self._draw_overworld_focus_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=semantic_key.removeprefix("overworld_focus_") or "corner_nw",
            )
            return semantic_key
        if semantic_key.startswith("overworld_district_"):
            self._draw_overworld_icon_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=f"district_{semantic_key.removeprefix('overworld_district_') or 'residential'}",
            )
            return semantic_key
        if semantic_key.startswith("overworld_area_"):
            self._draw_overworld_icon_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=f"area_{semantic_key.removeprefix('overworld_area_') or 'wilds'}",
            )
            return semantic_key
        if semantic_key.startswith("overworld_terrain_"):
            self._draw_overworld_icon_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=f"terrain_{semantic_key.removeprefix('overworld_terrain_') or 'plains'}",
            )
            return semantic_key
        if semantic_key == "overworld_landmark":
            self._draw_overworld_icon_overlay(x, y, color=color, attrs=attrs, kind="landmark")
            return semantic_key
        if semantic_key == "overworld_interest":
            self._draw_overworld_icon_overlay(x, y, color=color, attrs=attrs, kind="interest")
            return semantic_key
        if semantic_key == "overworld_player":
            self._draw_overworld_badge_overlay(x, y, glyph, color=color, attrs=attrs, kind="player")
            return semantic_key
        if semantic_key == "overworld_marker":
            self._draw_overworld_badge_overlay(x, y, glyph, color=color, attrs=attrs, kind="marker")
            return semantic_key
        if semantic_key == "overworld_marker_nearest":
            self._draw_overworld_badge_overlay(x, y, glyph, color=color, attrs=attrs, kind="marker_nearest")
            return semantic_key
        if semantic_key == "overworld_cursor":
            self._draw_overworld_badge_overlay(x, y, glyph, color=color, attrs=attrs, kind="cursor")
            return semantic_key
        if semantic_key == "feature_window" or (glyph == '"' and color_key == "feature_window"):
            self._draw_window_overlay(x, y, color=color, attrs=attrs)
            return "window"
        if semantic_key == "feature_door" or (glyph in {"+", "'"} and color_key == "feature_door"):
            self._draw_door_overlay(x, y, color=color, attrs=attrs, is_open=(glyph == "'"))
            return "door_open" if glyph == "'" else "door"
        if semantic_key == "feature_breach" or (glyph == "/" and color_key == "feature_breach"):
            self._draw_breach_overlay(x, y, color=color, attrs=attrs)
            return "breach"
        if semantic_key == "terrain_block" or (glyph == "#" and color_key == "terrain_block"):
            self._draw_block_overlay(x, y, color=color, attrs=attrs)
            return "terrain_block"
        if semantic_key == "terrain_brush" or (glyph == "," and color_key == "terrain_brush"):
            self._draw_brush_overlay(x, y, color=color, attrs=attrs)
            return "terrain_brush"
        if semantic_key == "terrain_rock" or (glyph == "^" and color_key == "terrain_rock"):
            self._draw_rock_overlay(x, y, color=color, attrs=attrs)
            return "terrain_rock"
        if semantic_key == "terrain_water" or (glyph == "~" and color_key == "terrain_water"):
            self._draw_water_overlay(x, y, color=color, attrs=attrs)
            return "terrain_water"
        if semantic_key == "terrain_road" or (glyph == "=" and color_key == "terrain_road"):
            self._draw_road_overlay(x, y, color=color, attrs=attrs, trail=False)
            return "terrain_road"
        if semantic_key == "terrain_trail" or (glyph == "=" and color_key == "terrain_trail"):
            self._draw_road_overlay(x, y, color=color, attrs=attrs, trail=True)
            return "terrain_trail"
        if semantic_key == "terrain_salt" or (glyph == "_" and color_key == "terrain_salt"):
            self._draw_salt_overlay(x, y, color=color, attrs=attrs)
            return "terrain_salt"
        if glyph == "%" and color_key == "floor_downtown":
            self._draw_district_floor_overlay(x, y, color=color, attrs=attrs, kind="downtown")
            return "floor_downtown"
        if glyph == "*" and color_key == "floor_entertainment":
            self._draw_district_floor_overlay(x, y, color=color, attrs=attrs, kind="entertainment")
            return "floor_entertainment"
        if semantic_key == "objective":
            self._draw_objective_marker_overlay(x, y, glyph, color=color or "objective", attrs=attrs)
            return "objective_marker"
        if color_key == "projectile" or semantic_key.startswith("projectile"):
            self._draw_projectile_overlay(x, y, glyph, color=color or "projectile", attrs=attrs)
            return "projectile"
        infra_kind_map = {
            "infra_lamp": "lamp",
            "infra_pole": "pole",
            "infra_hydrant": "hydrant",
            "infra_stop": "stop",
            "infra_utility_a": "utility_a",
            "infra_utility_b": "utility_b",
            "infra_atm": "atm",
            "infra_claim_terminal": "claim_terminal",
            "infra_access_panel": "access_panel",
        }
        infra_kind = infra_kind_map.get(semantic_key)
        if infra_kind:
            self._draw_infrastructure_overlay(x, y, color=color, attrs=attrs, kind=infra_kind)
            return f"infra_{infra_kind}"
        actor_kind = None
        if glyph == "@":
            if semantic_key == "entity_player" or color_key == "player":
                actor_kind = "player"
            elif semantic_key == "npc_guard" or color_key == "guard":
                actor_kind = "guard"
            elif semantic_key == "npc_scout" or color_key == "scout":
                actor_kind = "scout"
            elif semantic_key in {"npc_civilian", "npc_hominid"} or color_key == "human":
                actor_kind = "civilian"
        if actor_kind:
            self._draw_actor_token_overlay(x, y, glyph, color=color, attrs=attrs, kind=actor_kind)
            return f"entity_{actor_kind}"
        if color_key == "property_service":
            service_fixture_kind = {
                "v": "vending",
                "e": "charging",
                "i": "terminal",
                "t": "terminal",
            }.get(glyph)
            if service_fixture_kind:
                self._draw_service_security_fixture_overlay(
                    x,
                    y,
                    color=color,
                    attrs=attrs,
                    kind=service_fixture_kind,
                )
                return f"service_fixture_{service_fixture_kind}"
        if color_key == "property_asset" and glyph == "q":
            self._draw_service_security_fixture_overlay(x, y, color=color, attrs=attrs, kind="security_booth")
            return "security_booth"
        cover_fixture_kind = {
            "prop_cover_bench": "bench",
            "prop_cover_shelter": "shelter",
            "prop_cover_planter": "planter",
            "prop_cover_fence": "fence",
            "prop_cover_transformer": "transformer",
            "prop_cover_cache": "cache",
            "prop_cover_tank": "tank",
        }.get(semantic_key)
        if cover_fixture_kind:
            self._draw_cover_fixture_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=cover_fixture_kind,
            )
            return f"cover_{cover_fixture_kind}"
        item_kind_map = {
            "item_ground": "ground",
            "item_medical": "medical",
            "item_token": "token",
            "item_tool": "tool",
            "item_weapon": "weapon",
            "item_armor": "armor",
            "item_food": "food",
            "item_drink": "drink",
            "item_access": "access",
            "item_restricted": "restricted",
            "item_illegal": "illegal",
            "item_objective": "objective",
        }
        item_kind = item_kind_map.get(color_key)
        if item_kind:
            self._draw_item_overlay(x, y, color=color, attrs=attrs, kind=item_kind)
            return f"item_{item_kind}"
        if semantic_key == "item_objective":
            self._draw_item_overlay(x, y, color=color or "objective", attrs=attrs, kind="objective")
            return "item_objective"
        if color_key.startswith("vehicle_") and glyph in {"&", "V", "v"}:
            self._draw_vehicle_overlay(x, y, color=color, attrs=attrs)
            return "vehicle"
        if color_key == "property_service":
            self._draw_property_marker_overlay(x, y, glyph, color=color, attrs=attrs, kind="service")
            return "property_service"
        if color_key == "property_fixture":
            self._draw_property_marker_overlay(x, y, glyph, color=color, attrs=attrs, kind="fixture")
            return "property_fixture"
        if color_key == "property_asset":
            self._draw_property_marker_overlay(x, y, glyph, color=color, attrs=attrs, kind="asset")
            return "property_asset"
        if color_key == "property_building":
            self._draw_property_marker_overlay(x, y, glyph, color=color, attrs=attrs, kind="building")
            return "property_building"
        if (
            (color_key == "building_roof" or color_key.startswith("building_roof_"))
            and glyph in {"#", "=", "b", "B"}
        ):
            self._draw_roof_overlay(x, y, color=color, attrs=attrs)
            return "building_roof"
        if color_key == "building_edge" or (glyph == "#" and color_key.startswith("building_")):
            self._draw_wall_overlay(x, y, color=color, attrs=attrs, filled=False)
            return "building_edge"
        if color_key == "building_fill" or (glyph == "=" and color_key.startswith("building_")):
            self._draw_wall_overlay(x, y, color=color, attrs=attrs, filled=True)
            return "building_fill"
        if semantic_key == "stair_up" or (glyph == ">" and color_key == "transit"):
            self._draw_stairs_overlay(x, y, color=color, attrs=attrs, direction="up")
            return "stair_up"
        if semantic_key == "stair_down" or (glyph == "<" and color_key == "transit"):
            self._draw_stairs_overlay(x, y, color=color, attrs=attrs, direction="down")
            return "stair_down"
        if semantic_key == "transit_stair_landing" or (glyph == ":" and color_key == "transit"):
            self._draw_stairs_overlay(x, y, color=color, attrs=attrs, landing=True)
            return "stair_landing"
        if semantic_key == "elevator" or (glyph == "E" and color_key == "transit"):
            self._draw_elevator_overlay(x, y, color=color, attrs=attrs)
            return "elevator"
        return ""

    def _tile_id_for(self, glyph, color, semantic_id=None):
        """Resolve a sprite tile from direct atlas glyphs or semantic runtime IDs."""
        if not self._tile_map or self._atlas is None:
            semantic_key = str(semantic_id or "").strip()
            return semantic_key or None

        glyph = str(glyph)[:1] if glyph else ""
        color_key = str(color) if color else "default"
        strict_categories = set(self._strict_categories_for_color(color_key))

        tile_id = self._direct_tile_id_for(glyph, color_key)
        if tile_id:
            return tile_id

        semantic_key = str(semantic_id or "").strip()
        if semantic_key:
            return semantic_key

        ordered_categories = [
            self._tile_map.get(name)
            for name in self._category_order_for_color(color_key)
            if isinstance(self._tile_map.get(name), dict)
            and (not strict_categories or name in strict_categories)
        ]

        # Pass 1: exact glyph+color match only.
        for category in ordered_categories:
            tile_id = self._tile_id_for_category(category, glyph, color_key, allow_defaults=False)
            if tile_id:
                return tile_id

        # Pass 2: allow category defaults as fallback.
        for category in ordered_categories:
            tile_id = self._tile_id_for_category(category, glyph, color_key, allow_defaults=True)
            if tile_id:
                return tile_id

        return None

    def _asset_color_candidates(self, color_key):
        key = str(color_key or "default").strip().lower()
        candidates = []

        def _push(value):
            value = str(value or "").strip().lower()
            if value and value not in candidates:
                candidates.append(value)

        _push(key)
        for value in self._runtime_color_asset_families.get(key, ()):
            _push(value)

        if key.startswith("cat_"):
            coat = key.split("_", 1)[1]
            _push(coat)
            if coat in {"black", "gray", "tabby", "tuxedo"}:
                _push("darkgray")
            if coat in {"white", "calico"}:
                _push("pink")

        return candidates

    def _direct_tile_id_for(self, glyph, color_key):
        if not glyph or self._atlas is None:
            return None

        for asset_color in self._asset_color_candidates(color_key):
            tile_id = self._glyph_color_tiles.get((glyph, asset_color))
            if tile_id:
                return str(tile_id)
        return None

    def _any_direct_tile_id_for_glyph(self, glyph):
        glyph_key = str(glyph or "")[:1]
        if not glyph_key:
            return None
        for (candidate_glyph, _candidate_color), tile_id in self._glyph_color_tiles.items():
            if candidate_glyph == glyph_key:
                return str(tile_id)
        return None

    def _tile_id_for_category(self, category, glyph, color_key, allow_defaults):
        if not isinstance(category, dict):
            return None

        glyph_entry = category.get(glyph)
        if isinstance(glyph_entry, dict):
            tile_id = glyph_entry.get(color_key)
            if tile_id:
                return str(tile_id)
            if allow_defaults:
                tile_id = glyph_entry.get("default")
                if tile_id:
                    return str(tile_id)

        return None

    def _blit_tile(self, tile_id, x, y, attrs=0, preserve_background=False):
        """Blit a sprite tile to cell (x, y). Returns True if drawn, False if not found."""
        tile_id = self._semantic_aliases.get(str(tile_id), str(tile_id))
        rect = self._tile_rects.get(str(tile_id))
        if rect is None or self._atlas is None:
            return False

        dest_x = x * self.cell_px
        dest_y = y * self.cell_px
        if not preserve_background:
            self.surface.fill((0, 0, 0), (dest_x, dest_y, self.cell_px, self.cell_px))
        tile_surf = self._atlas.subsurface(rect)
        if rect.w != self.cell_px or rect.h != self.cell_px:
            tile_surf = self.pygame.transform.scale(tile_surf, (self.cell_px, self.cell_px))

        if self._has_attr(attrs, "A_DIM") or self._has_attr(attrs, "A_REVERSE"):
            tile_surf = tile_surf.copy()
            if self._has_attr(attrs, "A_REVERSE"):
                tile_surf = self.pygame.transform.flip(tile_surf, True, False)
            if self._has_attr(attrs, "A_DIM"):
                tile_surf.set_alpha(128)

        self.surface.blit(tile_surf, (dest_x, dest_y))
        return True

    def _color_value(self, color):
        if color is None:
            return self.palette["default"]
        if isinstance(color, str):
            return self.palette.get(color, self.palette["default"])
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            return (int(color[0]), int(color[1]), int(color[2]))
        return self.palette["default"]

    def _has_attr(self, attrs, flag_name):
        try:
            flag = int(getattr(curses, flag_name, 0) or 0)
        except (TypeError, ValueError):
            return False
        attrs = int(attrs or 0)
        if flag <= 0:
            return False
        return bool(attrs & flag)

    def size(self):
        return self.width_cells, self.height_cells

    def clear(self):
        self.surface.fill((0, 0, 0))
        self._queued_draw_calls.clear()
        self._draw_sequence = 0

    def begin_frame(self, *, animation_tick=None):
        if animation_tick is None:
            animation_tick = int(time.monotonic() * 10.0)
        try:
            self._animation_tick = int(animation_tick)
        except (TypeError, ValueError):
            self._animation_tick = 0

    def _wants_layered_draw(self, layer=None, priority=None):
        return layer is not None or priority is not None

    def _queue_draw_call(self, kind, **payload):
        self._draw_sequence += 1
        queued = {"kind": str(kind), "sequence": int(self._draw_sequence)}
        queued.update(payload)
        self._queued_draw_calls.append(queued)

    def _queued_draw_sort_key(self, queued):
        layer_name = queued.get("layer")
        if self._semantic_catalog is not None:
            layer_order = self._semantic_catalog.render_layer_order(layer_name)
        else:
            layer_key = str(layer_name or "").strip().lower() or "ground_overlay"
            layer_order = 0
            if layer_key == "ground_overlay":
                layer_order = 10
            elif layer_key == "item":
                layer_order = 20
            elif layer_key == "actor":
                layer_order = 30
            elif layer_key == "fx":
                layer_order = 40
            elif layer_key == "ui_overlay":
                layer_order = 50
        try:
            priority = int(queued.get("priority", 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        return (int(layer_order), priority, int(queued.get("sequence", 0) or 0))

    def _flush_queued_draws(self):
        if not self._queued_draw_calls:
            return
        queued = sorted(self._queued_draw_calls, key=self._queued_draw_sort_key)
        self._queued_draw_calls.clear()
        for call in queued:
            kind = call.get("kind")
            if kind == "glyph":
                self._draw_char(
                    call.get("x", 0),
                    call.get("y", 0),
                    call.get("glyph", " "),
                    color=call.get("color"),
                    attrs=call.get("attrs", 0),
                    semantic_id=call.get("semantic_id"),
                    effects=call.get("effects", ()),
                    overlays=call.get("overlays", ()),
                )
                continue
            if kind == "text":
                self._draw_text_now(
                    call.get("x", 0),
                    call.get("y", 0),
                    call.get("text", ""),
                    color=call.get("color"),
                    attrs=call.get("attrs", 0),
                )
                continue
            if kind == "segments":
                self._draw_segments_now(
                    call.get("x", 0),
                    call.get("y", 0),
                    call.get("segments", ()),
                    max_width=call.get("max_width"),
                    attrs=call.get("attrs", 0),
                )

    def _effects_visible(self, effects):
        effect_set = {
            str(effect).strip().lower()
            for effect in (effects or ())
            if str(effect).strip()
        }
        return True

    def _attrs_with_effects(self, attrs, effects):
        effect_set = {
            str(effect).strip().lower()
            for effect in (effects or ())
            if str(effect).strip()
        }
        resolved = int(attrs or 0)
        if "blink" in effect_set and ((int(self._animation_tick) // 4) % 2) != 0:
            resolved |= int(getattr(curses, "A_DIM", 0) or 0)
        return resolved

    def _clip_text(self, x, y, text):
        x = int(x)
        y = int(y)
        if y < 0 or y >= self.height_cells:
            return None

        text = "" if text is None else str(text)
        if x >= self.width_cells:
            return None

        if x < 0:
            clip = min(len(text), -x)
            text = text[clip:]
            x = 0

        if x >= self.width_cells:
            return None

        if text:
            text = text[: self.width_cells - x]
            if not text:
                return None

        return x, y, text

    def _draw_overlay_stack(self, x, y, overlays, attrs=0):
        for overlay in overlays or ():
            if not isinstance(overlay, dict):
                continue
            if not bool(overlay.get("visible", True)):
                continue
            if not self._effects_visible(overlay.get("effects", ())):
                continue
            glyph = str(overlay.get("glyph", " ") or " ")[:1] or " "
            color = overlay.get("color")
            semantic_id = overlay.get("semantic_id")
            overlay_attrs = int(attrs or 0) | int(overlay.get("attrs", 0) or 0)
            if self._draw_procedural_shape(x, y, glyph, color=color, attrs=overlay_attrs, semantic_id=semantic_id):
                continue
            tile_id = self._tile_id_for(glyph, color, semantic_id=semantic_id)
            if tile_id and self._blit_tile(tile_id, x, y, attrs=overlay_attrs, preserve_background=True):
                continue
            self._draw_font_char(
                x,
                y,
                glyph,
                color=color,
                attrs=overlay_attrs,
                preserve_background=True,
            )

    def _draw_char(self, x, y, ch, color=None, attrs=0, semantic_id=None, effects=None, overlays=None):
        region = self._clip_text(x, y, str(ch)[:1] or " ")
        if region is None:
            return
        if not self._effects_visible(effects):
            return
        attrs = self._attrs_with_effects(attrs, effects)
        x, y, text = region
        if self._draw_procedural_shape(x, y, text[0], color=color, attrs=attrs, semantic_id=semantic_id):
            self._draw_overlay_stack(x, y, overlays, attrs=attrs)
            return
        preserve_background = self._preserve_background_for_color(color)

        # Try sprite tile first; fall back to glyph text when no atlas loaded or
        # tile_id not yet available for this glyph+color pair.
        tile_id = self._tile_id_for(text, color, semantic_id=semantic_id)
        if tile_id and self._blit_tile(tile_id, x, y, attrs=attrs, preserve_background=preserve_background):
            self._draw_overlay_stack(x, y, overlays, attrs=attrs)
            return

        self._draw_font_char(x, y, text[0], color=color, attrs=attrs, preserve_background=preserve_background)
        self._draw_overlay_stack(x, y, overlays, attrs=attrs)

    def _draw_font_char(self, x, y, ch, color=None, attrs=0, preserve_background=False):
        fg = self._color_value(color)
        bg = (0, 0, 0)
        if self._has_attr(attrs, "A_REVERSE"):
            fg, bg = bg, fg

        if self._has_attr(attrs, "A_DIM"):
            fg = (fg[0] // 2, fg[1] // 2, fg[2] // 2)

        if self._has_attr(attrs, "A_BOLD"):
            fg = (
                min(255, int(fg[0] * 1.2)),
                min(255, int(fg[1] * 1.2)),
                min(255, int(fg[2] * 1.2)),
            )

        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        if not preserve_background or bg != (0, 0, 0):
            self.surface.fill(bg, (cell_x, cell_y, self.cell_px, self.cell_px))
        glyph = self.font.render(str(ch)[:1] or " ", True, fg)
        self.surface.blit(glyph, (cell_x, cell_y))

    def _should_use_grid_text(self, text):
        content = str(text or "")
        if len(content) <= 1:
            return True

        non_space = {ch for ch in content if not ch.isspace()}
        if not non_space:
            return True
        return non_space.issubset({"+", "-", "|", "="})

    def _ui_border_line_kind(self, text):
        content = str(text or "")
        if not content:
            return ""
        non_space = {ch for ch in content if not ch.isspace()}
        if not non_space:
            return ""
        if (
            len(content) >= 2
            and content.startswith("+")
            and content.endswith("+")
            and set(content[1:-1]).issubset({"-"})
        ):
            return "box_cap"
        if (
            len(content) >= 2
            and content.startswith("|")
            and content.endswith("|")
            and set(content[1:-1]).issubset({" "})
        ):
            return "box_mid"
        if non_space == {"-"}:
            return "divider"
        if non_space == {"="}:
            return "strong_divider"
        return ""

    def _looks_like_ui_header_text(self, text):
        content = str(text or "")
        stripped = content.strip()
        if len(stripped) < 3:
            return False
        if content.startswith(" ") and content.endswith(" "):
            return any(ch.isalnum() for ch in stripped)
        if content.startswith(" ") and stripped.upper() == stripped and any(ch.isalpha() for ch in stripped):
            return True
        return False

    def _looks_like_ui_tab_text(self, text):
        content = str(text or "")
        if "[" not in content or "]" not in content or "|" not in content:
            return False
        return any(ch.isalnum() for ch in content)

    def _looks_like_ui_footer_text(self, text):
        content = str(text or "")
        stripped = content.strip()
        if len(stripped) < 8:
            return False
        if self._looks_like_ui_header_text(text) or self._looks_like_ui_tab_text(text):
            return False

        lower = stripped.lower()
        prefix = lower.split(":", 1)[0] if ":" in lower else ""
        if prefix in {
            "move",
            "combat",
            "in-vehicle",
            "dialog",
            "trade",
            "inventory",
            "sheet",
            "notebook",
            "log",
            "debug",
            "look",
            "aim",
        }:
            return True

        action_terms = (
            "? help",
            "? for help",
            "esc close",
            "o ops",
            "y locations",
            "l log",
            "d debug",
            "pgup/pgdn",
            "up/down",
            "enter ",
            "tab/left/right",
            "shift+e",
            "shift+j",
            "e ask",
            "e select",
            "e trade",
            "u use",
            "r drop",
            "i close",
            "m trade",
            "m close",
            "g go",
        )
        score = sum(1 for term in action_terms if term in lower)
        if "|" in stripped and score >= 1:
            return True
        if "  " in content and score >= 2:
            return True
        if ("? help" in lower or "? for help" in lower) and score >= 1:
            return True
        return False

    def _ui_footer_tag_span(self, text):
        content = str(text or "")
        colon_index = content.find(":")
        if colon_index <= 0:
            return None
        prefix = content[:colon_index].strip()
        if not prefix or len(prefix) > 14:
            return None
        if prefix.lower() not in {
            "move",
            "combat",
            "in-vehicle",
            "dialog",
            "trade",
            "inventory",
            "sheet",
            "notebook",
            "log",
            "debug",
            "look",
            "aim",
        }:
            return None
        start = content.find(prefix)
        if start < 0:
            return None
        end = colon_index + 1
        return start, end, prefix

    def _ui_footer_chunks(self, text):
        content = str(text or "")
        if not content:
            return ()

        def _push_chunk(chunks, segment_start, segment_end):
            segment = content[segment_start:segment_end]
            stripped = segment.strip()
            if not stripped:
                return
            lead = len(segment) - len(segment.lstrip(" "))
            trail = len(segment) - len(segment.rstrip(" "))
            start = segment_start + lead
            end = max(start + 1, segment_end - trail)
            chunks.append((start, end, stripped))

        if "|" in content:
            chunks = []
            cursor = 0
            for segment in content.split("|"):
                seg_end = cursor + len(segment)
                _push_chunk(chunks, cursor, seg_end)
                cursor = seg_end + 1
            return tuple(chunks)

        if "  " in content:
            chunks = []
            start = 0
            idx = 0
            length = len(content)
            while idx < length:
                if content[idx] != " ":
                    idx += 1
                    continue
                run_start = idx
                while idx < length and content[idx] == " ":
                    idx += 1
                if (idx - run_start) >= 2:
                    _push_chunk(chunks, start, run_start)
                    start = idx
            _push_chunk(chunks, start, length)
            return tuple(chunks)

        return ()

    def _ui_font_for_attrs(self, attrs):
        if self._has_attr(attrs, "A_BOLD"):
            return self._ui_bold_font
        return self._ui_font

    def text_wrap_width(self, cell_width):
        cell_width = max(1, int(cell_width))
        font = self._ui_font
        char_px = max(1, int(font.size("M")[0]))
        return max(1, (cell_width * self.cell_px) // char_px)

    def _fit_text_to_pixel_width(self, text, font, max_pixel_width):
        text = str(text or "")
        max_pixel_width = max(0, int(max_pixel_width))
        if not text or max_pixel_width <= 0:
            return ""
        if font.size(text)[0] <= max_pixel_width:
            return text

        low = 0
        high = len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.size(text[:mid])[0] <= max_pixel_width:
                low = mid
            else:
                high = mid - 1
        return text[:low]

    def _clip_draw_position(self, x, y):
        x = int(x)
        y = int(y)
        if y < 0 or y >= self.height_cells:
            return None
        if x >= self.width_cells:
            return None
        return x, y

    def _draw_text_run(self, pixel_x, y, text, color=None, attrs=0):
        if not text:
            return 0

        fg = self._color_value(color)
        bg = None
        if self._has_attr(attrs, "A_REVERSE"):
            fg, bg = (0, 0, 0), fg

        if self._has_attr(attrs, "A_DIM"):
            fg = (fg[0] // 2, fg[1] // 2, fg[2] // 2)

        font = self._ui_font_for_attrs(attrs)
        if bg is None:
            surface = font.render(text, True, fg)
        else:
            surface = font.render(text, True, fg, bg)

        cell_y = int(y) * self.cell_px
        dest_y = cell_y + max(0, (self.cell_px - surface.get_height()) // 2)
        self.surface.blit(surface, (int(pixel_x), dest_y))
        return int(surface.get_width())

    def _draw_grid_text(self, x, y, text, color=None, attrs=0):
        for idx, ch in enumerate(text):
            self._draw_font_char(x + idx, y, ch, color=color, attrs=attrs)

    def _draw_ui_border_line(self, x, y, text, color=None, attrs=0):
        region = self._clip_text(x, y, text)
        if region is None:
            return False
        x, y, text = region
        kind = self._ui_border_line_kind(text)
        if not kind:
            return False

        frame = self._styled_overlay_color(color or "human", attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        width_px = max(1, len(text) * self.cell_px)
        inset = max(1, self.cell_px // 10)
        stroke_w = max(1, self.cell_px // 18)
        overlay = self.pygame.Surface((width_px, self.cell_px), self.pygame.SRCALPHA)

        fill = (
            min(255, 10 + (frame[0] // 8)),
            min(255, 12 + (frame[1] // 8)),
            min(255, 16 + (frame[2] // 8)),
            208,
        )
        accent = (
            min(255, int(frame[0] * 1.08)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            228,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 144)
        glow = (
            min(255, int(frame[0] * 1.15) + 10),
            min(255, int(frame[1] * 1.15) + 10),
            min(255, int(frame[2] * 1.15) + 10),
            84,
        )
        rect = self.pygame.Rect(0, 0, width_px, self.cell_px)
        self.pygame.draw.rect(overlay, fill, rect, border_radius=max(1, self.cell_px // 10))

        if kind in {"box_cap", "box_mid"}:
            left_x = inset
            right_x = width_px - inset - 1
            self.pygame.draw.line(overlay, accent, (left_x, inset), (left_x, self.cell_px - inset - 1), stroke_w)
            self.pygame.draw.line(overlay, shadow, (right_x, inset), (right_x, self.cell_px - inset - 1), stroke_w)

        if kind == "box_cap":
            top_y = inset
            bottom_y = self.cell_px - inset - 1
            self.pygame.draw.line(overlay, accent, (inset, top_y), (width_px - inset - 1, top_y), stroke_w)
            self.pygame.draw.line(overlay, shadow, (inset, bottom_y), (width_px - inset - 1, bottom_y), stroke_w)
            self.pygame.draw.line(
                overlay,
                glow,
                (max(2, self.cell_px // 3), max(2, self.cell_px // 4)),
                (width_px - max(3, self.cell_px // 3), max(2, self.cell_px // 4)),
                max(1, stroke_w),
            )
        elif kind == "divider":
            mid_y = self.cell_px // 2
            self.pygame.draw.line(
                overlay,
                glow,
                (max(1, self.cell_px // 4), mid_y),
                (width_px - max(2, self.cell_px // 4), mid_y),
                max(2, stroke_w + 1),
            )
            self.pygame.draw.line(
                overlay,
                accent,
                (max(1, self.cell_px // 4), mid_y),
                (width_px - max(2, self.cell_px // 4), mid_y),
                stroke_w,
            )
        elif kind == "strong_divider":
            upper_y = max(2, self.cell_px // 2 - 1)
            lower_y = min(self.cell_px - 3, self.cell_px // 2 + 1)
            for line_y in (upper_y, lower_y):
                self.pygame.draw.line(
                    overlay,
                    accent,
                    (max(1, self.cell_px // 4), line_y),
                    (width_px - max(2, self.cell_px // 4), line_y),
                    stroke_w,
                )

        self.surface.blit(overlay, (cell_x, cell_y))
        return True

    def _draw_ui_header_backdrop(self, x, y, text, color=None, attrs=0):
        region = self._clip_text(x, y, text)
        if region is None:
            return False
        x, y, text = region
        if not self._looks_like_ui_header_text(text):
            return False

        frame = self._styled_overlay_color(color or "objective", attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        width_px = max(1, len(text) * self.cell_px)
        overlay = self.pygame.Surface((width_px, self.cell_px), self.pygame.SRCALPHA)
        inset = max(1, self.cell_px // 10)
        rect = self.pygame.Rect(0, inset, width_px, max(4, self.cell_px - (inset * 2)))

        fill = (
            min(255, 12 + (frame[0] // 8)),
            min(255, 14 + (frame[1] // 8)),
            min(255, 18 + (frame[2] // 8)),
            214,
        )
        accent = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            228,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 138)
        glow = (
            min(255, int(frame[0] * 1.18) + 8),
            min(255, int(frame[1] * 1.12) + 8),
            min(255, int(frame[2] * 1.12) + 8),
            74,
        )

        self.pygame.draw.rect(overlay, fill, rect, border_radius=max(2, self.cell_px // 7))
        self.pygame.draw.line(
            overlay,
            glow,
            (max(2, self.cell_px // 3), rect.top + max(1, self.cell_px // 10)),
            (width_px - max(3, self.cell_px // 3), rect.top + max(1, self.cell_px // 10)),
            max(1, self.cell_px // 20),
        )
        self.pygame.draw.line(
            overlay,
            accent,
            (rect.left + max(2, self.cell_px // 5), rect.top),
            (rect.right - max(3, self.cell_px // 5), rect.top),
            max(1, self.cell_px // 18),
        )
        self.pygame.draw.line(
            overlay,
            shadow,
            (rect.left + max(2, self.cell_px // 5), rect.bottom - 1),
            (rect.right - max(3, self.cell_px // 5), rect.bottom - 1),
            max(1, self.cell_px // 18),
        )

        self.surface.blit(overlay, (cell_x, cell_y))
        return True

    def _draw_ui_tab_backdrop(self, x, y, text, color=None, attrs=0):
        region = self._clip_text(x, y, text)
        if region is None:
            return False
        x, y, text = region
        if not self._looks_like_ui_tab_text(text):
            return False

        frame = self._styled_overlay_color(color or "player", attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        width_px = max(1, len(text) * self.cell_px)
        overlay = self.pygame.Surface((width_px, self.cell_px), self.pygame.SRCALPHA)

        band_y = max(2, self.cell_px // 4)
        band_h = max(4, self.cell_px - (band_y * 2))
        band_rect = self.pygame.Rect(0, band_y, width_px, band_h)
        band_fill = (
            min(255, 10 + (frame[0] // 10)),
            min(255, 12 + (frame[1] // 10)),
            min(255, 18 + (frame[2] // 10)),
            176,
        )
        active_fill = (
            min(255, int(frame[0] * 0.52) + 18),
            min(255, int(frame[1] * 0.64) + 22),
            min(255, int(frame[2] * 0.74) + 26),
            214,
        )
        active_stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            228,
        )
        separator = (frame[0], frame[1], frame[2], 122)

        self.pygame.draw.rect(overlay, band_fill, band_rect, border_radius=max(2, self.cell_px // 8))

        cursor = 0
        for chunk in text.split("|"):
            segment = str(chunk)
            stripped = segment.strip()
            seg_start = cursor
            seg_end = cursor + len(segment)
            if stripped.startswith("[") and stripped.endswith("]"):
                lead = len(segment) - len(segment.lstrip(" "))
                trail = len(segment) - len(segment.rstrip(" "))
                left = max(0, (seg_start + lead) * self.cell_px)
                right = max(left + self.cell_px, (seg_end - trail) * self.cell_px)
                pill_rect = self.pygame.Rect(
                    left,
                    max(1, self.cell_px // 7),
                    max(4, right - left),
                    max(4, self.cell_px - (max(1, self.cell_px // 7) * 2)),
                )
                self.pygame.draw.rect(overlay, active_fill, pill_rect, border_radius=max(3, self.cell_px // 6))
                self.pygame.draw.rect(overlay, active_stroke, pill_rect, max(1, self.cell_px // 22), border_radius=max(3, self.cell_px // 6))
            cursor = seg_end + 1

        for idx, ch in enumerate(text):
            if ch != "|":
                continue
            px = (idx * self.cell_px) + (self.cell_px // 2)
            self.pygame.draw.line(
                overlay,
                separator,
                (px, band_rect.top + max(1, self.cell_px // 7)),
                (px, band_rect.bottom - max(1, self.cell_px // 7)),
                max(1, self.cell_px // 26),
            )

        self.surface.blit(overlay, (cell_x, cell_y))
        return True

    def _draw_ui_footer_band(self, x, y, text, color=None, attrs=0):
        region = self._clip_text(x, y, text)
        if region is None:
            return False
        x, y, text = region
        if not self._looks_like_ui_footer_text(text):
            return False

        frame = self._styled_overlay_color(color or "human", attrs=attrs, bold_scale=1.06)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        width_px = max(1, len(text) * self.cell_px)
        overlay = self.pygame.Surface((width_px, self.cell_px), self.pygame.SRCALPHA)

        band_y = max(1, self.cell_px // 6)
        band_h = max(4, self.cell_px - (band_y * 2))
        band_rect = self.pygame.Rect(0, band_y, width_px, band_h)
        band_fill = (
            min(255, 8 + (frame[0] // 12)),
            min(255, 10 + (frame[1] // 12)),
            min(255, 16 + (frame[2] // 10)),
            150,
        )
        accent = (
            min(255, int(frame[0] * 1.08)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            208,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 112)
        chip_fill = (
            min(255, int(frame[0] * 0.44) + 14),
            min(255, int(frame[1] * 0.48) + 16),
            min(255, int(frame[2] * 0.56) + 22),
            164,
        )
        chip_stroke = (
            min(255, int(frame[0] * 1.1)),
            min(255, int(frame[1] * 1.1)),
            min(255, int(frame[2] * 1.1)),
            196,
        )
        tag_fill = (
            min(255, int(frame[0] * 0.58) + 18),
            min(255, int(frame[1] * 0.66) + 20),
            min(255, int(frame[2] * 0.78) + 26),
            216,
        )

        self.pygame.draw.rect(overlay, band_fill, band_rect, border_radius=max(2, self.cell_px // 8))
        self.pygame.draw.line(
            overlay,
            accent,
            (max(2, self.cell_px // 5), band_rect.top),
            (width_px - max(3, self.cell_px // 5), band_rect.top),
            max(1, self.cell_px // 22),
        )
        self.pygame.draw.line(
            overlay,
            shadow,
            (max(2, self.cell_px // 5), band_rect.bottom - 1),
            (width_px - max(3, self.cell_px // 5), band_rect.bottom - 1),
            max(1, self.cell_px // 24),
        )

        tag_span = self._ui_footer_tag_span(text)
        if tag_span is not None:
            start, end, _tag = tag_span
            left = max(0, start * self.cell_px)
            right = max(left + self.cell_px, end * self.cell_px)
            tag_rect = self.pygame.Rect(
                left,
                max(1, self.cell_px // 8),
                max(4, right - left),
                max(4, self.cell_px - (max(1, self.cell_px // 8) * 2)),
            )
            self.pygame.draw.rect(overlay, tag_fill, tag_rect, border_radius=max(3, self.cell_px // 6))
            self.pygame.draw.rect(overlay, chip_stroke, tag_rect, max(1, self.cell_px // 24), border_radius=max(3, self.cell_px // 6))

        for start, end, _label in self._ui_footer_chunks(text):
            if tag_span is not None:
                tag_start, tag_end, _ = tag_span
                if start >= tag_start and end <= tag_end:
                    continue
            left = max(0, start * self.cell_px)
            right = max(left + self.cell_px, end * self.cell_px)
            chip_rect = self.pygame.Rect(
                left,
                max(2, self.cell_px // 5),
                max(4, right - left),
                max(4, self.cell_px - (max(2, self.cell_px // 5) * 2)),
            )
            self.pygame.draw.rect(overlay, chip_fill, chip_rect, border_radius=max(2, self.cell_px // 7))
            self.pygame.draw.rect(overlay, chip_stroke, chip_rect, max(1, self.cell_px // 26), border_radius=max(2, self.cell_px // 7))

        self.surface.blit(overlay, (cell_x, cell_y))
        return True

    def _blit_tile_pixels(self, tile_id, pixel_x, y, attrs=0):
        tile_id = self._semantic_aliases.get(str(tile_id), str(tile_id))
        rect = self._tile_rects.get(str(tile_id))
        if rect is None or self._atlas is None:
            return False

        dest_x = int(pixel_x)
        dest_y = int(y) * self.cell_px
        tile_surf = self._atlas.subsurface(rect)
        if rect.w != self.cell_px or rect.h != self.cell_px:
            tile_surf = self.pygame.transform.scale(tile_surf, (self.cell_px, self.cell_px))

        if self._has_attr(attrs, "A_DIM") or self._has_attr(attrs, "A_REVERSE"):
            tile_surf = tile_surf.copy()
            if self._has_attr(attrs, "A_REVERSE"):
                tile_surf = self.pygame.transform.flip(tile_surf, True, False)
            if self._has_attr(attrs, "A_DIM"):
                tile_surf.set_alpha(128)

        self.surface.blit(tile_surf, (dest_x, dest_y))
        return True

    def _draw_inline_glyph_run(self, pixel_x, y, ch, color=None, attrs=0, semantic_id=None):
        text = str(ch)[:1] or " "
        tile_id = self._tile_id_for(text, color, semantic_id=semantic_id)
        if tile_id is None:
            tile_id = self._any_direct_tile_id_for_glyph(text)
        if tile_id and self._blit_tile_pixels(tile_id, pixel_x, y, attrs=attrs):
            return self.cell_px

        fg = self._color_value(color)
        bg = None
        if self._has_attr(attrs, "A_REVERSE"):
            fg, bg = (0, 0, 0), fg
        if self._has_attr(attrs, "A_DIM"):
            fg = (fg[0] // 2, fg[1] // 2, fg[2] // 2)
        if self._has_attr(attrs, "A_BOLD"):
            fg = (
                min(255, int(fg[0] * 1.2)),
                min(255, int(fg[1] * 1.2)),
                min(255, int(fg[2] * 1.2)),
            )

        if bg is None:
            surface = self.font.render(text, True, fg)
        else:
            surface = self.font.render(text, True, fg, bg)
        cell_y = int(y) * self.cell_px
        dest_y = cell_y + max(0, (self.cell_px - surface.get_height()) // 2)
        self.surface.blit(surface, (int(pixel_x), dest_y))
        return self.cell_px

    def draw(self, x, y, glyph, color=None, attrs=0, semantic_id=None, effects=None, overlays=None, layer=None, priority=None):
        if self._wants_layered_draw(layer=layer, priority=priority):
            self._queue_draw_call(
                "glyph",
                x=int(x),
                y=int(y),
                glyph=str(glyph)[:1] or " ",
                color=color,
                attrs=int(attrs or 0),
                semantic_id=semantic_id,
                effects=tuple(effects or ()),
                overlays=tuple(overlays or ()),
                layer=layer,
                priority=0 if priority is None else int(priority),
            )
            return
        self._flush_queued_draws()
        self._draw_char(
            x,
            y,
            glyph,
            color=color,
            attrs=attrs,
            semantic_id=semantic_id,
            effects=effects,
            overlays=overlays,
        )

    def _draw_text_now(self, x, y, text, color=None, attrs=0):
        if self._draw_ui_border_line(x, y, text, color=color, attrs=attrs):
            return
        self._draw_ui_header_backdrop(x, y, text, color=color, attrs=attrs)
        self._draw_ui_tab_backdrop(x, y, text, color=color, attrs=attrs)
        self._draw_ui_footer_band(x, y, text, color=color, attrs=attrs)
        if self._should_use_grid_text(text):
            region = self._clip_text(x, y, text)
            if region is None:
                return
            x, y, text = region
            self._draw_grid_text(x, y, text, color=color, attrs=attrs)
            return

        region = self._clip_draw_position(x, y)
        if region is None:
            return
        x, y = region
        font = self._ui_font_for_attrs(attrs)
        pixel_x = x * self.cell_px
        available_px = (self.width_cells * self.cell_px) - pixel_x
        text = self._fit_text_to_pixel_width(text, font, available_px)
        if not text:
            return
        self._draw_text_run(pixel_x, y, text, color=color, attrs=attrs)

    def draw_text(self, x, y, text, color=None, attrs=0, layer=None, priority=None):
        if self._wants_layered_draw(layer=layer, priority=priority):
            self._queue_draw_call(
                "text",
                x=int(x),
                y=int(y),
                text=str(text),
                color=color,
                attrs=int(attrs or 0),
                layer=layer,
                priority=0 if priority is None else int(priority),
            )
            return
        self._flush_queued_draws()
        self._draw_text_now(x, y, text, color=color, attrs=attrs)

    def _draw_segments_now(self, x, y, segments, max_width=None, attrs=0):
        region = self._clip_draw_position(x, y)
        if region is None:
            return
        start_x, y = region
        plain_text = "".join(
            str(segment.get("text", "")) if isinstance(segment, dict) else str(segment)
            for segment in (segments or ())
        )
        self._draw_ui_header_backdrop(start_x, y, plain_text, color=None, attrs=attrs)
        self._draw_ui_tab_backdrop(start_x, y, plain_text, color=None, attrs=attrs)
        self._draw_ui_footer_band(start_x, y, plain_text, color=None, attrs=attrs)
        pixel_x = start_x * self.cell_px
        remaining_px = None if max_width is None else max(0, int(max_width) * self.cell_px)
        for segment in segments or ():
            if remaining_px is not None and remaining_px <= 0:
                break
            if isinstance(segment, dict):
                text = str(segment.get("text", ""))
                color = segment.get("color")
                seg_attrs = int(segment.get("attrs", 0) or 0)
                inline_glyph = bool(segment.get("inline_glyph"))
                semantic_id = segment.get("semantic_id")
            else:
                text = str(segment)
                color = None
                seg_attrs = 0
                inline_glyph = False
                semantic_id = None
            if not text:
                continue
            combined_attrs = int(attrs) | seg_attrs
            if inline_glyph:
                if remaining_px is not None and remaining_px < self.cell_px:
                    break
                drawn_px = self._draw_inline_glyph_run(
                    pixel_x,
                    y,
                    text[0],
                    color=color,
                    attrs=combined_attrs,
                    semantic_id=semantic_id,
                )
            elif self._should_use_grid_text(text) and pixel_x % self.cell_px == 0:
                if remaining_px is not None:
                    max_chars = max(0, remaining_px // self.cell_px)
                    if max_chars <= 0:
                        break
                    text = text[:max_chars]
                if not text:
                    continue
                self._draw_grid_text(pixel_x // self.cell_px, y, text, color=color, attrs=combined_attrs)
                drawn_px = len(text) * self.cell_px
            else:
                font = self._ui_font_for_attrs(combined_attrs)
                available_px = (self.width_cells * self.cell_px) - pixel_x
                if remaining_px is not None:
                    available_px = min(available_px, remaining_px)
                text = self._fit_text_to_pixel_width(text, font, available_px)
                if not text:
                    continue
                drawn_px = self._draw_text_run(pixel_x, y, text, color=color, attrs=combined_attrs)
            pixel_x += drawn_px
            if remaining_px is not None:
                remaining_px -= drawn_px

    def draw_segments(self, x, y, segments, max_width=None, attrs=0, layer=None, priority=None):
        if self._wants_layered_draw(layer=layer, priority=priority):
            self._queue_draw_call(
                "segments",
                x=int(x),
                y=int(y),
                segments=list(segments or ()),
                max_width=max_width,
                attrs=int(attrs or 0),
                layer=layer,
                priority=0 if priority is None else int(priority),
            )
            return
        self._flush_queued_draws()
        self._draw_segments_now(x, y, segments, max_width=max_width, attrs=attrs)

    def _map_key(self, event):
        if event.type == self.pygame.QUIT:
            return ord("q")
        if event.type != self.pygame.KEYDOWN:
            return None

        key = event.key
        keypad_enter = getattr(self.pygame, "K_KP_ENTER", None)
        if key == self.pygame.K_UP:
            return KEY_UP
        if key == self.pygame.K_DOWN:
            return KEY_DOWN
        if key == self.pygame.K_LEFT:
            return KEY_LEFT
        if key == self.pygame.K_RIGHT:
            return KEY_RIGHT
        if key in (self.pygame.K_RETURN, keypad_enter):
            return 10
        if key == self.pygame.K_ESCAPE:
            return 27
        if key == self.pygame.K_BACKSPACE:
            return 127
        if key == self.pygame.K_TAB:
            return 9
        if key == self.pygame.K_SPACE:
            return ord(" ")

        uni = getattr(event, "unicode", "")
        if uni:
            try:
                return ord(uni)
            except (TypeError, ValueError):
                return None
        return None

    def get_key(self):
        for event in self.pygame.event.get():
            mapped = self._map_key(event)
            if mapped is not None:
                self.key_queue.append(mapped)

        if not self.key_queue:
            return None
        return self.key_queue.popleft()

    def drain_keys(self):
        for event in self.pygame.event.get():
            mapped = self._map_key(event)
            if mapped is not None:
                self.key_queue.append(mapped)

        if not self.key_queue:
            return []

        drained = list(self.key_queue)
        self.key_queue.clear()
        return drained

    def held_movement_delta(self):
        self.pygame.event.pump()
        pressed = self.pygame.key.get_pressed()

        def _any_pressed(*keys):
            for key in keys:
                if key is None:
                    continue
                try:
                    if pressed[key]:
                        return True
                except (IndexError, TypeError):
                    continue
            return False

        left = _any_pressed(
            self.pygame.K_LEFT,
            self.pygame.K_a,
            self.pygame.K_h,
        )
        right = _any_pressed(
            self.pygame.K_RIGHT,
            self.pygame.K_d,
            self.pygame.K_l,
        )
        up = _any_pressed(
            self.pygame.K_UP,
            self.pygame.K_w,
            self.pygame.K_k,
        )
        down = _any_pressed(
            self.pygame.K_DOWN,
            self.pygame.K_s,
            self.pygame.K_j,
        )

        dx = (-1 if left and not right else 1 if right and not left else 0)
        dy = (-1 if up and not down else 1 if down and not up else 0)
        if dx or dy:
            return (dx, dy)

        keypad_diagonals = (
            (getattr(self.pygame, "K_KP7", None), (-1, -1)),
            (getattr(self.pygame, "K_KP9", None), (1, -1)),
            (getattr(self.pygame, "K_KP1", None), (-1, 1)),
            (getattr(self.pygame, "K_KP3", None), (1, 1)),
        )
        for key, delta in keypad_diagonals:
            if _any_pressed(key):
                return delta
        return None

    def refresh(self):
        self._flush_queued_draws()
        self.pygame.display.flip()

    def close(self):
        self.pygame.quit()
