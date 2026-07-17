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
    _row("human_skin_deep_brown", (92, 58, 45), 52, "yellow", tags=("actor", "human", "skin", "deep")),
    _row("human_skin_rich_brown", (126, 78, 57), 94, "yellow", tags=("actor", "human", "skin", "deep")),
    _row("human_skin_warm_brown", (169, 112, 77), 137, "yellow", tags=("actor", "human", "skin", "warm")),
    _row("human_skin_olive", (178, 143, 99), 143, "yellow", tags=("actor", "human", "skin", "olive")),
    _row("human_skin_golden", (207, 156, 101), 179, "yellow", tags=("actor", "human", "skin", "warm")),
    _row("human_skin_freckled_fair", (226, 184, 151), 181, "yellow", tags=("actor", "human", "skin", "fair")),
    _row("human_skin_pale", (239, 211, 191), 187, "white", tags=("actor", "human", "skin", "fair")),
    _row("human_monochrome", (238, 238, 238), 255, "white", attrs=("bold",), tags=("actor", "human", "neutral")),
    _row("human_rust", (205, 152, 112), 173, "yellow", tags=("actor", "human", "warm")),
    _row("human_slate", (142, 166, 188), 109, "blue", tags=("actor", "human", "cool")),
    _row("human_wine", (196, 142, 172), 175, "magenta", tags=("actor", "human", "warm")),
    _row("human_eye_dark_brown", (76, 51, 42), 52, "yellow", tags=("actor", "human", "eye")),
    _row("human_eye_brown", (119, 78, 54), 94, "yellow", tags=("actor", "human", "eye")),
    _row("human_eye_hazel", (151, 126, 68), 136, "yellow", tags=("actor", "human", "eye")),
    _row("human_eye_gray", (166, 178, 188), 145, "white", tags=("actor", "human", "eye")),
    _row("human_eye_green", (78, 166, 103), 71, "green", tags=("actor", "human", "eye")),
    _row("human_eye_blue", (79, 143, 207), 68, "blue", tags=("actor", "human", "eye")),
    _row("human_eye_amber", (214, 145, 54), 172, "yellow", tags=("actor", "human", "eye")),
    _row("human_hair_black", (42, 40, 46), 235, "black", tags=("actor", "human", "hair")),
    _row("human_hair_blue_black", (29, 38, 55), 234, "blue", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_espresso", (59, 38, 30), 52, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_dark_brown", (73, 49, 39), 52, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_chestnut", (128, 72, 46), 94, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_warm_brown", (112, 75, 52), 94, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_golden_brown", (151, 105, 53), 136, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_ash_brown", (127, 111, 97), 102, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_ash_blond", (180, 165, 135), 144, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_honey_blond", (205, 158, 76), 178, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_platinum_blond", (224, 218, 202), 187, "white", tags=("actor", "human", "hair")),
    _row("human_hair_auburn", (142, 62, 48), 130, "red", tags=("actor", "human", "hair")),
    _row("human_hair_copper_red", (181, 72, 43), 166, "red", tags=("actor", "human", "hair")),
    _row("human_hair_strawberry_blond", (210, 143, 89), 173, "yellow", tags=("actor", "human", "hair")),
    _row("human_hair_silver", (178, 184, 192), 145, "white", tags=("actor", "human", "hair")),
    _row("human_hair_charcoal", (67, 65, 72), 238, "black", tags=("actor", "human", "hair")),
    _row("human_hair_white", (232, 228, 218), 188, "white", tags=("actor", "human", "hair")),
    _row("human_hair_ink_blue", (42, 67, 116), 24, "blue", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_teal", (43, 137, 134), 30, "cyan", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_forest_green", (45, 106, 70), 29, "green", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_violet", (112, 72, 153), 97, "magenta", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_plum", (116, 55, 104), 96, "magenta", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_rose_pink", (194, 91, 130), 168, "magenta", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_cherry_red", (166, 43, 55), 124, "red", tags=("actor", "human", "hair", "dyed")),
    _row("human_hair_lavender", (158, 127, 188), 140, "magenta", tags=("actor", "human", "hair", "dyed")),
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
    _row("world_object_plant", (126, 194, 126), 114, "green", tags=("world_object", "plant")),
    _row("world_object_charm", (228, 194, 92), 221, "yellow", attrs=("bold",), tags=("world_object", "charm")),
    _row("world_object_tool", (178, 170, 154), 145, "white", tags=("world_object", "tool")),
    _row("world_object_textile", (184, 132, 214), 176, "magenta", tags=("world_object", "textile")),
    _row("world_object_paper", (230, 218, 176), 230, "white", attrs=("bold",), tags=("world_object", "paper")),
    _row("world_object_container", (190, 146, 92), 173, "yellow", tags=("world_object", "container")),
    _row("world_object_light", (236, 182, 86), 215, "yellow", attrs=("bold",), tags=("world_object", "light")),
    _row("world_object_home", (164, 190, 224), 153, "cyan", tags=("world_object", "home")),
    _row("world_object_trade", (210, 170, 102), 180, "yellow", tags=("world_object", "trade")),
    _row("world_object_nature", (150, 194, 162), 108, "green", tags=("world_object", "nature")),
    _row("world_object_medical", (132, 218, 174), 121, "green", attrs=("bold",), tags=("world_object", "medical")),
    _row("world_object_blue", (104, 154, 222), 111, "blue", attrs=("bold",), tags=("world_object", "color")),
    _row("world_object_green", (106, 176, 116), 107, "green", tags=("world_object", "color")),
    _row("world_object_red", (204, 100, 106), 167, "red", tags=("world_object", "color")),
    _row("world_object_purple", (170, 116, 216), 135, "magenta", attrs=("bold",), tags=("world_object", "color")),
    _row("world_object_pink", (226, 142, 190), 218, "magenta", attrs=("bold",), tags=("world_object", "color")),
    _row("world_object_coral", (232, 132, 108), 209, "red", tags=("world_object", "color")),
    _row("world_object_gold", (234, 194, 82), 221, "yellow", attrs=("bold",), tags=("world_object", "color", "metal")),
    _row("world_object_silver", (188, 198, 204), 250, "white", tags=("world_object", "color", "metal")),
    _row("world_object_white", (232, 228, 210), 230, "white", attrs=("bold",), tags=("world_object", "color")),
    _row("world_object_charcoal", (82, 86, 96), 240, "white", attrs=("dim",), tags=("world_object", "color")),
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
    _row("inventory_stowed", (126, 218, 150), 120, "green", attrs=("bold",), tags=("ui", "inventory")),
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
