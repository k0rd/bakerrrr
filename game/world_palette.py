from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldPaletteRow:
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
) -> WorldPaletteRow:
    return WorldPaletteRow(
        key=str(key),
        pygame_rgb=rgb,
        curses_256=int(c256),
        curses_limited=str(limited),
        curses_attrs=tuple(attrs),
        tags=tuple(tags),
    )


WORLD_PALETTE: tuple[WorldPaletteRow, ...] = (
    _row("floor_coarse", (76, 80, 86), 238, "white", attrs=("dim",), tags=("floor", "coarse", "neutral")),
    _row("floor_industrial", (112, 118, 116), 242, "white", tags=("floor", "district", "industrial")),
    _row("floor_residential", (164, 160, 148), 250, "white", tags=("floor", "district", "residential")),
    _row("floor_downtown", (178, 184, 204), 252, "cyan", tags=("floor", "district", "urban")),
    _row("floor_slums", (116, 96, 120), 96, "magenta", tags=("floor", "district", "rough")),
    _row("floor_corporate", (106, 166, 218), 117, "cyan", attrs=("bold",), tags=("floor", "district", "corporate")),
    _row("floor_military", (94, 142, 130), 66, "blue", tags=("floor", "district", "secure")),
    _row("floor_entertainment", (202, 158, 118), 181, "yellow", tags=("floor", "district", "entertainment")),
    _row("floor_frontier", (174, 142, 96), 180, "yellow", tags=("floor", "area", "frontier")),
    _row("floor_wilderness", (90, 150, 92), 71, "green", attrs=("bold",), tags=("floor", "area", "wilderness")),
    _row("floor_coastal", (94, 174, 206), 117, "cyan", attrs=("bold",), tags=("floor", "area", "coastal")),
    _row("building_fill", (96, 100, 104), 240, "blue", tags=("building", "fill", "neutral")),
    _row("building_edge", (158, 162, 166), 244, "white", tags=("building", "edge", "neutral")),
    _row("building_fill_gray_a", (102, 106, 110), 240, "blue", tags=("building", "fill", "concrete")),
    _row("building_edge_gray_a", (158, 162, 166), 244, "white", tags=("building", "edge", "concrete")),
    _row("building_fill_gray_b", (118, 122, 124), 242, "white", tags=("building", "fill", "concrete")),
    _row("building_edge_gray_b", (176, 180, 182), 250, "white", attrs=("bold",), tags=("building", "edge", "concrete")),
    _row("building_fill_gray_c", (82, 88, 94), 238, "blue", tags=("building", "fill", "concrete")),
    _row("building_edge_gray_c", (136, 146, 154), 246, "white", tags=("building", "edge", "concrete")),
    _row("building_fill_brick", (126, 66, 58), 131, "red", tags=("building", "fill", "brick")),
    _row("building_edge_brick", (188, 100, 82), 167, "red", attrs=("bold",), tags=("building", "edge", "brick")),
    _row("building_fill_plaster", (196, 190, 174), 223, "yellow", tags=("building", "fill", "plaster")),
    _row("building_edge_plaster", (234, 224, 198), 230, "white", attrs=("bold",), tags=("building", "edge", "plaster")),
    _row("building_fill_painted", (92, 134, 130), 66, "cyan", tags=("building", "fill", "painted")),
    _row("building_edge_painted", (146, 190, 180), 116, "cyan", attrs=("bold",), tags=("building", "edge", "painted")),
    _row("building_fill_dark", (48, 54, 62), 235, "white", attrs=("dim",), tags=("building", "fill", "dark")),
    _row("building_edge_dark", (98, 110, 122), 240, "blue", tags=("building", "edge", "dark")),
    _row("terrain_block", (78, 82, 86), 238, "blue", tags=("terrain", "block")),
    _row("terrain_brush", (104, 174, 108), 108, "green", attrs=("bold",), tags=("terrain", "greenery")),
    _row("terrain_burned", (78, 72, 62), 238, "black", attrs=("dim",), tags=("terrain", "burned")),
    _row("terrain_rock", (156, 158, 160), 245, "white", tags=("terrain", "rock")),
    _row("terrain_water", (78, 162, 218), 117, "cyan", attrs=("bold",), tags=("terrain", "water")),
    _row("contaminant_electrochemical", (142, 158, 66), 143, "green", attrs=("bold",), tags=("contaminant", "electrochemical", "toxic")),
    _row("terrain_salt", (226, 216, 184), 223, "yellow", attrs=("bold",), tags=("terrain", "salt")),
    _row("terrain_road", (202, 182, 106), 186, "yellow", tags=("terrain", "road")),
    _row("terrain_trail", (178, 126, 92), 173, "magenta", tags=("terrain", "trail")),
    _row("building_roof", (92, 96, 104), 239, "white", attrs=("dim",), tags=("roof", "neutral")),
    _row("building_roof_residential", (174, 92, 74), 173, "white", tags=("roof", "residential")),
    _row("building_roof_storefront", (206, 152, 72), 180, "yellow", attrs=("bold",), tags=("roof", "storefront")),
    _row("building_roof_industrial", (104, 136, 128), 66, "white", tags=("roof", "industrial")),
    _row("building_roof_corporate", (78, 142, 210), 75, "cyan", attrs=("bold",), tags=("roof", "corporate")),
    _row("building_roof_civic", (86, 184, 196), 153, "cyan", tags=("roof", "civic")),
    _row("building_roof_secure", (104, 132, 76), 71, "green", tags=("roof", "secure")),
    _row("building_roof_entertainment", (204, 78, 168), 176, "magenta", attrs=("bold",), tags=("roof", "entertainment")),
    _row("flora_leaf", (90, 176, 94), 77, "green", attrs=("bold",), tags=("flora", "leaf")),
    _row("flora_grass", (126, 188, 92), 113, "green", tags=("flora", "grass")),
    _row("flora_moss", (82, 160, 108), 72, "green", attrs=("dim",), tags=("flora", "moss")),
    _row("flora_vine", (76, 174, 116), 78, "green", attrs=("underline",), tags=("flora", "vine")),
    _row("flora_reed", (156, 174, 92), 149, "green", tags=("flora", "reed")),
    _row("flora_shrub", (102, 154, 86), 71, "green", attrs=("bold",), tags=("flora", "shrub")),
    _row("flora_flower_pink", (238, 132, 184), 211, "magenta", attrs=("bold",), tags=("flora", "flower", "pink")),
    _row("flora_flower_violet", (184, 132, 242), 141, "magenta", attrs=("bold",), tags=("flora", "flower", "violet")),
    _row("flora_flower_gold", (238, 196, 82), 220, "yellow", attrs=("bold",), tags=("flora", "flower", "gold")),
    _row("flora_flower_white", (238, 232, 214), 230, "white", attrs=("bold",), tags=("flora", "flower", "white")),
    _row("flora_flower_blue", (116, 178, 238), 117, "cyan", attrs=("bold",), tags=("flora", "flower", "blue")),
    _row("flora_flower_coral", (242, 128, 108), 210, "red", attrs=("bold",), tags=("flora", "flower", "coral")),
    _row("flora_flower_closed", (150, 116, 134), 138, "magenta", attrs=("dim",), tags=("flora", "flower", "closed")),
    _row("flora_flower_night", (210, 204, 250), 189, "cyan", attrs=("bold",), tags=("flora", "flower", "night")),
    _row("flora_seedling", (116, 206, 122), 120, "green", attrs=("bold",), tags=("flora", "cultivated", "seedling")),
    _row("flora_young", (98, 188, 112), 78, "green", attrs=("bold",), tags=("flora", "cultivated", "young")),
    _row("flora_withered", (150, 118, 72), 137, "yellow", attrs=("dim",), tags=("flora", "cultivated", "withered")),
    _row("flora_spent", (122, 108, 86), 101, "yellow", attrs=("dim",), tags=("flora", "spent")),
    _row("flora_accumulator_glow", (112, 244, 190), 86, "cyan", attrs=("bold",), tags=("flora", "fungus", "bioluminescent")),
    _row("flora_accumulator_glow_seaglass", (104, 236, 200), 86, "cyan", attrs=("bold",), tags=("flora", "fungus", "bioluminescent")),
    _row("flora_accumulator_glow_soft_green", (128, 240, 178), 120, "green", attrs=("bold",), tags=("flora", "fungus", "bioluminescent")),
    _row("flora_indicator_glow_amber", (238, 198, 108), 220, "yellow", attrs=("bold",), tags=("flora", "fungus", "bioluminescent", "indicator")),
    _row("flora_indicator_glow_blue", (106, 204, 238), 117, "cyan", attrs=("bold",), tags=("flora", "fungus", "bioluminescent", "indicator")),
    _row("flora_indicator_glow_green", (138, 222, 126), 114, "green", attrs=("bold",), tags=("flora", "fungus", "bioluminescent", "indicator")),
    _row("flora_indicator_glow_violet", (190, 148, 236), 183, "magenta", attrs=("bold",), tags=("flora", "fungus", "bioluminescent", "indicator")),
    _row("flora_indicator_glow_rose", (232, 144, 184), 211, "magenta", attrs=("bold",), tags=("flora", "fungus", "bioluminescent", "indicator")),
)

_ROWS_BY_KEY = {row.key: row for row in WORLD_PALETTE}


def world_palette_keys() -> tuple[str, ...]:
    return tuple(row.key for row in WORLD_PALETTE)


def palette_row_for_world_key(key: str) -> WorldPaletteRow | None:
    return _ROWS_BY_KEY.get(str(key or "").strip())


def pygame_world_palette_entries() -> dict[str, tuple[int, int, int]]:
    return {row.key: row.pygame_rgb for row in WORLD_PALETTE}


def curses_world_palette_entries(colors: int | None = None) -> dict[str, dict[str, object]]:
    use_256 = int(colors or 0) >= 256
    rows = {}
    for row in WORLD_PALETTE:
        rows[row.key] = {
            "fg": row.curses_256 if use_256 else row.curses_limited,
            "attrs": () if use_256 else row.curses_attrs,
        }
    return rows
