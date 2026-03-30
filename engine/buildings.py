"""Shared building shell/layout helpers."""

import random

BUILDING_LAYOUT_OFFSETS = (
    (-3, -3),
    (3, -3),
    (-3, 3),
    (3, 3),
)

WALL_SIDES = ("north", "south", "west", "east")
OPPOSITE_WALL_SIDE = {
    "north": "south",
    "south": "north",
    "west": "east",
    "east": "west",
}
PERPENDICULAR_WALL_SIDES = {
    "north": ("west", "east"),
    "south": ("west", "east"),
    "west": ("north", "south"),
    "east": ("north", "south"),
}

SIGNAGE_ARCHETYPE_HINTS = {
    "arcade",
    "auto_garage",
    "backroom_clinic",
    "bank",
    "bar",
    "bookshop",
    "casino",
    "brokerage",
    "checkpoint",
    "courier_office",
    "courthouse",
    "daycare",
    "flophouse",
    "gallery",
    "gaming_hall",
    "hardware_store",
    "hotel",
    "junk_market",
    "karaoke_box",
    "laundromat",
    "metro_exchange",
    "music_venue",
    "nightclub",
    "office",
    "pawn_shop",
    "pharmacy",
    "pool_hall",
    "recruitment_office",
    "restaurant",
    "soup_kitchen",
    "street_kitchen",
    "theater",
    "tavern",
    "tool_depot",
    "tower",
}

SERVICE_APERTURE_ARCHETYPE_HINTS = {
    "arcade",
    "auto_garage",
    "backroom_clinic",
    "bank",
    "bar",
    "checkpoint",
    "cold_storage",
    "courier_office",
    "courthouse",
    "data_center",
    "daycare",
    "flophouse",
    "gallery",
    "gaming_hall",
    "hardware_store",
    "hotel",
    "junk_market",
    "karaoke_box",
    "laundromat",
    "media_lab",
    "metro_exchange",
    "music_venue",
    "nightclub",
    "office",
    "pawn_shop",
    "pharmacy",
    "pool_hall",
    "recruitment_office",
    "restaurant",
    "soup_kitchen",
    "street_kitchen",
    "supply_bunker",
    "theater",
    "tool_depot",
    "tower",
    "warehouse",
}

WINDOWLESS_ARCHETYPE_HINTS = {
    "armory",
    "barracks",
    "checkpoint",
    "cold_storage",
    "command_center",
    "data_center",
    "server_hub",
    "supply_bunker",
    "warehouse",
}

RESIDENTIAL_ARCHETYPE_HINTS = {
    "apartment",
    "daycare",
    "field_camp",
    "flophouse",
    "house",
    "hotel",
    "ranger_hut",
    "ruin_shelter",
    "tenement",
}

INDUSTRIAL_ARCHETYPE_HINTS = {
    "auto_garage",
    "cold_storage",
    "dock_shack",
    "chop_shop",
    "factory",
    "freight_depot",
    "machine_shop",
    "motor_pool",
    "net_house",
    "pump_house",
    "recycling_plant",
    "salvage_camp",
    "warehouse",
    "work_shed",
}

CORPORATE_ARCHETYPE_HINTS = {
    "biotech_clinic",
    "brokerage",
    "co_working_hub",
    "lab",
    "media_lab",
    "office",
    "tower",
}

CIVIC_ARCHETYPE_HINTS = {
    "bank",
    "beacon_house",
    "courier_office",
    "courthouse",
    "ferry_post",
    "field_hospital",
    "lookout_post",
    "metro_exchange",
    "pharmacy",
    "recruitment_office",
    "relay_post",
    "roadhouse",
    "soup_kitchen",
    "survey_post",
    "tide_station",
}

SECURE_ARCHETYPE_HINTS = {
    "armory",
    "barracks",
    "checkpoint",
    "command_center",
    "data_center",
    "server_hub",
    "supply_bunker",
}

ENTERTAINMENT_ARCHETYPE_HINTS = {
    "arcade",
    "bar",
    "casino",
    "gallery",
    "gaming_hall",
    "karaoke_box",
    "music_venue",
    "nightclub",
    "pool_hall",
    "tavern",
    "theater",
}

BUILDING_EXTERIOR_PROFILES = {
    "building": {
        "roof_style": "building_roof",
        "frontage": "plain frontage",
        "window_mode": "basic",
    },
    "residential": {
        "roof_style": "building_roof_residential",
        "frontage": "residential frontage",
        "window_mode": "residential",
    },
    "storefront": {
        "roof_style": "building_roof_storefront",
        "frontage": "shopfront",
        "window_mode": "storefront",
    },
    "industrial": {
        "roof_style": "building_roof_industrial",
        "frontage": "service frontage",
        "window_mode": "industrial",
    },
    "corporate": {
        "roof_style": "building_roof_corporate",
        "frontage": "office frontage",
        "window_mode": "corporate",
    },
    "civic": {
        "roof_style": "building_roof_civic",
        "frontage": "public frontage",
        "window_mode": "civic",
    },
    "secure": {
        "roof_style": "building_roof_secure",
        "frontage": "hardened frontage",
        "window_mode": "secure",
    },
    "entertainment": {
        "roof_style": "building_roof_entertainment",
        "frontage": "venue frontage",
        "window_mode": "entertainment",
    },
}

BUILDING_SHELL_SPANS = {
    "building": (5, 5),
    "residential": (5, 5),
    "storefront": (7, 5),
    "industrial": (7, 7),
    "corporate": (7, 7),
    "civic": (7, 5),
    "secure": (7, 7),
    "entertainment": (7, 5),
}

BUILDING_SHELL_SPAN_OPTIONS = {
    "building": ((5, 5), (7, 5), (5, 7)),
    "residential": ((5, 5), (7, 5), (5, 7)),
    "storefront": ((7, 5), (9, 5), (7, 7), (9, 7)),
    "industrial": ((7, 7), (9, 7), (7, 9), (9, 9)),
    "corporate": ((7, 7), (9, 7), (7, 9), (9, 9)),
    "civic": ((7, 5), (9, 5), (7, 7), (9, 7)),
    "secure": ((7, 7), (9, 7), (7, 9)),
    "entertainment": ((7, 5), (9, 5), (7, 7), (9, 7)),
}

BUILDING_LARGE_PARCEL_SPAN_OPTIONS = {
    "building": ((11, 7), (13, 7), (11, 9)),
    "residential": ((11, 7), (13, 7), (11, 9)),
    "storefront": ((11, 7), (13, 7), (11, 9), (13, 9)),
    "industrial": ((11, 9), (13, 9), (15, 9)),
    "corporate": ((11, 9), (13, 9), (15, 9)),
    "civic": ((11, 7), (13, 7), (11, 9), (13, 9)),
    "secure": ((11, 9), (13, 9), (15, 9)),
    "entertainment": ((11, 7), (13, 7), (11, 9), (13, 9)),
}

BUILDING_SHAPE_WEIGHTS = {
    "building":      {"rect": 7, "notch": 2, "setback": 1},
    "residential":   {"rect": 5, "notch": 3, "l_shape": 1, "setback": 1},
    "storefront":    {"rect": 3, "notch": 3, "l_shape": 2, "setback": 2},
    "industrial":    {"rect": 2, "notch": 3, "l_shape": 2, "notch_pair": 1, "setback": 2},
    "corporate":     {"rect": 2, "notch": 2, "l_shape": 3, "notch_pair": 1, "setback": 3},
    "civic":         {"rect": 3, "notch": 3, "l_shape": 2, "setback": 2},
    "secure":        {"rect": 2, "notch": 3, "l_shape": 2, "notch_pair": 2, "setback": 1},
    "entertainment": {"rect": 3, "notch": 3, "l_shape": 2, "setback": 2},
}


def _clamp(value, low, high):
    return max(int(low), min(int(high), int(value)))


def _wall_points(left, right, top, bottom, side):
    left = int(left)
    right = int(right)
    top = int(top)
    bottom = int(bottom)
    side = str(side or "south").strip().lower() or "south"

    if side == "north":
        xs = list(range(left + 1, right))
        if not xs:
            xs = [(left + right) // 2]
        return [(int(x), top, 0) for x in xs]
    if side == "south":
        xs = list(range(left + 1, right))
        if not xs:
            xs = [(left + right) // 2]
        return [(int(x), bottom, 0) for x in xs]
    if side == "west":
        ys = list(range(top + 1, bottom))
        if not ys:
            ys = [(top + bottom) // 2]
        return [(left, int(y), 0) for y in ys]

    ys = list(range(top + 1, bottom))
    if not ys:
        ys = [(top + bottom) // 2]
    return [(right, int(y), 0) for y in ys]


def _wall_point_from_bias(left, right, top, bottom, side, bias):
    points = _wall_points(left, right, top, bottom, side)
    if not points:
        return int(left), int(bottom)

    side = str(side or "south").strip().lower() or "south"
    if side in {"north", "south"}:
        xs = [point[0] for point in points]
        target_x = _clamp(int(bias), min(xs), max(xs))
        for x, y, _ in points:
            if int(x) == target_x:
                return int(x), int(y)
    else:
        ys = [point[1] for point in points]
        target_y = _clamp(int(bias), min(ys), max(ys))
        for x, y, _ in points:
            if int(y) == target_y:
                return int(x), int(y)
    x, y, _ = points[len(points) // 2]
    return int(x), int(y)


def _adjacent_sign_point(left, right, top, bottom, side, entry_x, entry_y):
    side = str(side or "south").strip().lower() or "south"
    entry_x = int(entry_x)
    entry_y = int(entry_y)
    if side in {"north", "south"}:
        candidates = ((entry_x - 1, entry_y), (entry_x + 1, entry_y))
    else:
        candidates = ((entry_x, entry_y - 1), (entry_x, entry_y + 1))

    for sx, sy in candidates:
        if int(left) <= int(sx) <= int(right) and int(top) <= int(sy) <= int(bottom):
            if (int(sx), int(sy)) != (entry_x, entry_y):
                return int(sx), int(sy)
    return None


def _choose_block_front_side(left, right, top, bottom, block_left, block_right, block_top, block_bottom, rng):
    gaps = {
        "north": max(0, int(top) - int(block_top)),
        "south": max(0, int(block_bottom) - int(bottom)),
        "west": max(0, int(left) - int(block_left)),
        "east": max(0, int(block_right) - int(right)),
    }
    min_gap = min(gaps.values())
    candidates = sorted(side for side, gap in gaps.items() if int(gap) == int(min_gap))
    return rng.choice(candidates) if candidates else "south"


def _corner_cells(left, right, top, bottom, corner, width, height):
    corner = str(corner or "tl").strip().lower() or "tl"
    if "l" in corner:
        xs = range(int(left), int(left) + int(width))
    else:
        xs = range(int(right) - int(width) + 1, int(right) + 1)

    if corner.startswith("t"):
        ys = range(int(top), int(top) + int(height))
    else:
        ys = range(int(bottom) - int(height) + 1, int(bottom) + 1)

    return {(int(x), int(y)) for x in xs for y in ys}


def _center_strip_cells(left, right, top, bottom, side, depth):
    side = str(side or "north").strip().lower() or "north"
    depth = max(1, int(depth))

    if side == "north":
        ys = range(int(top), min(int(bottom) + 1, int(top) + depth))
        xs = range(int(left) + 1, int(right))
    elif side == "south":
        ys = range(max(int(top), int(bottom) - depth + 1), int(bottom) + 1)
        xs = range(int(left) + 1, int(right))
    elif side == "west":
        xs = range(int(left), min(int(right) + 1, int(left) + depth))
        ys = range(int(top) + 1, int(bottom))
    else:
        xs = range(max(int(left), int(right) - depth + 1), int(right) + 1)
        ys = range(int(top) + 1, int(bottom))

    return {(int(x), int(y)) for x in xs for y in ys}


def _linked_wing_cells(left, right, top, bottom, axis="horizontal"):
    left = int(left)
    right = int(right)
    top = int(top)
    bottom = int(bottom)
    axis = str(axis or "horizontal").strip().lower() or "horizontal"
    width = right - left + 1
    height = bottom - top + 1
    excluded = set()

    if axis == "vertical":
        if height < 7 or width < 5:
            return excluded
        connector_h = 3 if height >= 11 else 1
        connector_w = 3 if width >= 7 else 1
        center_y = (top + bottom) // 2
        center_x = (left + right) // 2
        connector_top = max(top + 1, center_y - (connector_h // 2))
        connector_bottom = min(bottom - 1, connector_top + connector_h - 1)
        connector_left = max(left + 1, center_x - (connector_w // 2))
        connector_right = min(right - 1, connector_left + connector_w - 1)
        for y in range(connector_top, connector_bottom + 1):
            for x in range(left + 1, right):
                if connector_left <= x <= connector_right:
                    continue
                excluded.add((int(x), int(y)))
        return excluded

    if width < 7 or height < 5:
        return excluded
    connector_w = 3 if width >= 11 else 1
    connector_h = 3 if height >= 7 else 1
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    connector_left = max(left + 1, center_x - (connector_w // 2))
    connector_right = min(right - 1, connector_left + connector_w - 1)
    connector_top = max(top + 1, center_y - (connector_h // 2))
    connector_bottom = min(bottom - 1, connector_top + connector_h - 1)
    for x in range(connector_left, connector_right + 1):
        for y in range(top + 1, bottom):
            if connector_top <= y <= connector_bottom:
                continue
            excluded.add((int(x), int(y)))
    return excluded


def building_shape_exclusions(
    rng,
    exterior_class,
    left,
    right,
    top,
    bottom,
    entry_x,
    entry_y,
    entry_side="south",
    parcel_span_x=1,
    parcel_span_y=1,
):
    """Return a frozenset of (x, y) cells to exclude from the building footprint."""
    width = right - left + 1
    height = bottom - top + 1
    if width < 5 or height < 5:
        return frozenset()

    weights = BUILDING_SHAPE_WEIGHTS.get(
        exterior_class, BUILDING_SHAPE_WEIGHTS.get("building", {"rect": 10})
    )
    shapes = list(weights.keys())
    shape_weights = [weights[s] for s in shapes]
    parcel_span_x = max(1, int(parcel_span_x))
    parcel_span_y = max(1, int(parcel_span_y))
    linked_axis = ""
    if parcel_span_x > parcel_span_y and width >= 7 and height >= 5:
        linked_axis = "horizontal"
    elif parcel_span_y > parcel_span_x and width >= 5 and height >= 7:
        linked_axis = "vertical"
    elif (parcel_span_x > 1 or parcel_span_y > 1) and width >= 7 and height >= 7:
        linked_axis = "horizontal" if width >= height else "vertical"
    if linked_axis:
        shapes.append("linked_wings")
        shape_weights.append(3 if width >= 11 or height >= 11 else 2)
    shape = rng.choices(shapes, weights=shape_weights, k=1)[0]
    if shape == "rect":
        return frozenset()

    notch_w = min(2, (width - 3) // 2)
    notch_h = min(2, (height - 3) // 2)
    if notch_w < 1 or notch_h < 1:
        return frozenset()

    excluded = set()
    entry_side = str(entry_side or "south").strip().lower() or "south"
    back_side = OPPOSITE_WALL_SIDE.get(entry_side, "north")
    back_corners = {
        "north": ("tl", "tr"),
        "south": ("bl", "br"),
        "west": ("tl", "bl"),
        "east": ("tr", "br"),
    }.get(back_side, ("tl", "tr"))
    corner = rng.choice(back_corners)

    if shape == "notch":
        excluded.update(_corner_cells(left, right, top, bottom, corner, notch_w, notch_h))

    elif shape == "notch_pair":
        for pair_corner in back_corners:
            excluded.update(_corner_cells(left, right, top, bottom, pair_corner, notch_w, notch_h))

    elif shape == "l_shape":
        if width >= 7 and height >= 7:
            l_w, l_h = 3, 3
        elif width >= 7:
            l_w, l_h = 3, 2
        else:
            l_w, l_h = 2, 2
        excluded.update(_corner_cells(left, right, top, bottom, corner, l_w, l_h))

    elif shape == "setback":
        if back_side in {"north", "south"}:
            setback_depth = min(2, max(1, height - 4))
        else:
            setback_depth = min(2, max(1, width - 4))
        excluded.update(_center_strip_cells(left, right, top, bottom, back_side, setback_depth))

    elif shape == "linked_wings":
        excluded.update(_linked_wing_cells(left, right, top, bottom, axis=linked_axis or "horizontal"))

    # Never exclude the front facade that carries the entry/signage.
    if entry_side in {"north", "south"}:
        excluded = {(ex, ey) for ex, ey in excluded if ey != int(entry_y)}
    else:
        excluded = {(ex, ey) for ex, ey in excluded if ex != int(entry_x)}
    return frozenset(excluded)


def _title_case_label(value):
    text = str(value or "").replace("_", " ").strip()
    return text.title() if text else ""


def _layout_rng_seed(origin_x, origin_y, chunk_size, block_grid_x, block_grid_y, building_index, building):
    building_id = ""
    archetype = ""
    floors = ""
    basement_levels = ""
    if isinstance(building, dict):
        building_id = str(building.get("building_id") or "").strip()
        archetype = str(building.get("archetype") or "").strip().lower()
        floors = str(building.get("floors") or "").strip()
        basement_levels = str(building.get("basement_levels") or "").strip()
    return (
        f"layout:{int(origin_x)}:{int(origin_y)}:{int(chunk_size)}:"
        f"{int(block_grid_x)}:{int(block_grid_y)}:{int(building_index)}:"
        f"{building_id}:{archetype}:{floors}:{basement_levels}"
    )


def world_building_id(chunk_x, chunk_y, building):
    """Return a chunk-qualified building id used for cross-system identity."""
    cx = int(chunk_x)
    cy = int(chunk_y)
    prefix = f"{cx}:{cy}:"

    raw_building_id = building
    if isinstance(building, dict):
        raw_building_id = building.get("building_id")
    local_id = str(raw_building_id or "").strip()
    if not local_id:
        return f"{prefix}unknown"
    if local_id.startswith(prefix):
        return local_id
    return f"{prefix}{local_id}"


def _building_archetype(building):
    if not isinstance(building, dict):
        return ""
    return str(building.get("archetype", "") or "").strip().lower()


def building_exterior_class(building):
    archetype = _building_archetype(building)

    if archetype in SECURE_ARCHETYPE_HINTS:
        return "secure"
    if archetype in INDUSTRIAL_ARCHETYPE_HINTS:
        return "industrial"
    if archetype in ENTERTAINMENT_ARCHETYPE_HINTS:
        return "entertainment"
    if archetype in CORPORATE_ARCHETYPE_HINTS:
        return "corporate"
    if archetype in CIVIC_ARCHETYPE_HINTS:
        return "civic"
    if archetype in RESIDENTIAL_ARCHETYPE_HINTS:
        return "residential"
    if bool(building.get("is_storefront")) or archetype in SIGNAGE_ARCHETYPE_HINTS:
        return "storefront"
    return "building"


def building_exterior_profile(building):
    exterior_class = building_exterior_class(building)
    profile = dict(BUILDING_EXTERIOR_PROFILES.get(exterior_class, BUILDING_EXTERIOR_PROFILES["building"]))
    profile["class"] = exterior_class
    profile["archetype"] = _building_archetype(building)
    return profile


def building_parcel_span(building):
    span_x = 1
    span_y = 1
    if isinstance(building, dict):
        try:
            span_x = max(1, int(building.get("parcel_span_x", 1)))
        except (TypeError, ValueError, AttributeError):
            span_x = 1
        try:
            span_y = max(1, int(building.get("parcel_span_y", 1)))
        except (TypeError, ValueError, AttributeError):
            span_y = 1
    return int(span_x), int(span_y)


def building_shell_span(building, rng=None):
    profile = building_exterior_profile(building)
    exterior_class = str(profile.get("class", "building")).strip().lower() or "building"
    parcel_span_x, parcel_span_y = building_parcel_span(building)
    options = BUILDING_SHELL_SPAN_OPTIONS.get(
        exterior_class,
        (BUILDING_SHELL_SPANS.get(exterior_class, BUILDING_SHELL_SPANS["building"]),),
    )
    if parcel_span_x > 1 or parcel_span_y > 1:
        large_options = BUILDING_LARGE_PARCEL_SPAN_OPTIONS.get(exterior_class, ())
        if large_options:
            if parcel_span_x > 1 and parcel_span_y > 1:
                options = tuple(dict.fromkeys(tuple(large_options) + tuple((h, w) for w, h in large_options)))
            elif parcel_span_y > 1:
                options = tuple((h, w) for w, h in large_options)
            else:
                options = tuple(large_options)
    if rng is not None and len(options) > 1:
        width, height = rng.choice(tuple(options))
    else:
        width, height = options[0]

    try:
        floors = int((building or {}).get("floors", 1))
    except (TypeError, ValueError, AttributeError):
        floors = 1
    try:
        basement_levels = int((building or {}).get("basement_levels", 0))
    except (TypeError, ValueError, AttributeError):
        basement_levels = 0

    if floors + basement_levels > 1:
        width = max(int(width), 7)
        height = max(int(height), 7)
    return int(width), int(height)


def building_signage_text(building):
    if not isinstance(building, dict):
        return ""

    business_name = str(building.get("business_name") or "").strip()
    if business_name:
        return business_name

    archetype = _building_archetype(building)
    if bool(building.get("is_storefront")) or archetype in SIGNAGE_ARCHETYPE_HINTS:
        return _title_case_label(archetype) or "Building"
    return ""


def _service_aperture(building, left, right, top, bottom, anchor_x, anchor_y, entry_x, entry_y, entry_side):
    if not isinstance(building, dict):
        return None

    archetype = _building_archetype(building)
    if not (bool(building.get("is_storefront")) or archetype in SERVICE_APERTURE_ARCHETYPE_HINTS):
        return None

    # Keep side/service doors for larger, non-residential shells so small
    # footprints do not become over-dense with awkward extra door glyphs.
    width = int(right) - int(left) + 1
    height = int(bottom) - int(top) + 1
    if width < 7 or height < 5:
        return None

    exterior_class = building_exterior_class(building)
    if exterior_class not in {"industrial", "corporate", "civic", "secure"}:
        return None

    side = OPPOSITE_WALL_SIDE.get(str(entry_side or "south").strip().lower() or "south", "north")
    bias = int(anchor_x) if side in {"north", "south"} else int(anchor_y)
    x, y = _wall_point_from_bias(left, right, top, bottom, side, bias)
    if (x, y) == (int(entry_x), int(entry_y)):
        alt_bias = int(anchor_y) if side in {"north", "south"} else int(anchor_x)
        x, y = _wall_point_from_bias(left, right, top, bottom, side, alt_bias)
    if (x, y) == (int(entry_x), int(entry_y)):
        return None

    return {
        "x": int(x),
        "y": int(y),
        "z": 0,
        "side": side,
        "kind": "service_door",
        "ordinary": False,
    }


def _append_window_candidate(candidates, reserved, x, y, z=0):
    point = (int(x), int(y), int(z))
    if point in reserved or point in candidates:
        return
    candidates.append(point)


def _window_apertures(building, left, right, top, bottom, entry_side, reserved=None):
    if not isinstance(building, dict):
        return []

    archetype = _building_archetype(building)
    if archetype in WINDOWLESS_ARCHETYPE_HINTS:
        return []

    reserved = {tuple(point) for point in (reserved or ())}
    profile = building_exterior_profile(building)
    mode = str(profile.get("window_mode", "basic")).strip().lower()
    candidates = []
    front_side = str(entry_side or "south").strip().lower() or "south"
    front_row = [point for point in _wall_points(left, right, top, bottom, front_side) if tuple(point) not in reserved]
    side_a, side_b = PERPENDICULAR_WALL_SIDES.get(front_side, ("west", "east"))
    side_a_mid = _wall_point_from_bias(
        left,
        right,
        top,
        bottom,
        side_a,
        (int(top) + int(bottom)) // 2 if side_a in {"west", "east"} else (int(left) + int(right)) // 2,
    )
    side_b_mid = _wall_point_from_bias(
        left,
        right,
        top,
        bottom,
        side_b,
        (int(top) + int(bottom)) // 2 if side_b in {"west", "east"} else (int(left) + int(right)) // 2,
    )
    span = max(int(right) - int(left), int(bottom) - int(top))

    if mode == "storefront":
        for point in front_row:
            _append_window_candidate(candidates, reserved, *point)
    elif mode == "residential":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
        _append_window_candidate(candidates, reserved, *side_a_mid, 0)
        _append_window_candidate(candidates, reserved, *side_b_mid, 0)
    elif mode == "industrial":
        _append_window_candidate(candidates, reserved, *side_b_mid, 0)
        if span >= 6:
            _append_window_candidate(candidates, reserved, *side_a_mid, 0)
    elif mode == "corporate":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
            if len(front_row) >= 4:
                _append_window_candidate(candidates, reserved, *front_row[len(front_row) // 2])
        _append_window_candidate(candidates, reserved, *side_b_mid, 0)
    elif mode == "civic":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
        _append_window_candidate(candidates, reserved, *side_a_mid, 0)
    elif mode == "entertainment":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
            if len(front_row) >= 5:
                _append_window_candidate(candidates, reserved, *front_row[len(front_row) // 2])
    elif mode == "secure":
        return []
    else:
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])

    apertures = []
    seen = set()
    for x, y, z in candidates:
        if (x, y, z) in seen:
            continue
        seen.add((x, y, z))
        side = "south"
        if int(y) == int(top):
            side = "north"
        elif int(y) == int(bottom):
            side = "south"
        elif int(x) == int(left):
            side = "west"
        elif int(x) == int(right):
            side = "east"
        apertures.append({
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "side": side,
            "kind": "window",
            "ordinary": False,
        })
    return apertures


def layout_chunk_building(origin_x, origin_y, chunk_size, block_grid_x, block_grid_y, building_index, building=None, building_count=None):
    chunk_size = int(max(8, chunk_size))
    block_w = max(4, chunk_size // 2)
    block_h = max(4, chunk_size // 2)
    block_grid_x = int(block_grid_x)
    block_grid_y = int(block_grid_y)
    block_cols = max(1, chunk_size // block_w)
    block_rows = max(1, chunk_size // block_h)
    parcel_span_x, parcel_span_y = building_parcel_span(building)
    parcel_span_x = max(1, min(int(parcel_span_x), max(1, block_cols - block_grid_x)))
    parcel_span_y = max(1, min(int(parcel_span_y), max(1, block_rows - block_grid_y)))

    block_left = int(origin_x) + (block_grid_x * block_w) + 1
    block_right = int(origin_x) + ((block_grid_x + parcel_span_x) * block_w) - 2
    block_top = int(origin_y) + (block_grid_y * block_h) + 1
    block_bottom = int(origin_y) + ((block_grid_y + parcel_span_y) * block_h) - 2
    if block_right - block_left < 4 or block_bottom - block_top < 4:
        return None

    center_x = (block_left + block_right) // 2
    center_y = (block_top + block_bottom) // 2

    try:
        building_count = int(building_count if building_count is not None else 1)
    except (TypeError, ValueError):
        building_count = 1
    building_count = max(1, building_count)
    if parcel_span_x > 1 or parcel_span_y > 1:
        building_count = 1
    block_rng = random.Random(
        f"layout_offsets:{int(origin_x)}:{int(origin_y)}:{int(chunk_size)}:{block_grid_x}:{block_grid_y}"
    )

    if building_count <= 1:
        offsets = [(0, 0)]
        layout_mode = "solo"
    elif building_count == 2:
        horizontal_pair = [(-3, 0), (3, 0)]
        vertical_pair = [(0, -3), (0, 3)]
        offsets = horizontal_pair if block_rng.randint(0, 1) == 0 else vertical_pair
        layout_mode = "pair_horizontal" if offsets is horizontal_pair else "pair_vertical"
    else:
        offsets = list(BUILDING_LAYOUT_OFFSETS)
        layout_mode = "cluster"
    if building_count > 2:
        block_rng.shuffle(offsets)
    off_x, off_y = offsets[int(building_index) % len(offsets)]

    layout_rng = random.Random(
        _layout_rng_seed(
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            block_grid_x=block_grid_x,
            block_grid_y=block_grid_y,
            building_index=building_index,
            building=building,
        )
    )

    shell_cx = center_x + off_x
    shell_cy = center_y + off_y
    shell_cx = max(block_left + 2, min(block_right - 2, shell_cx))
    shell_cy = max(block_top + 2, min(block_bottom - 2, shell_cy))

    span_w, span_h = building_shell_span(building, rng=layout_rng)
    if layout_mode == "pair_horizontal":
        span_w = min(span_w, 5)
    elif layout_mode == "pair_vertical":
        span_h = min(span_h, 5)
    elif layout_mode == "cluster":
        span_w = min(span_w, 5)
        span_h = min(span_h, 5)
    max_span_w = max(3, ((block_right - block_left) // 2) * 2 + 1)
    max_span_h = max(3, ((block_bottom - block_top) // 2) * 2 + 1)
    span_w = max(3, min(int(span_w), int(max_span_w)))
    span_h = max(3, min(int(span_h), int(max_span_h)))
    half_w = span_w // 2
    half_h = span_h // 2

    left = max(block_left, shell_cx - half_w)
    right = min(block_right, shell_cx + half_w)
    top = max(block_top, shell_cy - half_h)
    bottom = min(block_bottom, shell_cy + half_h)
    if right - left < 2 or bottom - top < 2:
        return None

    anchor_x = max(left + 1, min(right - 1, shell_cx))
    anchor_y = max(top + 1, min(bottom - 1, shell_cy))
    front_side = _choose_block_front_side(
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        block_left=block_left,
        block_right=block_right,
        block_top=block_top,
        block_bottom=block_bottom,
        rng=layout_rng,
    )
    entry_bias = (shell_cx + layout_rng.randint(-1, 1)) if front_side in {"north", "south"} else (shell_cy + layout_rng.randint(-1, 1))
    entry_x, entry_y = _wall_point_from_bias(left, right, top, bottom, front_side, entry_bias)

    sign_text = building_signage_text(building)
    signage = None
    if sign_text:
        sign_point = _adjacent_sign_point(left, right, top, bottom, front_side, entry_x, entry_y)
        if sign_point is not None:
            sign_x, sign_y = sign_point
            signage = {
                "x": int(sign_x),
                "y": int(sign_y),
                "z": 0,
                "side": front_side,
                "kind": "wall_sign",
                "text": sign_text,
            }

    excluded = building_shape_exclusions(
        rng=layout_rng,
        exterior_class=building_exterior_class(building) if isinstance(building, dict) else "building",
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        entry_x=entry_x,
        entry_y=entry_y,
        entry_side=front_side,
        parcel_span_x=parcel_span_x,
        parcel_span_y=parcel_span_y,
    )

    apertures = [
        {
            "x": int(entry_x),
            "y": int(entry_y),
            "z": 0,
            "side": front_side,
            "kind": "door",
            "ordinary": True,
        }
    ]

    service_aperture = _service_aperture(
        building=building,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        entry_x=entry_x,
        entry_y=entry_y,
        entry_side=front_side,
    )
    if service_aperture:
        apertures.append(service_aperture)

    reserved = {
        (int(aperture["x"]), int(aperture["y"]), int(aperture.get("z", 0)))
        for aperture in apertures
        if isinstance(aperture, dict)
    }
    if signage:
        reserved.add((int(signage["x"]), int(signage["y"]), int(signage.get("z", 0))))
    apertures.extend(
        _window_apertures(
            building=building,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            entry_side=front_side,
            reserved=reserved,
        )
    )

    # Remove apertures and signage that fall in excluded (notched) areas.
    if excluded:
        apertures = [
            a for a in apertures
            if (int(a["x"]), int(a["y"])) not in excluded
        ]
        if signage and (int(signage["x"]), int(signage["y"])) in excluded:
            signage = None

    return {
        "left": int(left),
        "right": int(right),
        "top": int(top),
        "bottom": int(bottom),
        "center_x": int(shell_cx),
        "center_y": int(shell_cy),
        "anchor_x": int(anchor_x),
        "anchor_y": int(anchor_y),
        "entry": {
            "x": int(entry_x),
            "y": int(entry_y),
            "z": 0,
            "side": front_side,
            "kind": "door",
        },
        "apertures": apertures,
        "excluded": excluded,
        "footprint": {
            "left": int(left),
            "right": int(right),
            "top": int(top),
            "bottom": int(bottom),
        },
        "signage": signage,
    }
