"""Shared building shell/layout helpers."""

import random

BUILDING_LAYOUT_OFFSETS = (
    (-3, -3),
    (3, -3),
    (-3, 3),
    (3, 3),
)

SIGNAGE_ARCHETYPE_HINTS = {
    "arcade",
    "auto_garage",
    "backroom_clinic",
    "bank",
    "bar",
    "bookshop",
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
    "gallery",
    "gaming_hall",
    "karaoke_box",
    "music_venue",
    "nightclub",
    "pool_hall",
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

BUILDING_SHAPE_WEIGHTS = {
    "building":      {"rect": 10},
    "residential":   {"rect": 7, "notch": 3},
    "storefront":    {"rect": 5, "notch": 3, "l_shape": 2},
    "industrial":    {"rect": 4, "notch": 3, "l_shape": 2, "notch_pair": 1},
    "corporate":     {"rect": 4, "notch": 2, "l_shape": 3, "notch_pair": 1},
    "civic":         {"rect": 5, "notch": 3, "l_shape": 2},
    "secure":        {"rect": 3, "notch": 3, "l_shape": 2, "notch_pair": 2},
    "entertainment": {"rect": 5, "notch": 3, "l_shape": 2},
}


def building_shape_exclusions(rng, exterior_class, left, right, top, bottom, entry_x, entry_y):
    """Return a frozenset of (x, y) cells to exclude from the building footprint."""
    width = right - left + 1
    height = bottom - top + 1
    if width < 7 or height < 5:
        return frozenset()

    weights = BUILDING_SHAPE_WEIGHTS.get(
        exterior_class, BUILDING_SHAPE_WEIGHTS.get("building", {"rect": 10})
    )
    shapes = list(weights.keys())
    shape_weights = [weights[s] for s in shapes]
    shape = rng.choices(shapes, weights=shape_weights, k=1)[0]
    if shape == "rect":
        return frozenset()

    notch_w = min(2, (width - 3) // 2)
    notch_h = min(2, (height - 3) // 2)
    if notch_w < 1 or notch_h < 1:
        return frozenset()

    excluded = set()
    # Only notch top corners (entry is always on the south/bottom wall).
    corner = rng.choice(["tl", "tr"])

    if shape == "notch":
        if corner == "tl":
            for dx in range(notch_w):
                for dy in range(notch_h):
                    excluded.add((left + dx, top + dy))
        else:
            for dx in range(notch_w):
                for dy in range(notch_h):
                    excluded.add((right - dx, top + dy))

    elif shape == "notch_pair":
        for dx in range(notch_w):
            for dy in range(notch_h):
                excluded.add((left + dx, top + dy))
                excluded.add((right - dx, top + dy))

    elif shape == "l_shape":
        if width >= 7 and height >= 7:
            l_w, l_h = 3, 3
        elif width >= 7:
            l_w, l_h = 3, 2
        else:
            l_w, l_h = 2, 2
        if corner == "tl":
            for dx in range(l_w):
                for dy in range(l_h):
                    excluded.add((left + dx, top + dy))
        else:
            for dx in range(l_w):
                for dy in range(l_h):
                    excluded.add((right - dx, top + dy))

    # Never exclude entry or signage row.
    excluded = {(ex, ey) for ex, ey in excluded if ey != int(entry_y)}
    return frozenset(excluded)


def _title_case_label(value):
    text = str(value or "").replace("_", " ").strip()
    return text.title() if text else ""


def _layout_rng_seed(origin_x, origin_y, chunk_size, block_grid_x, block_grid_y, building_index, building):
    building_id = ""
    archetype = ""
    floors = ""
    if isinstance(building, dict):
        building_id = str(building.get("building_id") or "").strip()
        archetype = str(building.get("archetype") or "").strip().lower()
        floors = str(building.get("floors") or "").strip()
    return (
        f"layout:{int(origin_x)}:{int(origin_y)}:{int(chunk_size)}:"
        f"{int(block_grid_x)}:{int(block_grid_y)}:{int(building_index)}:"
        f"{building_id}:{archetype}:{floors}"
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


def building_shell_span(building):
    profile = building_exterior_profile(building)
    width, height = BUILDING_SHELL_SPANS.get(
        str(profile.get("class", "building")).strip().lower() or "building",
        BUILDING_SHELL_SPANS["building"],
    )

    try:
        floors = int((building or {}).get("floors", 1))
    except (TypeError, ValueError, AttributeError):
        floors = 1

    if floors > 1:
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


def _service_aperture(building, left, right, top, bottom, anchor_y, entry_x, entry_y):
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

    side = "east"
    x = int(right)
    if int(entry_x) == int(right):
        side = "west"
        x = int(left)

    y = max(int(top) + 1, min(int(bottom) - 1, int(anchor_y)))
    if (x, y) == (int(entry_x), int(entry_y)):
        alt_y = int(top) + 1 if int(entry_y) != int(top) + 1 else int(bottom) - 1
        y = max(int(top) + 1, min(int(bottom) - 1, alt_y))
    if (x, y) == (int(entry_x), int(entry_y)):
        return None

    return {
        "x": x,
        "y": y,
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


def _window_apertures(building, left, right, top, bottom, reserved=None):
    if not isinstance(building, dict):
        return []

    archetype = _building_archetype(building)
    if archetype in WINDOWLESS_ARCHETYPE_HINTS:
        return []

    reserved = {tuple(point) for point in (reserved or ())}
    profile = building_exterior_profile(building)
    mode = str(profile.get("window_mode", "basic")).strip().lower()
    candidates = []

    front_row = [
        (int(x), int(bottom), 0)
        for x in range(int(left) + 1, int(right))
        if (int(x), int(bottom), 0) not in reserved
    ]
    side_mid = max(int(top) + 1, min(int(bottom) - 1, (int(top) + int(bottom)) // 2))

    if mode == "storefront":
        for point in front_row:
            _append_window_candidate(candidates, reserved, *point)
    elif mode == "residential":
        for x in (int(left) + 1, int(right) - 1):
            _append_window_candidate(candidates, reserved, x, int(bottom), 0)
        _append_window_candidate(candidates, reserved, int(left), side_mid, 0)
        _append_window_candidate(candidates, reserved, int(right), side_mid, 0)
    elif mode == "industrial":
        _append_window_candidate(candidates, reserved, int(right), side_mid, 0)
        if int(right) - int(left) >= 6:
            _append_window_candidate(candidates, reserved, int(left), side_mid, 0)
    elif mode == "corporate":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
            if len(front_row) >= 4:
                _append_window_candidate(candidates, reserved, *front_row[len(front_row) // 2])
        _append_window_candidate(candidates, reserved, int(right), side_mid, 0)
    elif mode == "civic":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
        _append_window_candidate(candidates, reserved, int(left), side_mid, 0)
    elif mode == "entertainment":
        if front_row:
            _append_window_candidate(candidates, reserved, *front_row[0])
            _append_window_candidate(candidates, reserved, *front_row[-1])
            if len(front_row) >= 5:
                _append_window_candidate(candidates, reserved, *front_row[len(front_row) // 2])
    elif mode == "secure":
        return []
    else:
        for x in (int(left) + 1, int(right) - 1):
            _append_window_candidate(candidates, reserved, x, int(bottom), 0)

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

    block_left = int(origin_x) + (block_grid_x * block_w) + 1
    block_right = int(origin_x) + ((block_grid_x + 1) * block_w) - 2
    block_top = int(origin_y) + (block_grid_y * block_h) + 1
    block_bottom = int(origin_y) + ((block_grid_y + 1) * block_h) - 2
    if block_right - block_left < 4 or block_bottom - block_top < 4:
        return None

    center_x = (block_left + block_right) // 2
    center_y = (block_top + block_bottom) // 2

    try:
        building_count = int(building_count if building_count is not None else 1)
    except (TypeError, ValueError):
        building_count = 1
    building_count = max(1, building_count)
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

    span_w, span_h = building_shell_span(building)
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

    entry_x = max(left + 1, min(right - 1, shell_cx + layout_rng.randint(-1, 1)))
    entry_y = bottom

    sign_text = building_signage_text(building)
    signage = None
    if sign_text:
        sign_x = entry_x - 1 if entry_x - 1 >= left else entry_x + 1
        if left <= sign_x <= right and sign_x != entry_x:
            signage = {
                "x": int(sign_x),
                "y": int(entry_y),
                "z": 0,
                "side": "south",
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
    )

    apertures = [
        {
            "x": int(entry_x),
            "y": int(entry_y),
            "z": 0,
            "side": "south",
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
        anchor_y=anchor_y,
        entry_x=entry_x,
        entry_y=entry_y,
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
            "side": "south",
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
