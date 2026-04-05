import curses

from ui.input_keys import ENTER_KEYS

class CursesView:

    def __init__(self, stdscr):
        self.scr = stdscr
        self.scr.nodelay(True)
        self.scr.keypad(True)
        self.color_enabled = False
        self.palette = {"default": 0}
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

        def _register(name, fg, bg=-1):
            nonlocal next_pair
            try:
                curses.init_pair(next_pair, fg, bg)
            except curses.error:
                return
            self.palette[str(name)] = next_pair
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
        if colors >= 256:
            _register("floor_coarse", 238)
            _register("floor_industrial", 242)
            _register("floor_residential", 250)
            _register("floor_downtown", 252)
            _register("floor_slums", 239)
            _register("floor_corporate", 117)
            _register("floor_military", 110)
            _register("floor_entertainment", 181)
            _register("floor_frontier", 180)
            _register("floor_wilderness", 71)
            _register("floor_coastal", 117)
            _register("building_fill", 240)
            _register("building_edge", 244)
            _register("terrain_block", 238)
            _register("terrain_brush", 108)
            _register("terrain_rock", 245)
            _register("terrain_water", 117)
            _register("terrain_salt", 223)
            _register("terrain_road", 186)
            _register("terrain_trail", 180)
            _register("building_roof", 239)
            _register("building_roof_residential", 250)
            _register("building_roof_storefront", 180)
            _register("building_roof_industrial", 242)
            _register("building_roof_corporate", 117)
            _register("building_roof_civic", 153)
            _register("building_roof_secure", 71)
            _register("building_roof_entertainment", 181)
            _register("feature_door", 186)
            _register("feature_window", 117)
            _register("feature_breach", 203)
            _register("transit", 229)
            _register("property_building", 223)
            _register("property_fixture", 111)
            _register("property_asset", 221)
            _register("property_service", 151)
            _register("vehicle_parked", 250)
            _register("vehicle_new", 220)
            _register("vehicle_player", 45)
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
            _register("projectile", 203)
            _register("objective", 226)
            _register("cat_orange", 208)
            _register("cat_black", 238)
            _register("cat_tabby", 180)
            _register("cat_calico", 215)
            _register("cat_white", 15)
            _register("cat_gray", 246)
            _register("cat_tuxedo", 250)
            _register("cat_purple", 135)
        else:
            _register("floor_coarse", curses.COLOR_BLUE)
            _register("floor_industrial", curses.COLOR_WHITE)
            _register("floor_residential", curses.COLOR_WHITE)
            _register("floor_downtown", curses.COLOR_CYAN)
            _register("floor_slums", curses.COLOR_MAGENTA)
            _register("floor_corporate", curses.COLOR_CYAN)
            _register("floor_military", curses.COLOR_BLUE)
            _register("floor_entertainment", curses.COLOR_YELLOW)
            _register("floor_frontier", curses.COLOR_YELLOW)
            _register("floor_wilderness", curses.COLOR_GREEN)
            _register("floor_coastal", curses.COLOR_CYAN)
            _register("building_fill", curses.COLOR_BLUE)
            _register("building_edge", curses.COLOR_WHITE)
            _register("terrain_block", curses.COLOR_BLUE)
            _register("terrain_brush", curses.COLOR_GREEN)
            _register("terrain_rock", curses.COLOR_WHITE)
            _register("terrain_water", curses.COLOR_CYAN)
            _register("terrain_salt", curses.COLOR_YELLOW)
            _register("terrain_road", curses.COLOR_YELLOW)
            _register("terrain_trail", curses.COLOR_MAGENTA)
            _register("building_roof", curses.COLOR_WHITE)
            _register("building_roof_residential", curses.COLOR_WHITE)
            _register("building_roof_storefront", curses.COLOR_YELLOW)
            _register("building_roof_industrial", curses.COLOR_WHITE)
            _register("building_roof_corporate", curses.COLOR_CYAN)
            _register("building_roof_civic", curses.COLOR_CYAN)
            _register("building_roof_secure", curses.COLOR_GREEN)
            _register("building_roof_entertainment", curses.COLOR_MAGENTA)
            _register("feature_door", curses.COLOR_YELLOW)
            _register("feature_window", curses.COLOR_CYAN)
            _register("feature_breach", curses.COLOR_RED)
            _register("transit", curses.COLOR_YELLOW)
            _register("property_building", curses.COLOR_WHITE)
            _register("property_fixture", curses.COLOR_CYAN)
            _register("property_asset", curses.COLOR_YELLOW)
            _register("property_service", curses.COLOR_GREEN)
            _register("vehicle_parked", curses.COLOR_WHITE)
            _register("vehicle_new", curses.COLOR_YELLOW)
            _register("vehicle_player", curses.COLOR_CYAN)
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
            _register("projectile", curses.COLOR_RED)
            _register("objective", curses.COLOR_YELLOW)
            _register("cat_orange", curses.COLOR_YELLOW)
            _register("cat_black", curses.COLOR_WHITE)
            _register("cat_tabby", curses.COLOR_YELLOW)
            _register("cat_calico", curses.COLOR_MAGENTA)
            _register("cat_white", curses.COLOR_WHITE)
            _register("cat_gray", curses.COLOR_CYAN)
            _register("cat_tuxedo", curses.COLOR_WHITE)
            _register("cat_purple", curses.COLOR_MAGENTA)

    def _attr_for(self, color):
        if not self.color_enabled or color is None:
            return 0

        if isinstance(color, str):
            pair = int(self.palette.get(color, self.palette.get("default", 0)))
            if pair <= 0:
                return 0
            return curses.color_pair(pair)

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

    def _draw_now(self, x, y, glyph, color=None, attrs=0, semantic_id=None, effects=None, overlays=None):
        region = self._clip_draw_region(x, y, str(glyph)[:1] or " ")
        if region is None:
            return
        try:
            x, y, text = region
            attr = self._attr_for(color) | int(attrs)
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

    def refresh(self):
        self._flush_queued_draws()
        self.scr.refresh()
