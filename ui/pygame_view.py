import json
import math
import os
import sys
import time
from collections import deque
from pathlib import Path

from game.appearance_palette import pygame_palette_entries
from game.action_bindings import CONTROLLER_DEADZONE, CONTROLLER_REPEAT_DELAY, CONTROLLER_REPEAT_INTERVAL
from game.color_words import casino_color_word, color_word_rgb
from game.semantic_catalog import DEFAULT_RENDER_SEMANTICS_PATH, get_runtime_semantic_catalog
from game.symbolic_palette import pygame_symbolic_palette_entries
from game.world_palette import pygame_world_palette_entries
from ui.input_keys import (
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RIGHT,
    KEY_UP,
)
from ui.text_attrs import A_DIM, attr_for_name

_DEFAULT_RENDER_SEMANTICS_PATH = DEFAULT_RENDER_SEMANTICS_PATH

_PYGAME_VEHICLE_HEADING_BY_KEY = {
    "n": (0, -1),
    "north": (0, -1),
    "ne": (1, -1),
    "northeast": (1, -1),
    "north_east": (1, -1),
    "e": (1, 0),
    "east": (1, 0),
    "se": (1, 1),
    "southeast": (1, 1),
    "south_east": (1, 1),
    "s": (0, 1),
    "south": (0, 1),
    "sw": (-1, 1),
    "southwest": (-1, 1),
    "south_west": (-1, 1),
    "w": (-1, 0),
    "west": (-1, 0),
    "nw": (-1, -1),
    "northwest": (-1, -1),
    "north_west": (-1, -1),
}
_PYGAME_VEHICLE_HEADING_BY_GLYPH = {
    "^": (0, -1),
    "7": (1, -1),
    ">": (1, 0),
    "J": (1, 1),
    "v": (0, 1),
    "L": (-1, 1),
    "<": (-1, 0),
    "F": (-1, -1),
}
_PYGAME_VEHICLE_HEADING_LABELS = {
    (0, -1): "n",
    (1, -1): "ne",
    (1, 0): "e",
    (1, 1): "se",
    (0, 1): "s",
    (-1, 1): "sw",
    (-1, 0): "w",
    (-1, -1): "nw",
}

_SDL_CONTROLLER_BUTTONS = {
    0: "south",
    1: "east",
    2: "west",
    3: "north",
    4: "view",
    5: "guide",
    6: "start",
    7: "left_stick",
    8: "right_stick",
    9: "left_shoulder",
    10: "right_shoulder",
    11: "dpad_up",
    12: "dpad_down",
    13: "dpad_left",
    14: "dpad_right",
}
_SDL_CONTROLLER_AXES = {
    0: "left_x",
    1: "left_y",
    2: "right_x",
    3: "right_y",
    4: "left_trigger",
    5: "right_trigger",
}
_CONTROLLER_DPAD_DELTAS = {
    "dpad_up": (0, -1),
    "dpad_down": (0, 1),
    "dpad_left": (-1, 0),
    "dpad_right": (1, 0),
}
_CONTROLLER_BUTTON_DEDUPE_SECONDS = 0.42
_CONTROLLER_HAT_DEDUPE_SECONDS = 0.28
_CONTROLLER_DIGITAL_REPEAT_DELAY = 0.42
_CONTROLLER_DIGITAL_REPEAT_INTERVAL = 0.22
_CONTROLLER_LOOK_DEADZONE = 0.55
_CONTROLLER_LOOK_REPEAT_DELAY = 0.28
_CONTROLLER_LOOK_REPEAT_INTERVAL = 0.16
_CONTROL_SEMANTIC_DEDUPE_SECONDS = 0.28
_CONTROL_SEMANTIC_DEDUPE_KEYS = frozenset({9, 10, 13, 27, ord("b"), ord("r")})
_INPUT_DEBUG_ENV = "BAKERRRR_INPUT_DEBUG"
_INPUT_DEBUG_PATH_ENV = "BAKERRRR_INPUT_DEBUG_PATH"
_INPUT_DEBUG_MAX_BYTES_ENV = "BAKERRRR_INPUT_DEBUG_MAX_BYTES"
_INPUT_DEBUG_DEFAULT_PATH = Path("saves") / "debug" / "input_debug.log"
_INPUT_DEBUG_DEFAULT_MAX_BYTES = 5 * 1024 * 1024


def _resource_path(*parts):
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).joinpath(*parts)
    return Path(__file__).resolve().parents[1].joinpath(*parts)


def _env_truthy(name):
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on", "debug", "trace"}


class PygameView:
    """Grid-based pygame view implementing the same drawing/input surface as CursesView.

    Rendering:
    - Procedural world rendering is the primary path.
    - When no procedural shape applies, glyph text rendering is the fallback.
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
        resolved_cell_px = 24 if cell_px is None else cell_px
        self.cell_px = max(8, int(resolved_cell_px))
        self._window_icon_path = None
        self._install_window_icon()
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
        self.input_queue = deque()
        self._controller_module = None
        self._controller_devices = {}
        self._controller_axis_state = {}
        self._controller_axis_pressed = {}
        self._controller_button_state = {}
        self._controller_button_accept_at = {}
        self._raw_joysticks = {}
        self._raw_axis_state = {}
        self._raw_axis_pressed = {}
        self._raw_button_state = {}
        self._raw_button_accept_at = {}
        self._raw_hat_state = {}
        self._raw_hat_accept_at = {}
        self._control_semantic_accept_at = {}
        self._control_semantic_accept_source = {}
        self._input_debug_enabled = _env_truthy(_INPUT_DEBUG_ENV)
        self._input_debug_file = None
        self._input_debug_seq = 0
        self._input_debug_path = self._resolve_input_debug_path()
        self._last_controller_move_delta = (0, 0)
        self._last_controller_move_at = 0.0
        self._next_controller_repeat_at = 0.0
        self._last_controller_look_delta = (0, 0)
        self._last_controller_look_at = 0.0
        self._next_controller_look_repeat_at = 0.0
        self._input_debug(
            "view_init",
            width_cells=self.width_cells,
            height_cells=self.height_cells,
            cell_px=self.cell_px,
            pygame_version=getattr(pygame, "version", None) and getattr(getattr(pygame, "version", None), "ver", ""),
        )
        self._init_controller_input()
        self._close_requested = False
        self._animation_tick = 0
        self.uses_realtime_animation = True
        self._queued_draw_calls = []
        self._draw_sequence = 0
        self._active_surface_light_tint = None
        self._semantic_catalog = None
        self._load_render_semantics()

        self.palette = {
            "default": (240, 240, 240),
        }
        self.palette.update(pygame_symbolic_palette_entries())
        self.palette.update(pygame_world_palette_entries())
        self.palette.update(pygame_palette_entries())

    def _resolve_input_debug_path(self):
        raw = str(os.getenv(_INPUT_DEBUG_PATH_ENV, "") or "").strip()
        if raw:
            return Path(raw).expanduser()
        return _INPUT_DEBUG_DEFAULT_PATH

    def _input_debug_max_bytes(self):
        raw = str(os.getenv(_INPUT_DEBUG_MAX_BYTES_ENV, "") or "").strip()
        if not raw:
            return _INPUT_DEBUG_DEFAULT_MAX_BYTES
        try:
            return max(64 * 1024, int(raw))
        except (TypeError, ValueError):
            return _INPUT_DEBUG_DEFAULT_MAX_BYTES

    def _ensure_input_debug_file(self):
        if not self._input_debug_enabled:
            return None
        if self._input_debug_file is not None:
            return self._input_debug_file
        try:
            path = Path(self._input_debug_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            max_bytes = self._input_debug_max_bytes()
            try:
                if path.exists() and path.stat().st_size > max_bytes:
                    rotated = path.with_suffix(path.suffix + ".1")
                    try:
                        rotated.unlink()
                    except FileNotFoundError:
                        pass
                    path.replace(rotated)
            except OSError:
                pass
            self._input_debug_file = path.open("a", encoding="utf-8", buffering=1)
            return self._input_debug_file
        except OSError:
            self._input_debug_enabled = False
            return None

    def _input_debug_safe(self, value):
        if isinstance(value, dict):
            return {str(key): self._input_debug_safe(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._input_debug_safe(val) for val in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _input_debug(self, event_name, **fields):
        handle = self._ensure_input_debug_file()
        if handle is None:
            return
        self._input_debug_seq += 1
        row = {
            "seq": int(self._input_debug_seq),
            "time": round(time.monotonic(), 6),
            "event": str(event_name),
        }
        for key, value in fields.items():
            row[str(key)] = self._input_debug_safe(value)
        try:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        except OSError:
            self._input_debug_enabled = False

    def _input_debug_event_fields(self, event):
        if event is None:
            return {}
        fields = {}
        event_type = getattr(event, "type", None)
        fields["type"] = event_type
        try:
            fields["type_name"] = self.pygame.event.event_name(event_type)
        except Exception:
            fields["type_name"] = str(event_type)
        for attr in (
            "key",
            "unicode",
            "button",
            "axis",
            "value",
            "which",
            "instance_id",
            "device_index",
            "hat",
        ):
            if hasattr(event, attr):
                fields[attr] = getattr(event, attr)
        return fields

    def _init_controller_input(self):
        try:
            self.pygame.joystick.init()
        except Exception:
            self._input_debug("controller_init_failed", stage="joystick_init")
            return False
        controller_mod = None
        try:
            from pygame._sdl2 import controller as controller_mod  # type: ignore
        except Exception:
            controller_mod = None
        self._controller_module = controller_mod
        try:
            if controller_mod is not None and hasattr(controller_mod, "init"):
                controller_mod.init()
        except Exception:
            pass
        try:
            count = self.pygame.joystick.get_count()
        except Exception:
            count = 0
        self._input_debug("controller_init", controller_module=bool(controller_mod is not None), joystick_count=int(count or 0))
        for index in range(max(0, int(count))):
            self._open_controller_device(index)
        return True

    def _device_instance_id(self, device, fallback):
        for attr in ("get_instance_id", "get_id"):
            getter = getattr(device, attr, None)
            if not callable(getter):
                continue
            try:
                return int(getter())
            except Exception:
                continue
        return int(fallback)

    def _device_guid(self, device, fallback=""):
        getter = getattr(device, "get_guid", None)
        if callable(getter):
            try:
                value = str(getter() or "").strip()
                if value:
                    return value
            except Exception:
                pass
        return str(fallback or "").strip()

    def _open_controller_device(self, index):
        controller_mod = getattr(self, "_controller_module", None)
        if controller_mod is not None:
            try:
                is_controller = getattr(controller_mod, "is_controller", None)
                if callable(is_controller) and is_controller(index):
                    controller = controller_mod.Controller(index)
                    init = getattr(controller, "init", None)
                    if callable(init):
                        init()
                    instance_id = self._device_instance_id(controller, index)
                    self._controller_devices[instance_id] = controller
                    self._input_debug(
                        "controller_opened",
                        index=int(index),
                        instance_id=int(instance_id),
                        source="controller",
                        guid=self._device_guid(controller, fallback=f"controller{instance_id}"),
                    )
                    return True
            except Exception as exc:
                self._input_debug("controller_open_failed", index=int(index), source="controller", error=repr(exc))

        try:
            joystick = self.pygame.joystick.Joystick(index)
            init = getattr(joystick, "init", None)
            if callable(init):
                init()
            instance_id = self._device_instance_id(joystick, index)
            self._raw_joysticks[instance_id] = joystick
            self._input_debug(
                "controller_opened",
                index=int(index),
                instance_id=int(instance_id),
                source="joystick",
                guid=self._device_guid(joystick, fallback=f"joy{instance_id}"),
            )
            return True
        except Exception as exc:
            self._input_debug("controller_open_failed", index=int(index), source="joystick", error=repr(exc))
            return False

    def _close_controller_device(self, instance_id):
        try:
            instance_id = int(instance_id)
        except (TypeError, ValueError):
            return False
        device = self._controller_devices.pop(instance_id, None)
        source = "controller" if device is not None else "joystick"
        if device is None:
            device = self._raw_joysticks.pop(instance_id, None)
        self._controller_axis_state = {
            key: value
            for key, value in self._controller_axis_state.items()
            if key[0] != instance_id
        }
        self._controller_axis_pressed = {
            key: value
            for key, value in self._controller_axis_pressed.items()
            if key[0] != instance_id
        }
        self._controller_button_state = {
            key: value
            for key, value in self._controller_button_state.items()
            if key[0] != instance_id
        }
        self._controller_button_accept_at = {
            key: value
            for key, value in self._controller_button_accept_at.items()
            if key[0] != instance_id
        }
        self._raw_axis_state = {
            key: value
            for key, value in self._raw_axis_state.items()
            if key[0] != instance_id
        }
        self._raw_axis_pressed = {
            key: value
            for key, value in self._raw_axis_pressed.items()
            if key[0] != instance_id
        }
        self._raw_button_state = {
            key: value
            for key, value in self._raw_button_state.items()
            if key[0] != instance_id
        }
        self._raw_button_accept_at = {
            key: value
            for key, value in self._raw_button_accept_at.items()
            if key[0] != instance_id
        }
        self._raw_hat_state = {
            key: value
            for key, value in self._raw_hat_state.items()
            if key[0] != instance_id
        }
        self._raw_hat_accept_at = {
            key: value
            for key, value in self._raw_hat_accept_at.items()
            if key[0] != instance_id
        }
        self._input_debug("controller_closed", instance_id=int(instance_id), source=source, had_device=bool(device is not None))
        quit_fn = getattr(device, "quit", None)
        if callable(quit_fn):
            try:
                quit_fn()
            except Exception:
                pass
        return True

    def _install_window_icon(self):
        icon_path = _resource_path("assets", "icons", "bakerrrr.png")
        try:
            if not icon_path.exists():
                return False
            icon = self.pygame.image.load(str(icon_path))
            self.pygame.display.set_icon(icon)
            self._window_icon_path = str(icon_path)
            return True
        except Exception:
            self._window_icon_path = None
            return False

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
            content_pixel_w = max(self.cell_px * 4, (panel_w - 4) * self.cell_px)
            subtitle_lines = self._wrap_text_to_pixel_width(subtitle, subtitle_font, content_pixel_w, max_lines=2)
            prompt_lines = self._wrap_text_to_pixel_width(prompt, self._ui_font, content_pixel_w, max_lines=2)
            detail_lines = self._wrap_text_to_pixel_width(detail, self._ui_font, content_pixel_w, max_lines=3)
            title_rows = max(1, (title_font.get_height() + self.cell_px - 1) // self.cell_px) if banner else 0
            subtitle_line_rows = max(1, (max(self.cell_px, subtitle_font.get_height()) + self.cell_px - 1) // self.cell_px)
            subtitle_rows = len(subtitle_lines) * subtitle_line_rows
            header_rows = title_rows + subtitle_rows
            status_reserve = 2 if status_callback else 0
            required_panel_h = 7 + header_rows + len(prompt_lines) + len(detail_lines) + status_reserve + (1 if header_rows else 0)
            panel_h = min(max(16, required_panel_h), self.height_cells)
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

            text_px = panel_px + (self.cell_px * 2)
            text_py = panel_py + self.cell_px
            if banner:
                banner_surface = title_font.render(banner, True, self._color_value("objective"))
                self.surface.blit(banner_surface, (text_px, text_py))
            if subtitle:
                subtitle_y = text_py + max(self.cell_px, title_font.get_height())
                for idx, line in enumerate(subtitle_lines):
                    subtitle_surface = subtitle_font.render(line, True, self._color_value("default"))
                    self.surface.blit(subtitle_surface, (text_px, subtitle_y + (idx * max(self.cell_px, subtitle_font.get_height()))))

            prompt_y = panel_y + 1 + header_rows + (1 if header_rows else 0)
            current_y = prompt_y
            for line in prompt_lines:
                self.draw_text(panel_x + 2, current_y, line, color="objective")
                current_y += 1
            for line in detail_lines:
                self.draw_text(panel_x + 2, current_y, line, color="default")
                current_y += 1

            field_y = current_y + 1
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
            if cursor_visible and len(field_text) < max(1, int(max_length)):
                field_text += "_"
            field_text = self._fit_text_to_pixel_width(field_text, self._ui_font, max(0, content_pixel_w - 4))
            self.draw_text(panel_x + 2, field_y, field_text, color="player")

            status_rows = _status_lines(text)
            for idx, row in enumerate(status_rows[:2]):
                status_text = self._fit_text_to_pixel_width(row["text"], self._ui_font, content_pixel_w)
                self.draw_text(panel_x + 2, field_y + 2 + idx, status_text, color=row.get("color") or "scout")

            footer = "Enter confirm  Esc cancel"
            footer = self._fit_text_to_pixel_width(footer, self._ui_font, content_pixel_w)
            self.draw_text(panel_x + 2, panel_y + panel_h - 2, footer, color="scout")
            if error_text:
                error_text_row = self._fit_text_to_pixel_width(error_text, self._ui_font, content_pixel_w)
                self.draw_text(panel_x + 2, panel_y + panel_h - 3, error_text_row, color="feature_breach")

            self.refresh()

            for event in self.pygame.event.get():
                if self._is_close_event(event):
                    self._mark_close_requested()
                    return None
                mapped = self._map_event_input(event)
                key = self._input_to_legacy_key(mapped)

                if key == 10:
                    normalized = normalize(text)
                    if normalized:
                        return normalized
                    error_text = invalid_message
                    continue

                if key == 27:
                    return None

                if key == 127:
                    text = text[:-1]
                    error_text = ""
                    continue

                if key == 9:
                    continue

                if event.type != self.pygame.KEYDOWN:
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

    def prompt_choice(
        self,
        prompt,
        options,
        *,
        detail="",
        title=None,
        banner="",
        subtitle="",
        initial_index=0,
    ):
        if title:
            self.pygame.display.set_caption(str(title))

        rows = [
            {
                "value": str(row.get("value", "")).strip(),
                "label": str(row.get("label", row.get("value", ""))).strip(),
                "description": str(row.get("description", "")).strip(),
            }
            for row in tuple(options or ())
            if isinstance(row, dict) and str(row.get("value", "")).strip()
        ]
        if not rows:
            return None

        selected = max(0, min(int(initial_index), len(rows) - 1))
        clock = self.pygame.time.Clock()
        title_font = self.pygame.font.SysFont("DejaVu Sans Mono", max(18, int(self.cell_px * 1.7)), bold=True)
        subtitle_font = self.pygame.font.SysFont("DejaVu Sans Mono", max(12, int(self.cell_px * 0.85)))

        prompt = str(prompt or "")
        detail = str(detail or "")
        banner = str(banner or "")
        subtitle = str(subtitle or "")

        while True:
            self.surface.fill((12, 16, 22))
            stripe_color = (18, 24, 31)
            for row_y in range(0, self.height_cells * self.cell_px, self.cell_px * 2):
                self.surface.fill(stripe_color, (0, row_y, self.width_cells * self.cell_px, self.cell_px))

            panel_w = min(max(44, self.width_cells - 10), self.width_cells)
            content_pixel_w = max(self.cell_px * 4, (panel_w - 4) * self.cell_px)
            subtitle_lines = self._wrap_text_to_pixel_width(subtitle, subtitle_font, content_pixel_w, max_lines=2)
            prompt_lines = self._wrap_text_to_pixel_width(prompt, self._ui_font, content_pixel_w, max_lines=2)
            detail_lines = self._wrap_text_to_pixel_width(detail, self._ui_font, content_pixel_w, max_lines=3)
            title_rows = max(1, (title_font.get_height() + self.cell_px - 1) // self.cell_px) if banner else 0
            subtitle_line_rows = max(1, (max(self.cell_px, subtitle_font.get_height()) + self.cell_px - 1) // self.cell_px)
            subtitle_rows = len(subtitle_lines) * subtitle_line_rows
            header_rows = title_rows + subtitle_rows
            topic_rows = len(prompt_lines) + len(detail_lines)
            required_panel_h = 5 + header_rows + topic_rows + len(rows) + (1 if header_rows else 0) + (1 if topic_rows else 0)
            panel_h = min(max(18, required_panel_h), self.height_cells)
            panel_x = max(0, (self.width_cells - panel_w) // 2)
            panel_y = max(0, (self.height_cells - panel_h) // 2)
            panel_px = panel_x * self.cell_px
            panel_py = panel_y * self.cell_px
            panel_pw = panel_w * self.cell_px
            panel_ph = panel_h * self.cell_px

            outer_rect = self.pygame.Rect(panel_px, panel_py, panel_pw, panel_ph)
            inner_rect = self.pygame.Rect(
                panel_px + self.cell_px,
                panel_py + self.cell_px,
                max(0, panel_pw - (self.cell_px * 2)),
                max(0, panel_ph - (self.cell_px * 2)),
            )
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

            text_px = panel_px + (self.cell_px * 2)
            text_py = panel_py + self.cell_px
            if banner:
                banner_surface = title_font.render(banner, True, self._color_value("objective"))
                self.surface.blit(banner_surface, (text_px, text_py))
            if subtitle:
                subtitle_y = text_py + max(self.cell_px, title_font.get_height())
                for idx, line in enumerate(subtitle_lines):
                    subtitle_surface = subtitle_font.render(line, True, self._color_value("default"))
                    self.surface.blit(subtitle_surface, (text_px, subtitle_y + (idx * max(self.cell_px, subtitle_font.get_height()))))

            prompt_y = panel_y + 1 + header_rows + (1 if header_rows else 0)
            current_y = prompt_y
            for line in prompt_lines:
                self.draw_text(panel_x + 2, current_y, line, color="objective")
                current_y += 1
            for line in detail_lines:
                self.draw_text(panel_x + 2, current_y, line, color="default")
                current_y += 1

            option_y = current_y + (1 if current_y > prompt_y else 0)
            for idx, row in enumerate(rows):
                label = f"{idx + 1}. {row['label']}"
                description = row["description"]
                prefix = ">" if idx == selected else " "
                line = f"{prefix} {label}"
                if description:
                    line = f"{line} - {description}"
                color = "player" if idx == selected else "human"
                line = self._fit_text_to_pixel_width(line, self._ui_font, content_pixel_w)
                self.draw_text(panel_x + 2, option_y + idx, line, color=color)

            footer = "Arrows move  1-3 choose  Enter confirm  Esc cancel"
            footer = self._fit_text_to_pixel_width(footer, self._ui_font, content_pixel_w)
            self.draw_text(panel_x + 2, panel_y + panel_h - 2, footer, color="scout")
            self.refresh()

            for event in self.pygame.event.get():
                if self._is_close_event(event):
                    self._mark_close_requested()
                    return None
                mapped = self._map_event_input(event)
                key = self._input_to_legacy_key(mapped)
                if key is None:
                    continue

                if key in (10, 13):
                    return rows[selected]["value"]
                if key == 27:
                    return None
                if key in (KEY_UP, KEY_LEFT):
                    selected = (selected - 1) % len(rows)
                    continue
                if key in (KEY_DOWN, KEY_RIGHT):
                    selected = (selected + 1) % len(rows)
                    continue
                if key in (ord("1"), ord("2"), ord("3")):
                    idx = key - ord("1")
                    if 0 <= idx < len(rows):
                        return rows[idx]["value"]

            clock.tick(30)

    def _load_render_semantics(self, path=None):
        """Load the shared authored render semantics used for lookup and layering."""
        catalog_path = str(path or _DEFAULT_RENDER_SEMANTICS_PATH)
        try:
            self._semantic_catalog = get_runtime_semantic_catalog(catalog_path)
        except Exception:
            self._semantic_catalog = get_runtime_semantic_catalog()

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
        } or key.startswith("cat_") or key.startswith("clothing_"):
            return ["entities"] + [name for name in default_order if name != "entities"]
        if key.startswith("item_"):
            return ["items"] + [name for name in default_order if name != "items"]
        if key.startswith("vehicle_"):
            return ["vehicles"] + [name for name in default_order if name != "vehicles"]
        if key.startswith("feature_"):
            return ["features"] + [name for name in default_order if name != "features"]
        if (
            key.startswith("terrain_")
            or key.startswith("floor_")
            or key in {"building_edge", "building_fill"}
            or key.startswith("building_edge_")
            or key.startswith("building_fill_")
        ):
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

    def _surface_lit_rgb(self, rgb):
        normalized = self._active_surface_light_tint
        if normalized is None:
            return rgb
        try:
            (red, green, blue), strength, _pulse = normalized
            strength = max(0.0, min(1.0, float(strength)))
        except (TypeError, ValueError):
            return rgb
        if strength <= 0.02:
            return rgb

        tint = (int(red), int(green), int(blue))
        intensity = max(0.0, min(0.72, 0.12 + (strength * 0.66)))
        lit = []
        for channel, tint_channel in zip(rgb, tint):
            tint_norm = max(0.0, min(1.0, tint_channel / 255.0))
            # Stylized multiplicative response: preserve the source color, but let
            # colored light cool/warm the surface enough to read at tile scale.
            multiplied = channel * (0.58 + (tint_norm * 0.82))
            lifted = multiplied + (tint_norm * 34.0 * intensity)
            value = (channel * (1.0 - intensity)) + (lifted * intensity)
            lit.append(max(0, min(255, int(round(value)))))
        return tuple(lit)

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
        frame = self._surface_lit_rgb(frame)
        return frame

    def _alpha_color(self, color, alpha):
        rgb = self._color_value(color)
        return (int(rgb[0]), int(rgb[1]), int(rgb[2]), max(0, min(255, int(alpha))))

    def _lightened_rgba(self, rgb, alpha=255, *, amount=0.18):
        amount = max(0.0, min(1.0, float(amount)))
        return (
            min(255, int(rgb[0] + ((255 - rgb[0]) * amount))),
            min(255, int(rgb[1] + ((255 - rgb[1]) * amount))),
            min(255, int(rgb[2] + ((255 - rgb[2]) * amount))),
            max(0, min(255, int(alpha))),
        )

    def _darkened_rgba(self, rgb, alpha=255, *, amount=0.42):
        amount = max(0.0, min(1.0, float(amount)))
        return (
            max(0, int(rgb[0] * (1.0 - amount))),
            max(0, int(rgb[1] * (1.0 - amount))),
            max(0, int(rgb[2] * (1.0 - amount))),
            max(0, min(255, int(alpha))),
        )

    def _local_tile_rect(self, *, inset=None, min_size=4):
        px_inset = max(0, int(self.cell_px // 8 if inset is None else inset))
        size = max(int(min_size), self.cell_px - (px_inset * 2))
        return self.pygame.Rect(px_inset, px_inset, size, size)

    def _draw_legibility_backing(self, overlay, rect=None, *, color="actor_outline", alpha=84, radius=None):
        backing_rect = rect.copy() if rect is not None else self._local_tile_rect(inset=max(1, self.cell_px // 10))
        backing_rect.clamp_ip(self.pygame.Rect(0, 0, self.cell_px, self.cell_px))
        border_radius = max(1, self.cell_px // 8) if radius is None else int(radius)
        self.pygame.draw.rect(
            overlay,
            self._alpha_color(color, alpha),
            backing_rect.move(1, 1),
            border_radius=border_radius,
        )

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
        color_key = str(color or "").strip().lower()
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

        material_line_w = max(1, self.cell_px // 26)
        light = (
            min(255, int(frame[0] * 1.16)),
            min(255, int(frame[1] * 1.16)),
            min(255, int(frame[2] * 1.16)),
            108,
        )
        dark = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 112)
        if "brick" in color_key:
            mortar = (
                min(255, int(frame[0] * 1.22)),
                min(255, int(frame[1] * 1.18)),
                min(255, int(frame[2] * 1.12)),
                126,
            )
            course_step = max(4, self.cell_px // 5)
            for course_idx, py in enumerate(range(rect.top + course_step, rect.bottom, course_step)):
                self.pygame.draw.line(overlay, mortar, (rect.left + 1, py), (rect.right - 2, py), material_line_w)
                joint_step = max(5, self.cell_px // 4)
                joint_offset = 0 if course_idx % 2 == 0 else joint_step // 2
                for px in range(rect.left + joint_offset + joint_step, rect.right - 2, joint_step):
                    self.pygame.draw.line(
                        overlay,
                        (mortar[0], mortar[1], mortar[2], 88),
                        (px, max(rect.top + 2, py - course_step + 2)),
                        (px, py - 1),
                        material_line_w,
                    )
        elif "plaster" in color_key:
            self.pygame.draw.rect(overlay, light, rect.inflate(-max(2, self.cell_px // 8), -max(2, self.cell_px // 8)), max(1, self.cell_px // 30))
            self.pygame.draw.line(
                overlay,
                (dark[0], dark[1], dark[2], 54),
                (rect.left + max(2, self.cell_px // 5), rect.bottom - max(3, self.cell_px // 5)),
                (rect.right - max(3, self.cell_px // 4), rect.bottom - max(2, self.cell_px // 4)),
                material_line_w,
            )
        elif "dark" in color_key:
            heavy_w = max(1, self.cell_px // 16)
            vent_w = max(4, self.cell_px // 3)
            vent_h = max(2, self.cell_px // 9)
            vent = self.pygame.Rect(rect.centerx - vent_w // 2, rect.top + max(2, self.cell_px // 5), vent_w, vent_h)
            self.pygame.draw.line(overlay, dark, (rect.left + 1, rect.centery), (rect.right - 2, rect.centery), heavy_w)
            self.pygame.draw.rect(overlay, (light[0], light[1], light[2], 78), vent, max(1, material_line_w))
            for py in (vent.top + 1, vent.centery, vent.bottom - 1):
                self.pygame.draw.line(overlay, dark, (vent.left + 1, py), (vent.right - 2, py), material_line_w)
        elif "painted" in color_key:
            band_w = max(2, self.cell_px // 7)
            band_x = rect.left + max(2, self.cell_px // 5)
            self.pygame.draw.rect(
                overlay,
                (light[0], light[1], light[2], 64),
                self.pygame.Rect(band_x, rect.top + 1, band_w, max(1, rect.h - 2)),
            )
            self.pygame.draw.line(overlay, dark, (rect.left + 1, rect.bottom - max(2, self.cell_px // 5)), (rect.right - 2, rect.bottom - max(2, self.cell_px // 5)), material_line_w)
        elif "gray_" in color_key or color_key in {"building_edge", "building_fill"}:
            tone_x = rect.right - max(3, self.cell_px // 5)
            tone_y = rect.top + max(2, self.cell_px // 5)
            self.pygame.draw.line(overlay, light, (rect.left + max(2, self.cell_px // 5), tone_y), (tone_x, tone_y), material_line_w)
            self.pygame.draw.circle(overlay, dark, (tone_x, rect.bottom - max(3, self.cell_px // 5)), max(1, self.cell_px // 28))

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

        if color_key == "building_roof_residential":
            tile_line = (
                min(255, int(frame[0] * 1.18)),
                min(255, int(frame[1] * 1.06)),
                min(255, int(frame[2] * 0.96)),
                132,
            )
            for py in range(rect.top + max(3, self.cell_px // 5), rect.bottom - 1, max(4, self.cell_px // 5)):
                self.pygame.draw.line(overlay, tile_line, (rect.left + 2, py), (rect.right - 3, py), seam_w)
            chimney = self.pygame.Rect(
                rect.right - max(5, self.cell_px // 4),
                rect.top + max(2, self.cell_px // 6),
                max(3, self.cell_px // 7),
                max(4, self.cell_px // 5),
            )
            self.pygame.draw.rect(overlay, (shadow[0], shadow[1], shadow[2], 150), chimney)
            self.pygame.draw.rect(overlay, tile_line, chimney, max(1, seam_w))
        elif color_key == "building_roof_storefront":
            awning_colors = (
                (244, 214, 132, 156),
                (196, 82, 72, 148),
            )
            stripe_w = max(3, self.cell_px // 6)
            awning_h = max(3, self.cell_px // 6)
            awning_y = rect.bottom - awning_h - max(1, self.cell_px // 18)
            stripe_idx = 0
            for px in range(rect.left + max(1, seam_w), rect.right - 1, stripe_w):
                stripe_rect = self.pygame.Rect(px, awning_y, min(stripe_w, rect.right - px - 1), awning_h)
                self.pygame.draw.rect(overlay, awning_colors[stripe_idx % 2], stripe_rect)
                stripe_idx += 1
        elif color_key == "building_roof_industrial":
            pipe_color = (shadow[0], shadow[1], shadow[2], 160)
            for px in (rect.left + max(3, self.cell_px // 5), rect.right - max(4, self.cell_px // 4)):
                self.pygame.draw.line(overlay, pipe_color, (px, rect.top + 2), (px, rect.bottom - 3), max(1, self.cell_px // 20))
            cap = self.pygame.Rect(rect.left + max(3, self.cell_px // 6), rect.bottom - max(5, self.cell_px // 4), max(5, self.cell_px // 4), max(3, self.cell_px // 7))
            self.pygame.draw.rect(overlay, (parapet[0], parapet[1], parapet[2], 130), cap)
            self.pygame.draw.rect(overlay, pipe_color, cap, max(1, seam_w))
        elif color_key == "building_roof_corporate":
            glass = (166, 220, 245, 128)
            pane_w = max(1, self.cell_px // 18)
            self.pygame.draw.line(overlay, glass, (rect.left + max(3, self.cell_px // 5), rect.top + 2), (rect.left + max(3, self.cell_px // 5), rect.bottom - 3), pane_w)
            self.pygame.draw.line(overlay, glass, (rect.right - max(3, self.cell_px // 5), rect.top + 2), (rect.right - max(3, self.cell_px // 5), rect.bottom - 3), pane_w)
            self.pygame.draw.line(overlay, (255, 255, 255, 98), (rect.left + 3, rect.top + 3), (rect.right - 4, rect.top + max(4, self.cell_px // 4)), pane_w)
        elif color_key == "building_roof_civic":
            civic_glow = (160, 236, 226, 132)
            self.pygame.draw.arc(
                overlay,
                civic_glow,
                rect.inflate(-max(3, self.cell_px // 4), -max(3, self.cell_px // 4)),
                3.14,
                6.28,
                max(1, self.cell_px // 18),
            )
            self.pygame.draw.line(overlay, civic_glow, (rect.left + 3, rect.centery), (rect.right - 4, rect.centery), max(1, self.cell_px // 22))
        elif color_key == "building_roof_secure":
            secure_band = (170, 190, 92, 146)
            band_y = rect.top + max(3, self.cell_px // 4)
            self.pygame.draw.line(overlay, secure_band, (rect.left + 3, band_y), (rect.right - 4, band_y), max(2, self.cell_px // 12))
            shield = [
                (rect.centerx, rect.top + max(3, self.cell_px // 5)),
                (rect.centerx + max(3, self.cell_px // 6), rect.centery),
                (rect.centerx, rect.bottom - max(3, self.cell_px // 5)),
                (rect.centerx - max(3, self.cell_px // 6), rect.centery),
            ]
            self.pygame.draw.polygon(overlay, (shadow[0], shadow[1], shadow[2], 126), shield)
            self.pygame.draw.polygon(overlay, secure_band, shield, max(1, seam_w))

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

    def _draw_flora_overlay(self, x, y, color=None, attrs=0, *, kind="flower"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)
        px = self.cell_px
        stem = (70, 148, 86, 172)
        soft = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            192,
        )
        deep = (
            max(0, int(frame[0] * 0.58)),
            max(0, int(frame[1] * 0.64)),
            max(0, int(frame[2] * 0.58)),
            116,
        )
        kind = str(kind or "flower").strip().lower()
        if kind == "seedling":
            stem_w = max(1, px // 20)
            base_y = px - max(2, px // 6)
            self.pygame.draw.line(overlay, stem, (px // 2, base_y), (px // 2, max(4, px // 2)), stem_w)
            leaf_r = max(2, px // 10)
            self.pygame.draw.ellipse(overlay, soft, (px // 2 - leaf_r * 2, px // 2 - leaf_r // 2, leaf_r * 2, leaf_r))
            self.pygame.draw.ellipse(overlay, soft, (px // 2, px // 2 - leaf_r // 2, leaf_r * 2, leaf_r))
            self.pygame.draw.arc(overlay, deep, (px // 3, px // 2, px // 3, px // 3), 3.1, 6.0, max(1, px // 24))
        elif kind == "young":
            stem_w = max(1, px // 18)
            base_y = px - 2
            for cx, top_y, lean in (
                (px // 3, max(4, px // 3), -max(1, px // 12)),
                (px // 2, max(3, px // 4), 0),
                (px - px // 3, max(4, px // 3), max(1, px // 12)),
            ):
                self.pygame.draw.line(overlay, (frame[0], frame[1], frame[2], 174), (px // 2, base_y), (cx + lean, top_y), stem_w)
                self.pygame.draw.circle(overlay, soft, (cx + lean, top_y), max(1, px // 16))
        elif kind == "withered":
            stem_w = max(1, px // 20)
            base_y = px - 2
            points = ((px // 3, base_y), (px // 2, px // 2), (px - px // 4, max(4, px // 3)))
            self.pygame.draw.lines(overlay, (frame[0], frame[1], frame[2], 150), False, points, stem_w)
            self.pygame.draw.ellipse(overlay, (frame[0], frame[1], frame[2], 78), (px // 4, px - max(5, px // 4), px // 2, max(3, px // 6)))
            self.pygame.draw.arc(overlay, deep, (px // 3, px // 3, px // 2, px // 2), 0.4, 2.8, max(1, px // 24))
        elif kind in {"flower_bud", "flower_closed"}:
            stem_w = max(1, px // 18)
            center_x = px // 2
            top_y = max(3, px // 3)
            self.pygame.draw.line(overlay, stem, (center_x, px - 2), (center_x, top_y + max(2, px // 8)), stem_w)
            bud_w = max(4, px // 4)
            bud_h = max(5, px // 3)
            bud_rect = self.pygame.Rect(center_x - bud_w // 2, top_y, bud_w, bud_h)
            self.pygame.draw.ellipse(overlay, (frame[0], frame[1], frame[2], 166), bud_rect)
            self.pygame.draw.arc(overlay, deep, bud_rect.inflate(-1, -1), 1.1, 5.1, max(1, px // 22))
            cap_y = top_y + bud_h - max(1, px // 8)
            self.pygame.draw.line(overlay, stem, (center_x - bud_w // 3, cap_y), (center_x + bud_w // 3, cap_y), stem_w)
        elif kind in {"flower", "flower_cluster", "flower_night"}:
            stem_w = max(1, px // 18)
            centers = (
                (px // 2, max(3, px // 3)),
                (max(3, px // 3), max(4, px // 2)),
                (px - max(4, px // 3), max(4, px // 2)),
            ) if kind == "flower_cluster" else ((px // 2, max(3, px // 3)),)
            self.pygame.draw.line(overlay, stem, (px // 2, px - 2), (px // 2, max(3, px // 3)), stem_w)
            for cx, cy in centers:
                r = max(2, px // 8 if kind == "flower_night" else px // 9)
                petal_r = max(1, px // 15 if kind == "flower_night" else px // 16)
                petals = ((0, -r), (r, 0), (0, r), (-r, 0))
                if kind == "flower_night":
                    petals = petals + ((r - 1, -r + 1), (-r + 1, -r + 1))
                    self.pygame.draw.circle(overlay, (soft[0], soft[1], soft[2], 42), (cx, cy), max(3, px // 4))
                for dx, dy in petals:
                    self.pygame.draw.circle(overlay, (frame[0], frame[1], frame[2], 186), (cx + dx, cy + dy), petal_r)
                self.pygame.draw.circle(overlay, soft, (cx, cy), max(1, px // 18))
            if kind == "flower_cluster":
                self.pygame.draw.line(overlay, stem, (px // 2, px - 2), (max(3, px // 3), max(4, px // 2)), stem_w)
                self.pygame.draw.line(overlay, stem, (px // 2, px - 2), (px - max(4, px // 3), max(4, px // 2)), stem_w)
        elif kind in {"moss", "lichen"}:
            base_h = max(3, px // 4)
            self.pygame.draw.ellipse(overlay, (frame[0], frame[1], frame[2], 100), (2, px - base_h - 1, px - 4, base_h + 1))
            dots = (
                (px // 4, px - max(4, px // 5), max(1, px // 15)),
                (px // 2, px - max(5, px // 4), max(1, px // 13)),
                (px - px // 4, px - max(4, px // 5), max(1, px // 16)),
                (px // 3, px - max(7, px // 3), max(1, px // 18)),
            )
            for cx, cy, r in dots:
                self.pygame.draw.circle(overlay, (frame[0], frame[1], frame[2], 158), (cx, cy), r)
            self.pygame.draw.arc(overlay, (soft[0], soft[1], soft[2], 98), (3, px // 3, px - 6, px // 2), 2.8, 6.0, max(1, px // 22))
        elif kind == "vine":
            width = max(1, px // 18)
            points = (
                (max(2, px // 7), px - 2),
                (px // 3, px - max(6, px // 3)),
                (px - max(5, px // 3), px // 2),
                (px - max(3, px // 6), max(3, px // 5)),
            )
            self.pygame.draw.lines(overlay, (frame[0], frame[1], frame[2], 180), False, points, width)
            leaf_r = max(1, px // 15)
            for cx, cy, side in ((px // 3, px - max(6, px // 3), -1), (px - max(5, px // 3), px // 2, 1)):
                leaf_rect = self.pygame.Rect(cx + side * leaf_r, cy - leaf_r, leaf_r * 2, leaf_r + max(1, px // 18))
                self.pygame.draw.ellipse(overlay, soft, leaf_rect)
        elif kind in {"grass", "reed"}:
            stalk_w = max(1, px // 18)
            base_y = px - 2
            specs = (
                (px // 4, max(3, px // 3)),
                (px // 2, max(2, px // 5)),
                (px - px // 4, max(4, px // 3)),
            )
            for cx, top_y in specs:
                lean = max(1, px // 12)
                self.pygame.draw.line(overlay, (frame[0], frame[1], frame[2], 172), (cx, base_y), (cx + lean, top_y), stalk_w)
                if kind == "reed":
                    self.pygame.draw.ellipse(overlay, soft, (cx + lean - max(1, px // 20), top_y - max(2, px // 9), max(2, px // 10), max(4, px // 5)))
        else:
            mound = self.pygame.Rect(max(2, px // 7), px // 3, px - max(4, px // 4), px - max(4, px // 3))
            self.pygame.draw.ellipse(overlay, (frame[0], frame[1], frame[2], 132), mound)
            self.pygame.draw.arc(overlay, deep, mound.inflate(-2, -2), 3.35, 6.1, max(1, px // 18))
            for cx, cy in ((px // 3, px // 2), (px // 2, px // 3), (px - px // 3, px // 2)):
                self.pygame.draw.circle(overlay, soft, (cx, cy), max(1, px // 18))
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

    def _draw_fire_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.12)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        ember = (255, min(255, frame[1] + 60), min(255, frame[2] + 12), 186)
        flame = (frame[0], frame[1], frame[2], 194)
        smoke = (72, 54, 46, 108)
        glow = (255, min(255, frame[1] + 82), min(255, frame[2] + 28), 82)
        base_y = self.cell_px - max(2, self.cell_px // 7)
        mid_x = self.cell_px // 2
        lobe = max(3, self.cell_px // 5)
        core = [
            (mid_x, max(1, self.cell_px // 10)),
            (self.cell_px - max(2, self.cell_px // 5), max(2, self.cell_px // 3)),
            (self.cell_px - max(3, self.cell_px // 8), base_y),
            (mid_x, self.cell_px - max(2, self.cell_px // 8)),
            (max(2, self.cell_px // 4), base_y),
            (max(2, self.cell_px // 6), max(2, self.cell_px // 2)),
        ]
        inner = [
            (mid_x, max(2, self.cell_px // 5)),
            (self.cell_px - max(3, self.cell_px // 7), max(3, self.cell_px // 3)),
            (self.cell_px - max(4, self.cell_px // 9), base_y - max(1, self.cell_px // 10)),
            (mid_x, self.cell_px - max(3, self.cell_px // 8)),
            (max(3, self.cell_px // 3), base_y - max(1, self.cell_px // 9)),
            (max(2, self.cell_px // 4), max(2, self.cell_px // 2)),
        ]

        self.pygame.draw.circle(overlay, glow, (mid_x, base_y - lobe), max(3, self.cell_px // 3))
        self.pygame.draw.polygon(overlay, smoke, [(p[0], min(self.cell_px - 1, p[1] + max(1, self.cell_px // 10))) for p in core])
        self.pygame.draw.polygon(overlay, flame, core)
        self.pygame.draw.polygon(overlay, ember, inner)
        for px, py, r in (
            (mid_x - max(1, self.cell_px // 8), base_y - max(2, self.cell_px // 5), max(1, self.cell_px // 20)),
            (mid_x + max(1, self.cell_px // 10), base_y - max(3, self.cell_px // 7), max(1, self.cell_px // 18)),
            (mid_x, base_y - max(4, self.cell_px // 7), max(1, self.cell_px // 22)),
        ):
            self.pygame.draw.circle(overlay, (255, 242, 176, 210), (px, py), r)
        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_smoke_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.02)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        haze = (frame[0], frame[1], frame[2], 74)
        plume = (
            min(255, int(frame[0] * 1.08)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            112,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 64)
        self.pygame.draw.rect(overlay, haze, (0, 0, self.cell_px, self.cell_px))
        clouds = (
            (self.cell_px // 3, self.cell_px // 2, max(2, self.cell_px // 5)),
            (self.cell_px // 2, max(2, self.cell_px // 3), max(2, self.cell_px // 4)),
            (self.cell_px - max(4, self.cell_px // 4), self.cell_px // 2, max(2, self.cell_px // 5)),
        )
        for px, py, radius in clouds:
            self.pygame.draw.circle(overlay, plume, (px, py), radius)
            self.pygame.draw.circle(overlay, shadow, (px, min(self.cell_px - 1, py + max(1, self.cell_px // 18))), max(1, radius - 1))
        self.pygame.draw.line(
            overlay,
            plume,
            (max(2, self.cell_px // 5), self.cell_px - max(3, self.cell_px // 8)),
            (self.cell_px - max(3, self.cell_px // 5), self.cell_px - max(3, self.cell_px // 8)),
            max(1, self.cell_px // 20),
        )
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
            min(255, int(frame[0] * 1.16) + 8),
            min(255, int(frame[1] * 1.16) + 8),
            min(255, int(frame[2] * 1.16) + 8),
            210,
        )
        dark = self._darkened_rgba(frame, 166, amount=0.55)
        outline = self._alpha_color("item_outline", 172)
        highlight = self._alpha_color("item_highlight", 156)
        metal = self._alpha_color("item_metal", 184)
        glass = self._alpha_color("item_glass", 148)
        paper = self._alpha_color("item_paper", 142)
        cloth = self._alpha_color("item_cloth", 132)
        chemical = self._alpha_color("item_chemical", 150)
        backing_rect = self._local_tile_rect(inset=max(2, self.cell_px // 7), min_size=6)
        self._draw_legibility_backing(overlay, backing_rect, color="item_outline", alpha=72)

        if kind == "ground":
            points = [
                (mid_x, max(2, self.cell_px // 5)),
                (self.cell_px - max(3, self.cell_px // 5), mid_y),
                (mid_x, self.cell_px - max(3, self.cell_px // 5)),
                (max(2, self.cell_px // 5), mid_y),
            ]
            self.pygame.draw.polygon(overlay, outline, [(px + 1, py + 1) for px, py in points], stroke_w + 1)
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
        elif kind == "medical":
            bar_w = max(2, self.cell_px // 5)
            arm = max(4, self.cell_px // 3)
            vertical = (mid_x - (bar_w // 2), max(2, mid_y - arm // 2), bar_w, arm)
            horizontal = (max(2, mid_x - arm // 2), mid_y - (bar_w // 2), arm, bar_w)
            self.pygame.draw.rect(overlay, outline, self.pygame.Rect(vertical).move(1, 1), border_radius=max(1, self.cell_px // 28))
            self.pygame.draw.rect(overlay, outline, self.pygame.Rect(horizontal).move(1, 1), border_radius=max(1, self.cell_px // 28))
            self.pygame.draw.rect(
                overlay,
                fill,
                vertical,
            )
            self.pygame.draw.rect(
                overlay,
                fill,
                horizontal,
            )
            self.pygame.draw.rect(
                overlay,
                stroke,
                vertical,
                stroke_w,
            )
            self.pygame.draw.rect(
                overlay,
                stroke,
                horizontal,
                stroke_w,
            )
            self.pygame.draw.circle(overlay, chemical, (mid_x, mid_y), max(2, stroke_w + 1))
        elif kind == "token":
            radius = max(3, self.cell_px // 4)
            self.pygame.draw.circle(overlay, outline, (mid_x + 1, mid_y + 1), radius)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), radius)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, metal, (mid_x, mid_y), max(1, radius // 2), max(1, stroke_w - 1))
            shine_y = mid_y - max(1, radius // 3)
            self.pygame.draw.arc(
                overlay,
                highlight,
                (mid_x - radius + 1, shine_y - max(2, radius // 2), max(2, radius * 2 - 2), max(3, radius)),
                3.4,
                5.7,
                max(1, stroke_w),
            )
        elif kind == "tool":
            handle_x0 = max(2, self.cell_px // 4)
            handle_y0 = self.cell_px - max(4, self.cell_px // 3)
            handle_x1 = self.cell_px - max(4, self.cell_px // 4)
            handle_y1 = max(3, self.cell_px // 3)
            self.pygame.draw.line(overlay, outline, (handle_x0 + 1, handle_y0 + 1), (handle_x1 + 1, handle_y1 + 1), max(3, stroke_w + 2))
            self.pygame.draw.line(overlay, metal, (handle_x0, handle_y0), (handle_x1, handle_y1), max(2, stroke_w + 1))
            jaw_r = max(2, self.cell_px // 7)
            self.pygame.draw.circle(overlay, metal, (handle_x1, handle_y1), jaw_r)
            self.pygame.draw.circle(overlay, outline, (handle_x1 + max(1, jaw_r // 2), handle_y1 - max(1, jaw_r // 2)), max(1, jaw_r - 1))
            self.pygame.draw.line(
                overlay,
                highlight,
                (handle_x0 + max(1, self.cell_px // 12), handle_y0 - max(1, self.cell_px // 12)),
                (handle_x1 - max(1, self.cell_px // 12), handle_y1 + max(1, self.cell_px // 12)),
                max(1, stroke_w),
            )
        elif kind == "weapon":
            self.pygame.draw.line(
                overlay,
                outline,
                (max(2, self.cell_px // 4) + 1, self.cell_px - max(3, self.cell_px // 4) + 1),
                (self.cell_px - max(2, self.cell_px // 4) + 1, max(2, self.cell_px // 4) + 1),
                max(3, stroke_w + 2),
            )
            self.pygame.draw.line(
                overlay,
                metal,
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
                max(2, stroke_w),
            )
            muzzle = self.pygame.Rect(
                self.cell_px - max(4, self.cell_px // 4),
                max(2, self.cell_px // 5),
                max(3, self.cell_px // 6),
                max(2, self.cell_px // 10),
            )
            self.pygame.draw.rect(overlay, metal, muzzle, border_radius=max(1, self.cell_px // 24))
        elif kind == "armor":
            points = [
                (mid_x, max(2, self.cell_px // 5)),
                (self.cell_px - max(3, self.cell_px // 4), max(3, self.cell_px // 3)),
                (self.cell_px - max(3, self.cell_px // 4), self.cell_px - max(4, self.cell_px // 4)),
                (mid_x, self.cell_px - max(2, self.cell_px // 5)),
                (max(2, self.cell_px // 4), self.cell_px - max(4, self.cell_px // 4)),
                (max(2, self.cell_px // 4), max(3, self.cell_px // 3)),
            ]
            self.pygame.draw.polygon(overlay, outline, [(px + 1, py + 1) for px, py in points], stroke_w + 1)
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.line(
                overlay,
                metal,
                (mid_x, max(3, self.cell_px // 4)),
                (mid_x, self.cell_px - max(3, self.cell_px // 4)),
                max(1, stroke_w),
            )
        elif kind == "food":
            plate = self.pygame.Rect(
                max(2, self.cell_px // 6),
                mid_y,
                self.cell_px - max(4, self.cell_px // 3),
                max(4, self.cell_px // 4),
            )
            bowl = self.pygame.Rect(
                max(3, self.cell_px // 4),
                mid_y - max(3, self.cell_px // 5),
                self.cell_px - max(6, self.cell_px // 2),
                max(5, self.cell_px // 3),
            )
            self.pygame.draw.ellipse(overlay, outline, plate.move(1, 1))
            self.pygame.draw.ellipse(overlay, paper, plate)
            self.pygame.draw.arc(overlay, stroke, bowl, 0.0, 3.14, max(2, stroke_w + 1))
            self.pygame.draw.rect(
                overlay,
                fill,
                (bowl.left, bowl.centery - max(1, self.cell_px // 14), bowl.w, max(3, bowl.h // 2)),
                border_radius=max(2, self.cell_px // 12),
            )
            self.pygame.draw.line(overlay, stroke, (bowl.left, bowl.centery), (bowl.right - 1, bowl.centery), max(1, stroke_w))
            steam = (245, 244, 224, 112)
            for px in (mid_x - max(3, self.cell_px // 6), mid_x, mid_x + max(3, self.cell_px // 6)):
                self.pygame.draw.line(
                    overlay,
                    steam,
                    (px, max(2, self.cell_px // 6)),
                    (px + max(1, self.cell_px // 16), mid_y - max(3, self.cell_px // 4)),
                    max(1, self.cell_px // 26),
                )
        elif kind == "drink":
            bottle_w = max(3, self.cell_px // 4)
            neck_w = max(2, self.cell_px // 8)
            neck_h = max(2, self.cell_px // 6)
            body_rect = self.pygame.Rect(
                mid_x - (bottle_w // 2),
                mid_y - max(2, self.cell_px // 6),
                bottle_w,
                max(6, self.cell_px // 3),
            )
            neck_rect = self.pygame.Rect(mid_x - (neck_w // 2), body_rect.top - neck_h + 1, neck_w, neck_h)
            cap_rect = self.pygame.Rect(neck_rect.left - 1, max(1, neck_rect.top - max(1, self.cell_px // 18)), neck_rect.w + 2, max(2, self.cell_px // 12))
            self.pygame.draw.rect(overlay, outline, body_rect.move(1, 1), border_radius=max(2, self.cell_px // 12))
            self.pygame.draw.rect(overlay, glass, body_rect, border_radius=max(2, self.cell_px // 12))
            self.pygame.draw.rect(overlay, fill, neck_rect)
            self.pygame.draw.rect(overlay, stroke, body_rect, stroke_w, border_radius=max(2, self.cell_px // 12))
            self.pygame.draw.rect(overlay, stroke, neck_rect, stroke_w)
            self.pygame.draw.rect(overlay, metal, cap_rect, border_radius=max(1, self.cell_px // 20))
            label = self.pygame.Rect(body_rect.left + 1, body_rect.centery - max(1, self.cell_px // 14), max(1, body_rect.w - 2), max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, paper, label, border_radius=max(1, self.cell_px // 24))
            self.pygame.draw.line(overlay, self._alpha_color("item_highlight", 132), (body_rect.left + 2, body_rect.top + 2), (body_rect.left + 2, body_rect.bottom - 3), max(1, self.cell_px // 28))
        elif kind == "access":
            ring_r = max(2, self.cell_px // 8)
            ring_x = max(3, self.cell_px // 3)
            self.pygame.draw.circle(overlay, outline, (ring_x + 1, mid_y + 1), ring_r + max(1, stroke_w // 2), stroke_w + 1)
            self.pygame.draw.circle(overlay, stroke, (ring_x, mid_y), ring_r, stroke_w)
            self.pygame.draw.line(
                overlay,
                metal,
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
            card = self.pygame.Rect(max(2, self.cell_px // 5), max(2, self.cell_px // 5), max(5, self.cell_px // 3), max(4, self.cell_px // 4))
            self.pygame.draw.rect(overlay, paper, card, border_radius=max(1, self.cell_px // 20))
            self.pygame.draw.line(overlay, highlight, (card.left + 1, card.centery), (card.right - 1, card.centery), max(1, stroke_w - 1))
        elif kind == "restricted":
            points = [
                (mid_x, max(2, self.cell_px // 6)),
                (self.cell_px - max(3, self.cell_px // 6), mid_y),
                (mid_x, self.cell_px - max(3, self.cell_px // 6)),
                (max(2, self.cell_px // 6), mid_y),
            ]
            self.pygame.draw.polygon(overlay, outline, [(px + 1, py + 1) for px, py in points], stroke_w + 1)
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.line(
                overlay,
                cloth,
                (mid_x - max(2, self.cell_px // 7), mid_y),
                (mid_x + max(2, self.cell_px // 7), mid_y),
                max(1, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                dark,
                (mid_x, max(3, self.cell_px // 4)),
                (mid_x, self.cell_px - max(3, self.cell_px // 4)),
                stroke_w,
            )
            self.pygame.draw.circle(overlay, dark, (mid_x, self.cell_px - max(3, self.cell_px // 5)), max(1, stroke_w))
        elif kind == "illegal":
            self.pygame.draw.circle(overlay, outline, (mid_x + 1, mid_y + 1), max(4, self.cell_px // 3), stroke_w + 1)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), max(4, self.cell_px // 3), max(1, stroke_w))
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
            self.pygame.draw.circle(overlay, chemical, (mid_x, mid_y), max(1, self.cell_px // 12))
        elif kind == "objective":
            outer_r = max(4, self.cell_px // 3)
            inner_r = max(2, self.cell_px // 6)
            points = []
            for idx in range(8):
                angle = (math.pi / 4.0) * idx - (math.pi / 2.0)
                radius = outer_r if idx % 2 == 0 else inner_r
                points.append((mid_x + int(math.cos(angle) * radius), mid_y + int(math.sin(angle) * radius)))
            self.pygame.draw.polygon(overlay, self._alpha_color("item_highlight", 86), [(px + 1, py + 1) for px, py in points])
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.circle(overlay, highlight, (mid_x, mid_y), max(1, self.cell_px // 10))
            self.pygame.draw.circle(overlay, outline, (mid_x, mid_y), max(1, self.cell_px // 18))

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_world_object_overlay(self, x, y, color=None, attrs=0, *, kind="personal_home", effects=None):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)
        effect_set = {
            str(effect).strip().lower()
            for effect in (effects or ())
            if str(effect).strip()
        }

        def _suffix(prefix, default=""):
            for effect in effect_set:
                if effect.startswith(prefix):
                    return effect.removeprefix(prefix)
            return default

        motif = _suffix("object_motif_", "none")
        condition = _suffix("object_condition_", "plain")
        rarity = _suffix("object_rarity_", "common")
        material = _suffix("object_material_", "")
        seed = 0
        try:
            seed = int(_suffix("object_seed_", "0"))
        except (TypeError, ValueError):
            seed = 0

        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 18)
        outline = self._alpha_color("item_outline", 180)
        highlight = self._alpha_color("item_highlight", 150)
        accent_key = "world_object_gold" if rarity in {"rare", "unique"} else "world_object_silver"
        accent = self._alpha_color(accent_key, 156)
        fill = (frame[0], frame[1], frame[2], 162)
        stroke = (
            min(255, int(frame[0] * 1.14) + 8),
            min(255, int(frame[1] * 1.14) + 8),
            min(255, int(frame[2] * 1.14) + 8),
            218,
        )
        dark = self._darkened_rgba(frame, 164, amount=0.58)
        glass = self._alpha_color("item_glass", 126)
        metal = self._alpha_color("item_metal", 150)
        paper = self._alpha_color("item_paper", 138)
        cloth = self._alpha_color("item_cloth", 128)
        plant = self._alpha_color("flora_leaf", 152)
        backing = self._local_tile_rect(inset=max(2, self.cell_px // 7), min_size=6)
        self._draw_legibility_backing(overlay, backing, color="item_outline", alpha=54)

        kind = str(kind or "personal_home").strip().lower()
        if kind == "plants_pots":
            pot = [
                (mid_x - max(4, self.cell_px // 4), mid_y),
                (mid_x + max(4, self.cell_px // 4), mid_y),
                (mid_x + max(3, self.cell_px // 5), self.cell_px - max(3, self.cell_px // 5)),
                (mid_x - max(3, self.cell_px // 5), self.cell_px - max(3, self.cell_px // 5)),
            ]
            self.pygame.draw.polygon(overlay, outline, [(px + 1, py + 1) for px, py in pot])
            self.pygame.draw.polygon(overlay, fill, pot)
            self.pygame.draw.polygon(overlay, stroke, pot, stroke_w)
            for idx, dx in enumerate((-1, 0, 1)):
                leaf_x = mid_x + dx * max(2, self.cell_px // 8)
                top = max(2, mid_y - max(4, self.cell_px // 3) + (idx % 2) * max(1, self.cell_px // 12))
                self.pygame.draw.ellipse(
                    overlay,
                    plant,
                    (leaf_x - max(2, self.cell_px // 12), top, max(4, self.cell_px // 6), max(6, self.cell_px // 4)),
                )
        elif kind == "tokens_charms":
            radius = max(4, self.cell_px // 4)
            self.pygame.draw.circle(overlay, outline, (mid_x + 1, mid_y + 1), radius)
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), radius)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, metal, (mid_x, mid_y), max(2, radius // 2), max(1, stroke_w - 1))
            self.pygame.draw.line(overlay, accent, (mid_x, mid_y - radius - 1), (mid_x, max(1, mid_y - radius // 2)), stroke_w)
        elif kind == "tools_parts":
            self.pygame.draw.line(
                overlay,
                outline,
                (max(3, self.cell_px // 5) + 1, self.cell_px - max(4, self.cell_px // 4) + 1),
                (self.cell_px - max(4, self.cell_px // 4) + 1, max(3, self.cell_px // 4) + 1),
                max(3, stroke_w + 2),
            )
            self.pygame.draw.line(
                overlay,
                metal,
                (max(3, self.cell_px // 5), self.cell_px - max(4, self.cell_px // 4)),
                (self.cell_px - max(4, self.cell_px // 4), max(3, self.cell_px // 4)),
                max(2, stroke_w + 1),
            )
            self.pygame.draw.circle(overlay, stroke, (self.cell_px - max(4, self.cell_px // 4), max(3, self.cell_px // 4)), max(2, self.cell_px // 8), stroke_w)
        elif kind == "textiles":
            fold = [
                (max(3, self.cell_px // 5), max(3, self.cell_px // 4)),
                (self.cell_px - max(4, self.cell_px // 5), max(4, self.cell_px // 5)),
                (self.cell_px - max(3, self.cell_px // 4), self.cell_px - max(4, self.cell_px // 4)),
                (mid_x, self.cell_px - max(3, self.cell_px // 5)),
                (max(3, self.cell_px // 4), self.cell_px - max(4, self.cell_px // 4)),
            ]
            self.pygame.draw.polygon(overlay, outline, [(px + 1, py + 1) for px, py in fold])
            self.pygame.draw.polygon(overlay, fill if material != "cloth" else cloth, fold)
            self.pygame.draw.polygon(overlay, stroke, fold, stroke_w)
            self.pygame.draw.line(overlay, highlight, (fold[0][0], mid_y), (fold[2][0], mid_y + max(1, self.cell_px // 10)), stroke_w)
        elif kind == "paper_books":
            book = self.pygame.Rect(max(3, self.cell_px // 4), max(3, self.cell_px // 5), max(7, self.cell_px // 2), max(8, self.cell_px // 2))
            self.pygame.draw.rect(overlay, outline, book.move(1, 1), border_radius=max(1, self.cell_px // 26))
            self.pygame.draw.rect(overlay, paper, book, border_radius=max(1, self.cell_px // 26))
            self.pygame.draw.rect(overlay, stroke, book, stroke_w, border_radius=max(1, self.cell_px // 26))
            self.pygame.draw.line(overlay, dark, (book.centerx, book.top + 2), (book.centerx, book.bottom - 2), max(1, stroke_w))
        elif kind == "containers":
            box = self.pygame.Rect(max(3, self.cell_px // 5), mid_y - max(2, self.cell_px // 8), self.cell_px - max(6, (self.cell_px // 5) * 2), max(7, self.cell_px // 3))
            self.pygame.draw.rect(overlay, outline, box.move(1, 1), border_radius=max(1, self.cell_px // 22))
            self.pygame.draw.rect(overlay, fill, box, border_radius=max(1, self.cell_px // 22))
            self.pygame.draw.rect(overlay, stroke, box, stroke_w, border_radius=max(1, self.cell_px // 22))
            self.pygame.draw.line(overlay, dark, (box.left + 2, box.centery), (box.right - 2, box.centery), stroke_w)
        elif kind == "light_ritual":
            base = self.pygame.Rect(mid_x - max(3, self.cell_px // 8), mid_y, max(6, self.cell_px // 4), max(7, self.cell_px // 3))
            self.pygame.draw.rect(overlay, outline, base.move(1, 1), border_radius=max(1, self.cell_px // 20))
            self.pygame.draw.rect(overlay, fill, base, border_radius=max(1, self.cell_px // 20))
            flame = [(mid_x, max(2, self.cell_px // 5)), (mid_x + max(3, self.cell_px // 8), mid_y), (mid_x, mid_y + max(1, self.cell_px // 14)), (mid_x - max(3, self.cell_px // 8), mid_y)]
            self.pygame.draw.polygon(overlay, self._alpha_color("hazard_fire", 174), flame)
            self.pygame.draw.rect(overlay, stroke, base, stroke_w, border_radius=max(1, self.cell_px // 20))
        elif kind == "personal_home":
            cup = self.pygame.Rect(mid_x - max(4, self.cell_px // 5), mid_y - max(2, self.cell_px // 8), max(8, self.cell_px // 3), max(8, self.cell_px // 3))
            self.pygame.draw.rect(overlay, outline, cup.move(1, 1), border_radius=max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, fill, cup, border_radius=max(2, self.cell_px // 8))
            self.pygame.draw.arc(overlay, stroke, (cup.right - 2, cup.top + 2, max(5, self.cell_px // 4), max(6, self.cell_px // 4)), -1.2, 1.2, stroke_w)
            self.pygame.draw.rect(overlay, stroke, cup, stroke_w, border_radius=max(2, self.cell_px // 8))
        elif kind == "trade_work":
            bell = self.pygame.Rect(mid_x - max(5, self.cell_px // 4), mid_y - max(1, self.cell_px // 12), max(10, self.cell_px // 2), max(7, self.cell_px // 3))
            self.pygame.draw.ellipse(overlay, outline, bell.move(1, 1))
            self.pygame.draw.ellipse(overlay, fill, bell)
            self.pygame.draw.arc(overlay, stroke, bell, 3.14, 6.28, stroke_w + 1)
            self.pygame.draw.circle(overlay, accent, (mid_x, bell.top), max(2, self.cell_px // 12))
            self.pygame.draw.line(overlay, dark, (bell.left, bell.bottom - 2), (bell.right, bell.bottom - 2), stroke_w)
        elif kind == "nature_finds":
            shell = self.pygame.Rect(max(3, self.cell_px // 4), max(3, self.cell_px // 4), max(8, self.cell_px // 2), max(8, self.cell_px // 2))
            self.pygame.draw.arc(overlay, outline, shell.move(1, 1), 3.2, 6.2, stroke_w + 2)
            self.pygame.draw.arc(overlay, fill, shell, 3.2, 6.2, max(3, stroke_w + 2))
            for offset in (-1, 0, 1):
                self.pygame.draw.line(overlay, stroke, (mid_x, shell.bottom - 2), (mid_x + offset * max(4, self.cell_px // 7), shell.top + max(2, self.cell_px // 8)), max(1, stroke_w))
        elif kind == "medical_herbal":
            vial = self.pygame.Rect(mid_x - max(3, self.cell_px // 8), mid_y - max(3, self.cell_px // 7), max(6, self.cell_px // 4), max(10, self.cell_px // 2))
            self.pygame.draw.rect(overlay, outline, vial.move(1, 1), border_radius=max(2, self.cell_px // 10))
            self.pygame.draw.rect(overlay, glass if material == "glass" else fill, vial, border_radius=max(2, self.cell_px // 10))
            liquid = self.pygame.Rect(vial.left + 1, vial.centery, max(2, vial.w - 2), max(2, vial.h // 3))
            self.pygame.draw.rect(overlay, self._alpha_color("item_chemical", 134), liquid, border_radius=max(1, self.cell_px // 18))
            self.pygame.draw.rect(overlay, stroke, vial, stroke_w, border_radius=max(2, self.cell_px // 10))

        motif_radius = max(2, self.cell_px // 12)
        motif_x = mid_x + ((seed % 3) - 1) * max(1, self.cell_px // 16)
        motif_y = mid_y + max(1, self.cell_px // 10)
        if motif == "star":
            points = []
            outer = max(3, self.cell_px // 8)
            inner = max(1, outer // 2)
            for idx in range(10):
                angle = (math.pi * 2 * idx / 10.0) - (math.pi / 2.0)
                radius = outer if idx % 2 == 0 else inner
                points.append((motif_x + int(math.cos(angle) * radius), motif_y + int(math.sin(angle) * radius)))
            self.pygame.draw.polygon(overlay, accent, points)
        elif motif == "stripe":
            self.pygame.draw.line(overlay, accent, (mid_x - max(4, self.cell_px // 5), motif_y), (mid_x + max(4, self.cell_px // 5), motif_y), stroke_w)
        elif motif == "dot_ring":
            for idx in range(6):
                angle = math.pi * 2 * idx / 6.0
                self.pygame.draw.circle(overlay, accent, (motif_x + int(math.cos(angle) * motif_radius * 2), motif_y + int(math.sin(angle) * motif_radius * 2)), max(1, stroke_w))
        elif motif == "crescent":
            self.pygame.draw.circle(overlay, accent, (motif_x, motif_y), motif_radius + 2)
            self.pygame.draw.circle(overlay, dark, (motif_x + max(1, motif_radius // 2), motif_y - 1), motif_radius + 1)
        elif motif == "flower":
            for idx in range(5):
                angle = math.pi * 2 * idx / 5.0
                self.pygame.draw.circle(overlay, accent, (motif_x + int(math.cos(angle) * motif_radius), motif_y + int(math.sin(angle) * motif_radius)), max(1, motif_radius // 2))
            self.pygame.draw.circle(overlay, highlight, (motif_x, motif_y), max(1, stroke_w))
        elif motif == "key_mark":
            self.pygame.draw.circle(overlay, accent, (motif_x - motif_radius, motif_y), motif_radius, max(1, stroke_w))
            self.pygame.draw.line(overlay, accent, (motif_x, motif_y), (motif_x + motif_radius * 2, motif_y), stroke_w)
        elif motif == "route_mark":
            self.pygame.draw.line(overlay, accent, (motif_x - motif_radius * 2, motif_y + motif_radius), (motif_x, motif_y - motif_radius), stroke_w)
            self.pygame.draw.line(overlay, accent, (motif_x, motif_y - motif_radius), (motif_x + motif_radius * 2, motif_y + motif_radius), stroke_w)
        elif motif == "slash":
            self.pygame.draw.line(overlay, accent, (motif_x - motif_radius * 2, motif_y + motif_radius * 2), (motif_x + motif_radius * 2, motif_y - motif_radius * 2), stroke_w)

        if condition in {"cracked", "chipped"}:
            self.pygame.draw.line(overlay, outline, (mid_x - max(2, self.cell_px // 10), mid_y - max(3, self.cell_px // 8)), (mid_x + max(1, self.cell_px // 14), mid_y), max(1, stroke_w))
            self.pygame.draw.line(overlay, outline, (mid_x + max(1, self.cell_px // 14), mid_y), (mid_x - max(1, self.cell_px // 12), mid_y + max(3, self.cell_px // 8)), max(1, stroke_w))
        elif condition == "repaired":
            self.pygame.draw.line(overlay, accent, (mid_x - max(4, self.cell_px // 6), mid_y), (mid_x + max(4, self.cell_px // 6), mid_y), max(1, stroke_w))
            for dx in (-1, 0, 1):
                self.pygame.draw.line(overlay, accent, (mid_x + dx * max(3, self.cell_px // 12), mid_y - max(2, self.cell_px // 10)), (mid_x + dx * max(3, self.cell_px // 12), mid_y + max(2, self.cell_px // 10)), max(1, stroke_w))
        elif condition == "dusty":
            for idx in range(4):
                px = max(2, (seed + idx * 7) % max(3, self.cell_px - 3))
                py = max(2, (seed // 3 + idx * 5) % max(3, self.cell_px - 3))
                self.pygame.draw.circle(overlay, self._alpha_color("hazard_smoke", 88), (px, py), max(1, stroke_w))
        elif condition == "polished":
            self.pygame.draw.arc(overlay, highlight, (max(3, self.cell_px // 5), max(3, self.cell_px // 5), self.cell_px - max(6, (self.cell_px // 5) * 2), self.cell_px - max(6, (self.cell_px // 5) * 2)), 3.7, 5.4, max(1, stroke_w))
        elif condition == "wrapped":
            self.pygame.draw.arc(overlay, cloth, (max(3, self.cell_px // 5), max(3, self.cell_px // 5), self.cell_px - max(6, (self.cell_px // 5) * 2), self.cell_px - max(6, (self.cell_px // 5) * 2)), 0.2, 2.9, max(1, stroke_w))

        if rarity == "unique":
            self.pygame.draw.circle(overlay, accent, (self.cell_px - max(3, self.cell_px // 6), max(3, self.cell_px // 6)), max(1, self.cell_px // 16))
        elif rarity == "rare":
            self.pygame.draw.circle(overlay, accent, (self.cell_px - max(3, self.cell_px // 6), max(3, self.cell_px // 6)), max(1, self.cell_px // 20))
        self.surface.blit(overlay, (cell_x, cell_y))

    def _vehicle_heading_from_render(self, glyph, semantic_key):
        semantic_key = str(semantic_key or "").strip().lower()
        prefix = "property_vehicle_heading_"
        if semantic_key.startswith(prefix):
            direction_key = semantic_key.removeprefix(prefix).replace("-", "_")
            heading = _PYGAME_VEHICLE_HEADING_BY_KEY.get(direction_key)
            if heading is not None:
                return heading
        return _PYGAME_VEHICLE_HEADING_BY_GLYPH.get(str(glyph or "")[:1])

    def _normalized_vehicle_heading(self, heading):
        if not heading:
            return 0, -1
        try:
            dx, dy = heading
        except (TypeError, ValueError):
            return 0, -1
        dx = 1 if dx > 0 else -1 if dx < 0 else 0
        dy = 1 if dy > 0 else -1 if dy < 0 else 0
        if dx == 0 and dy == 0:
            return 0, -1
        return dx, dy

    def _draw_vehicle_overlay(self, x, y, color=None, attrs=0, *, heading=None, headlights=True):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        color_key = str(color or "").strip().lower()
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        heading = self._normalized_vehicle_heading(heading)
        heading_len = math.hypot(heading[0], heading[1]) or 1.0
        forward_x = heading[0] / heading_len
        forward_y = heading[1] / heading_len
        right_x = -forward_y
        right_y = forward_x
        mid_x = (self.cell_px - 1) / 2.0
        mid_y = (self.cell_px - 1) / 2.0

        def oriented_point(along, across):
            return (
                int(round(mid_x + (forward_x * float(along)) + (right_x * float(across)))),
                int(round(mid_y + (forward_y * float(along)) + (right_y * float(across)))),
            )

        stroke_w = max(1, self.cell_px // 18)
        front_len = max(3.0, self.cell_px * 0.34)
        rear_len = max(3.0, self.cell_px * 0.32)
        nose_len = max(1.0, self.cell_px * 0.08)
        front_half_w = max(1.5, self.cell_px * 0.15)
        rear_half_w = max(2.0, self.cell_px * 0.21)

        body_fill = (frame[0], frame[1], frame[2], 170)
        body_stroke = (
            min(255, int(frame[0] * 1.12)),
            min(255, int(frame[1] * 1.12)),
            min(255, int(frame[2] * 1.12)),
            220,
        )
        shadow = self._alpha_color("vehicle_tire", 142)
        glass = self._alpha_color("vehicle_glass", 150)
        headlight = self._alpha_color("vehicle_light", 190)
        tail_light = self._alpha_color("vehicle_tail_light", 178)
        trim = self._alpha_color("vehicle_trim", 178)

        body_points = [
            oriented_point(front_len, -front_half_w),
            oriented_point(front_len + nose_len, 0),
            oriented_point(front_len, front_half_w),
            oriented_point(-rear_len, rear_half_w),
            oriented_point(-rear_len, -rear_half_w),
        ]
        self.pygame.draw.polygon(overlay, body_fill, body_points)
        self.pygame.draw.polygon(overlay, body_stroke, body_points, stroke_w)

        windshield_points = [
            oriented_point(front_len * 0.52, -front_half_w * 0.72),
            oriented_point(front_len * 0.52, front_half_w * 0.72),
            oriented_point(front_len * 0.12, front_half_w * 0.62),
            oriented_point(front_len * 0.12, -front_half_w * 0.62),
        ]
        rear_window_points = [
            oriented_point(-rear_len * 0.10, -rear_half_w * 0.58),
            oriented_point(-rear_len * 0.10, rear_half_w * 0.58),
            oriented_point(-rear_len * 0.56, rear_half_w * 0.70),
            oriented_point(-rear_len * 0.56, -rear_half_w * 0.70),
        ]
        self.pygame.draw.polygon(overlay, glass, windshield_points)
        self.pygame.draw.polygon(overlay, glass, rear_window_points)

        self.pygame.draw.line(overlay, trim, oriented_point(-rear_len * 0.82, 0), oriented_point(front_len * 0.68, 0), max(1, self.cell_px // 22))

        wheel_r = max(1, self.cell_px // 11)
        for wheel_along in (-rear_len * 0.58, front_len * 0.46):
            for wheel_across in (-rear_half_w - wheel_r * 0.35, rear_half_w + wheel_r * 0.35):
                self.pygame.draw.circle(overlay, shadow, oriented_point(wheel_along, wheel_across), wheel_r)
                self.pygame.draw.circle(overlay, trim, oriented_point(wheel_along, wheel_across), max(1, wheel_r - 1), max(1, stroke_w - 1))

        nose_across = max(1.0, front_half_w * 0.56)
        self.pygame.draw.line(
            overlay,
            body_stroke,
            oriented_point(front_len + nose_len * 0.18, -nose_across),
            oriented_point(front_len + nose_len * 0.18, nose_across),
            max(1, self.cell_px // 24),
        )
        light_r = max(1, self.cell_px // 24)
        if bool(headlights):
            self.pygame.draw.circle(overlay, headlight, oriented_point(front_len + nose_len * 0.28, -nose_across), light_r)
            self.pygame.draw.circle(overlay, headlight, oriented_point(front_len + nose_len * 0.28, nose_across), light_r)
        tail_across = max(1.0, rear_half_w * 0.58)
        if bool(headlights):
            self.pygame.draw.circle(overlay, tail_light, oriented_point(-rear_len * 0.96, -tail_across), light_r)
            self.pygame.draw.circle(overlay, tail_light, oriented_point(-rear_len * 0.96, tail_across), light_r)

        if color_key == "vehicle_player":
            ring_r = max(2, self.cell_px // 8)
            self.pygame.draw.circle(
                overlay,
                (84, 226, 255, 196),
                (int(round(mid_x)), int(round(mid_y))),
                ring_r + max(1, self.cell_px // 18),
                max(1, stroke_w),
            )
        elif color_key == "vehicle_police":
            stripe_w = max(1, self.cell_px // 20)
            self.pygame.draw.line(
                overlay,
                (244, 248, 255, 220),
                oriented_point(-rear_len * 0.72, -rear_half_w * 0.18),
                oriented_point(front_len * 0.72, -front_half_w * 0.18),
                stripe_w,
            )
            self.pygame.draw.line(
                overlay,
                (30, 44, 78, 230),
                oriented_point(-rear_len * 0.72, rear_half_w * 0.18),
                oriented_point(front_len * 0.72, front_half_w * 0.18),
                stripe_w,
            )
        elif color_key == "vehicle_new":
            self.pygame.draw.line(
                overlay,
                (250, 232, 162, 188),
                oriented_point(-rear_len * 0.68, -rear_half_w * 0.34),
                oriented_point(front_len * 0.66, -front_half_w * 0.34),
                max(1, self.cell_px // 22),
            )
        elif color_key == "vehicle_parked":
            self.pygame.draw.line(
                overlay,
                shadow,
                oriented_point(-rear_len * 0.68, -rear_half_w * 0.34),
                oriented_point(-rear_len * 0.68, rear_half_w * 0.34),
                max(1, self.cell_px // 28),
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
        fill = (frame[0], frame[1], frame[2], 152)
        stroke = self._lightened_rgba(frame, 232, amount=0.2)
        shadow = self._darkened_rgba(frame, 172, amount=0.55)
        outline = self._alpha_color("actor_outline", 188)
        highlight = self._alpha_color("actor_highlight", 142)
        accent = self._lightened_rgba(frame, 184, amount=0.32)
        role_accent = self._alpha_color("actor_role_accent", 172)
        self._draw_legibility_backing(
            overlay,
            self._local_tile_rect(inset=max(2, self.cell_px // 9), min_size=7),
            color="actor_outline",
            alpha=58,
            radius=max(2, self.cell_px // 7),
        )

        if kind == "player":
            radius = max(4, (self.cell_px // 2) - inset)
            self.pygame.draw.circle(overlay, outline, (mid_x + 1, mid_y + 1), radius + max(1, stroke_w))
            self.pygame.draw.circle(overlay, fill, (mid_x, mid_y), radius)
            self.pygame.draw.circle(overlay, stroke, (mid_x, mid_y), radius, stroke_w)
            self.pygame.draw.circle(overlay, highlight, (mid_x, mid_y), max(2, radius - max(2, self.cell_px // 6)), max(1, stroke_w))
            self.pygame.draw.arc(
                overlay,
                accent,
                (inset, inset, max(4, self.cell_px - (inset * 2)), max(4, self.cell_px - (inset * 2))),
                0.35,
                2.25,
                max(1, stroke_w),
            )
            tick = max(2, self.cell_px // 7)
            for start, end in (
                ((mid_x, inset), (mid_x, inset + tick)),
                ((mid_x, self.cell_px - inset - 1), (mid_x, self.cell_px - inset - 1 - tick)),
                ((inset, mid_y), (inset + tick, mid_y)),
                ((self.cell_px - inset - 1, mid_y), (self.cell_px - inset - 1 - tick, mid_y)),
            ):
                self.pygame.draw.line(overlay, accent, start, end, max(1, stroke_w))
            self.pygame.draw.polygon(
                overlay,
                highlight,
                [
                    (mid_x, inset + max(1, self.cell_px // 8)),
                    (mid_x + max(2, self.cell_px // 8), mid_y),
                    (mid_x, self.cell_px - inset - max(1, self.cell_px // 8)),
                    (mid_x - max(2, self.cell_px // 8), mid_y),
                ],
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
            shadow_points = [(px + 1, py + 1) for px, py in points]
            self.pygame.draw.polygon(overlay, outline, shadow_points)
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            cap = self.pygame.Rect(
                mid_x - max(3, self.cell_px // 5),
                inset + max(1, self.cell_px // 10),
                max(6, (self.cell_px // 5) * 2),
                max(2, self.cell_px // 8),
            )
            self.pygame.draw.rect(overlay, highlight, cap, border_radius=max(1, self.cell_px // 24))
            self.pygame.draw.rect(overlay, role_accent, cap.inflate(-max(2, self.cell_px // 7), 0), border_radius=max(1, self.cell_px // 28))
            self.pygame.draw.line(
                overlay,
                role_accent,
                (mid_x - max(2, self.cell_px // 6), mid_y - max(1, self.cell_px // 8)),
                (mid_x + max(2, self.cell_px // 6), mid_y - max(1, self.cell_px // 8)),
                max(1, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                shadow,
                (mid_x - max(2, self.cell_px // 8), mid_y + max(1, self.cell_px // 5)),
                (mid_x, mid_y + max(3, self.cell_px // 3)),
                max(1, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                shadow,
                (mid_x, mid_y + max(3, self.cell_px // 3)),
                (mid_x + max(2, self.cell_px // 8), mid_y + max(1, self.cell_px // 5)),
                max(1, stroke_w),
            )
            self.pygame.draw.circle(overlay, highlight, (mid_x, mid_y + max(1, self.cell_px // 12)), max(1, self.cell_px // 18))
        elif kind == "scout":
            diamond = [
                (mid_x, inset),
                (self.cell_px - inset - 1, mid_y),
                (mid_x, self.cell_px - inset - 1),
                (inset, mid_y),
            ]
            self.pygame.draw.polygon(overlay, outline, [(px + 1, py + 1) for px, py in diamond])
            self.pygame.draw.polygon(overlay, fill, diamond)
            self.pygame.draw.polygon(overlay, stroke, diamond, stroke_w)
            inner = [
                (mid_x, inset + max(3, self.cell_px // 5)),
                (mid_x + max(3, self.cell_px // 6), mid_y),
                (mid_x, self.cell_px - inset - max(3, self.cell_px // 5)),
                (mid_x - max(3, self.cell_px // 6), mid_y),
            ]
            self.pygame.draw.polygon(overlay, highlight, inner, max(1, stroke_w))
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
            self.pygame.draw.circle(overlay, role_accent, (mid_x, inset + max(2, self.cell_px // 5)), max(1, self.cell_px // 18))
        else:
            body = self.pygame.Rect(
                mid_x - max(3, self.cell_px // 5),
                mid_y - max(1, self.cell_px // 14),
                max(6, (self.cell_px // 5) * 2),
                max(5, self.cell_px // 3),
            )
            head_r = max(3, self.cell_px // 6)
            head_center = (mid_x, max(inset + head_r, mid_y - max(2, self.cell_px // 5)))
            self.pygame.draw.ellipse(overlay, outline, body.move(1, 1))
            self.pygame.draw.circle(overlay, outline, (head_center[0] + 1, head_center[1] + 1), head_r + max(1, stroke_w // 2))
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.circle(overlay, fill, head_center, head_r)
            self.pygame.draw.circle(overlay, stroke, head_center, head_r, stroke_w)
            self.pygame.draw.line(
                overlay,
                role_accent,
                (body.left + max(1, self.cell_px // 8), body.centery),
                (body.right - max(1, self.cell_px // 8), body.centery),
                max(1, stroke_w),
            )
            foot_y = body.bottom + max(1, self.cell_px // 14)
            self.pygame.draw.line(overlay, shadow, (mid_x - max(2, self.cell_px // 8), body.bottom), (mid_x - max(3, self.cell_px // 7), foot_y), max(1, stroke_w))
            self.pygame.draw.line(overlay, shadow, (mid_x + max(2, self.cell_px // 8), body.bottom), (mid_x + max(3, self.cell_px // 7), foot_y), max(1, stroke_w))

        text_value = str(glyph or "@")[:1] or "@"
        brightness = (frame[0] * 0.299) + (frame[1] * 0.587) + (frame[2] * 0.114)
        text_rgb = (24, 28, 32) if brightness >= 150 else (245, 245, 245)
        text_surface = self._ui_bold_font.render(text_value, True, text_rgb)
        text_rect = text_surface.get_rect(center=(mid_x, mid_y))
        text_rect.y += max(-1, self.cell_px // 32)
        overlay.blit(text_surface, text_rect)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_creature_overlay(self, x, y, color=None, attrs=0, *, kind="other"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.05)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 10)
        mid_x = self.cell_px // 2
        mid_y = self.cell_px // 2
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 164)
        stroke = (
            min(255, int(frame[0] * 1.1) + 10),
            min(255, int(frame[1] * 1.08) + 10),
            min(255, int(frame[2] * 1.08) + 10),
            228,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 128)
        accent = (
            min(255, int(frame[0] * 1.04) + 18),
            min(255, int(frame[1] * 1.04) + 18),
            min(255, int(frame[2] * 1.04) + 18),
            168,
        )

        if kind == "feline":
            body = self.pygame.Rect(inset + max(2, self.cell_px // 8), mid_y - max(1, self.cell_px // 12), max(6, self.cell_px - max(6, self.cell_px // 2)), max(5, self.cell_px // 3))
            head = self.pygame.Rect(body.left - max(1, self.cell_px // 10), body.top - max(1, self.cell_px // 10), max(4, self.cell_px // 3), max(4, self.cell_px // 3))
            ears = [
                [(head.left + max(2, self.cell_px // 10), head.top + max(2, self.cell_px // 10)), (head.left + max(3, self.cell_px // 8), head.top - max(2, self.cell_px // 10)), (head.left + max(4, self.cell_px // 6), head.top + max(2, self.cell_px // 10))],
                [(head.right - max(4, self.cell_px // 6), head.top + max(2, self.cell_px // 10)), (head.right - max(3, self.cell_px // 8), head.top - max(2, self.cell_px // 10)), (head.right - max(2, self.cell_px // 10), head.top + max(2, self.cell_px // 10))],
            ]
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.ellipse(overlay, fill, head)
            self.pygame.draw.ellipse(overlay, stroke, head, stroke_w)
            for ear in ears:
                self.pygame.draw.polygon(overlay, fill, ear)
                self.pygame.draw.polygon(overlay, stroke, ear, stroke_w)
            self.pygame.draw.line(
                overlay,
                accent,
                (body.right - max(1, self.cell_px // 10), body.centery),
                (self.cell_px - inset, body.top - max(3, self.cell_px // 8)),
                max(1, stroke_w),
            )
        elif kind == "canine":
            body = self.pygame.Rect(inset + max(2, self.cell_px // 10), mid_y - max(1, self.cell_px // 10), max(7, self.cell_px - max(6, self.cell_px // 2)), max(5, self.cell_px // 3))
            head = self.pygame.Rect(body.left - max(2, self.cell_px // 8), body.top - max(1, self.cell_px // 10), max(5, self.cell_px // 3), max(4, self.cell_px // 3))
            snout = [(head.right - max(2, self.cell_px // 8), head.centery - max(1, self.cell_px // 10)), (head.right + max(2, self.cell_px // 10), head.centery), (head.right - max(2, self.cell_px // 8), head.centery + max(1, self.cell_px // 10))]
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.ellipse(overlay, fill, head)
            self.pygame.draw.ellipse(overlay, stroke, head, stroke_w)
            self.pygame.draw.polygon(overlay, fill, snout)
            self.pygame.draw.polygon(overlay, stroke, snout, stroke_w)
            for leg_x in (body.left + max(2, self.cell_px // 7), body.centerx, body.right - max(2, self.cell_px // 7)):
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (leg_x, body.bottom - max(1, self.cell_px // 14)),
                    (leg_x, self.cell_px - inset - max(1, self.cell_px // 10)),
                    max(1, stroke_w),
                )
        elif kind == "avian":
            body = self.pygame.Rect(mid_x - max(3, self.cell_px // 5), mid_y - max(3, self.cell_px // 6), max(6, self.cell_px // 2), max(7, self.cell_px // 2))
            wing = [
                (body.left + max(2, self.cell_px // 10), body.top + max(2, self.cell_px // 10)),
                (body.right - max(2, self.cell_px // 10), body.centery),
                (body.left + max(3, self.cell_px // 8), body.bottom - max(2, self.cell_px // 10)),
            ]
            beak = [
                (body.right - max(1, self.cell_px // 12), body.top + max(3, self.cell_px // 8)),
                (body.right + max(2, self.cell_px // 10), body.top + max(1, self.cell_px // 3)),
                (body.right - max(1, self.cell_px // 12), body.top + max(1, self.cell_px // 2)),
            ]
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.polygon(overlay, accent, wing)
            self.pygame.draw.polygon(overlay, stroke, wing, stroke_w)
            self.pygame.draw.polygon(overlay, accent, beak)
            self.pygame.draw.polygon(overlay, stroke, beak, stroke_w)
        elif kind in {"insect", "arachnid"}:
            abdomen = self.pygame.Rect(mid_x - max(2, self.cell_px // 8), mid_y, max(4, self.cell_px // 4), max(4, self.cell_px // 4))
            thorax = self.pygame.Rect(mid_x - max(2, self.cell_px // 8), mid_y - max(2, self.cell_px // 6), max(4, self.cell_px // 4), max(4, self.cell_px // 4))
            head = self.pygame.Rect(mid_x - max(1, self.cell_px // 10), thorax.top - max(2, self.cell_px // 8), max(3, self.cell_px // 5), max(3, self.cell_px // 5))
            for segment in (abdomen, thorax, head):
                self.pygame.draw.ellipse(overlay, fill, segment)
                self.pygame.draw.ellipse(overlay, stroke, segment, stroke_w)
            leg_delta = max(2, self.cell_px // 5)
            for idx, py in enumerate((thorax.centery - max(1, self.cell_px // 10), thorax.centery, thorax.centery + max(1, self.cell_px // 10))):
                spread = leg_delta + idx
                self.pygame.draw.line(overlay, shadow, (thorax.left + max(1, self.cell_px // 20), py), (thorax.left - spread, py - max(2, self.cell_px // 8)), max(1, stroke_w))
                self.pygame.draw.line(overlay, shadow, (thorax.right - max(1, self.cell_px // 20), py), (thorax.right + spread, py - max(2, self.cell_px // 8)), max(1, stroke_w))
        elif kind == "rodent":
            body = self.pygame.Rect(mid_x - max(3, self.cell_px // 6), mid_y - max(1, self.cell_px // 10), max(7, self.cell_px // 2), max(5, self.cell_px // 3))
            head = self.pygame.Rect(body.left - max(2, self.cell_px // 8), body.top, max(4, self.cell_px // 3), max(4, self.cell_px // 3))
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.ellipse(overlay, fill, head)
            self.pygame.draw.ellipse(overlay, stroke, head, stroke_w)
            self.pygame.draw.circle(overlay, accent, (head.left + max(2, self.cell_px // 8), head.top + max(2, self.cell_px // 8)), max(1, self.cell_px // 12))
            self.pygame.draw.line(
                overlay,
                accent,
                (body.right - max(1, self.cell_px // 10), body.centery),
                (self.cell_px - inset, body.bottom + max(1, self.cell_px // 8)),
                max(1, stroke_w),
            )
        elif kind == "ungulate":
            body = self.pygame.Rect(inset + max(2, self.cell_px // 8), mid_y - max(2, self.cell_px // 10), max(7, self.cell_px - max(6, self.cell_px // 2)), max(5, self.cell_px // 3))
            neck = self.pygame.Rect(body.left + max(1, self.cell_px // 12), body.top - max(3, self.cell_px // 8), max(3, self.cell_px // 6), max(4, self.cell_px // 3))
            head = self.pygame.Rect(neck.left - max(1, self.cell_px // 12), neck.top - max(1, self.cell_px // 10), max(4, self.cell_px // 3), max(3, self.cell_px // 5))
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.rect(overlay, fill, neck, border_radius=max(1, self.cell_px // 14))
            self.pygame.draw.rect(overlay, stroke, neck, stroke_w, border_radius=max(1, self.cell_px // 14))
            self.pygame.draw.ellipse(overlay, fill, head)
            self.pygame.draw.ellipse(overlay, stroke, head, stroke_w)
            for leg_x in (body.left + max(2, self.cell_px // 8), body.centerx - max(1, self.cell_px // 10), body.centerx + max(1, self.cell_px // 10), body.right - max(2, self.cell_px // 8)):
                self.pygame.draw.line(overlay, shadow, (leg_x, body.bottom - max(1, self.cell_px // 14)), (leg_x, self.cell_px - inset - max(1, self.cell_px // 12)), max(1, stroke_w))
        elif kind == "fish":
            body = self.pygame.Rect(mid_x - max(3, self.cell_px // 6), mid_y - max(2, self.cell_px // 8), max(7, self.cell_px // 2), max(5, self.cell_px // 3))
            tail = [
                (body.left + max(1, self.cell_px // 16), body.centery),
                (body.left - max(3, self.cell_px // 8), body.top + max(1, self.cell_px // 10)),
                (body.left - max(3, self.cell_px // 8), body.bottom - max(1, self.cell_px // 10)),
            ]
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.polygon(overlay, accent, tail)
            self.pygame.draw.polygon(overlay, stroke, tail, stroke_w)
            self.pygame.draw.circle(overlay, shadow, (body.right - max(2, self.cell_px // 8), body.centery - max(1, self.cell_px // 12)), max(1, self.cell_px // 20))
        elif kind in {"reptile", "amphibian"}:
            body = self.pygame.Rect(mid_x - max(4, self.cell_px // 5), mid_y - max(2, self.cell_px // 10), max(8, self.cell_px - max(6, self.cell_px // 3)), max(4, self.cell_px // 3))
            head = self.pygame.Rect(body.right - max(3, self.cell_px // 8), body.top - max(1, self.cell_px // 12), max(4, self.cell_px // 3), max(4, self.cell_px // 3))
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.ellipse(overlay, fill, head)
            self.pygame.draw.ellipse(overlay, stroke, head, stroke_w)
            tail_end_y = body.centery + (max(2, self.cell_px // 8) if kind == "amphibian" else 0)
            self.pygame.draw.line(overlay, accent, (body.left + max(1, self.cell_px // 20), body.centery), (body.left - max(4, self.cell_px // 8), tail_end_y), max(1, stroke_w))
        else:
            body = self.pygame.Rect(mid_x - max(3, self.cell_px // 6), mid_y - max(3, self.cell_px // 8), max(6, self.cell_px // 2), max(6, self.cell_px // 2))
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.arc(
                overlay,
                accent,
                (body.left, body.top + max(1, self.cell_px // 10), body.w, max(4, body.h - max(2, self.cell_px // 6))),
                0.45,
                2.6,
                max(1, stroke_w),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_entity_state_overlay(self, x, y, color=None, attrs=0, *, kind="downed"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.02)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 10)
        stroke_w = max(1, self.cell_px // 18)
        shadow = (frame[0] // 3, frame[1] // 3, frame[2] // 3, 128)
        accent = (
            min(255, int(frame[0] * 1.08) + 18),
            min(255, int(frame[1] * 0.96) + 14),
            min(255, int(frame[2] * 0.96) + 14),
            196,
        )

        if kind == "downed":
            plate = self.pygame.Rect(inset, self.cell_px - inset - max(3, self.cell_px // 5), max(6, self.cell_px - (inset * 2)), max(3, self.cell_px // 5))
            self.pygame.draw.rect(overlay, shadow, plate, border_radius=max(1, self.cell_px // 16))
            self.pygame.draw.line(
                overlay,
                accent,
                (plate.left + max(2, self.cell_px // 8), plate.top + max(1, self.cell_px // 10)),
                (plate.right - max(2, self.cell_px // 8), plate.bottom - max(1, self.cell_px // 10)),
                max(1, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                accent,
                (plate.left + max(2, self.cell_px // 8), plate.bottom - max(1, self.cell_px // 10)),
                (plate.right - max(2, self.cell_px // 8), plate.top + max(1, self.cell_px // 10)),
                max(1, stroke_w),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_remains_overlay(self, x, y, color=None, attrs=0, *, kind="nonhuman"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=0.96)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 9)
        stroke_w = max(1, self.cell_px // 18)
        fill = (frame[0], frame[1], frame[2], 118)
        stroke = (
            min(255, int(frame[0] * 0.92) + 12),
            min(255, int(frame[1] * 0.92) + 12),
            min(255, int(frame[2] * 0.92) + 12),
            172,
        )
        shadow = (frame[0] // 3, frame[1] // 3, frame[2] // 3, 104)

        if kind == "hominid":
            body = self.pygame.Rect(inset + max(1, self.cell_px // 10), self.cell_px - inset - max(4, self.cell_px // 3), max(6, self.cell_px - max(6, self.cell_px // 2)), max(4, self.cell_px // 3))
            head_center = (body.left + max(2, self.cell_px // 8), body.top + max(1, self.cell_px // 10))
            self.pygame.draw.line(
                overlay,
                shadow,
                (body.left + max(1, self.cell_px // 12), body.centery),
                (body.right - max(1, self.cell_px // 12), body.centery + max(1, self.cell_px // 12)),
                max(2, stroke_w),
            )
            self.pygame.draw.line(
                overlay,
                fill,
                (body.left + max(2, self.cell_px // 8), body.top + max(1, self.cell_px // 10)),
                (body.right - max(2, self.cell_px // 8), body.bottom - max(1, self.cell_px // 10)),
                max(2, stroke_w + 1),
            )
            self.pygame.draw.circle(overlay, fill, head_center, max(2, self.cell_px // 9))
            self.pygame.draw.circle(overlay, stroke, head_center, max(2, self.cell_px // 9), stroke_w)
        else:
            body = self.pygame.Rect(inset + max(2, self.cell_px // 8), self.cell_px - inset - max(4, self.cell_px // 3), max(7, self.cell_px - max(6, self.cell_px // 2)), max(4, self.cell_px // 3))
            self.pygame.draw.ellipse(overlay, fill, body)
            self.pygame.draw.ellipse(overlay, stroke, body, stroke_w)
            self.pygame.draw.line(
                overlay,
                shadow,
                (body.left + max(1, self.cell_px // 10), body.centery),
                (body.left - max(3, self.cell_px // 8), body.centery + max(2, self.cell_px // 8)),
                max(1, stroke_w),
            )

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
        elif kind == "junction":
            box = self.pygame.Rect(
                inset + max(1, self.cell_px // 10),
                mid_y - max(2, self.cell_px // 7),
                max(7, self.cell_px - (inset * 2) - max(2, self.cell_px // 8)),
                max(5, self.cell_px // 3),
            )
            self.pygame.draw.rect(overlay, fill, box, border_radius=max(2, self.cell_px // 12))
            self.pygame.draw.rect(overlay, stroke, box, stroke_w, border_radius=max(2, self.cell_px // 12))
            lid_y = box.top + max(2, self.cell_px // 10)
            self.pygame.draw.line(
                overlay,
                bright,
                (box.left + max(2, self.cell_px // 8), lid_y),
                (box.right - max(2, self.cell_px // 8), lid_y),
                max(1, stroke_w),
            )
            for px in (box.left + max(2, self.cell_px // 6), box.right - max(3, self.cell_px // 5)):
                self.pygame.draw.line(
                    overlay,
                    shadow,
                    (px, box.bottom - max(2, self.cell_px // 8)),
                    (px, self.cell_px - inset - max(1, self.cell_px // 12)),
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

    def _draw_campfire_ring_overlay(self, x, y, color=None, attrs=0):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.04)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        px = self.cell_px
        mid = px // 2
        stroke_w = max(1, px // 22)
        stone = (
            max(45, min(190, int(frame[0] * 0.78) + 24)),
            max(45, min(190, int(frame[1] * 0.78) + 24)),
            max(45, min(190, int(frame[2] * 0.78) + 24)),
            222,
        )
        stone_dark = (
            max(24, int(stone[0] * 0.52)),
            max(24, int(stone[1] * 0.52)),
            max(24, int(stone[2] * 0.52)),
            164,
        )
        ember = self._alpha_color("hazard_fire", 218)
        ember_hot = (255, 232, 132, 214)
        coal = (42, 31, 26, 172)
        smoke = self._alpha_color("hazard_smoke", 78)

        ring_rect = self.pygame.Rect(
            max(2, px // 7),
            max(3, px // 5),
            max(8, px - max(4, px // 4)),
            max(6, px - max(5, px // 3)),
        )
        self.pygame.draw.ellipse(overlay, stone_dark, ring_rect.inflate(max(1, px // 8), max(1, px // 10)), max(1, stroke_w))
        self.pygame.draw.ellipse(overlay, stone, ring_rect, max(1, stroke_w + 1))
        inner = ring_rect.inflate(-max(4, px // 4), -max(3, px // 5))
        if inner.w > 2 and inner.h > 2:
            self.pygame.draw.ellipse(overlay, coal, inner)

        for ox, oy, radius in (
            (-max(3, px // 5), -max(1, px // 12), max(1, px // 14)),
            (max(3, px // 5), max(1, px // 16), max(1, px // 13)),
            (-max(1, px // 10), max(2, px // 7), max(1, px // 15)),
            (max(1, px // 12), -max(3, px // 7), max(1, px // 16)),
        ):
            self.pygame.draw.circle(overlay, stone, (mid + ox, mid + oy), radius)

        flame = (
            (mid, max(2, px // 5)),
            (mid - max(3, px // 7), mid + max(2, px // 8)),
            (mid - max(1, px // 12), mid + max(3, px // 10)),
            (mid, px - max(3, px // 5)),
            (mid + max(1, px // 12), mid + max(3, px // 10)),
            (mid + max(3, px // 7), mid + max(2, px // 8)),
        )
        self.pygame.draw.polygon(overlay, ember, flame)
        inner_flame = (
            (mid, mid - max(1, px // 10)),
            (mid - max(1, px // 9), mid + max(2, px // 9)),
            (mid, mid + max(3, px // 10)),
            (mid + max(1, px // 9), mid + max(2, px // 9)),
        )
        self.pygame.draw.polygon(overlay, ember_hot, inner_flame)
        self.pygame.draw.arc(
            overlay,
            smoke,
            (mid - max(4, px // 3), max(1, px // 10), max(8, px // 2), max(7, px // 2)),
            4.0,
            5.5,
            max(1, stroke_w),
        )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_cover_rating_overlay(self, x, y, color=None, attrs=0, *, kind="low"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.05)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        inset = max(1, self.cell_px // 10)
        chip_w = max(5, self.cell_px // 2)
        chip_h = max(2, self.cell_px // 8)
        chip_x = self.cell_px - inset - chip_w
        chip_y = self.cell_px - inset - chip_h
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 108)
        fill = (frame[0], frame[1], frame[2], 184)
        stroke = (
            min(255, int(frame[0] * 1.08) + 10),
            min(255, int(frame[1] * 1.08) + 10),
            min(255, int(frame[2] * 1.08) + 10),
            228,
        )
        plate = self.pygame.Rect(chip_x - max(1, self.cell_px // 20), chip_y - max(1, self.cell_px // 20), chip_w + max(2, self.cell_px // 10), chip_h + max(2, self.cell_px // 10))
        self.pygame.draw.rect(overlay, shadow, plate, border_radius=max(1, self.cell_px // 16))

        if kind == "full":
            top = self.pygame.Rect(chip_x, chip_y - max(2, self.cell_px // 7), chip_w, chip_h)
            bottom = self.pygame.Rect(chip_x, chip_y + max(1, self.cell_px // 10), chip_w, chip_h)
            for rect in (top, bottom):
                self.pygame.draw.rect(overlay, fill, rect, border_radius=max(1, self.cell_px // 16))
                self.pygame.draw.rect(overlay, stroke, rect, max(1, self.cell_px // 24), border_radius=max(1, self.cell_px // 16))
        else:
            bar = self.pygame.Rect(chip_x, chip_y, chip_w, chip_h)
            self.pygame.draw.rect(overlay, fill, bar, border_radius=max(1, self.cell_px // 16))
            self.pygame.draw.rect(overlay, stroke, bar, max(1, self.cell_px // 24), border_radius=max(1, self.cell_px // 16))

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
            self.pygame.draw.circle(
                overlay,
                (245, 248, 232, 88),
                (self.cell_px // 2, self.cell_px // 2),
                max(2, radius // 2),
            )
            self.pygame.draw.arc(
                overlay,
                (255, 255, 230, 118),
                (inset, inset, self.cell_px - inset * 2, self.cell_px - inset * 2),
                0.15,
                2.8,
                max(1, stroke_w),
            )
        elif kind == "fixture":
            points = [
                (self.cell_px // 2, inset),
                (self.cell_px - inset - 1, self.cell_px // 2),
                (self.cell_px // 2, self.cell_px - inset - 1),
                (inset, self.cell_px // 2),
            ]
            self.pygame.draw.polygon(overlay, fill, points)
            self.pygame.draw.polygon(overlay, stroke, points, stroke_w)
            self.pygame.draw.line(
                overlay,
                (245, 248, 232, 104),
                (inset + max(2, self.cell_px // 7), self.cell_px // 2),
                (self.cell_px - inset - max(2, self.cell_px // 7), self.cell_px // 2),
                max(1, stroke_w),
            )
        elif kind == "asset":
            rect = self.pygame.Rect(inset, inset, max(4, self.cell_px - (inset * 2)), max(4, self.cell_px - (inset * 2)))
            self.pygame.draw.rect(overlay, fill, rect, border_radius=max(2, self.cell_px // 8))
            self.pygame.draw.rect(overlay, stroke, rect, stroke_w, border_radius=max(2, self.cell_px // 8))
            stripe = self.pygame.Rect(rect.left + 1, rect.top + max(2, self.cell_px // 5), max(1, rect.w - 2), max(2, self.cell_px // 7))
            self.pygame.draw.rect(overlay, (245, 248, 232, 82), stripe, border_radius=max(1, self.cell_px // 24))
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
            sign = self.pygame.Rect(
                inset + max(1, self.cell_px // 10),
                self.cell_px // 2 - max(2, self.cell_px // 7),
                max(5, self.cell_px - (inset * 2) - max(2, self.cell_px // 5)),
                max(4, self.cell_px // 3),
            )
            self.pygame.draw.rect(overlay, (245, 248, 232, 74), sign, border_radius=max(1, self.cell_px // 24))
            self.pygame.draw.line(
                overlay,
                shadow,
                (sign.left + 1, sign.bottom - 1),
                (sign.right - 2, sign.bottom - 1),
                max(1, self.cell_px // 30),
            )

        if kind != "service":
            self.pygame.draw.line(
                overlay,
                shadow,
                (inset + 1, self.cell_px - inset - 2),
                (self.cell_px - inset - 2, self.cell_px - inset - 2),
                max(1, self.cell_px // 26),
            )
        elif glyph:
            self.pygame.draw.line(
                overlay,
                shadow,
                (self.cell_px // 2, inset + max(1, self.cell_px // 6)),
                (self.cell_px // 2, self.cell_px - inset - max(1, self.cell_px // 6)),
                max(1, self.cell_px // 28),
            )

        text_value = str(glyph or "P")[:1] or "P"
        brightness = (frame[0] * 0.299) + (frame[1] * 0.587) + (frame[2] * 0.114)
        text_rgb = (22, 26, 32) if brightness >= 150 else (245, 245, 245)
        text_surface = self._marker_font.render(text_value, True, text_rgb)
        text_rect = text_surface.get_rect(center=(self.cell_px // 2, self.cell_px // 2))
        overlay.blit(text_surface, text_rect)

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_actor_outfit_overlay(self, x, y, color=None, attrs=0, *, kind="secondary"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        px = self.cell_px
        stroke_w = max(1, px // 22)
        outline = self._alpha_color("actor_outline", 190)
        stroke = self._lightened_rgba(frame, 224, amount=0.22)
        fill = (frame[0], frame[1], frame[2], 212)
        shine = self._lightened_rgba(frame, 190, amount=0.48)

        if kind == "inner":
            chest = self.pygame.Rect(
                max(5, int(px * 0.38)),
                max(6, int(px * 0.38)),
                max(4, int(px * 0.24)),
                max(4, int(px * 0.22)),
            )
            notch = (
                (chest.centerx, chest.top + max(1, px // 18)),
                (chest.left + max(1, px // 9), chest.bottom - max(1, px // 12)),
                (chest.right - max(1, px // 9), chest.bottom - max(1, px // 12)),
            )
            self.pygame.draw.polygon(overlay, outline, (
                (notch[0][0], notch[0][1] - stroke_w),
                (notch[1][0] - stroke_w, notch[1][1] + stroke_w),
                (notch[2][0] + stroke_w, notch[2][1] + stroke_w),
            ))
            self.pygame.draw.polygon(overlay, fill, notch)
            self.pygame.draw.line(overlay, shine, notch[0], notch[1], stroke_w)
            self.pygame.draw.line(overlay, stroke, notch[0], notch[2], stroke_w)
        elif kind == "secondary":
            band = self.pygame.Rect(
                max(3, px // 3),
                max(7, int(px * 0.58)),
                max(5, px - (max(3, px // 3) * 2)),
                max(2, px // 7),
            )
            self.pygame.draw.rect(overlay, outline, band.inflate(stroke_w * 2, stroke_w * 2), border_radius=max(1, px // 12))
            self.pygame.draw.rect(overlay, fill, band, border_radius=max(1, px // 12))
            self.pygame.draw.line(overlay, stroke, band.midleft, band.midright, stroke_w)
        elif kind == "footwear":
            shoe_w = max(3, px // 5)
            shoe_h = max(2, px // 9)
            y0 = px - max(3, px // 6)
            left = self.pygame.Rect(max(3, px // 3) - shoe_w // 2, y0, shoe_w, shoe_h)
            right = self.pygame.Rect(px - max(3, px // 3) - shoe_w // 2, y0, shoe_w, shoe_h)
            for rect in (left, right):
                self.pygame.draw.ellipse(overlay, outline, rect.inflate(stroke_w * 2, stroke_w * 2))
                self.pygame.draw.ellipse(overlay, fill, rect)
                self.pygame.draw.line(overlay, stroke, (rect.left + 1, rect.centery), (rect.right - 1, rect.centery), stroke_w)
        elif kind == "headwear":
            cap = self.pygame.Rect(max(4, px // 4), max(2, px // 8), max(6, px // 2), max(3, px // 7))
            brim = self.pygame.Rect(max(3, px // 4) - max(2, px // 9), cap.bottom - 1, max(8, px // 2 + px // 5), max(2, px // 11))
            self.pygame.draw.rect(overlay, outline, cap.inflate(stroke_w * 2, stroke_w * 2), border_radius=max(1, px // 14))
            self.pygame.draw.rect(overlay, fill, cap, border_radius=max(1, px // 14))
            self.pygame.draw.rect(overlay, outline, brim.inflate(stroke_w, stroke_w), border_radius=max(1, px // 16))
            self.pygame.draw.rect(overlay, fill, brim, border_radius=max(1, px // 16))
            self.pygame.draw.arc(overlay, shine, cap.inflate(1, 1), 3.3, 6.0, stroke_w)
        elif kind == "accessory":
            radius = max(2, px // 11)
            center = (px - max(4, px // 4), max(5, px // 3))
            self.pygame.draw.circle(overlay, outline, (center[0] + 1, center[1] + 1), radius + stroke_w)
            self.pygame.draw.circle(overlay, fill, center, radius)
            self.pygame.draw.line(overlay, shine, (center[0] - radius, center[1]), (center[0] + radius, center[1]), stroke_w)
            self.pygame.draw.line(overlay, shine, (center[0], center[1] - radius), (center[0], center[1] + radius), stroke_w)
        else:
            self.pygame.draw.circle(overlay, fill, (px // 2, px // 2), max(2, px // 8))

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_actor_badge_overlay(self, x, y, color=None, attrs=0, *, kind="contact"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.12)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        badge_r = max(3, self.cell_px // 5)
        center = (self.cell_px - badge_r - max(1, self.cell_px // 14), badge_r + max(1, self.cell_px // 14))
        shadow = (0, 0, 0, 150)
        fill = (frame[0], frame[1], frame[2], 218)
        stroke = (
            min(255, int(frame[0] * 1.16) + 8),
            min(255, int(frame[1] * 1.16) + 8),
            min(255, int(frame[2] * 1.16) + 8),
            238,
        )
        self.pygame.draw.circle(overlay, shadow, (center[0] + 1, center[1] + 1), badge_r)
        self.pygame.draw.circle(overlay, fill, center, badge_r)
        self.pygame.draw.circle(overlay, stroke, center, badge_r, max(1, self.cell_px // 24))

        mark = {"threat": "!", "ally": "+", "contact": "*"}.get(kind, "*")
        text_rgb = (24, 26, 30) if sum(frame[:3]) >= 390 else (250, 250, 245)
        text_surface = self._marker_font.render(mark, True, text_rgb)
        text_rect = text_surface.get_rect(center=center)
        overlay.blit(text_surface, text_rect)

        if kind == "threat":
            arc_rect = (
                max(1, self.cell_px // 12),
                max(1, self.cell_px // 12),
                self.cell_px - max(2, self.cell_px // 6),
                self.cell_px - max(2, self.cell_px // 6),
            )
            self.pygame.draw.arc(
                overlay,
                (255, 255, 255, 118),
                arc_rect,
                -0.35,
                1.45,
                max(1, self.cell_px // 28),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_property_access_badge_overlay(self, x, y, color=None, attrs=0, *, kind="public"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.08)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        pad = max(1, self.cell_px // 12)
        badge_w = max(6, self.cell_px // 2)
        badge_h = max(5, self.cell_px // 3)
        rect = self.pygame.Rect(
            self.cell_px - pad - badge_w,
            self.cell_px - pad - badge_h,
            badge_w,
            badge_h,
        )
        shadow = (0, 0, 0, 138)
        fill = (frame[0], frame[1], frame[2], 202)
        stroke = (
            min(255, int(frame[0] * 1.12) + 8),
            min(255, int(frame[1] * 1.12) + 8),
            min(255, int(frame[2] * 1.12) + 8),
            232,
        )
        self.pygame.draw.rect(overlay, shadow, rect.move(1, 1), border_radius=max(1, self.cell_px // 18))
        self.pygame.draw.rect(overlay, fill, rect, border_radius=max(1, self.cell_px // 18))
        self.pygame.draw.rect(overlay, stroke, rect, max(1, self.cell_px // 26), border_radius=max(1, self.cell_px // 18))

        mark = {
            "owned": "*",
            "locked": "L",
            "restricted": "!",
            "public": "+",
        }.get(kind, "+")
        text_rgb = (24, 26, 30) if sum(frame[:3]) >= 390 else (250, 250, 245)
        text_surface = self._marker_font.render(mark, True, text_rgb)
        text_rect = text_surface.get_rect(center=rect.center)
        overlay.blit(text_surface, text_rect)

        if kind == "locked":
            shackle_rect = (
                rect.left + max(1, rect.w // 4),
                rect.top - max(2, rect.h // 3),
                max(3, rect.w // 2),
                max(4, rect.h),
            )
            self.pygame.draw.arc(
                overlay,
                stroke,
                shackle_rect,
                3.15,
                6.25,
                max(1, self.cell_px // 30),
            )
        elif kind == "restricted":
            self.pygame.draw.line(
                overlay,
                (255, 255, 255, 122),
                (rect.left + max(1, rect.w // 5), rect.bottom - 1),
                (rect.right - max(1, rect.w // 5), rect.top + 1),
                max(1, self.cell_px // 30),
            )

        self.surface.blit(overlay, (cell_x, cell_y))

    def _draw_property_open_status_overlay(self, x, y, color=None, attrs=0, *, kind="open"):
        frame = self._styled_overlay_color(color, attrs=attrs, bold_scale=1.16)
        cell_x = int(x) * self.cell_px
        cell_y = int(y) * self.cell_px
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)

        radius = max(2, self.cell_px // 8)
        pad = max(2, self.cell_px // 10)
        center = (pad + radius, pad + radius)
        fill = (
            min(255, int(frame[0] * 1.10) + (12 if kind == "open" else 22)),
            min(255, int(frame[1] * 1.10) + (24 if kind == "open" else 4)),
            min(255, int(frame[2] * 1.04) + (10 if kind == "open" else 4)),
            236,
        )
        stroke = (18, 22, 20, 208)
        glow = (fill[0], fill[1], fill[2], 72)
        self.pygame.draw.circle(overlay, glow, center, radius + max(1, self.cell_px // 18))
        self.pygame.draw.circle(overlay, stroke, (center[0] + 1, center[1] + 1), radius)
        self.pygame.draw.circle(overlay, fill, center, radius)
        self.pygame.draw.circle(overlay, (246, 250, 238, 112), center, max(1, radius // 2))

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
        elif glyph_key == ",":
            start = (mid_x - max(1, trail // 3), mid_y)
            end = (mid_x + trail, mid_y - max(1, trail // 8))
        else:
            start = (mid_x - trail, mid_y)
            end = (mid_x + trail, mid_y)

        if glyph_key == ",":
            hot_core = (
                min(255, int(frame[0] * 1.08) + 28),
                min(255, int(frame[1] * 1.35) + 22),
                min(255, int(frame[2] * 0.92) + 6),
                240,
            )
            twin_offset = max(1, stroke_w)
            rear_len = max(2, trail // 2)
            rear_start = (start[0] - max(1, trail // 6), start[1] + twin_offset)
            rear_end = (rear_start[0] + rear_len, rear_start[1])
            spark_len = max(2, trail // 3)
            spark_start = (start[0] + max(1, trail // 6), start[1] - twin_offset)
            spark_end = (spark_start[0] + spark_len, spark_start[1])

            self.pygame.draw.line(overlay, glow, start, end, max(2, stroke_w + 2))
            self.pygame.draw.line(overlay, tail, start, end, max(1, stroke_w + 1))
            self.pygame.draw.line(overlay, hot_core, start, end, stroke_w)
            self.pygame.draw.line(overlay, (frame[0], frame[1], frame[2], 96), rear_start, rear_end, max(1, stroke_w))
            self.pygame.draw.line(overlay, (hot_core[0], hot_core[1], hot_core[2], 122), spark_start, spark_end, max(1, stroke_w))

            head_rect = self.pygame.Rect(0, 0, max(2, point_r + 3), max(2, point_r + 2))
            head_rect.center = (end[0], end[1])
            self.pygame.draw.ellipse(overlay, stroke, head_rect)
            core_rect = head_rect.inflate(-max(1, point_r // 2), -max(1, point_r // 2))
            if core_rect.width > 0 and core_rect.height > 0:
                self.pygame.draw.ellipse(overlay, hot_core, core_rect)
            self.pygame.draw.circle(overlay, glow, end, max(1, point_r // 2))
        else:
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
        if kind_key in {"landmark", "interest"}:
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

    def _draw_procedural_shape(self, x, y, ch, color=None, attrs=0, semantic_id=None, effects=None, light_tint=None):
        glyph = str(ch)[:1] or " "
        color_key = str(color or "").strip().lower()
        semantic_key = str(semantic_id or "").strip().lower()
        effect_set = {
            str(effect).strip().lower()
            for effect in (effects or ())
            if str(effect).strip()
        }
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
        if semantic_key == "overworld_selector_horizontal":
            self._draw_overworld_focus_overlay(x, y, color=color, attrs=attrs, kind="horizontal")
            return semantic_key
        if semantic_key == "overworld_selector_vertical":
            self._draw_overworld_focus_overlay(x, y, color=color, attrs=attrs, kind="vertical")
            return semantic_key
        if semantic_key.startswith("overworld_selector_corner_"):
            self._draw_overworld_focus_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=semantic_key.removeprefix("overworld_selector_") or "corner_nw",
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
        if semantic_key.startswith("flora_") or color_key.startswith("flora_"):
            flora_kind = semantic_key.removeprefix("flora_") if semantic_key.startswith("flora_") else color_key.removeprefix("flora_")
            self._draw_flora_overlay(x, y, color=color, attrs=attrs, kind=flora_kind or "flower")
            return semantic_key or color_key
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
        if semantic_key in {"hazard_open_flame", "open_flame"} or color_key == "hazard_fire":
            self._draw_fire_overlay(x, y, color=color or "hazard_fire", attrs=attrs)
            return "hazard_open_flame"
        if semantic_key in {"hazard_smoke", "smoke_choke"} or color_key == "hazard_smoke":
            self._draw_smoke_overlay(x, y, color=color or "hazard_smoke", attrs=attrs)
            return "hazard_smoke"
        if glyph != " " and color_key.startswith("floor_"):
            self._draw_district_floor_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=color_key.removeprefix("floor_") or "generic",
            )
            return color_key
        outfit_overlay_kind = {
            "ui_actor_outfit_inner": "inner",
            "ui_actor_outfit_secondary": "secondary",
            "ui_actor_outfit_footwear": "footwear",
            "ui_actor_outfit_headwear": "headwear",
            "ui_actor_outfit_accessory": "accessory",
        }.get(semantic_key)
        if outfit_overlay_kind:
            self._draw_actor_outfit_overlay(x, y, color=color, attrs=attrs, kind=outfit_overlay_kind)
            return semantic_key
        actor_badge_kind = {
            "ui_actor_threat": "threat",
            "ui_actor_ally": "ally",
            "ui_actor_contact": "contact",
        }.get(semantic_key)
        if actor_badge_kind:
            self._draw_actor_badge_overlay(x, y, color=color, attrs=attrs, kind=actor_badge_kind)
            return semantic_key
        property_badge_kind = {
            "ui_property_owned": "owned",
            "ui_property_locked": "locked",
            "ui_property_restricted": "restricted",
            "ui_property_public": "public",
        }.get(semantic_key)
        if property_badge_kind:
            self._draw_property_access_badge_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=property_badge_kind,
            )
            return semantic_key
        property_status_kind = {
            "ui_property_open": "open",
            "ui_property_closed": "closed",
        }.get(semantic_key)
        if property_status_kind:
            self._draw_property_open_status_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=property_status_kind,
            )
            return semantic_key
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
        if semantic_key == "entity_corpse_hominid":
            self._draw_remains_overlay(x, y, color=color, attrs=attrs, kind="hominid")
            return "entity_corpse_hominid"
        if semantic_key == "entity_corpse_nonhuman":
            self._draw_remains_overlay(x, y, color=color, attrs=attrs, kind="nonhuman")
            return "entity_corpse_nonhuman"
        creature_kind = {
            "entity_feline": "feline",
            "entity_canine": "canine",
            "entity_avian": "avian",
            "entity_insect": "insect",
            "entity_arachnid": "arachnid",
            "entity_rodent": "rodent",
            "entity_reptile": "reptile",
            "entity_amphibian": "amphibian",
            "entity_fish": "fish",
            "entity_ungulate": "ungulate",
            "entity_other": "other",
        }.get(semantic_key)
        if creature_kind:
            self._draw_creature_overlay(x, y, color=color, attrs=attrs, kind=creature_kind)
            return f"entity_{creature_kind}"
        actor_kind = None
        if glyph == "@":
            if semantic_key == "entity_player" or color_key == "player":
                actor_kind = "player"
            elif semantic_key == "npc_guard" or color_key == "guard":
                actor_kind = "guard"
            elif semantic_key == "npc_scout" or color_key == "scout":
                actor_kind = "scout"
            elif (
                semantic_key in {"npc_civilian", "npc_hominid"}
                or color_key == "human"
                or color_key.startswith("human_")
                or color_key.startswith("clothing_")
            ):
                actor_kind = "civilian"
        if actor_kind:
            self._draw_actor_token_overlay(x, y, glyph, color=color, attrs=attrs, kind=actor_kind)
            return f"entity_{actor_kind}"
        if semantic_key == "entity_state_downed":
            self._draw_entity_state_overlay(x, y, color=color, attrs=attrs, kind="downed")
            return "entity_state_downed"
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
        if semantic_key == "prop_campfire_ring":
            self._draw_campfire_ring_overlay(x, y, color=color, attrs=attrs)
            return "campfire_ring"
        cover_fixture_kind = {
            "prop_cover_bench": "bench",
            "prop_cover_shelter": "shelter",
            "prop_cover_junction": "junction",
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
        if semantic_key == "cover_rating_low":
            self._draw_cover_rating_overlay(x, y, color=color, attrs=attrs, kind="low")
            return "cover_rating_low"
        if semantic_key == "cover_rating_full":
            self._draw_cover_rating_overlay(x, y, color=color, attrs=attrs, kind="full")
            return "cover_rating_full"
        if semantic_key.startswith("world_object_") or color_key.startswith("world_object_"):
            family_aliases = {
                "plant": "plants_pots",
                "charm": "tokens_charms",
                "tool": "tools_parts",
                "textile": "textiles",
                "paper": "paper_books",
                "container": "containers",
                "light": "light_ritual",
                "home": "personal_home",
                "trade": "trade_work",
                "nature": "nature_finds",
                "medical": "medical_herbal",
            }
            object_families = {
                "plants_pots",
                "tokens_charms",
                "tools_parts",
                "textiles",
                "paper_books",
                "containers",
                "light_ritual",
                "personal_home",
                "trade_work",
                "nature_finds",
                "medical_herbal",
            }
            if semantic_key.startswith("world_object_"):
                object_kind = semantic_key.removeprefix("world_object_")
            else:
                object_kind = color_key.removeprefix("world_object_")
            object_kind = family_aliases.get(
                object_kind,
                object_kind if object_kind in object_families else "personal_home",
            )
            self._draw_world_object_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                kind=object_kind,
                effects=effect_set,
            )
            return f"world_object_{object_kind}"
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
        if (
            semantic_key.startswith("property_vehicle")
            or (color_key.startswith("vehicle_") and glyph in {"&", "V", "v", "^", ">", "<", "7", "J", "L", "F"})
        ):
            heading = self._vehicle_heading_from_render(glyph, semantic_key)
            self._draw_vehicle_overlay(
                x,
                y,
                color=color,
                attrs=attrs,
                heading=heading,
                headlights="vehicle_headlights_off" not in effect_set,
            )
            heading_label = _PYGAME_VEHICLE_HEADING_LABELS.get(self._normalized_vehicle_heading(heading))
            return f"vehicle_{heading_label}" if heading_label and heading is not None else "vehicle"
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
        if (
            semantic_key == "wall_building"
            or color_key == "building_edge"
            or color_key.startswith("building_edge_")
            or (glyph == "#" and color_key.startswith("building_"))
        ):
            self._draw_wall_overlay(x, y, color=color, attrs=attrs, filled=False)
            return "building_edge"
        if (
            semantic_key == "floor_building_fill"
            or color_key == "building_fill"
            or color_key.startswith("building_fill_")
            or (glyph in {".", "="} and color_key.startswith("building_fill"))
        ):
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

    def _color_value(self, color):
        if color is None:
            return self.palette["default"]
        if isinstance(color, str):
            return self.palette.get(color, self.palette["default"])
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            return (int(color[0]), int(color[1]), int(color[2]))
        return self.palette["default"]

    def _has_attr(self, attrs, flag_name):
        flag = attr_for_name(flag_name)
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
                    light_tint=call.get("light_tint"),
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
                continue
            if kind == "light_tint":
                self._draw_light_tint_now(
                    call.get("x", 0),
                    call.get("y", 0),
                    call.get("tint", {}),
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
            resolved |= A_DIM
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

    def _draw_overlay_stack(self, x, y, overlays, attrs=0, light_tint=None):
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
            if self._draw_procedural_shape(x, y, glyph, color=color, attrs=overlay_attrs, semantic_id=semantic_id, light_tint=light_tint):
                continue
            self._draw_font_char(
                x,
                y,
                glyph,
                color=color,
                attrs=overlay_attrs,
                preserve_background=True,
            )

    def _draw_char(self, x, y, ch, color=None, attrs=0, semantic_id=None, effects=None, overlays=None, light_tint=None):
        region = self._clip_text(x, y, str(ch)[:1] or " ")
        if region is None:
            return
        if not self._effects_visible(effects):
            return
        attrs = self._attrs_with_effects(attrs, effects)
        x, y, text = region
        previous_light_tint = self._active_surface_light_tint
        self._active_surface_light_tint = self._normalize_light_tint(light_tint)
        try:
            if self._draw_procedural_shape(x, y, text[0], color=color, attrs=attrs, semantic_id=semantic_id, effects=effects, light_tint=light_tint):
                self._draw_overlay_stack(x, y, overlays, attrs=attrs, light_tint=light_tint)
                return
            preserve_background = self._preserve_background_for_color(color)

            self._draw_font_char(x, y, text[0], color=color, attrs=attrs, preserve_background=preserve_background)
            self._draw_overlay_stack(x, y, overlays, attrs=attrs, light_tint=light_tint)
        finally:
            self._active_surface_light_tint = previous_light_tint

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

    def _normalize_light_tint(self, tint):
        if not isinstance(tint, dict):
            return None
        rgb = tint.get("rgb")
        if not isinstance(rgb, (list, tuple)) or len(rgb) < 3:
            return None
        try:
            red = max(0, min(255, int(round(float(rgb[0])))))
            green = max(0, min(255, int(round(float(rgb[1])))))
            blue = max(0, min(255, int(round(float(rgb[2])))))
            strength = max(0.0, min(1.0, float(tint.get("strength", 0.0) or 0.0)))
        except (TypeError, ValueError):
            return None
        if strength <= 0.0:
            return None
        pulse = str(tint.get("pulse", "") or "").strip().lower()
        return (red, green, blue), strength, pulse

    def _draw_light_tint_now(self, x, y, tint):
        region = self._clip_draw_position(x, y)
        if region is None:
            return
        normalized = self._normalize_light_tint(tint)
        if normalized is None:
            return
        (red, green, blue), strength, pulse = normalized
        alpha = 10 + int(round(58 * strength))
        tick = int(self._animation_tick)
        if pulse == "emergency":
            alpha = int(alpha * (1.0 if ((tick // 3) % 2 == 0) else 0.36))
        elif pulse == "neon":
            alpha = int(alpha * (0.76 + (0.24 * ((math.sin(tick * 0.75) + 1.0) * 0.5))))
        elif pulse in {"slow", "warm", "soft"}:
            alpha = int(alpha * (0.84 + (0.16 * ((math.sin(tick * 0.35) + 1.0) * 0.5))))
        alpha = max(4, min(76, int(alpha)))
        if alpha <= 3:
            return
        x, y = region
        overlay = self.pygame.Surface((self.cell_px, self.cell_px), self.pygame.SRCALPHA)
        overlay.fill((int(red), int(green), int(blue), int(alpha)))
        self.surface.blit(overlay, (int(x) * self.cell_px, int(y) * self.cell_px))

    def draw_light_tint(self, x, y, tint, layer="fx", priority=-900):
        if self._wants_layered_draw(layer=layer, priority=priority):
            self._queue_draw_call(
                "light_tint",
                x=int(x),
                y=int(y),
                tint=dict(tint or {}),
                layer=layer,
                priority=0 if priority is None else int(priority),
            )
            return
        self._flush_queued_draws()
        self._draw_light_tint_now(x, y, tint)

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

    def _wrap_text_to_pixel_width(self, text, font, max_pixel_width, *, max_lines=None):
        text = str(text or "").strip()
        max_pixel_width = max(0, int(max_pixel_width))
        if not text or max_pixel_width <= 0:
            return ()

        wrapped = []
        for raw_line in text.splitlines() or [""]:
            line = str(raw_line).strip()
            if not line:
                wrapped.append("")
                continue
            remaining = line
            while remaining:
                if font.size(remaining)[0] <= max_pixel_width:
                    wrapped.append(remaining)
                    break
                words = remaining.split()
                candidate = ""
                consumed_words = 0
                for idx, word in enumerate(words):
                    proposed = word if not candidate else f"{candidate} {word}"
                    if font.size(proposed)[0] <= max_pixel_width:
                        candidate = proposed
                        consumed_words = idx + 1
                    else:
                        break
                if candidate:
                    wrapped.append(candidate)
                    remaining = " ".join(words[consumed_words:]).strip()
                    continue
                candidate = self._fit_text_to_pixel_width(remaining, font, max_pixel_width).rstrip()
                if not candidate:
                    break
                wrapped.append(candidate)
                remaining = remaining[len(candidate):].lstrip()
            if max_lines is not None and len(wrapped) >= max_lines:
                return tuple(wrapped[:max(1, int(max_lines))])

        if max_lines is not None:
            return tuple(wrapped[:max(1, int(max_lines))])
        return tuple(wrapped)

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
        inset = max(1, self.cell_px // 8)
        stroke_w = 1
        overlay = self.pygame.Surface((width_px, self.cell_px), self.pygame.SRCALPHA)

        fill_alpha = 180 if kind in {"box_cap", "box_mid"} else 112
        fill = (
            min(255, 10 + (frame[0] // 8)),
            min(255, 12 + (frame[1] // 8)),
            min(255, 16 + (frame[2] // 8)),
            fill_alpha,
        )
        accent = (
            min(255, int(frame[0] * 1.08)),
            min(255, int(frame[1] * 1.08)),
            min(255, int(frame[2] * 1.08)),
            218,
        )
        shadow = (frame[0] // 2, frame[1] // 2, frame[2] // 2, 112)
        glow = (
            min(255, int(frame[0] * 1.15) + 10),
            min(255, int(frame[1] * 1.15) + 10),
            min(255, int(frame[2] * 1.15) + 10),
            42,
        )
        rect = self.pygame.Rect(0, 0, width_px, self.cell_px)
        self.pygame.draw.rect(overlay, fill, rect)

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
                stroke_w,
            )
        elif kind == "divider":
            mid_y = self.cell_px // 2
            self.pygame.draw.line(
                overlay,
                glow,
                (max(1, self.cell_px // 4), mid_y),
                (width_px - max(2, self.cell_px // 4), mid_y),
                stroke_w,
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

    def _draw_inline_glyph_run(self, pixel_x, y, ch, color=None, attrs=0, semantic_id=None):
        text = str(ch)[:1] or " "
        if int(pixel_x) % self.cell_px == 0 and self._draw_procedural_shape(
            int(pixel_x) // self.cell_px,
            y,
            text,
            color=color,
            attrs=attrs,
            semantic_id=semantic_id,
        ):
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

    def draw(self, x, y, glyph, color=None, attrs=0, semantic_id=None, effects=None, overlays=None, layer=None, priority=None, light_tint=None):
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
                light_tint=dict(light_tint or {}) if isinstance(light_tint, dict) else light_tint,
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
            light_tint=light_tint,
        )

    def _draw_text_now(self, x, y, text, color=None, attrs=0):
        if self._draw_ui_border_line(x, y, text, color=color, attrs=attrs):
            return
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

    def draw_casino_table_art(self, x, y, width, height, state):
        self._flush_queued_draws()
        if not isinstance(state, dict):
            return 0
        try:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)
        except (TypeError, ValueError):
            return 0
        if width < 18 or height < 4:
            return 0
        if x < 0 or y < 0 or x >= self.width_cells or y >= self.height_cells:
            return 0
        width = max(1, min(width, self.width_cells - x))
        height = max(1, min(height, self.height_cells - y))
        used_cells = max(4, min(height, 7))
        rect = self.pygame.Rect(x * self.cell_px, y * self.cell_px, width * self.cell_px, used_cells * self.cell_px)
        if rect.w <= 0 or rect.h <= 0:
            return 0

        art = state.get("art") if isinstance(state.get("art"), dict) else None
        session = state.get("session") if isinstance(state.get("session"), dict) else None
        payload = art or session or {}
        service = str(state.get("service") or payload.get("service") or "").strip().lower()
        if not service:
            return 0

        felt = (14, 42, 36)
        felt_alt = (19, 55, 47)
        rail = (87, 55, 30)
        gold = self._color_value("casino_gold")
        cursor = self._color_value("casino_cursor")
        muted = (133, 145, 139)
        red = (216, 42, 64)
        black = (23, 29, 34)
        white = (232, 229, 214)
        pip_dark = (28, 32, 36)
        self.pygame.draw.rect(self.surface, felt, rect)
        self.pygame.draw.rect(self.surface, felt_alt, rect.inflate(-max(2, self.cell_px // 3), -max(2, self.cell_px // 3)))
        self.pygame.draw.rect(self.surface, rail, rect, max(1, self.cell_px // 8))
        self.pygame.draw.line(self.surface, gold, (rect.left + 3, rect.top + 3), (rect.right - 4, rect.top + 3), 1)

        def _text(text, px, py, color=white, font=None):
            font = font or self._ui_font
            surface = font.render(str(text), True, color)
            self.surface.blit(surface, (int(px), int(py)))

        def _center_text(text, target, color=white, font=None):
            font = font or self._ui_font
            text = str(text)
            if not text or target.w <= 0 or target.h <= 0:
                return
            fitted = self._fit_text_to_pixel_width(text, font, max(1, target.w - 4))
            if not fitted:
                return
            surface = font.render(fitted, True, color)
            self.surface.blit(surface, (
                target.left + max(0, (target.w - surface.get_width()) // 2),
                target.top + max(0, (target.h - surface.get_height()) // 2),
            ))

        suit_label = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}

        def _card_parts(card):
            code = str(card or "").strip().upper()
            if len(code) < 2 or code == "??":
                return "?", "?", muted
            rank = code[:-1] or code[0]
            suit = code[-1]
            rank = "10" if rank == "T" else rank
            color = red if suit in {"H", "D"} else black
            return rank, suit_label.get(suit, suit), color

        def _draw_card(card_rect, card, *, hidden=False):
            card_rect = self.pygame.Rect(card_rect)
            self.pygame.draw.rect(self.surface, (244, 241, 226), card_rect, border_radius=max(2, self.cell_px // 6))
            self.pygame.draw.rect(self.surface, (86, 75, 58), card_rect, 1, border_radius=max(2, self.cell_px // 6))
            if hidden or str(card or "").strip() == "??":
                inset = max(3, self.cell_px // 5)
                back = card_rect.inflate(-inset, -inset)
                self.pygame.draw.rect(self.surface, (56, 83, 126), back, border_radius=max(1, self.cell_px // 8))
                self.pygame.draw.line(self.surface, (180, 205, 238), back.topleft, back.bottomright, 1)
                self.pygame.draw.line(self.surface, (180, 205, 238), back.topright, back.bottomleft, 1)
                return
            rank, suit, color = _card_parts(card)
            _text(rank, card_rect.left + 3, card_rect.top + 1, color, self._ui_bold_font)
            _center_text(suit, card_rect.inflate(-4, -4), color, self._ui_bold_font)

        def _draw_cards_row(cards, top, label="", hidden_tail=False):
            cards = [card for card in list(cards or ())][:7]
            if not cards:
                return 0
            label_w = max(0, min(rect.w // 5, self.cell_px * 7))
            if label:
                label_rect = self.pygame.Rect(rect.left + 8, top, label_w, self.cell_px)
                _center_text(label, label_rect, gold, self._ui_font)
            available_w = rect.w - label_w - 20
            card_w = max(self.cell_px + 4, min(self.cell_px * 3, available_w // max(1, len(cards))))
            card_h = max(self.cell_px * 2, min(self.cell_px * 4, rect.bottom - top - 5))
            gap = max(3, min(self.cell_px // 2, (available_w - (card_w * len(cards))) // max(1, len(cards) - 1) if len(cards) > 1 else self.cell_px // 2))
            start_x = rect.left + 10 + label_w
            for idx, card in enumerate(cards):
                card_rect = self.pygame.Rect(start_x + (idx * (card_w + gap)), top, card_w, card_h)
                _draw_card(card_rect, card, hidden=hidden_tail and idx == len(cards) - 1)
            return card_h

        def _draw_die(die_rect, value):
            try:
                value = max(1, min(6, int(value)))
            except (TypeError, ValueError):
                value = 1
            die_rect = self.pygame.Rect(die_rect)
            self.pygame.draw.rect(self.surface, white, die_rect, border_radius=max(2, self.cell_px // 5))
            self.pygame.draw.rect(self.surface, (78, 76, 67), die_rect, 1, border_radius=max(2, self.cell_px // 5))
            cx = die_rect.centerx
            cy = die_rect.centery
            dx = max(2, die_rect.w // 4)
            dy = max(2, die_rect.h // 4)
            spots = {
                1: [(cx, cy)],
                2: [(cx - dx, cy - dy), (cx + dx, cy + dy)],
                3: [(cx - dx, cy - dy), (cx, cy), (cx + dx, cy + dy)],
                4: [(cx - dx, cy - dy), (cx + dx, cy - dy), (cx - dx, cy + dy), (cx + dx, cy + dy)],
                5: [(cx - dx, cy - dy), (cx + dx, cy - dy), (cx, cy), (cx - dx, cy + dy), (cx + dx, cy + dy)],
                6: [(cx - dx, cy - dy), (cx + dx, cy - dy), (cx - dx, cy), (cx + dx, cy), (cx - dx, cy + dy), (cx + dx, cy + dy)],
            }
            radius = max(2, min(die_rect.w, die_rect.h) // 11)
            for spot in spots.get(value, spots[1]):
                self.pygame.draw.circle(self.surface, pip_dark, spot, radius)

        def _last_roll_pair():
            for key in ("roll_pairs", "roll_history"):
                rolls = list(payload.get(key, ()) or ())
                if not rolls:
                    continue
                raw = rolls[-1]
                if isinstance(raw, dict):
                    return int(raw.get("die_one", 1) or 1), int(raw.get("die_two", 1) or 1)
                if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                    return int(raw[0] or 1), int(raw[1] or 1)
            return 3, 4

        def _casino_color_rgb(color_word):
            normalized = casino_color_word(color_word)
            if normalized == "black":
                return color_word_rgb("total_black", fallback=cursor) or cursor
            return color_word_rgb(normalized, fallback=cursor) or cursor

        def _draw_color_die(die_rect, color_word, label=""):
            die_rect = self.pygame.Rect(die_rect)
            base = _casino_color_rgb(color_word)
            border = (246, 236, 186) if sum(base) < 180 else (55, 48, 42)
            pip = (248, 244, 228) if sum(base) < 260 else (31, 35, 39)
            self.pygame.draw.rect(self.surface, base, die_rect, border_radius=max(2, self.cell_px // 5))
            self.pygame.draw.rect(self.surface, border, die_rect, 2, border_radius=max(2, self.cell_px // 5))
            shine = die_rect.inflate(-max(4, die_rect.w // 5), -max(4, die_rect.h // 5))
            shine.h = max(2, shine.h // 3)
            highlight = tuple(min(255, int(channel) + 48) for channel in base)
            self.pygame.draw.ellipse(self.surface, highlight, shine)
            cx = die_rect.centerx
            cy = die_rect.centery
            offset = max(3, min(die_rect.w, die_rect.h) // 5)
            radius = max(2, min(die_rect.w, die_rect.h) // 12)
            for spot in ((cx - offset, cy - offset), (cx, cy), (cx + offset, cy + offset)):
                self.pygame.draw.circle(self.surface, pip, spot, radius)
            if label:
                _center_text(str(label)[:1].upper(), die_rect.inflate(-4, -4), pip, self._ui_bold_font)

        def _bloom_card_rgb(card):
            if not isinstance(card, dict):
                return (214, 174, 214)
            hue = str(card.get("hue", "") or "").strip().lower()
            return {
                "pink": (235, 130, 178),
                "violet": (168, 112, 224),
                "purple": (142, 89, 184),
                "blue": (90, 148, 224),
                "white": (238, 234, 214),
                "gold": (224, 183, 72),
                "yellow": (224, 183, 72),
                "coral": (235, 110, 88),
                "red": (212, 62, 84),
                "green": (90, 168, 96),
                "mint": (118, 204, 156),
                "copper": (185, 113, 72),
                "amber": (216, 145, 58),
            }.get(hue, (116, 176, 116))

        def _draw_bloom_card(card_rect, card, *, hidden=False):
            card_rect = self.pygame.Rect(card_rect)
            base = (245, 240, 222) if not hidden else (68, 86, 78)
            self.pygame.draw.rect(self.surface, base, card_rect, border_radius=max(2, self.cell_px // 6))
            self.pygame.draw.rect(self.surface, (83, 76, 58), card_rect, 1, border_radius=max(2, self.cell_px // 6))
            if hidden:
                inset = max(3, self.cell_px // 5)
                inner = card_rect.inflate(-inset, -inset)
                self.pygame.draw.rect(self.surface, (38, 63, 54), inner, border_radius=max(1, self.cell_px // 8))
                self.pygame.draw.line(self.surface, (156, 196, 164), inner.midtop, inner.midbottom, 1)
                self.pygame.draw.line(self.surface, (156, 196, 164), inner.midleft, inner.midright, 1)
                return
            bloom = _bloom_card_rgb(card)
            stem = (54, 113, 70)
            cx = card_rect.centerx
            cy = card_rect.centery
            radius = max(3, min(card_rect.w, card_rect.h) // 8)
            self.pygame.draw.line(self.surface, stem, (cx, cy + radius * 2), (cx, cy - radius), max(1, radius // 2))
            for dx, dy in ((0, -radius), (radius, 0), (0, radius), (-radius, 0)):
                self.pygame.draw.ellipse(self.surface, bloom, self.pygame.Rect(cx + dx - radius, cy + dy - radius, radius * 2, radius * 2))
            self.pygame.draw.circle(self.surface, (236, 207, 86), (cx, cy), max(2, radius // 2))
            glyph = str(card.get("glyph", "'") if isinstance(card, dict) else "'")[:1] or "'"
            _text(glyph, card_rect.left + 3, card_rect.top + 1, bloom, self._ui_bold_font)

        def _draw_roulette():
            wheel = self.pygame.Rect(rect.left + 12, rect.top + 10, min(rect.h - 20, rect.w // 3), min(rect.h - 20, rect.w // 3))
            wheel.center = (rect.left + max(wheel.w // 2 + 12, rect.w // 4), rect.centery)
            radius = max(8, min(wheel.w, wheel.h) // 2)
            center = wheel.center
            for idx in range(24):
                angle = (math.tau / 24.0) * idx
                color = red if idx % 2 else black
                end = (center[0] + int(math.cos(angle) * radius), center[1] + int(math.sin(angle) * radius))
                self.pygame.draw.line(self.surface, color, center, end, max(2, radius // 6))
            self.pygame.draw.circle(self.surface, gold, center, radius, 2)
            self.pygame.draw.circle(self.surface, (28, 76, 46), center, max(4, radius // 3))
            spin_number = payload.get("spin_number", None)
            label = "--" if spin_number is None else str(spin_number)
            label_rect = self.pygame.Rect(rect.centerx, rect.top + self.cell_px, rect.right - rect.centerx - 8, rect.h - self.cell_px * 2)
            _center_text("ROULETTE", label_rect.move(0, -self.cell_px), gold, self._ui_bold_font)
            _center_text(f"Pocket {label}", label_rect, cursor, self._ui_bold_font)

        def _draw_crash():
            graph = rect.inflate(-self.cell_px, -self.cell_px)
            graph.top += max(0, self.cell_px // 3)
            graph.h = max(12, graph.h - self.cell_px // 3)
            self.pygame.draw.line(self.surface, muted, (graph.left, graph.bottom), (graph.right, graph.bottom), 1)
            self.pygame.draw.line(self.surface, muted, (graph.left, graph.top), (graph.left, graph.bottom), 1)
            history = []
            for value in list(payload.get("history", ()) or (1.0,)):
                try:
                    history.append(max(1.0, float(value)))
                except (TypeError, ValueError):
                    continue
            if not history:
                history = [1.0]
            max_mult = max(2.0, max(history), float(payload.get("crash_point", 0.0) or 0.0))
            points = []
            for idx, value in enumerate(history):
                px = graph.left + int((graph.w - 2) * (idx / max(1, len(history) - 1)))
                py = graph.bottom - int((graph.h - 2) * ((value - 1.0) / max(0.1, max_mult - 1.0)))
                points.append((px, py))
            if len(points) == 1:
                points.append((graph.left + max(8, graph.w // 8), points[0][1] - max(2, graph.h // 12)))
            if len(points) >= 2:
                self.pygame.draw.lines(self.surface, cursor, False, points, max(2, self.cell_px // 7))
            if str(payload.get("outcome_key", "")).strip().lower() == "crash":
                mark = points[-1]
                self.pygame.draw.line(self.surface, red, (mark[0] - 6, mark[1] - 6), (mark[0] + 6, mark[1] + 6), 2)
                self.pygame.draw.line(self.surface, red, (mark[0] + 6, mark[1] - 6), (mark[0] - 6, mark[1] + 6), 2)
            current = float(payload.get("current_multiplier", history[-1]) or history[-1])
            cashout = float(payload.get("cashout_multiplier", 0.0) or 0.0)
            label = f"x{cashout:.2f} cashed" if cashout > 0 else f"x{current:.2f}"
            _text("CRASH", graph.left + 6, graph.top + 3, gold, self._ui_bold_font)
            _text(label, graph.right - max(self.cell_px * 8, 90), graph.top + 3, cursor, self._ui_bold_font)

        if service in {"video_poker", "baccarat", "three_card_poker", "twenty_one", "casino_holdem"}:
            top = rect.top + 9
            dealer = payload.get("dealer_cards") or payload.get("banker_cards") or ()
            player = payload.get("cards") or payload.get("player_cards") or ()
            outcome_key = str(payload.get("outcome_key", "") or "").strip().lower()
            if service in {"casino_holdem", "three_card_poker"} and dealer and outcome_key in {"", "fold", "forfeit"}:
                dealer = tuple("??" for _card in list(dealer or ()))
            hands = payload.get("hands") or payload.get("player_hands") or ()
            if hands and not player:
                first = list(hands)[0]
                if isinstance(first, dict):
                    player = first.get("cards", ())
                else:
                    player = first
            board = payload.get("board") or payload.get("flop") or ()
            if dealer:
                top += _draw_cards_row(dealer, top, "Dealer" if service != "baccarat" else "Banker", hidden_tail=(service == "twenty_one" and not payload.get("outcome_key")))
            if board:
                top += 5
                top += _draw_cards_row(board, top, "Board")
            if player:
                top += 5
                _draw_cards_row(player, top, "You" if service != "baccarat" else "Player")
        elif service == "roulette":
            _draw_roulette()
        elif service == "craps":
            die_one, die_two = _last_roll_pair()
            size = min(rect.h - 24, rect.w // 5)
            size = max(self.cell_px * 2, size)
            start_x = rect.left + rect.w // 2 - size - 6
            top = rect.top + (rect.h - size) // 2
            _draw_die(self.pygame.Rect(start_x, top, size, size), die_one)
            _draw_die(self.pygame.Rect(start_x + size + 12, top, size, size), die_two)
            _center_text("CRAPS", self.pygame.Rect(rect.left + 8, rect.top + 4, rect.w - 16, self.cell_px), gold, self._ui_bold_font)
        elif service == "three_bright":
            context = payload.get("table_context") if isinstance(payload.get("table_context"), dict) else {}
            colors = list(payload.get("dice_colors", ()) or ())
            if len(colors) < 3:
                palette = list(payload.get("color_words", ()) or context.get("accent_colors", ()) or ("red", "green", "blue"))
                while len(palette) < 3:
                    palette.append(("red", "green", "blue")[len(palette) % 3])
                colors = palette[:3]
            accent = _casino_color_rgb((context.get("accent_colors") or colors or ("gold",))[0] if isinstance(context, dict) else colors[0])
            self.pygame.draw.line(self.surface, accent, (rect.left + 8, rect.bottom - 5), (rect.right - 8, rect.bottom - 5), max(2, self.cell_px // 8))
            size = min(rect.h - 26, max(self.cell_px * 2, rect.w // 7))
            size = max(self.cell_px * 2, size)
            gap = max(8, self.cell_px // 2)
            total_w = (size * 3) + (gap * 2)
            start_x = rect.centerx - total_w // 2
            top = rect.top + max(self.cell_px + 4, (rect.h - size) // 2)
            for idx, color_word in enumerate(colors[:3]):
                die = self.pygame.Rect(start_x + idx * (size + gap), top, size, size)
                _draw_color_die(die, color_word, label=color_word)
            _center_text("THREE BRIGHT", self.pygame.Rect(rect.left + 8, rect.top + 4, rect.w - 16, self.cell_px), gold, self._ui_bold_font)
        elif service == "three_bones":
            dice = list(payload.get("dice", ()) or (3, 4, 5))
            while len(dice) < 3:
                dice.append(len(dice) + 2)
            cup = self.pygame.Rect(rect.left + rect.w // 2 - rect.w // 7, rect.top + self.cell_px, max(self.cell_px * 5, rect.w // 4), max(self.cell_px * 2, rect.h // 3))
            self.pygame.draw.ellipse(self.surface, (92, 58, 36), cup.inflate(0, max(4, self.cell_px // 2)))
            self.pygame.draw.rect(self.surface, (126, 77, 44), cup, border_radius=max(3, self.cell_px // 5))
            self.pygame.draw.arc(self.surface, gold, cup.inflate(-4, -4), 0, math.pi, max(2, self.cell_px // 8))
            size = max(self.cell_px * 2, min(rect.h - cup.h - self.cell_px, rect.w // 8))
            gap = max(5, self.cell_px // 3)
            start_x = rect.centerx - ((size * 3) + (gap * 2)) // 2
            top = max(cup.bottom - self.cell_px // 4, rect.bottom - size - 8)
            for idx, value in enumerate(dice[:3]):
                _draw_die(self.pygame.Rect(start_x + idx * (size + gap), top, size, size), value)
            _center_text("THREE BONES", self.pygame.Rect(rect.left + 8, rect.top + 4, rect.w - 16, self.cell_px), gold, self._ui_bold_font)
        elif service == "bloom_cards":
            cards = list(payload.get("player_cards", payload.get("garden_cards", ())) or ())
            house = list(payload.get("house_cards", ()) or ())
            top = rect.top + self.cell_px + 4
            card_count = max(3, min(6, len(cards) if cards else 3))
            card_w = max(self.cell_px * 2, min(self.cell_px * 4, (rect.w - self.cell_px * 2) // card_count))
            card_h = max(self.cell_px * 3, min(rect.h - self.cell_px * 2, card_w + self.cell_px))
            gap = max(3, min(self.cell_px // 2, (rect.w - (card_w * card_count) - self.cell_px) // max(1, card_count - 1)))
            start_x = rect.centerx - ((card_w * card_count) + (gap * (card_count - 1))) // 2
            display_cards = cards[:card_count] if cards else ({}, {}, {})
            for idx, card in enumerate(display_cards):
                _draw_bloom_card(self.pygame.Rect(start_x + idx * (card_w + gap), top, card_w, card_h), card)
            if house:
                hidden_w = max(self.cell_px * 2, card_w - self.cell_px // 2)
                hidden_h = max(self.cell_px * 2, card_h - self.cell_px)
                hx = rect.right - hidden_w * 2 - gap - 8
                hy = rect.top + 6
                _draw_bloom_card(self.pygame.Rect(hx, hy, hidden_w, hidden_h), house[0], hidden=True)
                _draw_bloom_card(self.pygame.Rect(hx + hidden_w + gap, hy, hidden_w, hidden_h), house[-1], hidden=True)
            _center_text("BLOOM CARDS", self.pygame.Rect(rect.left + 8, rect.bottom - self.cell_px - 3, rect.w - 16, self.cell_px), gold, self._ui_bold_font)
        elif service == "crash":
            _draw_crash()
        elif service == "plinko":
            board = rect.inflate(-self.cell_px, -self.cell_px // 2)
            rows = 6
            for row in range(rows):
                count = row + 3
                y_pos = board.top + self.cell_px + int((board.h - self.cell_px * 2) * (row / max(1, rows - 1)))
                for idx in range(count):
                    x_pos = board.left + int(board.w * ((idx + 1) / (count + 1)))
                    self.pygame.draw.circle(self.surface, gold, (x_pos, y_pos), max(2, self.cell_px // 8))
            path = list(payload.get("path", ()) or ())
            if path:
                last = path[-1]
                lane_count = max(1, 7)
                ball_x = board.left + int(board.w * ((int(last) + 1) / (lane_count + 1)))
                ball_y = board.bottom - self.cell_px
            else:
                ball_x = board.centerx
                ball_y = board.top + self.cell_px // 2
            self.pygame.draw.circle(self.surface, cursor, (ball_x, ball_y), max(4, self.cell_px // 4))
            _text("PLINKO", board.left + 6, board.top + 4, gold, self._ui_bold_font)
        elif service == "slots":
            reels = list(payload.get("reels", ()) or ("BELL", "BAR", "7"))
            reel_w = max(self.cell_px * 3, min(self.cell_px * 6, (rect.w - self.cell_px * 3) // max(1, len(reels))))
            reel_h = max(self.cell_px * 3, rect.h - self.cell_px * 2)
            start_x = rect.centerx - ((reel_w * len(reels)) + (self.cell_px * (len(reels) - 1))) // 2
            top = rect.top + (rect.h - reel_h) // 2
            for idx, symbol in enumerate(reels[:5]):
                reel = self.pygame.Rect(start_x + idx * (reel_w + self.cell_px), top, reel_w, reel_h)
                self.pygame.draw.rect(self.surface, (232, 225, 202), reel, border_radius=max(2, self.cell_px // 5))
                self.pygame.draw.rect(self.surface, gold, reel, 2, border_radius=max(2, self.cell_px // 5))
                _center_text(str(symbol).replace("_", " ")[:7], reel, red if str(symbol).upper() == "7" else black, self._ui_bold_font)
        else:
            _center_text(str(service).replace("_", " ").title(), rect, gold, self._ui_bold_font)
        return used_cells

    def _is_close_event(self, event):
        close_types = {self.pygame.QUIT}
        window_close = getattr(self.pygame, "WINDOWCLOSE", None)
        if window_close is not None:
            close_types.add(window_close)
        return event.type in close_types

    def _mark_close_requested(self):
        self._close_requested = True

    def close_requested(self):
        return bool(self._close_requested)

    def consume_close_requested(self):
        requested = bool(self._close_requested)
        self._close_requested = False
        return requested

    def _map_key(self, event):
        if self._is_close_event(event):
            self._mark_close_requested()
            return ord("Q")
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
        if key == self.pygame.K_PAGEUP:
            return KEY_PAGE_UP
        if key == self.pygame.K_PAGEDOWN:
            return KEY_PAGE_DOWN
        if key == self.pygame.K_HOME:
            return KEY_HOME
        if key == self.pygame.K_END:
            return KEY_END
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

    def _normalized_axis_value(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        if abs(value) > 1.0:
            value = value / (32767.0 if value > 0 else 32768.0)
        return max(-1.0, min(1.0, value))

    def _axis_direction(self, value):
        value = self._normalized_axis_value(value)
        if value >= 0.55:
            return "positive"
        if value <= -0.55:
            return "negative"
        return ""

    def _controller_dpad_delta(self, instance_id):
        dx = 0
        dy = 0
        for button, delta in _CONTROLLER_DPAD_DELTAS.items():
            if not self._controller_button_state.get((int(instance_id), button)):
                continue
            dx += int(delta[0])
            dy += int(delta[1])
        return (max(-1, min(1, dx)), max(-1, min(1, dy)))

    def _raw_hat_delta(self):
        dx = 0
        dy = 0
        for value in self._raw_hat_state.values():
            try:
                hx = int(value[0])
                hy = int(value[1])
            except (TypeError, ValueError, IndexError):
                continue
            dx += hx
            # Pygame hats use positive Y for up; the game grid uses negative Y.
            dy -= hy
        return (max(-1, min(1, dx)), max(-1, min(1, dy)))

    def _axis_pair_delta(self, x_value, y_value):
        x_value = self._normalized_axis_value(x_value)
        y_value = self._normalized_axis_value(y_value)
        dx = -1 if x_value <= -CONTROLLER_DEADZONE else 1 if x_value >= CONTROLLER_DEADZONE else 0
        dy = -1 if y_value <= -CONTROLLER_DEADZONE else 1 if y_value >= CONTROLLER_DEADZONE else 0
        return (dx, dy)

    def _right_stick_delta(self, x_value, y_value):
        x_value = self._normalized_axis_value(x_value)
        y_value = self._normalized_axis_value(y_value)
        dx = -1 if x_value <= -_CONTROLLER_LOOK_DEADZONE else 1 if x_value >= _CONTROLLER_LOOK_DEADZONE else 0
        dy = -1 if y_value <= -_CONTROLLER_LOOK_DEADZONE else 1 if y_value >= _CONTROLLER_LOOK_DEADZONE else 0
        return (dx, dy)

    def _controller_input_instance_ids(self):
        ids = {int(instance_id) for instance_id in tuple(self._controller_devices.keys())}
        for key in tuple(self._controller_button_state.keys()) + tuple(self._controller_axis_state.keys()):
            if not isinstance(key, tuple) or not key:
                continue
            try:
                ids.add(int(key[0]))
            except (TypeError, ValueError):
                continue
        return tuple(sorted(ids))

    def _controller_diagonal_filter_active(self):
        for instance_id in self._controller_input_instance_ids():
            if self._controller_button_state.get((int(instance_id), "left_shoulder")):
                return True
        return False

    def _active_chord_modifiers(self, instance_id=None, *, source="controller"):
        modifiers = []
        if source == "joystick":
            ids = [instance_id] if instance_id is not None else tuple(self._raw_joysticks.keys())
            for raw_id in ids:
                try:
                    raw_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if self._normalized_axis_value(self._raw_axis_state.get((raw_id, 4), 0.0)) >= 0.55:
                    modifiers.append("left_trigger")
                if self._normalized_axis_value(self._raw_axis_state.get((raw_id, 5), 0.0)) >= 0.55:
                    modifiers.append("right_trigger")
        else:
            ids = [instance_id] if instance_id is not None else self._controller_input_instance_ids()
            for controller_id in ids:
                try:
                    controller_id = int(controller_id)
                except (TypeError, ValueError):
                    continue
                if self._normalized_axis_value(self._controller_axis_state.get((controller_id, "left_trigger"), 0.0)) >= 0.55:
                    modifiers.append("left_trigger")
                if self._normalized_axis_value(self._controller_axis_state.get((controller_id, "right_trigger"), 0.0)) >= 0.55:
                    modifiers.append("right_trigger")
        return tuple(sorted(set(modifiers)))

    def _with_chord_modifiers(self, physical, instance_id=None, *, source="controller"):
        if not isinstance(physical, dict):
            return physical
        modifiers = self._active_chord_modifiers(instance_id, source=source)
        if modifiers:
            physical = dict(physical)
            physical["modifiers"] = modifiers
        return physical

    def _filter_controller_delta(self, delta):
        try:
            dx = max(-1, min(1, int(delta[0])))
            dy = max(-1, min(1, int(delta[1])))
        except (TypeError, ValueError, IndexError):
            return (0, 0)
        if self._controller_diagonal_filter_active() and not (dx and dy):
            return (0, 0)
        return (dx, dy)

    def _controller_movement_delta(self):
        delta, _source = self._controller_movement_delta_with_source()
        return delta

    def _controller_movement_delta_with_source(self):
        for instance_id in self._controller_input_instance_ids():
            delta = self._filter_controller_delta(self._controller_dpad_delta(instance_id))
            if delta != (0, 0):
                return delta, "digital"
        raw_hat = self._filter_controller_delta(self._raw_hat_delta())
        if raw_hat != (0, 0):
            return raw_hat, "digital"

        for instance_id in self._controller_input_instance_ids():
            delta = self._filter_controller_delta(
                self._axis_pair_delta(
                    self._controller_axis_state.get((instance_id, "left_x"), 0.0),
                    self._controller_axis_state.get((instance_id, "left_y"), 0.0),
                )
            )
            if delta != (0, 0):
                return delta, "axis"
        for instance_id in tuple(self._raw_joysticks.keys()):
            delta = self._filter_controller_delta(
                self._axis_pair_delta(
                    self._raw_axis_state.get((instance_id, 0), 0.0),
                    self._raw_axis_state.get((instance_id, 1), 0.0),
                )
            )
            if delta != (0, 0):
                return delta, "axis"
        return (0, 0), ""

    def _movement_physical_input(self, delta, *, source="controller"):
        try:
            dx = max(-1, min(1, int(delta[0])))
            dy = max(-1, min(1, int(delta[1])))
        except (TypeError, ValueError, IndexError):
            return None
        if not (dx or dy):
            return None
        return {
            "kind": "axis",
            "axis": "left_stick",
            "direction": f"{dx},{dy}",
            "value": f"{dx},{dy}",
            "dx": dx,
            "dy": dy,
            "source": source,
        }

    def _right_stick_physical_input(self, delta, *, source="controller"):
        try:
            dx = max(-1, min(1, int(delta[0])))
            dy = max(-1, min(1, int(delta[1])))
        except (TypeError, ValueError, IndexError):
            return None
        if not (dx or dy):
            return None
        return {
            "kind": "axis",
            "axis": "right_stick",
            "direction": f"{dx},{dy}",
            "value": f"{dx},{dy}",
            "dx": dx,
            "dy": dy,
            "source": source,
        }

    def _controller_has_left_stick(self, instance_id):
        try:
            instance_id = int(instance_id)
        except (TypeError, ValueError):
            return False
        if instance_id in self._controller_devices:
            return True
        return (
            (instance_id, "left_x") in self._controller_axis_state
            or (instance_id, "left_y") in self._controller_axis_state
        )

    def _raw_joystick_has_left_stick(self, instance_id):
        try:
            instance_id = int(instance_id)
        except (TypeError, ValueError):
            return False
        joystick = self._raw_joysticks.get(instance_id)
        getter = getattr(joystick, "get_numaxes", None)
        if callable(getter):
            try:
                if int(getter()) >= 4:
                    return True
            except Exception:
                pass
        return (instance_id, 0) in self._raw_axis_state or (instance_id, 1) in self._raw_axis_state

    def _controller_right_stick_delta_with_source(self):
        for instance_id in self._controller_input_instance_ids():
            if not self._controller_has_left_stick(instance_id):
                continue
            delta = self._right_stick_delta(
                self._controller_axis_state.get((instance_id, "right_x"), 0.0),
                self._controller_axis_state.get((instance_id, "right_y"), 0.0),
            )
            if delta != (0, 0):
                return delta, "controller"
        for instance_id in tuple(self._raw_joysticks.keys()) + tuple({key[0] for key in self._raw_axis_state.keys()}):
            if not self._raw_joystick_has_left_stick(instance_id):
                continue
            delta = self._right_stick_delta(
                self._raw_axis_state.get((instance_id, 2), 0.0),
                self._raw_axis_state.get((instance_id, 3), 0.0),
            )
            if delta != (0, 0):
                return delta, "joystick"
        return (0, 0), ""

    def _controller_right_stick_input_for_instance(self, instance_id, *, source="controller"):
        if source == "joystick":
            if not self._raw_joystick_has_left_stick(instance_id):
                self._input_debug("right_stick_drop", instance_id=int(instance_id), source=source, reason="no_left_stick")
                return None
            delta = self._right_stick_delta(
                self._raw_axis_state.get((int(instance_id), 2), 0.0),
                self._raw_axis_state.get((int(instance_id), 3), 0.0),
            )
        else:
            if not self._controller_has_left_stick(instance_id):
                self._input_debug("right_stick_drop", instance_id=int(instance_id), source=source, reason="no_left_stick")
                return None
            delta = self._right_stick_delta(
                self._controller_axis_state.get((int(instance_id), "right_x"), 0.0),
                self._controller_axis_state.get((int(instance_id), "right_y"), 0.0),
            )
        physical = self._right_stick_physical_input(delta, source=source)
        if physical is None:
            self._input_debug("right_stick_center", instance_id=int(instance_id), source=source)
            self._last_controller_look_delta = (0, 0)
            self._last_controller_look_at = 0.0
            self._next_controller_look_repeat_at = 0.0
            return None
        if delta == self._last_controller_look_delta:
            self._input_debug("right_stick_edge_drop", instance_id=int(instance_id), source=source, delta=delta, reason="same_delta")
            return None
        self._prime_controller_look_repeat_delay(delta)
        self._input_debug("right_stick_edge", instance_id=int(instance_id), source=source, delta=delta, physical=physical)
        return physical

    def _controller_repeat_input(self):
        delta, source_kind = self._controller_movement_delta_with_source()
        now = time.monotonic()
        if delta == (0, 0):
            self._last_controller_move_delta = (0, 0)
            self._last_controller_move_at = 0.0
            self._next_controller_repeat_at = 0.0
            return None
        if source_kind == "digital" and self._active_chord_modifiers():
            return None
        repeat_delay = _CONTROLLER_DIGITAL_REPEAT_DELAY if source_kind == "digital" else CONTROLLER_REPEAT_DELAY
        repeat_interval = _CONTROLLER_DIGITAL_REPEAT_INTERVAL if source_kind == "digital" else CONTROLLER_REPEAT_INTERVAL
        if delta != self._last_controller_move_delta:
            self._last_controller_move_delta = delta
            self._last_controller_move_at = now
            self._next_controller_repeat_at = now + repeat_delay
            physical = self._movement_physical_input(delta, source=source_kind or "controller")
            self._input_debug("movement_repeat_prime", delta=delta, source=source_kind, delay=round(float(repeat_delay), 4), physical=physical)
            return physical
        if now >= float(self._next_controller_repeat_at or 0.0):
            self._next_controller_repeat_at = now + repeat_interval
            physical = self._movement_physical_input(delta, source=source_kind or "controller")
            self._input_debug("movement_repeat", delta=delta, source=source_kind, interval=round(float(repeat_interval), 4), physical=physical)
            return physical
        return None

    def _controller_look_repeat_input(self):
        delta, source_kind = self._controller_right_stick_delta_with_source()
        now = time.monotonic()
        if delta == (0, 0):
            self._last_controller_look_delta = (0, 0)
            self._last_controller_look_at = 0.0
            self._next_controller_look_repeat_at = 0.0
            return None
        if delta != self._last_controller_look_delta:
            self._last_controller_look_delta = delta
            self._last_controller_look_at = now
            self._next_controller_look_repeat_at = now + _CONTROLLER_LOOK_REPEAT_DELAY
            physical = self._right_stick_physical_input(delta, source=source_kind or "controller")
            self._input_debug("look_repeat_prime", delta=delta, source=source_kind, delay=round(float(_CONTROLLER_LOOK_REPEAT_DELAY), 4), physical=physical)
            return physical
        if now >= float(self._next_controller_look_repeat_at or 0.0):
            self._next_controller_look_repeat_at = now + _CONTROLLER_LOOK_REPEAT_INTERVAL
            physical = self._right_stick_physical_input(delta, source=source_kind or "controller")
            self._input_debug("look_repeat", delta=delta, source=source_kind, interval=round(float(_CONTROLLER_LOOK_REPEAT_INTERVAL), 4), physical=physical)
            return physical
        return None

    def _prime_controller_repeat_delay(self, delta):
        try:
            dx = max(-1, min(1, int(delta[0])))
            dy = max(-1, min(1, int(delta[1])))
        except (TypeError, ValueError, IndexError):
            return
        if not (dx or dy):
            return
        now = time.monotonic()
        self._last_controller_move_delta = (dx, dy)
        self._last_controller_move_at = now
        self._next_controller_repeat_at = now + _CONTROLLER_DIGITAL_REPEAT_DELAY

    def _prime_controller_look_repeat_delay(self, delta):
        try:
            dx = max(-1, min(1, int(delta[0])))
            dy = max(-1, min(1, int(delta[1])))
        except (TypeError, ValueError, IndexError):
            return
        if not (dx or dy):
            return
        now = time.monotonic()
        self._last_controller_look_delta = (dx, dy)
        self._last_controller_look_at = now
        self._next_controller_look_repeat_at = now + _CONTROLLER_LOOK_REPEAT_DELAY

    def _button_press_is_duplicate(self, state, accepted_at, key, *, pressed, window=_CONTROLLER_BUTTON_DEDUPE_SECONDS, accept_key=None):
        accept_key = key if accept_key is None else accept_key
        now = time.monotonic()
        if not pressed:
            state[key] = False
            self._input_debug("button_release", key=key)
            return True
        was_pressed = bool(state.get(key))
        state[key] = True
        try:
            last_at = float(accepted_at.get(accept_key, 0.0) or 0.0)
        except (TypeError, ValueError):
            last_at = 0.0
        if was_pressed or (last_at and now - last_at < float(window)):
            self._input_debug(
                "button_dedupe_drop",
                key=key,
                accept_key=accept_key,
                was_pressed=bool(was_pressed),
                age=round(now - last_at, 6) if last_at else None,
                window=float(window),
            )
            return True
        accepted_at[accept_key] = now
        return False

    def _input_source_kind(self, physical):
        if not isinstance(physical, dict):
            return ""
        if str(physical.get("kind", "") or "").strip().lower() == "key":
            return "key"
        source = str(physical.get("source", "") or "").strip().lower()
        return source or "controller"

    def _control_semantic_key(self, physical):
        key = self._input_to_legacy_key(physical)
        try:
            key = int(key)
        except (TypeError, ValueError):
            return None
        if key in _CONTROL_SEMANTIC_DEDUPE_KEYS:
            return key
        return None

    def _control_semantic_duplicate(self, physical):
        semantic_key = self._control_semantic_key(physical)
        if semantic_key is None:
            return False
        source = self._input_source_kind(physical)
        now = time.monotonic()
        for queued in self.input_queue:
            if self._control_semantic_key(queued) != semantic_key:
                continue
            queued_source = self._input_source_kind(queued)
            if source != "key" or queued_source != "key":
                self._input_debug(
                    "semantic_dedupe_drop",
                    semantic_key=int(semantic_key),
                    source=source,
                    queued_source=queued_source,
                    queued_input=queued,
                    physical=physical,
                    reason="queued_equivalent",
                )
                return True
        try:
            last_at = float(self._control_semantic_accept_at.get(semantic_key, 0.0) or 0.0)
        except (TypeError, ValueError):
            last_at = 0.0
        last_source = str(self._control_semantic_accept_source.get(semantic_key, "") or "")
        if last_at and now - last_at < _CONTROL_SEMANTIC_DEDUPE_SECONDS:
            if source != "key" or last_source != "key":
                self._input_debug(
                    "semantic_dedupe_drop",
                    semantic_key=int(semantic_key),
                    source=source,
                    last_source=last_source,
                    age=round(now - last_at, 6),
                    window=float(_CONTROL_SEMANTIC_DEDUPE_SECONDS),
                    physical=physical,
                    reason="recent_equivalent",
                )
                return True
        self._control_semantic_accept_at[semantic_key] = now
        self._control_semantic_accept_source[semantic_key] = source
        return False

    def _axis_press_input(self, key, *, axis, value, device_guid="", source="controller"):
        direction = self._axis_direction(value)
        pressed = bool(direction)
        was_pressed = bool(key in self._controller_axis_pressed or key in self._raw_axis_pressed)
        pressed_store = self._raw_axis_pressed if source == "joystick" else self._controller_axis_pressed
        if not pressed:
            pressed_store.pop(key, None)
            self._input_debug("axis_release", key=key, axis=axis, source=source, value=round(float(value or 0.0), 4))
            return None
        if was_pressed:
            self._input_debug("axis_edge_drop", key=key, axis=axis, source=source, direction=direction, reason="already_pressed")
            return None
        pressed_store[key] = direction
        physical = {
            "kind": "axis",
            "axis": axis,
            "value": direction,
            "direction": direction,
            "source": source,
        }
        if device_guid:
            physical["device_guid"] = device_guid
        return physical

    def _map_controller_button_event(self, event, *, pressed):
        instance_id = int(getattr(event, "which", 0) or 0)
        code = _SDL_CONTROLLER_BUTTONS.get(int(getattr(event, "button", -1)), f"button_{getattr(event, 'button', 0)}")
        key = (instance_id, code)
        modifiers = self._active_chord_modifiers(instance_id, source="controller")
        accept_key = (instance_id, code, modifiers)
        duplicate = self._button_press_is_duplicate(
            self._controller_button_state,
            self._controller_button_accept_at,
            key,
            pressed=pressed,
            accept_key=accept_key,
        )
        if duplicate:
            if pressed and code in _CONTROLLER_DPAD_DELTAS:
                delta = self._filter_controller_delta(self._controller_dpad_delta(instance_id))
                if delta != (0, 0):
                    self._prime_controller_repeat_delay(delta)
            return None
        if code in _CONTROLLER_DPAD_DELTAS:
            if pressed:
                delta = self._filter_controller_delta(self._controller_dpad_delta(instance_id))
                if delta == (0, 0):
                    return None
                self._prime_controller_repeat_delay(delta)
                return self._with_chord_modifiers({
                    "kind": "button",
                    "code": code,
                    "dx": int(delta[0]),
                    "dy": int(delta[1]),
                    "source": "controller",
                }, instance_id, source="controller")
            return None
        if not pressed:
            return None
        return self._with_chord_modifiers(
            {"kind": "button", "code": code, "source": "controller"},
            instance_id,
            source="controller",
        )

    def _map_raw_button_event(self, event, *, pressed):
        instance_id = int(getattr(event, "instance_id", getattr(event, "which", 0)) or 0)
        button = int(getattr(event, "button", 0) or 0)
        key = (instance_id, button)
        modifiers = self._active_chord_modifiers(instance_id, source="joystick")
        accept_key = (instance_id, button, modifiers)
        if self._button_press_is_duplicate(
            self._raw_button_state,
            self._raw_button_accept_at,
            key,
            pressed=pressed,
            accept_key=accept_key,
        ):
            return None
        joystick = self._raw_joysticks.get(instance_id)
        return self._with_chord_modifiers(
            {
                "kind": "button",
                "code": button,
                "device_guid": self._device_guid(joystick, fallback=f"joy{instance_id}"),
                "source": "joystick",
            },
            instance_id,
            source="joystick",
        )

    def _map_event_input(self, event):
        mapped_key = self._map_key(event)
        if mapped_key is not None:
            return {"kind": "key", "code": int(mapped_key)}

        pg = self.pygame
        event_type = event.type
        joy_added = getattr(pg, "JOYDEVICEADDED", None)
        joy_removed = getattr(pg, "JOYDEVICEREMOVED", None)
        controller_added = getattr(pg, "CONTROLLERDEVICEADDED", None)
        controller_removed = getattr(pg, "CONTROLLERDEVICEREMOVED", None)
        if event_type in {joy_added, controller_added}:
            index = int(getattr(event, "device_index", getattr(event, "which", 0)) or 0)
            self._input_debug("controller_device_added", raw_event=self._input_debug_event_fields(event), index=int(index))
            self._open_controller_device(index)
            return None
        if event_type in {joy_removed, controller_removed}:
            instance_id = getattr(event, "instance_id", getattr(event, "which", 0))
            self._input_debug("controller_device_removed", raw_event=self._input_debug_event_fields(event), instance_id=instance_id)
            self._close_controller_device(instance_id)
            return None

        controller_button_down = getattr(pg, "CONTROLLERBUTTONDOWN", None)
        controller_button_up = getattr(pg, "CONTROLLERBUTTONUP", None)
        controller_axis_motion = getattr(pg, "CONTROLLERAXISMOTION", None)
        if event_type == controller_button_down:
            return self._map_controller_button_event(event, pressed=True)
        if event_type == controller_button_up:
            return self._map_controller_button_event(event, pressed=False)
        if event_type == controller_axis_motion:
            instance_id = int(getattr(event, "which", 0) or 0)
            axis = _SDL_CONTROLLER_AXES.get(int(getattr(event, "axis", -1)), f"axis_{getattr(event, 'axis', 0)}")
            value = self._normalized_axis_value(getattr(event, "value", 0.0))
            self._controller_axis_state[(instance_id, axis)] = value
            if axis in {"left_x", "left_y"}:
                return None
            if axis in {"right_x", "right_y"}:
                return self._controller_right_stick_input_for_instance(instance_id, source="controller")
            if axis in {"left_trigger", "right_trigger"}:
                return None
            return self._axis_press_input((instance_id, axis), axis=axis, value=value, source="controller")

        joy_button_down = getattr(pg, "JOYBUTTONDOWN", None)
        joy_button_up = getattr(pg, "JOYBUTTONUP", None)
        joy_axis_motion = getattr(pg, "JOYAXISMOTION", None)
        joy_hat_motion = getattr(pg, "JOYHATMOTION", None)
        if event_type == joy_button_down:
            return self._map_raw_button_event(event, pressed=True)
        if event_type == joy_button_up:
            return self._map_raw_button_event(event, pressed=False)
        if event_type == joy_axis_motion:
            instance_id = int(getattr(event, "instance_id", getattr(event, "which", 0)) or 0)
            axis = int(getattr(event, "axis", 0) or 0)
            value = self._normalized_axis_value(getattr(event, "value", 0.0))
            self._raw_axis_state[(instance_id, axis)] = value
            if axis in {0, 1}:
                return None
            if axis in {2, 3}:
                return self._controller_right_stick_input_for_instance(instance_id, source="joystick")
            if axis in {4, 5}:
                return None
            joystick = self._raw_joysticks.get(instance_id)
            return self._axis_press_input(
                (instance_id, axis),
                axis=axis,
                value=value,
                device_guid=self._device_guid(joystick, fallback=f"joy{instance_id}"),
                source="joystick",
            )
        if event_type == joy_hat_motion:
            instance_id = int(getattr(event, "instance_id", getattr(event, "which", 0)) or 0)
            hat = int(getattr(event, "hat", 0) or 0)
            value = tuple(getattr(event, "value", (0, 0)) or (0, 0))
            self._raw_hat_state[(instance_id, hat)] = value
            try:
                dx = max(-1, min(1, int(value[0])))
                dy = max(-1, min(1, -int(value[1])))
            except (TypeError, ValueError, IndexError):
                dx = dy = 0
            if not (dx or dy):
                return None
            dedupe_key = (instance_id, hat, dx, dy)
            now = time.monotonic()
            try:
                last_at = float(self._raw_hat_accept_at.get(dedupe_key, 0.0) or 0.0)
            except (TypeError, ValueError):
                last_at = 0.0
            if last_at and now - last_at < _CONTROLLER_HAT_DEDUPE_SECONDS:
                self._prime_controller_repeat_delay((dx, dy))
                return None
            self._raw_hat_accept_at[dedupe_key] = now
            self._prime_controller_repeat_delay((dx, dy))
            joystick = self._raw_joysticks.get(instance_id)
            return self._with_chord_modifiers(
                {
                    "kind": "hat",
                    "hat": f"hat{hat}",
                    "value": f"{dx},{dy}",
                    "direction": f"{dx},{dy}",
                    "dx": dx,
                    "dy": dy,
                    "device_guid": self._device_guid(joystick, fallback=f"joy{instance_id}"),
                    "source": "joystick",
                },
                instance_id,
                source="joystick",
            )
        return None

    def _pump_inputs(self, *, include_repeat=True):
        for event in self.pygame.event.get():
            self._input_debug("raw_event", raw_event=self._input_debug_event_fields(event))
            mapped = self._map_event_input(event)
            self._input_debug("mapped_event", raw_event=self._input_debug_event_fields(event), mapped=mapped)
            if mapped is not None:
                if self._control_semantic_duplicate(mapped):
                    self._input_debug("mapped_event_dropped", mapped=mapped, reason="semantic_dedupe")
                else:
                    self.input_queue.append(mapped)
                    self._input_debug("queued_input", mapped=mapped, queue_len=len(self.input_queue))
        if include_repeat and not self.input_queue:
            repeated = self._controller_repeat_input()
            if repeated is None:
                repeated = self._controller_look_repeat_input()
            if repeated is not None:
                self.input_queue.append(repeated)
                self._input_debug("queued_repeat", mapped=repeated, queue_len=len(self.input_queue))

    def get_input(self):
        self._pump_inputs(include_repeat=True)
        if not self.input_queue:
            return None
        result = self.input_queue.popleft()
        self._input_debug("get_input", result=result, queue_len=len(self.input_queue))
        return result

    def drain_inputs(self):
        self._pump_inputs(include_repeat=True)
        if not self.input_queue:
            return []
        drained = list(self.input_queue)
        self.input_queue.clear()
        self._input_debug("drain_inputs", result=drained, queue_len=0)
        return drained

    def _input_to_legacy_key(self, physical):
        if not isinstance(physical, dict):
            return None
        if physical.get("kind") == "key":
            try:
                return int(physical.get("code"))
            except (TypeError, ValueError):
                return None
        if physical.get("modifiers"):
            return None
        if physical.get("kind") == "button":
            code = str(physical.get("code", "") or "").strip().lower()
            if code == "south":
                return 10
            if code == "east":
                return 27
            if code in {"view", "select", "back"}:
                return 9
            if code == "west":
                return ord("b")
            if code == "north":
                return ord("r")
        try:
            dx = int(physical.get("dx", 0) or 0)
            dy = int(physical.get("dy", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            return None
        movement_keys = {
            (-1, -1): ord("q"),
            (0, -1): KEY_UP,
            (1, -1): ord("e"),
            (-1, 0): KEY_LEFT,
            (1, 0): KEY_RIGHT,
            (-1, 1): ord("z"),
            (0, 1): KEY_DOWN,
            (1, 1): ord("c"),
        }
        return movement_keys.get((max(-1, min(1, dx)), max(-1, min(1, dy))))

    def get_key(self):
        physical = self.get_input()
        return self._input_to_legacy_key(physical)

    def drain_keys(self):
        inputs = self.drain_inputs()
        keys = [self._input_to_legacy_key(row) for row in inputs]
        return [key for key in keys if key is not None]

    def pump_window(self):
        self.pygame.event.pump()

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
        self.pygame.event.pump()
        self.pygame.display.flip()

    def close(self):
        if self._input_debug_file is not None:
            self._input_debug("view_close")
            try:
                self._input_debug_file.close()
            except OSError:
                pass
            self._input_debug_file = None
        self.pygame.quit()
