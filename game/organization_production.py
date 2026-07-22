"""Durable organization culture and manufacturing identity.

The public half of a profile gives products a stable visual and linguistic
author.  The hidden half is simulation truth: repeatable factory tendencies
which affect goods without automatically becoming known to the manufacturer or
the player.
"""

from __future__ import annotations

from hashlib import blake2b
import random

from game.appearance_palette import render_key_for_color_word
from game.color_words import approved_color_words, color_word_rgb


ORGANIZATION_PRODUCTION_SCHEMA_VERSION = 1

_REGISTERS = (
    "clipped", "neighborly", "procedural", "ceremonial", "blunt",
    "aspirational", "solicitous", "wry", "austere", "breathless",
    "measured", "proprietary", "plainspoken", "evangelical",
)
_CADENCES = (
    "short bursts", "balanced clauses", "stacked assurances", "ritual repetition",
    "terse acknowledgements", "technical fragments", "sales patter", "street shorthand",
)
_ADDRESSES = (
    "operator", "neighbor", "associate", "subscriber", "friend", "member",
    "customer", "runner", "guest", "asset", "traveler", "initiate",
)
_WARNINGS = (
    "state the consequence", "offer one clean exit", "cite the rule",
    "make the risk personal", "bury the threat in courtesy", "challenge the listener",
    "repeat the boundary", "frame compliance as belonging",
)
_MOTIFS = (
    "broken chevrons", "nested windows", "threaded rings", "offset teeth",
    "split halos", "stepped bars", "little eyes", "branching traces",
    "stacked doors", "knotted lines", "quartered stars", "leaning towers",
    "open palms", "hooked petals", "circuit thorns", "soft grids",
)
_GEOMETRIES = (
    "compact", "angular", "rounded", "tall", "low", "asymmetric",
    "layered", "spare", "dense", "modular", "ribbed", "faceted",
)
_FINISHES = (
    "matte", "polished", "brushed", "rubberized", "lacquered", "powder-coated",
    "woven", "scuffed", "mirrored", "speckled", "translucent", "hammered",
)
_DRONE_DOCTRINES = (
    "watchful", "escort", "courier", "interdiction", "quiet survey",
    "visible deterrence", "close protection", "salvage utility",
)
_WIRE_BIOMES = (
    "stacked_lattice", "signal_garden", "processional_grid", "switchback_basin",
    "broken_arcade", "nested_exchange", "thorned_bus", "quiet_machine",
    "market_constellation", "ringed_archive", "service_canopy", "hardline_sprawl",
)
_SPECIALTIES_BY_KIND = {
    "corporation": ("wire gear", "drone frames", "power systems", "consumer electronics", "security systems"),
    "business": ("consumer goods", "service tools", "small electronics", "repair parts"),
    "gang": ("field repairs", "concealment", "salvage", "weapons", "street communications"),
    "crew": ("field repairs", "concealment", "salvage", "courier gear"),
    "cult": ("ceremonial goods", "member tokens", "consumer goods", "broadcast gear", "meeting supplies"),
    "municipal": ("public terminals", "utility drones", "records systems", "service equipment"),
    "civic": ("public terminals", "utility drones", "records systems", "service equipment"),
    "other": ("small electronics", "repair parts", "service equipment", "consumer goods"),
}
_HIDDEN_AXES = (
    "quality_bias", "consistency", "durability", "power_efficiency",
    "signal_integrity", "heat_management", "concealment", "repairability",
)
_QUIRKS = (
    "overbuilt connectors", "temperamental seals", "clean signal paths",
    "wasteful standby draw", "easy field access", "inconsistent soldering",
    "surprisingly tough housings", "fragile cosmetic panels", "quiet cooling",
    "noisy regulators", "excellent cable strain relief", "awkward fasteners",
)
_PRODUCTION_COLOR_WORDS = tuple(
    word
    for word in approved_color_words(include_reserved=True)
    if color_word_rgb(word) is not None
)


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _seed_int(*parts):
    digest = blake2b("|".join(_text(part) for part in parts).encode("utf-8"), digest_size=16).digest()
    return int.from_bytes(digest, "big")


def _family_for_profile(profile):
    kind = _text(getattr(profile, "kind", "")).lower() or "other"
    tags = {_text(tag).lower() for tag in getattr(profile, "tags", ()) or () if _text(tag)}
    if kind in {"gang", "crew"} or tags & {"gang", "street_gang"}:
        return "gang"
    if kind == "cult" or "cult" in tags:
        return "cult"
    if kind in {"corporation", "corporate"} or tags & {"corporate", "corpsec"}:
        return "corporation"
    if kind in {"municipal", "civic", "government"} or tags & {"municipal", "civic"}:
        return "civic"
    return kind if kind in _SPECIALTIES_BY_KIND else "other"


def _production_colors(rng):
    words = _PRODUCTION_COLOR_WORDS
    if not words:
        return ("blue", "charcoal", "gold")
    primary = rng.choice(words)
    primary_rgb = color_word_rgb(primary, (128, 128, 128))

    # Sample broadly from the full named palette, then take color-distance
    # winners.  This retains the installation's enormous vocabulary without
    # allowing a single near-duplicate draw to flatten an organization's mark.
    sample = rng.sample(words, min(96, len(words)))
    sample.sort(
        key=lambda word: sum(
            (int(a) - int(b)) ** 2
            for a, b in zip(primary_rgb, color_word_rgb(word, primary_rgb))
        ),
        reverse=True,
    )
    secondary = sample[0] if sample else "charcoal"
    secondary_rgb = color_word_rgb(secondary, (64, 64, 64))
    accent = max(
        sample[1:] or words,
        key=lambda word: min(
            sum((int(a) - int(b)) ** 2 for a, b in zip(color_word_rgb(word, primary_rgb), primary_rgb)),
            sum((int(a) - int(b)) ** 2 for a, b in zip(color_word_rgb(word, secondary_rgb), secondary_rgb)),
        ),
    )
    return primary, secondary, accent


def _new_profile(sim, organization_eid, profile):
    org_key = _text(getattr(profile, "key", "")) or f"org:{organization_eid}"
    seed = _seed_int(getattr(sim, "seed", 0), "organization-production", org_key)
    rng = random.Random(seed)
    family = _family_for_profile(profile)
    name = _text(getattr(profile, "name", "")) or "Organization"
    primary, secondary, accent = _production_colors(rng)
    available_specialties = list(_SPECIALTIES_BY_KIND.get(family, _SPECIALTIES_BY_KIND["other"]))
    rng.shuffle(available_specialties)
    specialties = tuple(available_specialties[: rng.randint(2, min(4, len(available_specialties)))])

    hidden = {axis: rng.randint(-2, 2) for axis in _HIDDEN_AXES}
    if not any(hidden.values()):
        hidden[rng.choice(_HIDDEN_AXES)] = rng.choice((-1, 1))
    quirk_count = 1 + int(abs(hidden["consistency"]) >= 2)
    hidden["quirks"] = tuple(rng.sample(_QUIRKS, quirk_count))
    hidden["known_to_organization"] = False

    brand_suffix = rng.choice(("Works", "Systems", "Fabrication", "Line", "Devices", "House", "Cooperative"))
    return {
        "schema_version": ORGANIZATION_PRODUCTION_SCHEMA_VERSION,
        "seed": int(seed % 2_147_483_647),
        "organization_eid": int(organization_eid),
        "organization_key": org_key,
        "organization_name": name,
        "family": family,
        "culture": {
            "register": rng.choice(_REGISTERS),
            "cadence": rng.choice(_CADENCES),
            "address": rng.choice(_ADDRESSES),
            "warning_style": rng.choice(_WARNINGS),
        },
        "visual": {
            "primary_color_word": primary,
            "secondary_color_word": secondary,
            "accent_color_word": accent,
            "motif": rng.choice(_MOTIFS),
            "geometry": rng.choice(_GEOMETRIES),
            "finish": rng.choice(_FINISHES),
        },
        "manufacturing": {
            "brand": f"{name} {brand_suffix}",
            "specialties": specialties,
            "drone_doctrine": rng.choice(_DRONE_DOCTRINES),
            "interface_style": f"{rng.choice(_GEOMETRIES)} {rng.choice(_MOTIFS)}",
            "wire_biome_style": rng.choice(_WIRE_BIOMES),
        },
        "hidden_manufacturing": hidden,
        "discoveries": {},
    }


def ensure_organization_production_profile(sim, organization_eid):
    """Return/create one durable seeded culture profile for an organization."""

    from game.organizations import organization_profile

    organization_eid = _safe_int(organization_eid, 0)
    profile = organization_profile(sim, organization_eid) if organization_eid > 0 else None
    if profile is None:
        return {}
    stored = getattr(profile, "production_profile", None)
    if isinstance(stored, dict) and _safe_int(stored.get("schema_version"), 0) == ORGANIZATION_PRODUCTION_SCHEMA_VERSION:
        return stored
    stored = _new_profile(sim, organization_eid, profile)
    profile.production_profile = stored
    return stored


def ensure_organization_clothing_culture(sim, organization_eid):
    """Return/create the organization's durable public work-clothing grammar.

    This is a lazy extension of the existing production profile rather than a
    schema reroll.  Older installations therefore keep every established
    product color and hidden manufacturing trait; their clothing culture is
    derived deterministically from that already-durable identity.
    """

    profile = ensure_organization_production_profile(sim, organization_eid)
    if not profile:
        return {}
    stored = profile.get("clothing_culture")
    if isinstance(stored, dict) and stored.get("signature"):
        return stored

    organization_eid = _safe_int(organization_eid, 0)
    visual = dict(profile.get("visual") or {})
    family = _text(profile.get("family")) or "other"
    rng = random.Random(_seed_int(profile.get("seed"), "organization-clothing-culture"))
    primary = _text(visual.get("primary_color_word")) or "steel"
    secondary = _text(visual.get("secondary_color_word")) or "charcoal"
    accent = _text(visual.get("accent_color_word")) or "gold"
    motif = _text(visual.get("motif")) or "work mark"
    slot_sets = {
        "corporation": (("outer", "top"), ("top", "hat"), ("outer", "accessory")),
        "civic": (("outer", "top"), ("top", "accessory"), ("outer", "hat")),
        "gang": (("outer", "accessory"), ("top", "hat"), ("outer", "hat")),
        "cult": (("top", "accessory"), ("full_body", "accessory"), ("outer", "accessory")),
        "business": (("top", "accessory"), ("outer", "top"), ("top", "hat")),
        "other": (("top", "accessory"), ("outer", "top"), ("top", "hat")),
    }
    cohesion_ranges = {
        "corporation": (0.7, 0.94),
        "civic": (0.72, 0.96),
        "cult": (0.76, 0.98),
        "gang": (0.48, 0.86),
        "business": (0.42, 0.8),
        "other": (0.34, 0.7),
    }
    lo, hi = cohesion_ranges.get(family, cohesion_ranges["other"])
    cohesion = round(rng.uniform(lo, hi), 3)
    signature_slots = tuple(rng.choice(slot_sets.get(family, slot_sets["other"])))
    signature = f"org-clothing:{organization_eid}:{int(profile.get('seed', 0) or 0):x}"
    stored = {
        "signature": signature,
        "organization_eid": organization_eid,
        "organization_name": _text(profile.get("organization_name")) or "Organization",
        "family": family,
        "primary_color_word": primary,
        "secondary_color_word": secondary,
        "accent_color_word": accent,
        "motif": motif,
        "signature_slots": signature_slots,
        "cohesion": cohesion,
        "recognition_salience": round(0.4 + (cohesion * 0.42), 3),
    }
    profile["clothing_culture"] = stored
    return stored


def organization_clothing_culture(sim, organization_eid):
    return dict(ensure_organization_clothing_culture(sim, organization_eid) or {})


def organization_production_profile(sim, organization_eid, *, include_hidden=False):
    profile = ensure_organization_production_profile(sim, organization_eid)
    if not profile:
        return {}
    result = dict(profile)
    result["culture"] = dict(profile.get("culture") or {})
    result["visual"] = dict(profile.get("visual") or {})
    result["manufacturing"] = dict(profile.get("manufacturing") or {})
    result["discoveries"] = dict(profile.get("discoveries") or {})
    if isinstance(profile.get("clothing_culture"), dict):
        result["clothing_culture"] = dict(profile.get("clothing_culture") or {})
    if include_hidden:
        result["hidden_manufacturing"] = dict(profile.get("hidden_manufacturing") or {})
    else:
        result.pop("hidden_manufacturing", None)
    return result


def organization_manufacturing_modifiers(sim, organization_eid):
    profile = ensure_organization_production_profile(sim, organization_eid)
    hidden = dict(profile.get("hidden_manufacturing") or {})
    return {axis: max(-2, min(2, _safe_int(hidden.get(axis), 0))) for axis in _HIDDEN_AXES}


def organization_manufacturing_identity(sim, organization_eid):
    """Compact product metadata; omits the unknowable hidden trait labels."""

    profile = ensure_organization_production_profile(sim, organization_eid)
    if not profile:
        return {}
    visual = dict(profile.get("visual") or {})
    manufacturing = dict(profile.get("manufacturing") or {})
    culture = dict(profile.get("culture") or {})
    primary = _text(visual.get("primary_color_word")) or "steel"
    secondary = _text(visual.get("secondary_color_word")) or "charcoal"
    accent = _text(visual.get("accent_color_word")) or "gold"
    return {
        "organization_eid": int(organization_eid),
        "organization_key": _text(profile.get("organization_key")),
        "organization_name": _text(profile.get("organization_name")),
        "manufacturer": _text(manufacturing.get("brand")) or _text(profile.get("organization_name")),
        "manufacturer_family": _text(profile.get("family")) or "other",
        "manufacturing_signature": f"{profile.get('seed', 0):x}",
        "product_motif": _text(visual.get("motif")),
        "product_geometry": _text(visual.get("geometry")),
        "product_finish": _text(visual.get("finish")),
        "primary_color_word": primary,
        "secondary_color_word": secondary,
        "accent_color_word": accent,
        "primary_render_key": render_key_for_color_word(primary, default="property_service"),
        "secondary_render_key": render_key_for_color_word(secondary, default="human_slate"),
        "accent_render_key": render_key_for_color_word(accent, default="world_object_gold"),
        "drone_doctrine": _text(manufacturing.get("drone_doctrine")),
        "interface_style": _text(manufacturing.get("interface_style")),
        "wire_biome_style": _text(manufacturing.get("wire_biome_style")),
        "diagnostic_voice": {
            "register": _text(culture.get("register")),
            "cadence": _text(culture.get("cadence")),
            "address": _text(culture.get("address")),
            "warning_style": _text(culture.get("warning_style")),
        },
    }


def manufacturing_quality_label(score):
    score = max(-2, min(2, _safe_int(score, 0)))
    return {-2: "poor", -1: "rough", 0: "standard", 1: "good", 2: "excellent"}[score]


__all__ = [
    "ORGANIZATION_PRODUCTION_SCHEMA_VERSION",
    "ensure_organization_production_profile",
    "ensure_organization_clothing_culture",
    "manufacturing_quality_label",
    "organization_manufacturing_identity",
    "organization_manufacturing_modifiers",
    "organization_clothing_culture",
    "organization_production_profile",
]
