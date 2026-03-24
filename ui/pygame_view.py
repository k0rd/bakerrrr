import curses
import json
import time
from collections import deque
from pathlib import Path
from typing import Any

from ui.input_keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP

_TILE_MAP_PATH = Path(__file__).resolve().parents[1] / "assets" / "tiles" / "tile_map.json"
_DEFAULT_ATLAS_PATH = Path(__file__).resolve().parents[1] / "assets" / "tiles" / "atlas" / "tileset.png"
_DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "assets" / "tiles" / "atlas" / "tileset.json"
_DEFAULT_SEMANTIC_MAP_PATH = Path(__file__).resolve().parents[1] / "assets" / "tiles" / "atlas" / "semantic_mapping.json"


def atlas_manifest_tile_size(manifest_path=None, default=40, minimum=8):
    """Return the atlas cell size declared in the manifest, with safe fallback."""
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
    - If an atlas + manifest are present they are loaded automatically.
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
        self.key_queue = deque()

        # Atlas tile rendering. Populated by _load_atlas().
        self._atlas: Any = None            # pygame.Surface or None
        self._tile_rects: dict = {}        # tile_id -> pygame.Rect
        self._glyph_color_tiles: dict = {} # (glyph, asset_color) -> tile_id
        self._tile_map: dict = {}          # glyph/category lookup table from tile_map.json
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
            "item_ground": (225, 185, 95),
            "item_token": (240, 220, 110),
            "item_tool": (200, 170, 120),
            "item_medical": (120, 220, 140),
            "item_restricted": (230, 150, 100),
            "item_illegal": (220, 90, 90),
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
        atlas_path = Path(atlas_path) if atlas_path else _DEFAULT_ATLAS_PATH
        manifest_path = Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST_PATH

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
        """Load the glyph -> tile_id mapping table."""
        path = Path(path) if path else _TILE_MAP_PATH
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return
        self._tile_map = {k: v for k, v in raw.items() if not k.startswith("_")}
        aliases = raw.get("_color_aliases", {}) if isinstance(raw, dict) else {}
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
        path = Path(path) if path else _DEFAULT_SEMANTIC_MAP_PATH
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return

        mapping = raw.get("assignments", {}) if isinstance(raw, dict) else {}
        if not isinstance(mapping, dict):
            return
        self._semantic_aliases = {
            str(k): str(v)
            for k, v in mapping.items()
            if k and v
        }

    def _category_order_for_color(self, color_key):
        """Return preferred tile-map category order for a given color key."""
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

    def _tile_id_for(self, glyph, color):
        """Resolve a tile_id from glyph+color using tile_map; return None if unmapped."""
        if not self._tile_map or self._atlas is None:
            return None

        glyph = str(glyph)[:1] if glyph else ""
        color_key = str(color) if color else "default"

        tile_id = self._direct_tile_id_for(glyph, color_key)
        if tile_id:
            return tile_id

        ordered_categories = [
            self._tile_map.get(name)
            for name in self._category_order_for_color(color_key)
            if isinstance(self._tile_map.get(name), dict)
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

    def _blit_tile(self, tile_id, x, y, attrs=0):
        """Blit a sprite tile to cell (x, y). Returns True if drawn, False if not found."""
        tile_id = self._semantic_aliases.get(str(tile_id), str(tile_id))
        rect = self._tile_rects.get(str(tile_id))
        if rect is None or self._atlas is None:
            return False

        dest_x = x * self.cell_px
        dest_y = y * self.cell_px
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

    def _draw_char(self, x, y, ch, color=None, attrs=0):
        region = self._clip_text(x, y, str(ch)[:1] or " ")
        if region is None:
            return
        x, y, text = region

        # Try sprite tile first; fall back to glyph text when no atlas loaded or
        # tile_id not yet available for this glyph+color pair.
        tile_id = self._tile_id_for(text, color)
        if tile_id and self._blit_tile(tile_id, x, y, attrs=attrs):
            return

        self._draw_font_char(x, y, text[0], color=color, attrs=attrs)

    def _draw_font_char(self, x, y, ch, color=None, attrs=0):
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

    def _draw_inline_glyph_run(self, pixel_x, y, ch, color=None, attrs=0):
        text = str(ch)[:1] or " "
        tile_id = self._tile_id_for(text, color)
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

    def draw(self, x, y, glyph, color=None, attrs=0):
        self._draw_char(x, y, glyph, color=color, attrs=attrs)

    def draw_text(self, x, y, text, color=None, attrs=0):
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

    def draw_segments(self, x, y, segments, max_width=None, attrs=0):
        region = self._clip_draw_position(x, y)
        if region is None:
            return
        start_x, y = region
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
            else:
                text = str(segment)
                color = None
                seg_attrs = 0
                inline_glyph = False
            if not text:
                continue
            combined_attrs = int(attrs) | seg_attrs
            if inline_glyph:
                if remaining_px is not None and remaining_px < self.cell_px:
                    break
                drawn_px = self._draw_inline_glyph_run(pixel_x, y, text[0], color=color, attrs=combined_attrs)
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

    def refresh(self):
        self.pygame.display.flip()

    def close(self):
        self.pygame.quit()
