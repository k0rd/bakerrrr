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
        "site_services": ("intel",),
    },
    "roadhouse": {
        "public": True,
        "is_storefront": True,
    },
    "truck_stop": {
        "public": True,
        "is_storefront": True,
        "site_services": ("shelter",),
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
    },
    "bait_shop": {
        "public": True,
        "is_storefront": True,
    },
    "ferry_post": {
        "public": True,
        "site_services": ("intel",),
    },
    "tide_station": {
        "public": True,
        "site_services": ("intel",),
    },
    "coast_watch": {
        "public": True,
        "site_services": ("intel",),
    },
    "beacon_house": {
        "site_services": ("intel",),
    },
}


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

    profile["public"] = bool(profile.get("public", site_is_public(site)))
    profile["is_storefront"] = bool(profile.get("is_storefront", False))
    profile["finance_services"] = tuple(
        str(service).strip().lower()
        for service in profile.get("finance_services", ())
        if str(service).strip()
    )
    profile["site_services"] = tuple(
        str(service).strip().lower()
        for service in profile.get("site_services", ())
        if str(service).strip()
    )
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
            entry_x = max(left + 1, min(right - 1, shell_cx + cand_rng.randint(-1, 1)))
            entry_y = bottom

            apertures = [{
                "x": int(entry_x),
                "y": int(entry_y),
                "z": 0,
                "side": "south",
                "kind": "door",
                "ordinary": True,
            }]

            if kind in WINDOWED_SITE_KINDS:
                for wx in (left + 1, right - 1):
                    if wx == entry_x:
                        continue
                    apertures.append({
                        "x": int(wx),
                        "y": int(entry_y),
                        "z": 0,
                        "side": "south",
                        "kind": "window",
                        "ordinary": False,
                    })

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
                    "side": "south",
                    "kind": "door",
                },
                "apertures": apertures,
                "footprint": footprint,
                "signage": signage,
            }
            if not _layout_overlaps_reserved(footprint, reserved_footprints):
                return candidate

    return None
