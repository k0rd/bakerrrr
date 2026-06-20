import curses
import time

from game.appearance_palette import curses_palette_entries
from game.world_palette import curses_world_palette_entries
from ui.input_keys import ENTER_KEYS

class CursesView:

    def __init__(self, stdscr):
        self.scr = stdscr
        self.scr.nodelay(True)
        self.scr.keypad(True)
        self.color_enabled = False
        self.palette = {"default": 0}
        self.palette_attrs = {"default": 0}
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self._init_colors()
        self._animation_tick = 0
        self._queued_draw_calls = []
        self._draw_sequence = 0

    def _init_colors(self):
        if not curses.has_colors():
            return

        try:
            curses.start_color()
        except curses.error:
            return

        self.color_enabled = True
        try:
            curses.use_default_colors()
        except curses.error:
            pass

        next_pair = 1

        def _register(name, fg, bg=-1, attrs=0):
            nonlocal next_pair
            try:
                curses.init_pair(next_pair, fg, bg)
            except curses.error:
                return
            self.palette[str(name)] = next_pair
            self.palette_attrs[str(name)] = int(attrs or 0)
            next_pair += 1

        _register("player", curses.COLOR_CYAN)
        _register("human", curses.COLOR_WHITE)
        _register("guard", curses.COLOR_BLUE)
        _register("scout", curses.COLOR_GREEN)
        _register("feline", curses.COLOR_YELLOW)
        _register("canine", curses.COLOR_WHITE)
        _register("avian", curses.COLOR_MAGENTA)
        _register("insect", curses.COLOR_GREEN)
        _register("rodent", curses.COLOR_YELLOW)
        _register("reptile", curses.COLOR_GREEN)
        _register("amphibian", curses.COLOR_CYAN)
        _register("fish", curses.COLOR_CYAN)
        _register("ungulate", curses.COLOR_YELLOW)
        _register("other", curses.COLOR_MAGENTA)

        colors = int(getattr(curses, "COLORS", 0) or 0)
        limited_color_map = {
            "white": curses.COLOR_WHITE,
            "blue": curses.COLOR_BLUE,
            "cyan": curses.COLOR_CYAN,
            "green": curses.COLOR_GREEN,
            "yellow": curses.COLOR_YELLOW,
            "red": curses.COLOR_RED,
            "magenta": curses.COLOR_MAGENTA,
        }

        def _attrs_from_names(names):
            attrs = 0
            for name in tuple(names or ()):
                token = str(name or "").strip().lower()
                if token == "bold":
                    attrs |= getattr(curses, "A_BOLD", 0)
                elif token == "dim":
                    attrs |= getattr(curses, "A_DIM", 0)
                elif token == "underline":
                    attrs |= getattr(curses, "A_UNDERLINE", 0)
                elif token == "reverse":
                    attrs |= getattr(curses, "A_REVERSE", 0)
            return attrs

        def _register_palette_entries(entries):
            for name, row in entries.items():
                fg = row.get("fg") if isinstance(row, dict) else None
                attrs = _attrs_from_names(row.get("attrs", ())) if isinstance(row, dict) else 0
                if isinstance(fg, str):
                    fg = limited_color_map.get(fg, curses.COLOR_WHITE)
                _register(name, int(fg), attrs=attrs)

        def _register_appearance_palette():
            _register_palette_entries(curses_palette_entries(colors))

        def _register_world_palette():
            _register_palette_entries(curses_world_palette_entries(colors))

        if colors >= 256:
            _register_world_palette()
            _register("feature_door", 186)
            _register("feature_window", 117)
            _register("feature_breach", 203)
            _register("hazard_fire", 209)
            _register("hazard_smoke", 245)
            _register("survival_meter_high", 117)
            _register("survival_meter_mid", 120)
            _register("survival_meter_low", 203)
            _register("transit", 229)
            _register("property_building", 223)
            _register("property_fixture", 111)
            _register("property_asset", 221)
            _register("property_service", 151)
            _register("vehicle_parked", 250)
            _register("vehicle_new", 220)
            _register("vehicle_player", 45)
            _register("vehicle_police", 33)
            _register("vehicle_paint_red", 167)
            _register("vehicle_paint_blue", 111)
            _register("vehicle_paint_green", 71)
            _register("vehicle_paint_white", 252)
            _register("vehicle_paint_black", 238)
            _register("vehicle_paint_teal", 80)
            _register("vehicle_paint_rust", 130)
            _register("vehicle_paint_brown", 137)
            _register("vehicle_paint_yellow", 221)
            _register("item_ground", 221)
            _register("item_token", 229)
            _register("item_tool", 180)
            _register("item_medical", 121)
            _register("item_restricted", 215)
            _register("item_illegal", 203)
            _register("item_outline", 235)
            _register("item_highlight", 230)
            _register("inventory_equipped_clothing", 153)
            _register("inventory_equipped_weapon", 209)
            _register("inventory_equipped_consequence", 177)
            _register("inventory_critical_quest", 123)
            _register("projectile", 203)
            _register("objective", 226)
            _register("human_charcoal", 250)
            _register("human_olive", 107)
            _register("human_denim", 110)
            _register("human_accent", 221)
            _register("human_monochrome", 255)
            _register("human_rust", 173)
            _register("human_slate", 109)
            _register("human_wine", 175)
            _register_appearance_palette()
            _register("actor_outline", 235)
            _register("actor_highlight", 195)
            _register("cat_orange", 208)
            _register("cat_black", 238)
            _register("cat_tabby", 180)
            _register("cat_calico", 215)
            _register("cat_white", 15)
            _register("cat_gray", 246)
            _register("cat_tuxedo", 250)
            _register("cat_purple", 135)
            _register("casino_felt", 29)
            _register("casino_gold", 221)
            _register("casino_red", 203)
            _register("casino_black", 240)
            _register("casino_chip", 45)
            _register("casino_cursor", 159)
        else:
            _register_world_palette()
            _register("feature_door", curses.COLOR_YELLOW)
            _register("feature_window", curses.COLOR_CYAN)
            _register("feature_breach", curses.COLOR_RED)
            _register("hazard_fire", curses.COLOR_RED)
            _register("hazard_smoke", curses.COLOR_WHITE)
            _register("survival_meter_high", curses.COLOR_CYAN)
            _register("survival_meter_mid", curses.COLOR_GREEN)
            _register("survival_meter_low", curses.COLOR_RED)
            _register("transit", curses.COLOR_YELLOW)
            _register("property_building", curses.COLOR_WHITE)
            _register("property_fixture", curses.COLOR_CYAN)
            _register("property_asset", curses.COLOR_YELLOW)
            _register("property_service", curses.COLOR_GREEN)
            _register("vehicle_parked", curses.COLOR_WHITE)
            _register("vehicle_new", curses.COLOR_YELLOW)
            _register("vehicle_player", curses.COLOR_CYAN)
            _register("vehicle_police", curses.COLOR_BLUE)
            _register("vehicle_paint_red", curses.COLOR_RED)
            _register("vehicle_paint_blue", curses.COLOR_BLUE)
            _register("vehicle_paint_green", curses.COLOR_GREEN)
            _register("vehicle_paint_white", curses.COLOR_WHITE)
            _register("vehicle_paint_black", curses.COLOR_WHITE)
            _register("vehicle_paint_teal", curses.COLOR_CYAN)
            _register("vehicle_paint_rust", curses.COLOR_YELLOW)
            _register("vehicle_paint_brown", curses.COLOR_YELLOW)
            _register("vehicle_paint_yellow", curses.COLOR_YELLOW)
            _register("item_ground", curses.COLOR_YELLOW)
            _register("item_token", curses.COLOR_YELLOW)
            _register("item_tool", curses.COLOR_WHITE)
            _register("item_medical", curses.COLOR_GREEN)
            _register("item_restricted", curses.COLOR_MAGENTA)
            _register("item_illegal", curses.COLOR_RED)
            _register("item_outline", curses.COLOR_WHITE, attrs=getattr(curses, "A_DIM", 0))
            _register("item_highlight", curses.COLOR_YELLOW, attrs=getattr(curses, "A_BOLD", 0))
            _register("inventory_equipped_clothing", curses.COLOR_CYAN)
            _register("inventory_equipped_weapon", curses.COLOR_YELLOW)
            _register("inventory_equipped_consequence", curses.COLOR_MAGENTA)
            _register("inventory_critical_quest", curses.COLOR_CYAN)
            _register("projectile", curses.COLOR_RED)
            _register("objective", curses.COLOR_YELLOW)
            _register("human_charcoal", curses.COLOR_WHITE)
            _register("human_olive", curses.COLOR_GREEN)
            _register("human_denim", curses.COLOR_CYAN)
            _register("human_accent", curses.COLOR_YELLOW)
            _register("human_monochrome", curses.COLOR_WHITE)
            _register("human_rust", curses.COLOR_YELLOW)
            _register("human_slate", curses.COLOR_BLUE)
            _register("human_wine", curses.COLOR_MAGENTA)
            _register_appearance_palette()
            _register("actor_outline", curses.COLOR_WHITE, attrs=getattr(curses, "A_DIM", 0))
            _register("actor_highlight", curses.COLOR_CYAN, attrs=getattr(curses, "A_BOLD", 0))
            _register("cat_orange", curses.COLOR_YELLOW)
            _register("cat_black", curses.COLOR_WHITE)
            _register("cat_tabby", curses.COLOR_YELLOW)
            _register("cat_calico", curses.COLOR_MAGENTA)
            _register("cat_white", curses.COLOR_WHITE)
            _register("cat_gray", curses.COLOR_CYAN)
            _register("cat_tuxedo", curses.COLOR_WHITE)
            _register("cat_purple", curses.COLOR_MAGENTA)
            _register("casino_felt", curses.COLOR_GREEN)
            _register("casino_gold", curses.COLOR_YELLOW)
            _register("casino_red", curses.COLOR_RED)
            _register("casino_black", curses.COLOR_WHITE)
            _register("casino_chip", curses.COLOR_CYAN)
            _register("casino_cursor", curses.COLOR_CYAN)

    def _attr_for(self, color):
        if not self.color_enabled or color is None:
            return 0

        if isinstance(color, str):
            key = str(color)
            pair = int(self.palette.get(key, self.palette.get("default", 0)))
            if pair <= 0:
                return 0
            return curses.color_pair(pair) | int(self.palette_attrs.get(key, 0) or 0)

        try:
            pair = int(color)
        except (TypeError, ValueError):
            return 0
        if pair <= 0:
            return 0
        return curses.color_pair(pair)

    def size(self):
        h, w = self.scr.getmaxyx()
        return w, h

    def clear(self):
        self.scr.erase()
        self._queued_draw_calls.clear()
        self._draw_sequence = 0

    def begin_frame(self, *, animation_tick=None):
        try:
            self._animation_tick = int(animation_tick or 0)
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
        layer_key = str(queued.get("layer", "") or "").strip().lower() or "ground_overlay"
        layer_order = {
            "terrain": 0,
            "ground_overlay": 10,
            "item": 20,
            "actor": 30,
            "fx": 40,
            "ui_overlay": 50,
        }.get(layer_key, 10)
        try:
            priority = int(queued.get("priority", 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        return (layer_order, priority, int(queued.get("sequence", 0) or 0))

    def _flush_queued_draws(self):
        if not self._queued_draw_calls:
            return
        queued = sorted(self._queued_draw_calls, key=self._queued_draw_sort_key)
        self._queued_draw_calls.clear()
        for call in queued:
            kind = call.get("kind")
            if kind == "glyph":
                self._draw_now(
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

    def _clip_draw_region(self, x, y, text=""):
        width, height = self.size()
        x = int(x)
        y = int(y)
        if y < 0 or y >= height:
            return None

        if text is None:
            text = ""
        text = str(text)

        if x >= width:
            return None

        if x < 0:
            clip = min(len(text), -x)
            text = text[clip:]
            x = 0

        if x >= width:
            return None

        available = width - x
        if text:
            text = text[:available]
            if not text:
                return None

        return x, y, text

    def _attrs_for_overlay_semantics(self, overlays):
        attr = 0
        for overlay in overlays or ():
            if not isinstance(overlay, dict) or not bool(overlay.get("visible", True)):
                continue
            semantic_id = str(overlay.get("semantic_id", "") or "").strip().lower()
            if semantic_id in {"ui_actor_threat", "ui_property_restricted"}:
                attr |= int(getattr(curses, "A_BOLD", 0) or 0)
                attr |= int(getattr(curses, "A_REVERSE", 0) or 0)
            elif semantic_id == "ui_property_locked":
                attr |= int(getattr(curses, "A_BOLD", 0) or 0)
                attr |= int(getattr(curses, "A_UNDERLINE", 0) or 0)
            elif semantic_id in {
                "ui_actor_ally",
                "ui_actor_contact",
                "ui_property_owned",
                "ui_property_public",
            }:
                attr |= int(getattr(curses, "A_BOLD", 0) or 0)
        return attr

    def _draw_now(self, x, y, glyph, color=None, attrs=0, semantic_id=None, effects=None, overlays=None):
        region = self._clip_draw_region(x, y, str(glyph)[:1] or " ")
        if region is None:
            return
        try:
            x, y, text = region
            attr = self._attr_for(color) | int(attrs) | self._attrs_for_overlay_semantics(overlays)
            effect_set = {
                str(effect).strip().lower()
                for effect in (effects or ())
                if str(effect).strip()
            }
            if "blink" in effect_set:
                attr |= int(getattr(curses, "A_BLINK", 0) or 0)
            self.scr.addch(y, x, text[0], attr)
        except curses.error:
            pass

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
        self._draw_now(x, y, glyph, color=color, attrs=attrs, semantic_id=semantic_id, effects=effects, overlays=overlays)

    def _draw_text_now(self, x, y, text, color=None, attrs=0):
        region = self._clip_draw_region(x, y, text)
        if region is None:
            return
        try:
            x, y, text = region
            attr = self._attr_for(color) | int(attrs)
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass

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
        cursor_x = int(x)
        remaining = None if max_width is None else max(0, int(max_width))
        base_attrs = int(attrs)

        for segment in segments or ():
            if remaining is not None and remaining <= 0:
                break

            if isinstance(segment, dict):
                text = str(segment.get("text", ""))
                color = segment.get("color")
                seg_attrs = int(segment.get("attrs", 0) or 0)
            else:
                text = str(segment)
                color = None
                seg_attrs = 0

            if not text:
                continue

            if remaining is not None:
                text = text[:remaining]
                remaining -= len(text)
            if not text:
                continue

            self._draw_text_now(cursor_x, y, text, color=color, attrs=base_attrs | seg_attrs)
            cursor_x += len(text)

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
        prompt = str(prompt or "")
        detail = str(detail or "")
        title = str(title or "").strip()
        banner = str(banner or "").strip()
        subtitle = str(subtitle or "").strip()

        try:
            curses.curs_set(0)
        except curses.error:
            pass

        while True:
            self.clear()
            width, height = self.size()
            x = 2
            y = 1
            max_width = max(1, width - x - 1)

            def _line(text, *, color="default", attrs=0):
                nonlocal y
                if y >= height:
                    return
                self.draw_text(x, y, str(text or "")[:max_width], color=color, attrs=attrs)
                y += 1

            if banner:
                _line(banner, color="objective", attrs=getattr(curses, "A_BOLD", 0))
            if title:
                _line(title, color="human", attrs=getattr(curses, "A_BOLD", 0))
            if subtitle:
                _line(subtitle, color="default")
            y += 1
            _line(prompt, color="objective", attrs=getattr(curses, "A_BOLD", 0))
            if detail:
                _line(detail, color="default")
            y += 1
            for idx, row in enumerate(rows):
                prefix = ">" if idx == selected else " "
                line = f"{prefix} {idx + 1}. {row['label']}"
                if row["description"]:
                    line = f"{line} - {row['description']}"
                attrs = getattr(curses, "A_REVERSE", 0) if idx == selected else 0
                _line(line, color="player" if idx == selected else "human", attrs=attrs)
            y += 1
            _line("Arrows move | 1-3 choose | Enter confirm | Esc cancel", color="scout")
            self.refresh()

            key = self.get_key()
            if key is None:
                time.sleep(0.01)
                continue
            if key in ENTER_KEYS:
                return rows[selected]["value"]
            if key == 27:
                return None
            if key in (curses.KEY_UP, curses.KEY_LEFT):
                selected = (selected - 1) % len(rows)
                continue
            if key in (curses.KEY_DOWN, curses.KEY_RIGHT):
                selected = (selected + 1) % len(rows)
                continue
            if key in (ord("1"), ord("2"), ord("3")):
                idx = key - ord("1")
                if 0 <= idx < len(rows):
                    return rows[idx]["value"]

    def get_key(self):
        key = self.scr.getch()
        if key == -1:
            return None
        if key in ENTER_KEYS:
            return 10
        return key

    def drain_keys(self):
        keys = []
        while True:
            key = self.get_key()
            if key is None:
                break
            keys.append(key)
        return keys

    def pump_window(self):
        return None

    def refresh(self):
        self._flush_queued_draws()
        self.scr.refresh()
