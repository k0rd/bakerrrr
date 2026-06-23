from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolicPaletteRow:
    key: str
    pygame_rgb: tuple[int, int, int]
    curses_256: int
    curses_limited: str
    curses_attrs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def _row(
    key: str,
    rgb: tuple[int, int, int],
    c256: int,
    limited: str,
    *,
    attrs: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> SymbolicPaletteRow:
    return SymbolicPaletteRow(
        key=str(key),
        pygame_rgb=rgb,
        curses_256=int(c256),
        curses_limited=str(limited),
        curses_attrs=tuple(attrs),
        tags=tuple(tags),
    )


SYMBOLIC_PALETTE: tuple[SymbolicPaletteRow, ...] = (
    _row("player", (100, 220, 255), 45, "cyan", attrs=("bold",), tags=("actor", "player")),
    _row("human", (230, 230, 230), 255, "white", tags=("actor", "human")),
    _row("human_charcoal", (198, 200, 208), 250, "white", tags=("actor", "human", "neutral")),
    _row("human_olive", (166, 181, 118), 107, "green", tags=("actor", "human", "earth")),
    _row("human_denim", (146, 171, 208), 110, "cyan", tags=("actor", "human", "blue")),
    _row("human_accent", (228, 196, 118), 221, "yellow", attrs=("bold",), tags=("actor", "human", "accent")),
    _row("human_monochrome", (238, 238, 238), 255, "white", attrs=("bold",), tags=("actor", "human", "neutral")),
    _row("human_rust", (205, 152, 112), 173, "yellow", tags=("actor", "human", "warm")),
    _row("human_slate", (142, 166, 188), 109, "blue", tags=("actor", "human", "cool")),
    _row("human_wine", (196, 142, 172), 175, "magenta", tags=("actor", "human", "warm")),
    _row("guard", (95, 140, 255), 69, "blue", attrs=("bold",), tags=("actor", "role")),
    _row("scout", (120, 220, 120), 120, "green", attrs=("bold",), tags=("actor", "role")),
    _row("actor_outline", (16, 20, 28), 235, "white", attrs=("dim",), tags=("actor", "support")),
    _row("actor_highlight", (232, 246, 255), 195, "cyan", attrs=("bold",), tags=("actor", "support")),
    _row("actor_shadow", (22, 24, 32), 235, "white", attrs=("dim",), tags=("actor", "support")),
    _row("actor_role_accent", (244, 214, 122), 221, "yellow", attrs=("bold",), tags=("actor", "support")),
    _row("feline", (255, 220, 90), 221, "yellow", tags=("creature",)),
    _row("canine", (220, 220, 220), 250, "white", tags=("creature",)),
    _row("avian", (220, 120, 220), 177, "magenta", attrs=("bold",), tags=("creature",)),
    _row("insect", (110, 200, 110), 107, "green", tags=("creature",)),
    _row("rodent", (205, 170, 105), 180, "yellow", tags=("creature",)),
    _row("reptile", (120, 185, 120), 108, "green", tags=("creature",)),
    _row("amphibian", (100, 210, 190), 116, "cyan", tags=("creature",)),
    _row("fish", (110, 185, 235), 117, "cyan", attrs=("bold",), tags=("creature",)),
    _row("ungulate", (200, 185, 120), 180, "yellow", tags=("creature",)),
    _row("other", (205, 145, 205), 176, "magenta", tags=("creature",)),
    _row("feature_door", (205, 190, 110), 186, "yellow", tags=("feature",)),
    _row("feature_window", (110, 180, 220), 117, "cyan", tags=("feature",)),
    _row("feature_breach", (220, 100, 100), 203, "red", attrs=("bold",), tags=("feature", "damage")),
    _row("hazard_fire", (242, 132, 68), 209, "red", attrs=("bold",), tags=("hazard",)),
    _row("hazard_smoke", (150, 150, 158), 245, "white", attrs=("dim",), tags=("hazard",)),
    _row("survival_meter_high", (100, 170, 240), 117, "cyan", tags=("ui", "survival")),
    _row("survival_meter_mid", (120, 210, 130), 120, "green", tags=("ui", "survival")),
    _row("survival_meter_low", (230, 95, 95), 203, "red", attrs=("bold",), tags=("ui", "survival")),
    _row("transit", (220, 220, 140), 229, "yellow", tags=("feature", "transit")),
    _row("property_building", (220, 210, 190), 223, "white", tags=("property",)),
    _row("property_fixture", (130, 180, 235), 111, "cyan", tags=("property", "fixture")),
    _row("property_asset", (225, 190, 95), 221, "yellow", tags=("property", "asset")),
    _row("property_service", (140, 200, 140), 151, "green", tags=("property", "service")),
    _row("vehicle_parked", (190, 190, 190), 250, "white", tags=("vehicle", "neutral")),
    _row("vehicle_new", (235, 190, 95), 220, "yellow", attrs=("bold",), tags=("vehicle", "status")),
    _row("vehicle_player", (80, 210, 240), 45, "cyan", attrs=("bold",), tags=("vehicle", "player")),
    _row("vehicle_police", (76, 126, 232), 33, "blue", attrs=("bold",), tags=("vehicle", "justice")),
    _row("vehicle_paint_red", (198, 90, 90), 167, "red", tags=("vehicle", "paint")),
    _row("vehicle_paint_blue", (92, 132, 208), 111, "blue", tags=("vehicle", "paint")),
    _row("vehicle_paint_green", (96, 168, 104), 71, "green", tags=("vehicle", "paint")),
    _row("vehicle_paint_white", (215, 215, 215), 252, "white", attrs=("bold",), tags=("vehicle", "paint")),
    _row("vehicle_paint_black", (96, 96, 104), 238, "white", attrs=("dim",), tags=("vehicle", "paint")),
    _row("vehicle_paint_teal", (82, 170, 170), 80, "cyan", attrs=("bold",), tags=("vehicle", "paint")),
    _row("vehicle_paint_rust", (156, 96, 64), 130, "yellow", tags=("vehicle", "paint")),
    _row("vehicle_paint_brown", (150, 118, 82), 137, "yellow", attrs=("dim",), tags=("vehicle", "paint")),
    _row("vehicle_paint_yellow", (214, 186, 86), 221, "yellow", attrs=("bold",), tags=("vehicle", "paint")),
    _row("vehicle_paint_orange", (224, 122, 58), 208, "yellow", attrs=("bold",), tags=("vehicle", "paint")),
    _row("vehicle_paint_purple", (150, 96, 210), 99, "magenta", attrs=("bold",), tags=("vehicle", "paint")),
    _row("vehicle_paint_silver", (190, 202, 208), 250, "white", tags=("vehicle", "paint", "metal")),
    _row("vehicle_paint_cream", (230, 216, 176), 223, "white", attrs=("bold",), tags=("vehicle", "paint")),
    _row("vehicle_paint_charcoal", (72, 78, 88), 238, "white", attrs=("dim",), tags=("vehicle", "paint")),
    _row("vehicle_paint_navy", (54, 78, 142), 25, "blue", tags=("vehicle", "paint")),
    _row("vehicle_paint_olive", (112, 138, 82), 65, "green", tags=("vehicle", "paint")),
    _row("vehicle_glass", (124, 198, 230), 117, "cyan", attrs=("bold",), tags=("vehicle", "support")),
    _row("vehicle_tire", (30, 32, 38), 235, "white", attrs=("dim",), tags=("vehicle", "support")),
    _row("vehicle_light", (255, 240, 156), 229, "yellow", attrs=("bold",), tags=("vehicle", "support")),
    _row("vehicle_tail_light", (238, 72, 72), 203, "red", attrs=("bold",), tags=("vehicle", "support")),
    _row("vehicle_trim", (214, 220, 224), 250, "white", tags=("vehicle", "support")),
    _row("item_ground", (225, 185, 95), 221, "yellow", tags=("item", "generic")),
    _row("item_token", (240, 220, 110), 229, "yellow", attrs=("bold",), tags=("item", "money")),
    _row("item_tool", (200, 170, 120), 180, "white", tags=("item", "tool")),
    _row("item_medical", (120, 220, 140), 121, "green", attrs=("bold",), tags=("item", "medical")),
    _row("item_restricted", (230, 150, 100), 215, "magenta", tags=("item", "restricted")),
    _row("item_illegal", (220, 90, 90), 203, "red", attrs=("bold",), tags=("item", "illegal")),
    _row("item_weapon", (210, 130, 110), 173, "red", tags=("item", "weapon")),
    _row("item_armor", (170, 190, 225), 153, "cyan", tags=("item", "armor")),
    _row("item_food", (220, 185, 105), 180, "yellow", tags=("item", "food")),
    _row("item_drink", (120, 190, 235), 117, "cyan", attrs=("bold",), tags=("item", "drink")),
    _row("item_access", (200, 220, 160), 151, "green", tags=("item", "access")),
    _row("item_objective", (245, 220, 110), 226, "yellow", attrs=("bold",), tags=("item", "objective")),
    _row("item_outline", (18, 22, 28), 235, "white", attrs=("dim",), tags=("item", "support")),
    _row("item_highlight", (248, 242, 204), 230, "yellow", attrs=("bold",), tags=("item", "support")),
    _row("item_metal", (184, 196, 204), 250, "white", tags=("item", "support")),
    _row("item_glass", (154, 220, 238), 123, "cyan", attrs=("bold",), tags=("item", "support")),
    _row("item_paper", (236, 224, 188), 230, "white", attrs=("bold",), tags=("item", "support")),
    _row("item_cloth", (186, 150, 220), 183, "magenta", tags=("item", "support")),
    _row("item_chemical", (146, 236, 174), 121, "green", attrs=("bold",), tags=("item", "support")),
    _row("inventory_equipped_clothing", (145, 205, 215), 153, "cyan", tags=("ui", "inventory")),
    _row("inventory_equipped_weapon", (230, 145, 95), 209, "yellow", tags=("ui", "inventory")),
    _row("inventory_equipped_consequence", (198, 160, 230), 177, "magenta", tags=("ui", "inventory")),
    _row("inventory_critical_quest", (95, 230, 210), 123, "cyan", attrs=("bold",), tags=("ui", "inventory")),
    _row("projectile", (220, 110, 110), 203, "red", attrs=("bold",), tags=("fx",)),
    _row("objective", (245, 220, 110), 226, "yellow", attrs=("bold",), tags=("objective",)),
    _row("cat_orange", (230, 140, 70), 208, "yellow", tags=("creature", "cat")),
    _row("cat_black", (90, 90, 90), 238, "white", attrs=("dim",), tags=("creature", "cat")),
    _row("cat_tabby", (190, 140, 100), 180, "yellow", tags=("creature", "cat")),
    _row("cat_calico", (235, 150, 110), 215, "magenta", tags=("creature", "cat")),
    _row("cat_white", (240, 240, 240), 15, "white", attrs=("bold",), tags=("creature", "cat")),
    _row("cat_gray", (170, 170, 170), 246, "cyan", tags=("creature", "cat")),
    _row("cat_tuxedo", (215, 215, 215), 250, "white", tags=("creature", "cat")),
    _row("cat_purple", (175, 125, 220), 135, "magenta", attrs=("bold",), tags=("creature", "cat")),
    _row("casino_felt", (34, 112, 74), 29, "green", tags=("casino",)),
    _row("casino_gold", (228, 196, 74), 221, "yellow", attrs=("bold",), tags=("casino",)),
    _row("casino_red", (210, 82, 68), 203, "red", attrs=("bold",), tags=("casino",)),
    _row("casino_black", (78, 82, 88), 240, "white", attrs=("dim",), tags=("casino",)),
    _row("casino_chip", (84, 182, 198), 45, "cyan", attrs=("bold",), tags=("casino",)),
    _row("casino_cursor", (198, 240, 214), 159, "cyan", attrs=("bold",), tags=("casino",)),
)

_ROWS_BY_KEY = {row.key: row for row in SYMBOLIC_PALETTE}


def symbolic_palette_keys() -> tuple[str, ...]:
    return tuple(row.key for row in SYMBOLIC_PALETTE)


def palette_row_for_symbolic_key(key: str) -> SymbolicPaletteRow | None:
    return _ROWS_BY_KEY.get(str(key or "").strip().lower())


def pygame_symbolic_palette_entries() -> dict[str, tuple[int, int, int]]:
    return {row.key: row.pygame_rgb for row in SYMBOLIC_PALETTE}


def curses_symbolic_palette_entries(colors: int | None = None) -> dict[str, dict[str, object]]:
    use_256 = int(colors or 0) >= 256
    rows = {}
    for row in SYMBOLIC_PALETTE:
        rows[row.key] = {
            "fg": row.curses_256 if use_256 else row.curses_limited,
            "attrs": () if use_256 else row.curses_attrs,
        }
    return rows
