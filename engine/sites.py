"""Shared layout helpers for sparse non-city local sites."""

import random

SITE_LAYOUT_OFFSETS = (
    (0, 0),
    (-4, -2),
    (4, -2),
    (-4, 2),
    (4, 2),
    (0, -4),
    (0, 4),
)

WIDE_SITE_KINDS = {
    "beacon_house",
    "breaker_yard",
    "dock_shack",
    "drydock_yard",
    "ferry_post",
    "net_house",
    "relay_post",
    "roadhouse",
    "salvage_camp",
    "truck_stop",
    "tide_station",
}

PUBLIC_SITE_KINDS = {
    "bait_shop",
    "coast_watch",
    "dock_shack",
    "ferry_post",
    "firewatch_tower",
    "herbalist_camp",
    "inspection_shed",
    "relay_post",
    "roadhouse",
    "truck_stop",
    "tide_station",
    "weather_station",
}

WINDOWED_SITE_KINDS = {
    "bait_shop",
    "beacon_house",
    "dock_shack",
    "firewatch_tower",
    "ferry_post",
    "herbalist_camp",
    "net_house",
    "ranger_hut",
    "relay_post",
    "roadhouse",
    "truck_stop",
    "survey_post",
    "tide_station",
    "weather_station",
}

SITE_GAMEPLAY_PROFILES = {
    "relay_post": {
        "public": True,
        "site_services": ("intel", "bus_transit", "shuttle_transit"),
    },
    "roadhouse": {
        "public": True,
        "is_storefront": True,
        "site_services": ("shuttle_transit",),
    },
    "truck_stop": {
        "public": True,
        "is_storefront": True,
        "site_services": ("shelter", "bus_transit", "shuttle_transit"),
    },
    "inspection_shed": {
        "public": True,
        "site_services": ("intel",),
    },
    "field_camp": {
        "site_services": ("shelter",),
    },
    "survey_post": {
        "site_services": ("intel",),
    },
    "ranger_hut": {
        "site_services": ("shelter",),
    },
    "ruin_shelter": {
        "site_services": ("shelter",),
    },
    "lookout_post": {
        "site_services": ("intel",),
    },
    "firewatch_tower": {
        "public": True,
        "site_services": ("intel",),
    },
    "weather_station": {
        "public": True,
        "site_services": ("intel",),
    },
    "herbalist_camp": {
        "public": True,
        "is_storefront": True,
    },
    "dock_shack": {
        "public": True,
        "is_storefront": True,
        "site_services": ("shuttle_transit", "ferry_transit"),
    },
    "bait_shop": {
        "public": True,
        "is_storefront": True,
    },
    "ferry_post": {
        "public": True,
        "site_services": ("intel", "ferry_transit"),
    },
    "tide_station": {
        "public": True,
        "site_services": ("intel", "ferry_transit"),
    },
    "coast_watch": {
        "public": True,
        "site_services": ("intel",),
    },
    "beacon_house": {
        "site_services": ("intel",),
    },
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


def _front_side_toward_target(left, right, top, bottom, target_x, target_y, rng):
    scores = {}
    for side in ("north", "south", "west", "east"):
        px, py = _wall_point_from_bias(left, right, top, bottom, side, target_x if side in {"north", "south"} else target_y)
        scores[side] = abs(int(px) - int(target_x)) + abs(int(py) - int(target_y))

    best = min(scores.values())
    choices = sorted(side for side, score in scores.items() if int(score) == int(best))
    return rng.choice(choices) if choices else "south"


def _site_kind(site):
    if not isinstance(site, dict):
        return ""
    return str(site.get("kind", "") or "").strip().lower()


def _site_layout_rng_seed(origin_x, origin_y, chunk_size, site_index, site):
    site_id = ""
    kind = ""
    if isinstance(site, dict):
        site_id = str(site.get("site_id") or "").strip()
        kind = str(site.get("kind") or "").strip().lower()
    return (
        f"site_layout:{int(origin_x)}:{int(origin_y)}:{int(chunk_size)}:"
        f"{int(site_index)}:{site_id}:{kind}"
    )


def _footprint_rect(left, right, top, bottom):
    return {
        "left": int(left),
        "right": int(right),
        "top": int(top),
        "bottom": int(bottom),
    }


def _footprint_overlaps(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    try:
        a_left = int(a.get("left"))
        a_right = int(a.get("right"))
        a_top = int(a.get("top"))
        a_bottom = int(a.get("bottom"))
        b_left = int(b.get("left"))
        b_right = int(b.get("right"))
        b_top = int(b.get("top"))
        b_bottom = int(b.get("bottom"))
    except (TypeError, ValueError):
        return False
    return not (
        a_right < b_left
        or b_right < a_left
        or a_bottom < b_top
        or b_bottom < a_top
    )


def _layout_overlaps_reserved(footprint, reserved_footprints):
    if not isinstance(footprint, dict):
        return False
    for reserved in reserved_footprints or ():
        if _footprint_overlaps(footprint, reserved):
            return True
    return False


def _footprint_contains_point(footprint, x, y):
    if not isinstance(footprint, dict):
        return False
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return False
    return left <= int(x) <= right and top <= int(y) <= bottom


def site_entry_front_cell(entry):
    if not isinstance(entry, dict):
        return None
    try:
        x = int(entry.get("x"))
        y = int(entry.get("y"))
        z = int(entry.get("z", 0))
    except (TypeError, ValueError):
        return None

    side = str(entry.get("side", "south") or "south").strip().lower() or "south"
    deltas = {
        "north": (0, -1),
        "south": (0, 1),
        "west": (-1, 0),
        "east": (1, 0),
    }
    dx, dy = deltas.get(side, (0, 1))
    return (int(x + dx), int(y + dy), int(z))


def site_layout_reserved_footprints(layout):
    if not isinstance(layout, dict):
        return ()

    reserved = []
    footprint = layout.get("footprint")
    if isinstance(footprint, dict):
        reserved.append(dict(footprint))

    front = site_entry_front_cell(layout.get("entry"))
    if front is not None:
        fx, fy, _fz = front
        reserved.append(_footprint_rect(fx, fx, fy, fy))
    return tuple(reserved)


def site_is_public(site):
    kind = _site_kind(site)
    if kind in PUBLIC_SITE_KINDS:
        return True
    return bool(isinstance(site, dict) and site.get("public"))


def site_gameplay_profile(site):
    profile = {}
    kind = _site_kind(site)
    if kind:
        profile.update(SITE_GAMEPLAY_PROFILES.get(kind, {}))

    configured_finance_services = ()
    configured_site_services = ()
    configured_opportunity_tags = ()
    specialty_label = ""
    specialty_theme = ""
    if isinstance(site, dict):
        raw_finance_services = site.get("finance_services", ()) or ()
        raw_site_services = site.get("site_services", ()) or ()
        raw_opportunity_tags = site.get("opportunity_tags", ()) or ()
        if isinstance(raw_finance_services, str):
            configured_finance_services = (raw_finance_services,)
        else:
            configured_finance_services = tuple(raw_finance_services)
        if isinstance(raw_site_services, str):
            configured_site_services = (raw_site_services,)
        else:
            configured_site_services = tuple(raw_site_services)
        if isinstance(raw_opportunity_tags, str):
            configured_opportunity_tags = (raw_opportunity_tags,)
        else:
            configured_opportunity_tags = tuple(raw_opportunity_tags)
        specialty_label = str(site.get("specialty_label", "") or "").strip()
        specialty_theme = str(site.get("specialty_theme", "") or "").strip().lower()
        if "is_storefront" in site:
            profile["is_storefront"] = bool(site.get("is_storefront"))

    profile["public"] = bool(profile.get("public", site_is_public(site)))
    profile["is_storefront"] = bool(profile.get("is_storefront", False))

    finance_services = []
    seen = set()
    for service in tuple(profile.get("finance_services", ())) + configured_finance_services:
        label = str(service).strip().lower()
        if not label or label in seen:
            continue
        seen.add(label)
        finance_services.append(label)

    site_services = []
    seen = set()
    for service in tuple(profile.get("site_services", ())) + configured_site_services:
        label = str(service).strip().lower()
        if not label or label in seen:
            continue
        seen.add(label)
        site_services.append(label)

    opportunity_tags = []
    seen = set()
    for tag in tuple(profile.get("opportunity_tags", ())) + configured_opportunity_tags:
        label = str(tag).strip().lower()
        if not label or label in seen:
            continue
        seen.add(label)
        opportunity_tags.append(label)

    profile["finance_services"] = tuple(finance_services)
    profile["site_services"] = tuple(site_services)
    profile["opportunity_tags"] = tuple(opportunity_tags)
    if specialty_label:
        profile["specialty_label"] = specialty_label
    if specialty_theme:
        profile["specialty_theme"] = specialty_theme
    return profile


def layout_chunk_site(origin_x, origin_y, chunk_size, site_index, site=None, reserved_footprints=None):
    chunk_size = int(max(8, chunk_size))
    center_x = int(origin_x) + (chunk_size // 2)
    center_y = int(origin_y) + (chunk_size // 2)
    arrival_pad = (
        (center_x - 1, center_y - 1),
        (center_x, center_y - 1),
        (center_x - 1, center_y),
        (center_x, center_y),
    )
    arrival_cx = sum(point[0] for point in arrival_pad) / float(len(arrival_pad))
    arrival_cy = sum(point[1] for point in arrival_pad) / float(len(arrival_pad))

    offsets = list(SITE_LAYOUT_OFFSETS)
    block_rng = random.Random(f"site_layout_offsets:{int(origin_x)}:{int(origin_y)}:{int(chunk_size)}")
    block_rng.shuffle(offsets)
    off_x, off_y = offsets[int(site_index) % len(offsets)]

    layout_rng = random.Random(
        _site_layout_rng_seed(
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            site_index=site_index,
            site=site,
        )
    )
    off_x += layout_rng.randint(-1, 1)
    off_y += layout_rng.randint(-1, 1)
    shell_cx = center_x + off_x
    shell_cy = center_y + off_y

    kind = _site_kind(site)
    base_half_w = 3 if kind in WIDE_SITE_KINDS else 2
    preferred_half_w = max(2, min(4, base_half_w + layout_rng.randint(0, 1)))
    preferred_half_h = max(2, min(3, 2 + layout_rng.randint(0, 1)))

    offset_order = list(range(len(offsets)))
    offset_start = int(site_index) % len(offsets)
    offset_order = offset_order[offset_start:] + offset_order[:offset_start]
    size_candidates = [(preferred_half_w, preferred_half_h)]
    if preferred_half_w > 2 or preferred_half_h > 2:
        smaller = (max(2, preferred_half_w - 1), max(2, preferred_half_h - 1))
        if smaller not in size_candidates:
            size_candidates.append(smaller)

    sign_text = ""
    if site_is_public(site):
        sign_text = str((site or {}).get("name", "") or "").strip()

    base_seed = _site_layout_rng_seed(
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        site_index=site_index,
        site=site,
    )

    for size_idx, (half_w, half_h) in enumerate(size_candidates):
        for offset_rank, offset_idx in enumerate(offset_order):
            cand_rng = random.Random(f"{base_seed}:candidate:{size_idx}:{offset_rank}")
            base_off_x, base_off_y = offsets[offset_idx]
            shell_cx = center_x + int(base_off_x) + cand_rng.randint(-1, 1)
            shell_cy = center_y + int(base_off_y) + cand_rng.randint(-1, 1)

            left = max(int(origin_x) + 1, shell_cx - half_w)
            right = min(int(origin_x) + chunk_size - 2, shell_cx + half_w)
            top = max(int(origin_y) + 1, shell_cy - half_h)
            bottom = min(int(origin_y) + chunk_size - 2, shell_cy + half_h)
            if right - left < 2 or bottom - top < 2:
                continue

            footprint = _footprint_rect(left, right, top, bottom)
            if any(_footprint_contains_point(footprint, px, py) for px, py in arrival_pad):
                continue
            anchor_x = max(left + 1, min(right - 1, shell_cx))
            anchor_y = max(top + 1, min(bottom - 1, shell_cy))
            front_side = _front_side_toward_target(left, right, top, bottom, arrival_cx, arrival_cy, cand_rng)
            entry_bias = arrival_cx if front_side in {"north", "south"} else arrival_cy
            entry_x, entry_y = _wall_point_from_bias(left, right, top, bottom, front_side, entry_bias)
            front_cell = site_entry_front_cell({
                "x": int(entry_x),
                "y": int(entry_y),
                "z": 0,
                "side": front_side,
            })
            if front_cell is not None:
                front_x, front_y, _front_z = front_cell
                if any(_footprint_contains_point(reserved, front_x, front_y) for reserved in reserved_footprints or ()):
                    continue

            apertures = [{
                "x": int(entry_x),
                "y": int(entry_y),
                "z": 0,
                "side": front_side,
                "kind": "door",
                "ordinary": True,
            }]

            if kind in WINDOWED_SITE_KINDS:
                front_points = [point for point in _wall_points(left, right, top, bottom, front_side) if (int(point[0]), int(point[1])) != (int(entry_x), int(entry_y))]
                for point in (front_points[:1] + front_points[-1:]):
                    wx, wy, _ = point
                    if (int(wx), int(wy)) == (int(entry_x), int(entry_y)):
                        continue
                    apertures.append({
                        "x": int(wx),
                        "y": int(wy),
                        "z": 0,
                        "side": front_side,
                        "kind": "window",
                        "ordinary": False,
                    })

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

            candidate = {
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
                "footprint": footprint,
                "signage": signage,
            }
            if not _layout_overlaps_reserved(footprint, reserved_footprints):
                return candidate

    return None
