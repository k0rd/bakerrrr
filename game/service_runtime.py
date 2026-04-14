"""Shared casino and service runtime helpers.

This module holds the shared service-stack behavior that used to live inside
``game/systems.py`` so the extracted service systems can depend on a focused
runtime seam instead of reaching back into the monolith.
"""

import curses
import itertools
import random
from collections import Counter

from game.components import AI, CreatureIdentity, NPCNeeds, Occupation, PlayerAssets, Position
from game.organizations import occupation_targets_property, property_org_members
from game.population import work_shift_active
from game.property_runtime import (
    property_covering as _property_covering,
    property_focus_position as _property_focus_position,
    property_is_storefront as _property_is_storefront,
    storefront_service_mode as _storefront_service_mode,
)
from game.vehicles import roll_vehicle_paint_key, roll_vehicle_profile


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


def _line_text(line):
    if isinstance(line, dict):
        return str(line.get("text", ""))
    return str(line)


def _segment(text, *, color=None, attrs=0, **extras):
    segment = {
        "text": str(text),
        "color": color,
        "attrs": int(attrs or 0),
    }
    for key, value in extras.items():
        segment[str(key)] = value
    return segment


def _segments_text(segments):
    return "".join(str(segment.get("text", "")) for segment in segments or () if isinstance(segment, dict))


def _rich_line(segments, text=None):
    normalized = []
    for segment in segments or ():
        if not isinstance(segment, dict):
            continue
        seg_text = str(segment.get("text", ""))
        if not seg_text:
            continue
        extras = {
            key: value
            for key, value in segment.items()
            if key not in {"text", "color", "attrs"}
        }
        normalized.append(_segment(
            seg_text,
            color=segment.get("color"),
            attrs=segment.get("attrs", 0),
            **extras,
        ))
    plain = str(text) if text is not None else _segments_text(normalized)
    return {
        "text": plain,
        "segments": normalized,
    }


def _legend_line(text, glyph=None, color=None, prefix="", attrs=0):
    segments = []
    plain = ""
    prefix = str(prefix)
    if prefix:
        segments.append(_segment(prefix))
        plain += prefix
    glyph_text = str(glyph)[:1] if glyph not in (None, "") else ""
    if glyph_text:
        segments.append(_segment(glyph_text, color=color, attrs=attrs, inline_glyph=True))
        plain += glyph_text
        if text:
            segments.append(_segment(" "))
            plain += " "
    text = str(text)
    if text:
        segments.append(_segment(text))
        plain += text
    return _rich_line(segments, text=plain)


def _tick_duration_label(sim, ticks):
    try:
        total_ticks = int(ticks)
    except (TypeError, ValueError):
        total_ticks = 0
    total_ticks = max(0, total_ticks)
    if total_ticks <= 0:
        return "0t"

    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError, AttributeError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)

    hours = total_ticks / float(ticks_per_hour)
    if hours >= 1.0:
        rounded = round(hours, 1)
        if abs(rounded - int(rounded)) < 0.05:
            return f"{int(round(rounded))}h"
        return f"{rounded:.1f}h"
    return f"{total_ticks}t"


def _sentence_from_note(note):
    text = str(note or "").strip()
    if not text:
        return ""
    text = text[:1].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


OVERWORLD_DISTRICT_GLYPHS = {
    "industrial": "I",
    "residential": "R",
    "downtown": "D",
    "slums": "S",
    "corporate": "C",
    "military": "M",
    "entertainment": "E",
}
OVERWORLD_AREA_GLYPHS = {
    "city": "X",
    "frontier": "F",
    "wilderness": "W",
    "coastal": "O",
}
OVERWORLD_DISTRICT_COLORS = {
    "industrial": "guard",
    "residential": "human",
    "downtown": "player",
    "slums": "cat_purple",
    "corporate": "avian",
    "military": "guard",
    "entertainment": "cat_orange",
}
OVERWORLD_AREA_COLORS = {
    "city": "human",
    "frontier": "cat_tabby",
    "wilderness": "insect",
    "coastal": "avian",
}
OVERWORLD_TERRAIN_GLYPHS = {
    "urban": "u",
    "park": "p",
    "industrial_waste": "x",
    "scrub": "s",
    "plains": "p",
    "badlands": "b",
    "hills": "h",
    "forest": "f",
    "marsh": "m",
    "shore": "o",
    "shoals": "a",
    "dunes": "d",
    "cliffs": "c",
    "salt_flats": "t",
    "lake": "l",
    "ruins": "r",
}
OVERWORLD_TERRAIN_COLORS = {
    "urban": "human",
    "park": "insect",
    "industrial_waste": "guard",
    "scrub": "cat_tabby",
    "plains": "human",
    "badlands": "cat_orange",
    "hills": "guard",
    "forest": "insect",
    "marsh": "insect",
    "shore": "avian",
    "shoals": "avian",
    "dunes": "cat_orange",
    "cliffs": "guard",
    "salt_flats": "cat_gray",
    "lake": "avian",
    "ruins": "cat_purple",
}
OVERWORLD_PATH_GLYPHS = {
    "freeway": "#",
    "road": "=",
    "trail": ":",
}
OVERWORLD_PATH_COLORS = {
    "freeway": "player",
    "road": "human",
    "trail": "cat_tabby",
}


def _overworld_render_style(sim, cx, cy):
    desc = sim.world.overworld_descriptor(cx, cy)
    area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
    district_type = str(desc.get("district_type", "unknown")).strip().lower() or "unknown"
    terrain_key = str(desc.get("terrain", "plain")).strip().lower() or "plain"
    path = str(desc.get("path", "")).strip().lower()
    landmark_here = desc.get("landmark")
    interest = sim.world.overworld_interest(cx, cy, descriptor=desc)

    if isinstance(landmark_here, dict) and landmark_here.get("glyph"):
        glyph = str(landmark_here.get("glyph", "*"))[:1] or "*"
        color = landmark_here.get("color", "human")
    elif interest.get("show_on_map") and interest.get("glyph"):
        glyph = str(interest.get("glyph", "?"))[:1] or "?"
        color = str(interest.get("color", "human") or "human")
    elif path:
        glyph = OVERWORLD_PATH_GLYPHS.get(path, "=")
        color = OVERWORLD_PATH_COLORS.get(path, "human")
    elif area_type == "city":
        if (cx, cy) in sim.world.loaded_chunks:
            glyph = OVERWORLD_DISTRICT_GLYPHS.get(district_type, "X")
            color = OVERWORLD_DISTRICT_COLORS.get(district_type, "human")
        else:
            glyph = OVERWORLD_AREA_GLYPHS.get("city", "X")
            color = OVERWORLD_AREA_COLORS.get("city", "human")
    else:
        glyph = OVERWORLD_TERRAIN_GLYPHS.get(
            terrain_key,
            OVERWORLD_AREA_GLYPHS.get(area_type, "?"),
        )
        color = OVERWORLD_TERRAIN_COLORS.get(
            terrain_key,
            OVERWORLD_AREA_COLORS.get(area_type, "human"),
        )

    if str(glyph).isalpha():
        glyph = str(glyph).upper() if (cx, cy) in sim.world.loaded_chunks else str(glyph).lower()
    return glyph, color


def _overworld_legend_line(sim, cx, cy, text):
    glyph, color = _overworld_render_style(sim, cx, cy)
    return _legend_line(text, glyph=glyph, color=color, attrs=getattr(curses, "A_BOLD", 0))


def _overworld_travel_profile(sim, cx, cy, desc=None, interest=None):
    return sim.world.overworld_travel_profile(cx, cy, descriptor=desc, interest=interest)


def _overworld_discovery_profile(sim, cx, cy, desc=None, interest=None, travel=None):
    return sim.world.overworld_discovery_profile(
        cx,
        cy,
        descriptor=desc,
        interest=interest,
        travel=travel,
    )


def _overworld_travel_tax_text(profile):
    bits = []
    try:
        energy_cost = int(profile.get("energy_cost", 0))
    except (AttributeError, TypeError, ValueError):
        energy_cost = 0
    try:
        safety_cost = int(profile.get("safety_cost", 0))
    except (AttributeError, TypeError, ValueError):
        safety_cost = 0
    try:
        social_cost = int(profile.get("social_cost", 0))
    except (AttributeError, TypeError, ValueError):
        social_cost = 0

    if energy_cost > 0:
        bits.append(f"E{energy_cost}")
    if safety_cost > 0:
        bits.append(f"S{safety_cost}")
    if social_cost > 0:
        bits.append(f"So{social_cost}")
    return "/".join(bits) if bits else "light"


def _overworld_travel_summary_bits(profile):
    if not isinstance(profile, dict):
        return ()
    risk = str(profile.get("risk_label", "")).strip() or "low"
    support = str(profile.get("support_label", "")).strip() or "none"
    return (
        f"risk:{risk}",
        f"support:{support}",
        f"tax:{_overworld_travel_tax_text(profile)}",
    )


def _overworld_discovery_summary_bits(profile):
    if not isinstance(profile, dict):
        return ()
    label = str(profile.get("label", "")).strip()
    if not label:
        return ()
    return (f"opp:{label}",)


def _entity_display_name(sim, eid, title_case=False):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)

    if identity:
        label = str(identity.display_name()).replace("_", " ").strip()
    elif ai:
        label = str(ai.role or "entity").replace("_", " ").strip()
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label


def _storefront_service_role_priority(role):
    role = str(role or "").strip().lower()
    return {
        "owner": 0,
        "manager": 1,
        "staff": 2,
    }.get(role, 3)


def _occupation_service_role(occupation):
    if not occupation:
        return "staff"

    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, dict):
        configured = str(
            workplace.get("authority_role", workplace.get("access_role", ""))
            or ""
        ).strip().lower()
        if configured in {"owner", "manager", "staff"}:
            return configured

    career = str(getattr(occupation, "career", "") or "").strip().lower()
    if any(keyword in career for keyword in ("manager", "director", "lead", "supervisor", "chief", "controller")):
        return "manager"
    return "staff"


def _actor_in_storefront_service_zone(sim, actor_eid, prop):
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(actor_eid)
    if not actor_pos:
        return False, 999999

    focus = _property_focus_position(prop)
    if not focus:
        return False, 999999

    if int(actor_pos.z) != int(focus[2]):
        return False, 999999

    dist = abs(int(actor_pos.x) - int(focus[0])) + abs(int(actor_pos.y) - int(focus[1]))
    if dist <= 2:
        return True, dist

    covered = _property_covering(sim, actor_pos.x, actor_pos.y, actor_pos.z)
    if covered and covered.get("id") == prop.get("id") and dist <= 3:
        return True, dist
    return False, dist


def _storefront_service_profile(sim, prop):
    profile = {
        "mode": "",
        "available": False,
        "blocked_reason": "",
        "service_eid": None,
        "service_name": "",
        "service_role": "",
        "service_note": "",
        "summary_label": "",
        "fallback_self_serve": False,
    }
    if not isinstance(prop, dict) or not _property_is_storefront(prop):
        return profile

    mode = _storefront_service_mode(prop)
    if mode == "automated":
        profile.update({
            "mode": "automated",
            "available": True,
            "service_note": "self-serve",
            "summary_label": "self-serve",
        })
        return profile

    ais = sim.ecs.get(AI)
    occupations = sim.ecs.get(Occupation)
    owner_eid = prop.get("owner_eid")
    candidates_by_eid = {}

    if owner_eid is not None:
        candidates_by_eid[owner_eid] = {
            "eid": owner_eid,
            "role": "owner",
            "occupation": occupations.get(owner_eid),
        }

    for member in property_org_members(sim, prop):
        actor_eid = member.get("eid")
        occupation = member.get("occupation")
        existing = candidates_by_eid.get(actor_eid)
        role = "owner" if actor_eid == owner_eid else str(member.get("role", "") or "").strip().lower()
        if role not in {"owner", "manager", "staff"}:
            role = _occupation_service_role(occupation)
        if existing and existing.get("role") == "owner":
            continue
        candidates_by_eid[actor_eid] = {
            "eid": actor_eid,
            "role": role,
            "occupation": occupation,
            "source": member.get("source", "workplace"),
        }

    available = []
    for info in candidates_by_eid.values():
        actor_eid = info["eid"]
        present, distance = _actor_in_storefront_service_zone(sim, actor_eid, prop)
        occupation = info.get("occupation")
        ai = ais.get(actor_eid)
        on_shift = False
        if occupation and (
            occupation_targets_property(prop, occupation)
            or str(info.get("source", "")).strip().lower() == "affiliation"
        ):
            on_shift = bool(
                work_shift_active(
                    sim,
                    occupation=occupation,
                    workplace_prop=prop,
                    role=getattr(ai, "role", None),
                )
            )
        if not present:
            continue
        if info["role"] != "owner" and occupation and not on_shift:
            continue
        available.append((info["role"], distance, actor_eid))

    if available:
        available.sort(key=lambda row: (_storefront_service_role_priority(row[0]), row[1], row[2]))
        service_role, _distance, service_eid = available[0]
        service_name = _entity_display_name(sim, service_eid, title_case=True)
        profile.update({
            "mode": "staffed",
            "available": True,
            "service_eid": service_eid,
            "service_name": service_name,
            "service_role": service_role,
            "service_note": f"served by {service_name}" if service_name else "counter service",
            "summary_label": f"counter:{service_name}" if service_name else "counter",
        })
        return profile

    if candidates_by_eid:
        profile.update({
            "mode": "staffed",
            "available": False,
            "blocked_reason": "no_staff",
            "service_note": "counter service",
            "summary_label": "counter",
        })
        return profile

    profile.update({
        "mode": "automated",
        "available": True,
        "service_note": "unattended self-serve",
        "summary_label": "self-serve",
        "fallback_self_serve": True,
    })
    return profile


CASINO_CARD_RANKS = "23456789TJQKA"
CASINO_CARD_SUITS = ("S", "H", "D", "C")
CASINO_CARD_VALUE_BY_RANK = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}
CASINO_RANK_NAME_BY_VALUE = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "jack",
    12: "queen",
    13: "king",
    14: "ace",
}
CASINO_SLOT_REELS = (
    ("CHERRY", "LEMON", "BAR", "HORSESHOE", "BELL", "CHERRY", "BAR", "SEVEN", "LEMON", "BAR", "BELL", "SEVEN"),
    ("BAR", "CHERRY", "BELL", "LEMON", "BAR", "HORSESHOE", "SEVEN", "CHERRY", "BAR", "BELL", "LEMON", "SEVEN"),
    ("LEMON", "BAR", "CHERRY", "SEVEN", "BAR", "BELL", "CHERRY", "HORSESHOE", "BAR", "SEVEN", "LEMON", "BELL"),
)
CASINO_SLOT_SYMBOL_LABELS = {
    "CHERRY": "Cherry",
    "LEMON": "Lemon",
    "BAR": "Bar",
    "HORSESHOE": "Horseshoe",
    "BELL": "Bell",
    "SEVEN": "Seven",
}
CASINO_PLINKO_LANE_COUNT = 7
CASINO_PLINKO_ROWS = 8
CASINO_PLINKO_BUCKET_MULTIPLIERS = (0.0, 0.4, 0.8, 1.2, 3.0, 1.2, 0.8, 0.4, 0.0)
CASINO_POKER_CATEGORY_NAMES = {
    8: "straight flush",
    7: "four of a kind",
    6: "full house",
    5: "flush",
    4: "straight",
    3: "three of a kind",
    2: "two pair",
    1: "pair",
    0: "high card",
}
CASINO_HOLDEM_ANTE_BONUS_MULTIPLIERS = {
    "royal_flush": 100,
    8: 20,
    7: 10,
    6: 3,
    5: 2,
    4: 1,
}
CASINO_GAME_PROFILES = {
    "slots": {
        "title": "Slots",
        "service_label": "slots",
        "menu_label": "Play slots",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a stake and let the reels fly.",
        "note": "Three reels, classic symbols, and a loud machine when the sevens land.",
        "social_gain": (1, 3),
    },
    "casino_holdem": {
        "title": "Casino Hold'em",
        "service_label": "casino hold'em",
        "menu_label": "Play casino hold'em",
        "bet_options": (25, 50, 100),
        "prompt": "Post an ante, read the flop, then decide whether to call or fold.",
        "note": "You get two hole cards, the flop comes out first, and calling adds a matching stake.",
        "social_gain": (2, 5),
    },
    "plinko": {
        "title": "Plinko",
        "service_label": "plinko",
        "menu_label": "Play plinko",
        "bet_options": (5, 15, 30),
        "prompt": "Choose a chip size and a drop lane.",
        "note": "The center buckets pay best if the pegs break your way.",
        "social_gain": (1, 3),
    },
    "twenty_one": {
        "title": "21",
        "service_label": "21",
        "menu_label": "Play 21",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a wager and play a real hand against the dealer.",
        "note": "Hit, stand, and hope the house runs cold.",
        "social_gain": (2, 4),
    },
}
CASINO_GAME_SERVICE_IDS = frozenset(CASINO_GAME_PROFILES)


def _site_service_state(sim):
    state = getattr(sim, "site_service_state", None)
    if not isinstance(state, dict):
        state = {"cooldowns": {}}
        sim.site_service_state = state
    cooldowns = state.get("cooldowns")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["cooldowns"] = cooldowns
    return state


def _vehicle_sale_quality(quality):
    quality = str(quality or "used").strip().lower()
    if quality not in {"new", "used"}:
        return "used"
    return quality


def _vehicle_sale_quality_title(quality):
    return "New" if _vehicle_sale_quality(quality) == "new" else "Used"


def _vehicle_sale_stock_count(quality):
    quality = _vehicle_sale_quality(quality)
    return 3 if quality == "new" else 5


def _vehicle_sale_inventory(sim):
    state = _site_service_state(sim)
    inventory = state.get("vehicle_sale_inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        state["vehicle_sale_inventory"] = inventory
    return inventory


def _vehicle_sale_offer_record(profile, quality, cycle_index, slot_index):
    quality = _vehicle_sale_quality(quality)
    vehicle_name = f"{profile.get('make', 'Unknown')} {profile.get('model', 'Vehicle')}"
    return {
        "offering_id": f"{quality}-{int(cycle_index)}-{int(slot_index)}",
        "quality": quality,
        "vehicle_name": vehicle_name,
        "make": str(profile.get("make", "Unknown")).strip() or "Unknown",
        "model": str(profile.get("model", "Vehicle")).strip() or "Vehicle",
        "vehicle_class": str(profile.get("vehicle_class", "sedan")).strip().lower() or "sedan",
        "price": int(max(80, _int_or_default(profile.get("price"), 500))),
        "power": max(1, min(10, _int_or_default(profile.get("power"), 5))),
        "durability": max(1, min(10, _int_or_default(profile.get("durability"), 5))),
        "fuel_efficiency": max(1, min(10, _int_or_default(profile.get("fuel_efficiency"), 5))),
        "fuel": max(0, _int_or_default(profile.get("fuel"), _int_or_default(profile.get("fuel_capacity"), 60))),
        "fuel_capacity": max(10, _int_or_default(profile.get("fuel_capacity"), 60)),
        "glyph": str(profile.get("glyph", "&"))[:1] or "&",
        "paint": str(profile.get("paint", "")).strip(),
        "display_color": str(profile.get("paint", "")).strip() or "vehicle_parked",
    }


def _vehicle_sale_generate_offers(sim, prop_or_id, quality, cycle_index):
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    quality = _vehicle_sale_quality(quality)
    offers = []
    for slot_index in range(_vehicle_sale_stock_count(quality)):
        rng = random.Random(f"{sim.seed}:vehicle_sale_inventory:{prop_id}:{quality}:{int(cycle_index)}:{int(slot_index)}")
        profile = roll_vehicle_profile(rng, quality=quality)
        profile["paint"] = roll_vehicle_paint_key(rng, quality=quality)
        offers.append(_vehicle_sale_offer_record(profile, quality, cycle_index, slot_index))
    offers.sort(key=lambda offer: (int(offer.get("price", 0)), str(offer.get("vehicle_name", ""))))
    for slot_index, offer in enumerate(offers):
        offer["offering_id"] = f"{quality}-{int(cycle_index)}-{int(slot_index)}"
    return offers


def _vehicle_sale_listing(sim, prop_or_id, quality, *, create=True):
    inventory = _vehicle_sale_inventory(sim)
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    quality = _vehicle_sale_quality(quality)
    key = (str(prop_id), quality)
    listing = inventory.get(key)
    if not isinstance(listing, dict):
        listing = None
    if listing is not None:
        offers = listing.get("offers")
        if not isinstance(offers, list):
            offers = []
            listing["offers"] = offers
    if create and (listing is None or not list(listing.get("offers", ()) or ())):
        next_cycle = int(listing.get("cycle", -1)) + 1 if isinstance(listing, dict) else 0
        listing = {
            "property_id": str(prop_id),
            "quality": quality,
            "cycle": int(next_cycle),
            "offers": _vehicle_sale_generate_offers(sim, prop_id, quality, next_cycle),
        }
        inventory[key] = listing
    return listing


def _vehicle_sale_offers(sim, prop_or_id, quality):
    listing = _vehicle_sale_listing(sim, prop_or_id, quality, create=True)
    offers = list(listing.get("offers", ()) or []) if isinstance(listing, dict) else []
    return [dict(offer) for offer in offers if isinstance(offer, dict)]


def _vehicle_sale_lookup_offer(sim, prop_or_id, quality, offering_id=None):
    listing = _vehicle_sale_listing(sim, prop_or_id, quality, create=True)
    offers = list(listing.get("offers", ()) or []) if isinstance(listing, dict) else []
    if not offers:
        return None
    offering_id = str(offering_id or "").strip().lower()
    if offering_id:
        for offer in offers:
            if str(offer.get("offering_id", "")).strip().lower() == offering_id:
                return dict(offer)
    return dict(offers[0])


def _vehicle_sale_remove_offer(sim, prop_or_id, quality, offering_id):
    listing = _vehicle_sale_listing(sim, prop_or_id, quality, create=False)
    if not isinstance(listing, dict):
        return None
    offers = list(listing.get("offers", ()) or [])
    offering_id = str(offering_id or "").strip().lower()
    for idx, offer in enumerate(offers):
        if str(offer.get("offering_id", "")).strip().lower() != offering_id:
            continue
        removed = dict(offer)
        del offers[idx]
        listing["offers"] = offers
        return removed
    return None


def _vehicle_sale_stats_text(data):
    if not isinstance(data, dict):
        return ""
    vehicle_class = str(data.get("vehicle_class", "")).strip().replace("_", " ")
    power = max(1, min(10, _int_or_default(data.get("power"), 5)))
    durability = max(1, min(10, _int_or_default(data.get("durability"), 5)))
    fuel_efficiency = max(1, min(10, _int_or_default(data.get("fuel_efficiency"), 5)))
    fuel_capacity = max(0, _int_or_default(data.get("fuel_capacity"), 0))
    fuel = max(0, min(fuel_capacity if fuel_capacity > 0 else 9999, _int_or_default(data.get("fuel"), fuel_capacity)))
    bits = []
    if vehicle_class:
        bits.append(vehicle_class.title())
    if fuel_capacity > 0:
        bits.append(f"fuel {fuel}/{fuel_capacity}")
    bits.append(f"P{power}/D{durability}/E{fuel_efficiency}")
    return " | ".join(bits)


def _vehicle_sale_offer_label(offer):
    if not isinstance(offer, dict):
        return "Vehicle"
    vehicle_name = str(offer.get("vehicle_name", "Vehicle")).strip() or "Vehicle"
    price = _credit_amount_label(offer.get("price", 0))
    stats = _vehicle_sale_stats_text(offer)
    if stats:
        return f"{vehicle_name} {price} {stats}"
    return f"{vehicle_name} {price}"


def _site_service_roll_index(sim, eid, prop_or_id, service):
    state = _site_service_state(sim)
    rolls = state.get("roll_counts")
    if not isinstance(rolls, dict):
        rolls = {}
        state["roll_counts"] = rolls
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    key = (int(eid), str(prop_id), str(service or "").strip().lower())
    index = int(rolls.get(key, 0))
    rolls[key] = index + 1
    return index


def _casino_round_seed(sim, eid, prop_or_id, service, wager, round_index):
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    return (
        f"{sim.seed}:casino:{prop_id}:{int(eid)}:{str(service or '').strip().lower()}:"
        f"{int(sim.tick)}:{int(round_index)}:{int(wager)}"
    )


def _casino_social_gain(service, seed_token):
    profile = _casino_game_profile(service)
    social_lo, social_hi = (1, 3)
    if profile:
        social_lo, social_hi = profile.get("social_gain", (1, 3))
    social_rng = random.Random(f"{seed_token}:social")
    social_lo = int(social_lo)
    social_hi = int(max(social_lo, social_hi))
    return social_rng.randint(social_lo, social_hi)


def _casino_card_rank(card):
    return CASINO_CARD_VALUE_BY_RANK.get(str(card or "??")[0].upper(), 0)


def _casino_card_suit(card):
    text = str(card or "??").strip().upper()
    return text[1:2] if len(text) >= 2 else "?"


def _casino_card_label(card):
    text = str(card or "??").strip().upper()
    if len(text) < 2:
        return "??"
    rank = text[0]
    suit = text[1]
    rank_label = "10" if rank == "T" else rank
    return f"{rank_label}{suit}"


def _casino_cards_text(cards):
    rendered = [_casino_card_label(card) for card in list(cards or ())]
    return " ".join(rendered) if rendered else "--"


def _casino_shuffled_deck(seed_token):
    deck = [f"{rank}{suit}" for suit in CASINO_CARD_SUITS for rank in CASINO_CARD_RANKS]
    rng = random.Random(f"{seed_token}:deck")
    rng.shuffle(deck)
    return deck


def _casino_blackjack_value(card):
    rank = str(card or "??").strip().upper()[:1]
    if rank == "A":
        return 11
    if rank in {"T", "J", "Q", "K"}:
        return 10
    try:
        return int(rank)
    except (TypeError, ValueError):
        return 0


def _casino_blackjack_total(cards):
    total = 0
    aces = 0
    for card in list(cards or ()):
        total += _casino_blackjack_value(card)
        if str(card or "??").strip().upper().startswith("A"):
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total, aces > 0


def _casino_blackjack_line(label, cards, *, hide_hole=False):
    shown = []
    for idx, card in enumerate(list(cards or ())):
        if hide_hole and idx == 1:
            shown.append("??")
        else:
            shown.append(_casino_card_label(card))
    total, soft = _casino_blackjack_total(cards)
    suffix = ""
    if not hide_hole:
        suffix = f" ({total}"
        if soft and total <= 21:
            suffix += " soft"
        suffix += ")"
    return f"{label}: {' '.join(shown) if shown else '--'}{suffix}"


def _casino_straight_high(ranks):
    unique = sorted({int(rank) for rank in list(ranks or ()) if int(rank) > 0}, reverse=True)
    if 14 in unique:
        unique.append(1)
    streak = 1
    for idx in range(len(unique) - 1):
        if unique[idx] - 1 == unique[idx + 1]:
            streak += 1
            if streak >= 5:
                return unique[idx - 3]
        elif unique[idx] != unique[idx + 1]:
            streak = 1
    return 0


def _casino_rank_name(rank):
    return CASINO_RANK_NAME_BY_VALUE.get(int(rank), str(rank))


def _casino_poker_hand_name(score):
    category = int(score[0]) if score else 0
    primary = int(score[1]) if len(score) > 1 else 0
    secondary = int(score[2]) if len(score) > 2 else 0
    if category == 8 and primary == 14:
        return "royal flush"
    if category == 8:
        return f"{_casino_rank_name(primary)}-high straight flush"
    if category == 7:
        return f"four {_casino_rank_name(primary)}s"
    if category == 6:
        return f"{_casino_rank_name(primary)}s full of {_casino_rank_name(secondary)}s"
    if category == 5:
        return f"{_casino_rank_name(primary)}-high flush"
    if category == 4:
        return f"{_casino_rank_name(primary)}-high straight"
    if category == 3:
        return f"three {_casino_rank_name(primary)}s"
    if category == 2:
        return f"{_casino_rank_name(primary)}s and {_casino_rank_name(secondary)}s"
    if category == 1:
        return f"pair of {_casino_rank_name(primary)}s"
    return f"{_casino_rank_name(primary)}-high"


def _casino_evaluate_five_card_poker(cards):
    ranks = sorted((_casino_card_rank(card) for card in list(cards or ())), reverse=True)
    suits = [_casino_card_suit(card) for card in list(cards or ())]
    counts = Counter(ranks)
    ordered_counts = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = len(set(suits)) == 1 if suits else False
    straight_high = _casino_straight_high(ranks)

    if flush and straight_high:
        return (8, straight_high)

    if ordered_counts and ordered_counts[0][1] == 4:
        quad_rank = ordered_counts[0][0]
        kicker = max(rank for rank in ranks if rank != quad_rank)
        return (7, quad_rank, kicker)

    if len(ordered_counts) >= 2 and ordered_counts[0][1] == 3 and ordered_counts[1][1] >= 2:
        return (6, ordered_counts[0][0], ordered_counts[1][0])

    if flush:
        return tuple([5] + sorted(ranks, reverse=True))

    if straight_high:
        return (4, straight_high)

    if ordered_counts and ordered_counts[0][1] == 3:
        trips = ordered_counts[0][0]
        kickers = sorted((rank for rank in ranks if rank != trips), reverse=True)
        return tuple([3, trips] + kickers)

    pair_ranks = [rank for rank, count in ordered_counts if count == 2]
    if len(pair_ranks) >= 2:
        high_pair, low_pair = sorted(pair_ranks, reverse=True)[:2]
        kicker = max(rank for rank in ranks if rank not in {high_pair, low_pair})
        return (2, high_pair, low_pair, kicker)

    if len(pair_ranks) == 1:
        pair_rank = pair_ranks[0]
        kickers = sorted((rank for rank in ranks if rank != pair_rank), reverse=True)
        return tuple([1, pair_rank] + kickers)

    return tuple([0] + sorted(ranks, reverse=True))


def _casino_best_poker_hand(cards):
    best_score = None
    best_cards = None
    for combo in itertools.combinations(list(cards or ()), 5):
        score = _casino_evaluate_five_card_poker(combo)
        if best_score is None or score > best_score:
            best_score = score
            best_cards = combo
    if best_score is None:
        best_score = (0, 0)
        best_cards = ()
    return {
        "score": best_score,
        "name": _casino_poker_hand_name(best_score),
        "category": CASINO_POKER_CATEGORY_NAMES.get(int(best_score[0]), "hand"),
        "cards": tuple(best_cards),
    }


def _casino_slots_resolve(seed_token, wager):
    reels = []
    spin_rng = random.Random(f"{seed_token}:slots")
    for strip in CASINO_SLOT_REELS:
        reels.append(str(strip[spin_rng.randrange(len(strip))]).strip().upper() or "BAR")
    counts = Counter(reels)
    payout_mult = 0.0
    outcome_key = "blank"
    headline = "Cold reels."
    detail = "The machine clacks through a dead spin and the house keeps the bet."
    if len(counts) == 1:
        symbol = reels[0]
        if symbol == "SEVEN":
            payout_mult = 8.0
            outcome_key = "jackpot"
            headline = "Triple sevens."
            detail = "All three reels land on sevens and the cabinet starts screaming."
        elif symbol == "BAR":
            payout_mult = 5.0
            outcome_key = "triple_bar"
            headline = "Triple bars."
            detail = "The bars line up cleanly and the hopper rattles out a chunky win."
        elif symbol == "BELL":
            payout_mult = 4.0
            outcome_key = "triple_bell"
            headline = "Bell line."
            detail = "Three bells ring together and the machine pays with gusto."
        elif symbol == "CHERRY":
            payout_mult = 3.0
            outcome_key = "triple_cherry"
            headline = "Cherry line."
            detail = "Three cherries roll through and the house coughs up a bright little prize."
        else:
            payout_mult = 2.0
            outcome_key = "triple_match"
            headline = "Full match."
            detail = "All three reels match for a tidy line hit."
    elif counts.get("CHERRY", 0) == 2:
        payout_mult = 1.4
        outcome_key = "double_cherry"
        headline = "Two cherries."
        detail = "A pair of cherries catches the payline and softens the swing."
    elif counts.get("CHERRY", 0) == 1 and counts.get("SEVEN", 0) == 1:
        payout_mult = 1.1
        outcome_key = "mixed_line"
        headline = "Mixed line."
        detail = "A cherry and a seven clip the line for a tiny kickback."

    payout = max(0, int(round(float(payout_mult) * float(wager))))
    reel_text = " | ".join(CASINO_SLOT_SYMBOL_LABELS.get(symbol, symbol.title()) for symbol in reels)
    return {
        "service": "slots",
        "wager": int(wager),
        "stake": int(wager),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Reels {reel_text}. {headline}",
        "result_lines": [
            f"Reels: {reel_text}",
            detail,
        ],
        "reels": tuple(reels),
        "social_gain": _casino_social_gain("slots", seed_token),
    }


def _casino_plinko_resolve(seed_token, wager, drop_lane):
    lane = max(0, min(int(drop_lane), CASINO_PLINKO_LANE_COUNT - 1))
    bounce_rng = random.Random(f"{seed_token}:plinko:{lane}")
    position = lane + 1
    path = []
    for _ in range(CASINO_PLINKO_ROWS):
        step = -1 if bounce_rng.random() < 0.5 else 1
        path.append("L" if step < 0 else "R")
        position = max(0, min(position + step, len(CASINO_PLINKO_BUCKET_MULTIPLIERS) - 1))
    payout_mult = float(CASINO_PLINKO_BUCKET_MULTIPLIERS[position])
    payout = max(0, int(round(float(wager) * payout_mult)))
    if payout_mult <= 0.0:
        headline = "Edge bucket."
        detail = "The disc chatters off the pegs and dies in a zero lane."
        outcome_key = "rim"
    elif payout_mult < 1.0:
        headline = "Shallow bucket."
        detail = "The board gives a little back, but not enough to cover the full drop."
        outcome_key = "low"
    elif payout_mult < 2.0:
        headline = "Middle bucket."
        detail = "The disc settles into a fair-paying lane and the crowd gives a polite murmur."
        outcome_key = "mid"
    else:
        headline = "Center bucket."
        detail = "The disc fights through the pegs and snaps into the hot center pocket."
        outcome_key = "center"
    return {
        "service": "plinko",
        "wager": int(wager),
        "stake": int(wager),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Lane {lane + 1} rides {' '.join(path)} into bucket {position + 1}. {headline}",
        "result_lines": [
            f"Drop lane {lane + 1}: {' '.join(path)}",
            f"Bucket {position + 1} pays x{payout_mult:.1f}.",
            detail,
        ],
        "drop_lane": int(lane),
        "bucket_index": int(position),
        "path": tuple(path),
        "social_gain": _casino_social_gain("plinko", seed_token),
    }


def _casino_blackjack_can_split(cards):
    cards = list(cards or ())
    if len(cards) != 2:
        return False
    return _casino_blackjack_value(cards[0]) == _casino_blackjack_value(cards[1])


def _casino_twenty_one_hand(cards, stake, *, state="pending", doubled=False, natural_eligible=True, split_origin=False):
    return {
        "cards": list(cards or ()),
        "stake": int(stake),
        "state": str(state or "pending").strip().lower() or "pending",
        "doubled": bool(doubled),
        "natural_eligible": bool(natural_eligible),
        "split_origin": bool(split_origin),
    }


def _casino_twenty_one_normalize_session(session):
    if not isinstance(session, dict):
        return None
    current = {
        "service": "twenty_one",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "deck": list(session.get("deck", ()) or ()),
        "deck_index": int(session.get("deck_index", 0)),
        "dealer_cards": list(session.get("dealer_cards", ()) or ()),
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "split_used": bool(session.get("split_used", False)),
    }
    raw_hands = list(session.get("hands", ()) or ())
    hands = []
    if raw_hands:
        for idx, raw in enumerate(raw_hands):
            raw = raw if isinstance(raw, dict) else {}
            hands.append(_casino_twenty_one_hand(
                raw.get("cards", ()),
                raw.get("stake", current["wager"]),
                state=raw.get("state", "active" if idx == 0 else "pending"),
                doubled=raw.get("doubled", False),
                natural_eligible=raw.get("natural_eligible", True),
                split_origin=raw.get("split_origin", False),
            ))
    else:
        hands.append(_casino_twenty_one_hand(
            session.get("player_cards", ()),
            current["stake"],
            state="active",
            natural_eligible=True,
        ))
    current["hands"] = hands
    current["split_used"] = bool(current["split_used"] or len(hands) > 1)
    active_hand_index = int(session.get("active_hand_index", 0))
    active_found = False
    for idx, hand in enumerate(current["hands"]):
        state = str(hand.get("state", "pending")).strip().lower()
        if state == "active":
            current["active_hand_index"] = idx
            active_found = True
            break
    if not active_found:
        if current["hands"]:
            active_hand_index = max(0, min(active_hand_index, len(current["hands"]) - 1))
            if str(current["hands"][active_hand_index].get("state", "pending")).strip().lower() == "pending":
                current["hands"][active_hand_index]["state"] = "active"
                current["active_hand_index"] = active_hand_index
                active_found = True
        if not active_found:
            for idx, hand in enumerate(current["hands"]):
                if str(hand.get("state", "pending")).strip().lower() == "pending":
                    hand["state"] = "active"
                    current["active_hand_index"] = idx
                    active_found = True
                    break
    if not active_found:
        current["active_hand_index"] = -1
    current["stake"] = sum(max(0, int(hand.get("stake", 0))) for hand in current["hands"])
    return current


def _casino_twenty_one_active_hand(session):
    if not isinstance(session, dict):
        return None
    hands = list(session.get("hands", ()) or ())
    idx = int(session.get("active_hand_index", -1))
    if 0 <= idx < len(hands):
        return hands[idx]
    return None


def _casino_twenty_one_draw_card(session):
    if not isinstance(session, dict):
        return None
    deck = list(session.get("deck", ()) or ())
    deck_index = int(session.get("deck_index", 0))
    if deck_index >= len(deck):
        return None
    card = deck[deck_index]
    session["deck_index"] = deck_index + 1
    return card


def _casino_twenty_one_activate_next_hand(session):
    if not isinstance(session, dict):
        return False
    for idx, hand in enumerate(list(session.get("hands", ()) or ())):
        if str(hand.get("state", "pending")).strip().lower() == "pending":
            hand["state"] = "active"
            session["active_hand_index"] = idx
            return True
    session["active_hand_index"] = -1
    return False


def _casino_twenty_one_auto_progress(session):
    if not isinstance(session, dict):
        return False
    while True:
        hand = _casino_twenty_one_active_hand(session)
        if not isinstance(hand, dict):
            return False
        total, _soft = _casino_blackjack_total(hand.get("cards", ()))
        if total > 21:
            hand["state"] = "bust"
        elif total == 21:
            hand["state"] = "stood"
        else:
            return True
        if not _casino_twenty_one_activate_next_hand(session):
            return False


def _casino_twenty_one_action_ids(session, wallet_credits=0):
    current = _casino_twenty_one_normalize_session(session)
    hand = _casino_twenty_one_active_hand(current)
    if not current or not isinstance(hand, dict):
        return ()
    action_ids = ["twenty_one:hit", "twenty_one:stand"]
    wager = int(current.get("wager", 0))
    if len(list(hand.get("cards", ()) or ())) == 2 and wallet_credits >= wager:
        action_ids.append("twenty_one:double")
        if (
            len(list(current.get("hands", ()) or ())) == 1
            and not bool(current.get("split_used", False))
            and _casino_blackjack_can_split(hand.get("cards", ()))
        ):
            action_ids.append("twenty_one:split")
    return tuple(action_ids)


def _casino_twenty_one_finalize(session):
    current = _casino_twenty_one_normalize_session(session)
    if not current:
        return None
    while True:
        dealer_total, dealer_soft = _casino_blackjack_total(current["dealer_cards"])
        if dealer_total > 17:
            break
        if dealer_total == 17 and not dealer_soft:
            break
        card = _casino_twenty_one_draw_card(current)
        if not card:
            break
        current["dealer_cards"].append(card)

    dealer_total, _dealer_soft = _casino_blackjack_total(current["dealer_cards"])
    hand_results = []
    payout = 0
    for idx, hand in enumerate(current["hands"]):
        cards = list(hand.get("cards", ()) or ())
        total, _soft = _casino_blackjack_total(cards)
        hand_stake = int(hand.get("stake", current["wager"]))
        if total > 21 or str(hand.get("state", "")).strip().lower() == "bust":
            result_key = "bust"
            hand_payout = 0
        elif dealer_total > 21 or total > dealer_total:
            result_key = "win"
            hand_payout = hand_stake * 2
        elif dealer_total == total:
            result_key = "push"
            hand_payout = hand_stake
        else:
            result_key = "lose"
            hand_payout = 0
        hand_results.append({
            "index": idx,
            "cards": tuple(cards),
            "total": int(total),
            "stake": int(hand_stake),
            "result": result_key,
            "doubled": bool(hand.get("doubled", False)),
            "split_origin": bool(hand.get("split_origin", False)),
        })
        payout += int(hand_payout)

    result_counter = Counter(row["result"] for row in hand_results)
    if result_counter.get("win", 0) > 0 and result_counter.get("lose", 0) == 0 and result_counter.get("bust", 0) == 0:
        outcome_key = "player_win"
        headline = "You beat the dealer."
    elif result_counter.get("win", 0) > 0 and (result_counter.get("lose", 0) > 0 or result_counter.get("bust", 0) > 0):
        outcome_key = "mixed"
        headline = "The split goes both ways."
    elif result_counter.get("push", 0) == len(hand_results):
        outcome_key = "push"
        headline = "Push."
    elif dealer_total > 21 and result_counter.get("bust", 0) == len(hand_results):
        outcome_key = "player_bust"
        headline = "Every hand busts."
    elif dealer_total > 21:
        outcome_key = "dealer_bust"
        headline = "Dealer busts."
    elif result_counter.get("bust", 0) == len(hand_results):
        outcome_key = "player_bust"
        headline = "Every hand busts."
    else:
        outcome_key = "dealer_win"
        headline = "Dealer takes it."

    detail_bits = []
    for row in hand_results:
        label = f"Hand {row['index'] + 1}"
        status = row["result"]
        if status == "win":
            status_text = "wins"
        elif status == "push":
            status_text = "pushes"
        elif status == "bust":
            status_text = "busts"
        else:
            status_text = "loses"
        detail_bits.append(f"{label} {status_text}")
    detail = ", ".join(detail_bits) + "."

    result_lines = [_casino_blackjack_line("Dealer", current["dealer_cards"])]
    for row in hand_results:
        tags = []
        if row["split_origin"]:
            tags.append("split")
        if row["doubled"]:
            tags.append("double")
        suffix = f" [{', '.join(tags)}]" if tags else ""
        hand_label = f"Hand {row['index'] + 1}"
        result_lines.append(f"{_casino_blackjack_line(hand_label, row['cards'])}{suffix} -> {row['result']}.")
    result_lines.append(detail)

    return {
        "service": "twenty_one",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": (
            f"Dealer {_casino_cards_text(current['dealer_cards'])} ({dealer_total}). "
            f"{detail}"
        ),
        "result_lines": result_lines,
        "player_cards": tuple(hand_results[0]["cards"]) if hand_results else (),
        "player_hands": tuple(row["cards"] for row in hand_results),
        "player_total": int(hand_results[0]["total"]) if hand_results else 0,
        "player_totals": tuple(int(row["total"]) for row in hand_results),
        "dealer_cards": tuple(current["dealer_cards"]),
        "dealer_total": int(dealer_total),
        "hand_results": tuple(
            {
                "index": int(row["index"]),
                "total": int(row["total"]),
                "stake": int(row["stake"]),
                "result": str(row["result"]),
                "doubled": bool(row["doubled"]),
                "split_origin": bool(row["split_origin"]),
            }
            for row in hand_results
        ),
        "social_gain": _casino_social_gain("twenty_one", f"{current['seed_token']}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_twenty_one_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "twenty_one",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "deck": list(deck),
        "deck_index": 4,
        "dealer_cards": [deck[1], deck[3]],
        "hands": [
            _casino_twenty_one_hand([deck[0], deck[2]], int(wager), state="active", natural_eligible=True),
        ],
        "active_hand_index": 0,
        "split_used": False,
    }


def _casino_twenty_one_resolve(session, action):
    current = _casino_twenty_one_normalize_session(session)
    if not current:
        return None, None
    action = str(action or "").strip().lower()
    active_hand = _casino_twenty_one_active_hand(current)
    dealer_total, _dealer_soft = _casino_blackjack_total(current["dealer_cards"])

    if action == "start" and isinstance(active_hand, dict):
        player_total, _player_soft = _casino_blackjack_total(active_hand.get("cards", ()))
        player_natural = len(list(active_hand.get("cards", ()) or ())) == 2 and player_total == 21 and bool(active_hand.get("natural_eligible", True))
        dealer_natural = len(current["dealer_cards"]) == 2 and dealer_total == 21
        if player_natural or dealer_natural:
            if player_natural and dealer_natural:
                outcome_key = "push_blackjack"
                payout = int(active_hand.get("stake", current["wager"]))
                headline = "Both hands open hot."
                detail = "You and the dealer both flip blackjack, so the bet pushes."
            elif player_natural:
                outcome_key = "player_blackjack"
                payout = int(round(float(active_hand.get("stake", current["wager"])) * 2.5))
                headline = "Natural 21."
                detail = "You peel blackjack off the deal and the table pays 3 to 2."
            else:
                outcome_key = "dealer_blackjack"
                payout = 0
                headline = "Dealer blackjack."
                detail = "The dealer turns over a natural and sweeps the felt clean."
            return None, {
                "service": "twenty_one",
                "wager": int(current["wager"]),
                "stake": int(current["stake"]),
                "payout": int(payout),
                "outcome_key": outcome_key,
                "headline": headline,
                "detail": detail,
                "summary": (
                    f"Dealer {_casino_cards_text(current['dealer_cards'])} against "
                    f"{_casino_cards_text(active_hand.get('cards', ())) }. {headline}"
                ).replace("  ", " "),
                "result_lines": [
                    _casino_blackjack_line("Dealer", current["dealer_cards"]),
                    _casino_blackjack_line("You", active_hand.get("cards", ())),
                    detail,
                ],
                "player_cards": tuple(active_hand.get("cards", ()) or ()),
                "player_hands": (tuple(active_hand.get("cards", ()) or ()),),
                "player_total": int(player_total),
                "player_totals": (int(player_total),),
                "dealer_cards": tuple(current["dealer_cards"]),
                "dealer_total": int(dealer_total),
                "social_gain": _casino_social_gain("twenty_one", current["seed_token"]),
                "stake_already_paid": True,
            }
        return current, None

    if not isinstance(active_hand, dict):
        return None, _casino_twenty_one_finalize(current)

    if action == "split" and _casino_blackjack_can_split(active_hand.get("cards", ())):
        cards = list(active_hand.get("cards", ()) or ())
        card_a = _casino_twenty_one_draw_card(current)
        card_b = _casino_twenty_one_draw_card(current)
        if card_a:
            current["hands"][0] = _casino_twenty_one_hand(
                [cards[0], card_a],
                current["wager"],
                state="active",
                natural_eligible=False,
                split_origin=True,
            )
        if card_b:
            current["hands"].append(_casino_twenty_one_hand(
                [cards[1], card_b],
                current["wager"],
                state="pending",
                natural_eligible=False,
                split_origin=True,
            ))
        current["active_hand_index"] = 0
        current["split_used"] = True
        current["stake"] = sum(int(hand.get("stake", 0)) for hand in current["hands"])
        if _casino_twenty_one_auto_progress(current):
            return current, None
        return None, _casino_twenty_one_finalize(current)

    if action == "double":
        active_hand["stake"] = int(active_hand.get("stake", current["wager"])) + int(current["wager"])
        active_hand["doubled"] = True
        current["stake"] = sum(int(hand.get("stake", 0)) for hand in current["hands"])
        card = _casino_twenty_one_draw_card(current)
        if card:
            active_hand["cards"].append(card)
        total, _soft = _casino_blackjack_total(active_hand.get("cards", ()))
        active_hand["state"] = "bust" if total > 21 else "stood"
        if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
            return current, None
        return None, _casino_twenty_one_finalize(current)

    if action == "hit":
        card = _casino_twenty_one_draw_card(current)
        if card:
            active_hand["cards"].append(card)
        total, _soft = _casino_blackjack_total(active_hand.get("cards", ()))
        if total > 21:
            active_hand["state"] = "bust"
            if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
                return current, None
            return None, _casino_twenty_one_finalize(current)
        if total == 21:
            active_hand["state"] = "stood"
            if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
                return current, None
            return None, _casino_twenty_one_finalize(current)
        return current, None

    if action == "stand":
        active_hand["state"] = "stood"
        if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
            return current, None
        return None, _casino_twenty_one_finalize(current)

    return current, None


def _casino_holdem_dealer_qualifies(score):
    if not score:
        return False
    category = int(score[0])
    if category >= 2:
        return True
    if category == 1:
        return int(score[1]) >= 4
    return False


def _casino_holdem_ante_bonus_multiplier(score):
    if not score:
        return 0
    if int(score[0]) == 8 and len(score) > 1 and int(score[1]) == 14:
        return int(CASINO_HOLDEM_ANTE_BONUS_MULTIPLIERS.get("royal_flush", 0))
    return int(CASINO_HOLDEM_ANTE_BONUS_MULTIPLIERS.get(int(score[0]), 0))


def _casino_holdem_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "casino_holdem",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "player_cards": [deck[0], deck[2]],
        "dealer_cards": [deck[1], deck[3]],
        "flop": [deck[4], deck[5], deck[6]],
        "turn": deck[7],
        "river": deck[8],
    }


def _casino_holdem_resolve(session, action):
    if not isinstance(session, dict):
        return None
    wager = int(session.get("wager", 0))
    stake = int(session.get("stake", wager))
    action = str(action or "").strip().lower()
    player_cards = list(session.get("player_cards", ()) or ())
    dealer_cards = list(session.get("dealer_cards", ()) or ())
    flop = list(session.get("flop", ()) or ())
    turn = str(session.get("turn", "")).strip().upper()
    river = str(session.get("river", "")).strip().upper()
    board = flop + ([turn] if turn else []) + ([river] if river else [])
    board_text = _casino_cards_text(board)
    if action == "fold":
        return {
            "service": "casino_holdem",
            "wager": int(wager),
            "stake": int(stake),
            "payout": 0,
            "outcome_key": "fold",
            "headline": "You fold the ante.",
            "detail": "The flop looks wrong, so you release the hand and leave the ante in the circle.",
            "summary": f"You fold after the flop and forfeit the {wager}c ante.",
            "result_lines": [
                f"Your hand: {_casino_cards_text(player_cards)}",
                f"Flop: {_casino_cards_text(flop)}",
                "You fold and let the ante go.",
            ],
            "player_cards": tuple(player_cards),
            "dealer_cards": tuple(dealer_cards),
            "board": tuple(flop),
            "social_gain": _casino_social_gain("casino_holdem", f"{session.get('seed_token', '')}:fold"),
            "stake_already_paid": True,
        }

    ante_stake = int(wager)
    call_stake = max(0, int(stake) - int(ante_stake))
    player_best = _casino_best_poker_hand(player_cards + board)
    dealer_best = _casino_best_poker_hand(dealer_cards + board)
    dealer_qualifies = _casino_holdem_dealer_qualifies(dealer_best["score"])
    ante_bonus_mult = _casino_holdem_ante_bonus_multiplier(player_best["score"])
    ante_bonus = int(max(0, ante_bonus_mult) * ante_stake)

    if not dealer_qualifies:
        outcome_key = "dealer_not_qualify"
        payout = int((ante_stake * 2) + call_stake + ante_bonus)
        headline = "Dealer doesn't qualify."
        detail = "The dealer misses pair of fours, so the ante wins and the call pushes."
    elif player_best["score"] > dealer_best["score"]:
        outcome_key = "player_win"
        payout = int((stake * 2) + ante_bonus)
        headline = "You drag the pot."
        detail = "Your made hand holds up, so both circles win even money."
    elif player_best["score"] == dealer_best["score"]:
        outcome_key = "push"
        payout = int(stake + ante_bonus)
        headline = "Split pot."
        detail = "The board runs out into a tie, so the ante and call both push."
    else:
        outcome_key = "dealer_win"
        payout = int(ante_bonus)
        headline = "Dealer takes it."
        detail = "The house makes the better hand and sweeps the ante and call."

    result_lines = [
        f"Board: {board_text}",
        f"You: {_casino_cards_text(player_cards)} ({player_best['name']})",
        f"Dealer: {_casino_cards_text(dealer_cards)} ({dealer_best['name']})",
        "Dealer qualifies." if dealer_qualifies else "Dealer does not qualify (needs pair of 4s+).",
    ]
    if ante_bonus > 0:
        result_lines.append(f"Ante bonus pays x{ante_bonus_mult} for your {player_best['name']}.")
    result_lines.append(detail)
    return {
        "service": "casino_holdem",
        "wager": int(wager),
        "stake": int(stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": (
            f"Board {board_text}. You show {player_best['name']}; dealer shows {dealer_best['name']}. {headline}"
        ),
        "result_lines": result_lines,
        "player_cards": tuple(player_cards),
        "dealer_cards": tuple(dealer_cards),
        "board": tuple(board),
        "player_hand_name": str(player_best["name"]),
        "dealer_hand_name": str(dealer_best["name"]),
        "dealer_qualifies": bool(dealer_qualifies),
        "ante_bonus": int(ante_bonus),
        "ante_bonus_mult": int(ante_bonus_mult),
        "social_gain": _casino_social_gain("casino_holdem", f"{session.get('seed_token', '')}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_apply_round_result(sim, eid, prop, service, round_result):
    service = str(service or "").strip().lower()
    profile = _casino_game_profile(service)
    if not profile or not isinstance(round_result, dict):
        return None, {
            "eid": eid,
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
            "property_name": prop.get("name", prop.get("id")) if isinstance(prop, dict) else str(prop or "Casino"),
            "service": service,
            "reason": "invalid_round",
        }

    wager = max(0, int(round_result.get("wager", 0)))
    stake = max(0, int(round_result.get("stake", wager)))
    payout = max(0, int(round_result.get("payout", 0)))
    stake_already_paid = bool(round_result.get("stake_already_paid", False))
    assets = sim.ecs.get(PlayerAssets).get(eid)
    credits_before = int(getattr(assets, "credits", 0)) if assets else 0
    if not stake_already_paid:
        if credits_before < stake:
            return None, {
                "eid": eid,
                "property_id": prop.get("id") if isinstance(prop, dict) else None,
                "property_name": prop.get("name", prop.get("id")) if isinstance(prop, dict) else str(prop or "Casino"),
                "service": service,
                "reason": "no_credits",
                "cost": int(stake),
                "credits": int(credits_before),
            }
        if assets:
            assets.credits = max(0, int(assets.credits) - int(stake))
            assets.credits = int(assets.credits) + int(payout)
            credits_after = int(assets.credits)
        else:
            credits_after = max(0, int(credits_before) - int(stake) + int(payout))
    else:
        if assets:
            assets.credits = int(assets.credits) + int(payout)
            credits_after = int(assets.credits)
        else:
            credits_after = int(credits_before) + int(payout)

    social_gain = max(0, int(round_result.get("social_gain", 0)))
    needs = sim.ecs.get(NPCNeeds).get(eid)
    if needs and social_gain > 0:
        needs.social = _clamp(float(needs.social) + float(social_gain))

    payload = dict(round_result)
    payload.update({
        "eid": eid,
        "property_id": prop.get("id") if isinstance(prop, dict) else None,
        "property_name": (
            str(prop.get("name", prop.get("id", "Casino"))).strip()
            if isinstance(prop, dict)
            else str(prop or "Casino").strip()
        ) or "Casino",
        "service": service,
        "wager": int(wager),
        "stake": int(stake),
        "payout": int(payout),
        "net_credits": int(payout - stake),
        "credits_after": int(credits_after),
        "social_gain": int(social_gain),
    })
    return payload, None


def _casino_game_profile(service):
    return CASINO_GAME_PROFILES.get(str(service or "").strip().lower())


def _casino_game_title(service):
    profile = _casino_game_profile(service)
    if profile:
        return str(profile.get("title", service)).strip() or str(service or "Casino game").strip()
    return str(service or "Casino game").replace("_", " ").title()


def _site_service_label(service):
    service = str(service or "").strip().lower()
    casino_profile = CASINO_GAME_PROFILES.get(service)
    if casino_profile:
        return str(casino_profile.get("service_label", casino_profile.get("title", service))).strip().lower()
    mapping = {
        "intel": "intel",
        "shelter": "shelter",
        "rest": "lodging",
        "vending": "snacks",
        "fuel": "fuel",
        "repair": "repair",
        "vehicle_sales_new": "new vehicles",
        "vehicle_sales_used": "used vehicles",
        "vehicle_fetch": "vehicle retrieval",
    }
    return mapping.get(service, service.replace("_", " "))


def _service_menu_option_label(option_id):
    option_id = str(option_id or "").strip().lower()
    casino_profile = _casino_game_profile(option_id)
    if casino_profile:
        return str(casino_profile.get("menu_label", _casino_game_title(option_id))).strip()
    mapping = {
        "trade_buy": "Browse goods",
        "trade_sell": "Sell goods",
        "banking": "Manage bank funds",
        "insurance": "Review coverage",
        "vending": "Buy a snack",
        "fuel": "Refuel vehicle",
        "repair": "Repair vehicle",
        "shelter": "Use shelter",
        "rest": "Rent a room",
        "intel": "Ask for local intel",
        "vehicle_sales_new": "Browse new vehicles",
        "vehicle_sales_used": "Browse used vehicles",
        "vehicle_fetch": "Have a vehicle delivered",
    }
    if option_id in mapping:
        return mapping[option_id]
    if option_id.startswith("vehicle_sales_"):
        return _site_service_label(option_id).title()
    return option_id.replace("_", " ").title()


def _credit_amount_label(amount):
    try:
        value = int(amount)
    except (TypeError, ValueError):
        value = 0
    return f"{max(0, value)}c"


__all__ = [
    "CASINO_GAME_SERVICE_IDS",
    "CASINO_PLINKO_LANE_COUNT",
    "_casino_apply_round_result",
    "_casino_blackjack_line",
    "_casino_blackjack_total",
    "_casino_cards_text",
    "_casino_game_profile",
    "_casino_game_title",
    "_casino_holdem_resolve",
    "_casino_holdem_start",
    "_casino_plinko_resolve",
    "_casino_round_seed",
    "_casino_slots_resolve",
    "_casino_twenty_one_action_ids",
    "_casino_twenty_one_normalize_session",
    "_casino_twenty_one_resolve",
    "_casino_twenty_one_start",
    "_clamp",
    "_credit_amount_label",
    "_int_or_default",
    "_line_text",
    "_manhattan",
    "_overworld_discovery_profile",
    "_overworld_discovery_summary_bits",
    "_overworld_legend_line",
    "_overworld_render_style",
    "_overworld_travel_profile",
    "_overworld_travel_summary_bits",
    "_sentence_from_note",
    "_service_menu_option_label",
    "_site_service_label",
    "_site_service_roll_index",
    "_site_service_state",
    "_storefront_service_profile",
    "_tick_duration_label",
    "_vehicle_sale_lookup_offer",
    "_vehicle_sale_offer_label",
    "_vehicle_sale_offers",
    "_vehicle_sale_quality",
    "_vehicle_sale_quality_title",
    "_vehicle_sale_remove_offer",
    "_vehicle_sale_stats_text",
]
