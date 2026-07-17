"""Passive flora genetic code and deterministic expression helpers.

The genetics layer is deliberately metadata-only in V1. It gives future
crossbreeding, reward flora, dyes, and herbal systems a shared language without
changing current plant spawning, harvesting, crafting, or breeding behavior.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping

from game.color_words import (
    color_word_rgb,
    find_nearest_color_word,
    flora_render_key_for_color_word,
    normalize_color_word,
    parse_color_value,
)


GENETICS_SCHEMA_VERSION = 1
DEFAULT_EFFECT_BUDGET = 4

PARENT_ROLE_ANY = "any"
PARENT_ROLE_SEED = "seed_parent"
PARENT_ROLE_POLLEN = "pollen_parent"
PARENT_ROLE_CATALOG = "catalog"
PARENT_ROLE_MUTATION = "mutation"
PARENT_ROLE_VALUES = frozenset((PARENT_ROLE_ANY, PARENT_ROLE_SEED, PARENT_ROLE_POLLEN))
SOURCE_VALUES = frozenset((PARENT_ROLE_CATALOG, PARENT_ROLE_SEED, PARENT_ROLE_POLLEN, PARENT_ROLE_MUTATION))

CHEMISTRY_CLASSES = (
    "mending",
    "hydrating",
    "cooling",
    "calming",
    "energizing",
    "cleansing",
    "numbing",
    "binding",
    "catalyst",
    "irritant",
    "toxic",
    "deliriant",
    "volatile",
)

STRENGTH_CLASSES = ("weak", "ordinary", "strong", "concentrated")
STABILITY_BANDS = ("stable", "temperamental", "volatile", "feral", "collapsed")
SPOILABILITY_BANDS = ("none", "slow", "normal", "fast", "volatile")
BLENDABILITY_BANDS = ("poor", "ordinary", "good", "excellent")
INHERITABILITY_BANDS = ("fragile", "ordinary", "sticky", "dominant")
NOTABILITY_BANDS = ("ordinary", "unusual", "suspect", "contraband", "notorious")

EFFECT_TRAIT_IDS = frozenset(
    (
        "potentiator",
        "diluter",
        "stabilizer",
        "spoiler",
        "binder",
        "fader",
        "+nourish",
        "+hydrate",
        "+mend",
        "+warm",
        "+steady",
        "+calm",
        "+focus",
        "+antitoxin",
        "+coverhop",
        "+barkskin",
        "+stanch",
        "+clear_eyes",
    )
)
EFFECT_TRAIT_COSTS = {
    "potentiator": 1,
    "diluter": 1,
    "stabilizer": 1,
    "spoiler": 1,
    "binder": 1,
    "fader": 1,
    "+nourish": 2,
    "+hydrate": 2,
    "+mend": 2,
    "+warm": 2,
    "+steady": 2,
    "+calm": 2,
    "+focus": 2,
    "+stanch": 2,
    "+clear_eyes": 2,
    "+antitoxin": 3,
    "+coverhop": 3,
    "+barkskin": 3,
}

SHAPE_AXES = ("petal_shape", "blade_shape", "stem_shape", "leaf_shape", "habit", "texture")
VALID_GROWTH_FORMS = frozenset(("flower", "grass", "reed", "moss", "lichen", "vine", "shrub", "fern"))
VALID_GLYPHS = frozenset((",", "'", ";", "*"))
DEFAULT_GLYPH_BY_FORM = {
    "flower": "'",
    "grass": ",",
    "reed": ",",
    "moss": ",",
    "lichen": ",",
    "vine": ";",
    "shrub": "*",
    "fern": ",",
}
DEFAULT_COLOR_WORD_BY_FORM = {
    "flower": "pink",
    "grass": "green",
    "reed": "olive",
    "moss": "moss",
    "lichen": "gray",
    "vine": "green",
    "shrub": "sage",
    "fern": "green",
}
COLOR_WORD_BY_RENDER_KEY = {
    "flora_leaf": "green",
    "flora_grass": "green",
    "flora_moss": "moss",
    "flora_vine": "green",
    "flora_reed": "olive",
    "flora_shrub": "sage",
    "flora_flower_pink": "pink",
    "flora_flower_violet": "violet",
    "flora_flower_gold": "gold",
    "flora_flower_white": "white",
    "flora_flower_blue": "blue",
    "flora_flower_coral": "coral",
}
STABILITY_COST_BY_TRAIT = {
    "potentiator": 0.25,
    "diluter": -0.08,
    "stabilizer": -0.35,
    "spoiler": 0.45,
    "binder": -0.2,
    "fader": 0.12,
    "+antitoxin": 0.18,
    "+coverhop": 0.4,
    "+barkskin": 0.34,
}
CHEMISTRY_BIAS_TERMS = {
    "mending": ("restorative", "soothing", "staunch", "heal", "mending", "clover", "soft"),
    "hydrating": ("water", "wet", "moist", "marsh", "hydrating", "coastal", "drink"),
    "cooling": ("cool", "cooling", "wetland", "blue", "mint", "shade"),
    "calming": ("calm", "calming", "dream", "sleep", "night", "violet", "soft"),
    "energizing": ("warm", "warming", "gold", "sun", "spice", "aromatic", "bright"),
    "cleansing": ("clean", "cleansing", "fresh", "salt", "white", "mineral", "antiseptic"),
    "numbing": ("sleep", "numb", "bitter", "thorn", "poppy", "dream"),
    "binding": ("fiber", "thread", "vine", "reed", "root", "clump", "patch"),
    "catalyst": ("rare", "orchid", "lantern", "moon", "lichen", "moss", "mineral"),
    "irritant": ("thorn", "bramble", "briar", "snapdragon", "sedge", "ash", "hardy", "astringent"),
    "toxic": ("bitter", "holly", "sorrel", "redleaf", "deep", "wine", "night", "toxic"),
    "deliriant": ("dream", "night", "moon", "morning", "violet", "poppy", "lace", "delicate"),
    "volatile": ("warm", "copper", "amber", "gold", "lantern", "aromatic", "spice", "dry"),
}


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or str(fallback or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, lo=0.0, hi=1.0):
    return max(float(lo), min(float(hi), float(value)))


def _deepcopy_dict(value):
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _stable_unit(*parts) -> float:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def _stable_hash(*parts, length=12) -> str:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[: max(4, int(length))]


def _normalize_source(value, default=PARENT_ROLE_CATALOG):
    source = _key(value, default)
    return source if source in SOURCE_VALUES else default


def _normalize_parent_role_gate(value):
    gate = _key(value, PARENT_ROLE_ANY)
    return gate if gate in PARENT_ROLE_VALUES else PARENT_ROLE_ANY


def _as_tuple(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(value)
    return (value,)


def _shape_value(row, raw_genetics):
    growth_form = _key(row.get("growth_form"), "flower")
    if growth_form not in VALID_GROWTH_FORMS:
        growth_form = "flower"
    glyph = str(row.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(growth_form, "'"))[:1]
    if glyph not in VALID_GLYPHS:
        glyph = DEFAULT_GLYPH_BY_FORM.get(growth_form, "'")
    shape = {
        "growth_form": growth_form,
        "glyph": glyph,
    }
    for axis in SHAPE_AXES:
        value = raw_genetics.get(axis) if isinstance(raw_genetics, Mapping) else None
        if value:
            shape[axis] = _key(value)
    return shape


def _infer_color_word(row, raw_genetics):
    raw_hue = raw_genetics.get("hue_family") if isinstance(raw_genetics, Mapping) else ""
    hue = normalize_color_word(raw_hue)
    if hue:
        return hue
    for value in _as_tuple(row.get("color_key")) + _as_tuple(row.get("render_key")) + tuple(row.get("colors", ()) or ()):
        key = _key(value)
        hue = normalize_color_word(COLOR_WORD_BY_RENDER_KEY.get(key, ""))
        if hue:
            return hue
        if key.startswith("flora_flower_"):
            hue = normalize_color_word(key.removeprefix("flora_flower_"))
            if hue:
                return hue
    return normalize_color_word(DEFAULT_COLOR_WORD_BY_FORM.get(_key(row.get("growth_form"), "flower"), "green")) or "green"


def _color_value(row, raw_genetics):
    word = _infer_color_word(row, raw_genetics)
    rgb = color_word_rgb(word, fallback=(90, 176, 94)) or (90, 176, 94)
    growth_form = _key(row.get("growth_form"), "flower")
    render_hint = str(row.get("render_key") or row.get("color_key") or "").strip()
    render_hint = render_hint or flora_render_key_for_color_word(word, growth_form=growth_form, fallback="")
    return {
        "word": word,
        "rgb": [int(channel) for channel in rgb],
        "render_key_hint": render_hint,
    }


def _chemistry_class_for_row(plant_id, row, raw_genetics, seed):
    explicit = _key(raw_genetics.get("main_class") or raw_genetics.get("chemistry_class") or row.get("chemistry_class"))
    if explicit in CHEMISTRY_CLASSES:
        return explicit
    text_bits = [str(plant_id), str(row.get("name", "")), str(row.get("growth_form", "")), str(row.get("rarity", ""))]
    text_bits.extend(str(token) for token in tuple(row.get("tags", ()) or ()))
    text_bits.extend(str(token) for token in tuple(row.get("crossbreed_tags", ()) or ()))
    if isinstance(raw_genetics, Mapping):
        for key, value in raw_genetics.items():
            if str(key).startswith("_") or key in {"schema_version", "genes", "expressed", "carried", "lineage"}:
                continue
            text_bits.append(str(key))
            text_bits.append(str(value))
    text = " ".join(text_bits).lower()
    weights = []
    for class_id in CHEMISTRY_CLASSES:
        weight = 1.0 + sum(1.45 for term in CHEMISTRY_BIAS_TERMS[class_id] if term in text)
        weights.append((class_id, weight))
    total = sum(weight for _class_id, weight in weights)
    roll = _stable_unit(seed, plant_id, "catalog-main-class") * total
    cursor = 0.0
    for class_id, weight in weights:
        cursor += weight
        if roll <= cursor:
            return class_id
    return weights[-1][0]


def _allele(
    value,
    *,
    locus,
    source=PARENT_ROLE_CATALOG,
    dominance=1.0,
    inherit_chance=1.0,
    expression_chance=1.0,
    generation_skip=1,
    descendant_skip_chance=0.0,
    parent_role_gate=PARENT_ROLE_ANY,
    stability_cost=0.0,
    tags=(),
):
    return {
        "id": _stable_hash(locus, source, value, length=10),
        "value": copy.deepcopy(value),
        "source": _normalize_source(source),
        "dominance": _clamp(dominance),
        "inherit_chance": _clamp(inherit_chance),
        "expression_chance": _clamp(expression_chance),
        "generation_skip": max(1, _safe_int(generation_skip, 1)),
        "descendant_skip_chance": _clamp(descendant_skip_chance),
        "parent_role_gate": _normalize_parent_role_gate(parent_role_gate),
        "stability_cost": float(stability_cost or 0.0),
        "tags": [_key(tag) for tag in _as_tuple(tags) if _key(tag)],
    }


def _normalize_allele(raw, *, locus, fallback_value, source=PARENT_ROLE_CATALOG):
    if isinstance(raw, Mapping):
        value = raw.get("value", fallback_value)
        return _allele(
            value,
            locus=locus,
            source=raw.get("source", source),
            dominance=raw.get("dominance", 1.0),
            inherit_chance=raw.get("inherit_chance", 1.0),
            expression_chance=raw.get("expression_chance", 1.0),
            generation_skip=raw.get("generation_skip", 1),
            descendant_skip_chance=raw.get("descendant_skip_chance", 0.0),
            parent_role_gate=raw.get("parent_role_gate", PARENT_ROLE_ANY),
            stability_cost=raw.get("stability_cost", 0.0),
            tags=raw.get("tags", ()),
        )
    return _allele(raw if raw is not None else fallback_value, locus=locus, source=source)


def _normalize_allele_list(raw, *, locus, fallback_value, source=PARENT_ROLE_CATALOG):
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    alleles = []
    for value in values:
        if value is None:
            continue
        alleles.append(_normalize_allele(value, locus=locus, fallback_value=fallback_value, source=source))
    if not alleles:
        alleles.append(_allele(fallback_value, locus=locus, source=source))
    return alleles


def _legacy_effect_traits(raw_genetics):
    values = []
    if isinstance(raw_genetics, Mapping):
        values.extend(_key(value) for value in _as_tuple(raw_genetics.get("secondary_traits")) if _key(value))
        values.extend(_key(value) for value in _as_tuple(raw_genetics.get("joined_traits")) if _key(value))
        value = _key(raw_genetics.get("effect_trait") or raw_genetics.get("effect"))
        if value:
            values.append(value)
    return tuple(dict.fromkeys(value for value in values if value in EFFECT_TRAIT_IDS or value.startswith("+")))


def _ensure_effect_trait_alleles(genetics, traits):
    if not isinstance(genetics, Mapping):
        return {}
    genome = copy.deepcopy(dict(genetics))
    genes = genome.setdefault("genes", {})
    if not isinstance(genes, dict):
        genes = {}
        genome["genes"] = genes
    effects = genes.setdefault("effects", {})
    if not isinstance(effects, dict):
        effects = {}
        genes["effects"] = effects
    rows = list(effects.get("traits") or ())
    existing = {_key((row or {}).get("value")) for row in rows if isinstance(row, Mapping)}
    for trait in tuple(traits or ()):
        trait_key = _key(trait)
        if trait_key not in EFFECT_TRAIT_IDS or trait_key in existing:
            continue
        rows.append(_allele(
            trait_key,
            locus="effects.traits",
            dominance=0.55,
            inherit_chance=0.75,
            expression_chance=0.75,
            stability_cost=STABILITY_COST_BY_TRAIT.get(trait_key, 0.12 if trait_key.startswith("+") else 0.0),
            tags=("effect", trait_key),
        ))
        existing.add(trait_key)
    effects["traits"] = rows
    return genome


def flora_effect_trait_cost(trait_id):
    return max(0, _safe_int(EFFECT_TRAIT_COSTS.get(_key(trait_id)), 0))


def _apply_effect_budget(genome, expressed_state, *, seed, lineage_hash):
    """Cap expressed biological effects while retaining overflow as carriers."""

    budget = max(1, _safe_int(genome.get("effect_budget"), DEFAULT_EFFECT_BUDGET))
    expressed = expressed_state.get("expressed") if isinstance(expressed_state.get("expressed"), Mapping) else {}
    effects = expressed.get("effects") if isinstance(expressed.get("effects"), Mapping) else {}
    traits = tuple(dict.fromkeys(
        _key(value)
        for value in tuple(effects.get("traits") or ())
        if _key(value) in EFFECT_TRAIT_COSTS
    ))
    allele_rows = tuple((((genome.get("genes") or {}).get("effects") or {}).get("traits") or ()))
    dominance = {}
    for row in allele_rows:
        if not isinstance(row, Mapping):
            continue
        trait = _key(row.get("value"))
        dominance[trait] = max(dominance.get(trait, 0.0), _safe_float(row.get("dominance"), 0.0))
    ranked = sorted(
        traits,
        key=lambda trait: (
            -dominance.get(trait, 0.0),
            _stable_unit(seed, lineage_hash, trait, "effect-budget"),
            trait,
        ),
    )
    kept = []
    used = 0
    for trait in ranked:
        cost = flora_effect_trait_cost(trait)
        if cost <= 0 or used + cost > budget:
            continue
        kept.append(trait)
        used += cost
    expressed.setdefault("effects", {})["traits"] = tuple(kept)
    expressed_state["expressed"] = expressed

    overflow = set(traits) - set(kept)
    if overflow:
        carried = expressed_state.get("carried") if isinstance(expressed_state.get("carried"), Mapping) else {}
        carried = copy.deepcopy(dict(carried))
        carried_rows = list(((carried.setdefault("effects", {})).get("traits") or ()))
        carried_tokens = {
            (_key(row.get("value")), str(row.get("id", "")))
            for row in carried_rows
            if isinstance(row, Mapping)
        }
        for row in allele_rows:
            token = (_key(row.get("value")), str(row.get("id", ""))) if isinstance(row, Mapping) else ("", "")
            if token[0] in overflow and token not in carried_tokens:
                carried_rows.append(copy.deepcopy(dict(row)))
                carried_tokens.add(token)
        carried["effects"]["traits"] = carried_rows
        expressed_state["carried"] = carried
    genome["effect_budget"] = budget
    genome["effect_cost_used"] = used
    return expressed_state


def _legacy_genes_for_row(plant_id, row, raw_genetics, seed):
    color = _color_value(row, raw_genetics)
    shape = _shape_value(row, raw_genetics)
    main_class = _chemistry_class_for_row(plant_id, row, raw_genetics, seed)
    effects = _legacy_effect_traits(raw_genetics)
    return {
        "visual": {
            "color": [_allele(color, locus="visual.color", tags=("visual", "color"))],
            "shape": [_allele(shape, locus="visual.shape", tags=("visual", "shape"))],
        },
        "chemistry": {
            "main_class": [_allele(main_class, locus="chemistry.main_class", tags=("chemistry", main_class))],
        },
        "handling": {
            "strength_class": [_allele(_key(raw_genetics.get("strength_class"), "ordinary"), locus="handling.strength_class")],
            "stability": [_allele(_key(raw_genetics.get("stability"), "stable"), locus="handling.stability")],
            "spoilability": [_allele(_key(raw_genetics.get("spoilability"), "none"), locus="handling.spoilability")],
            "blendability": [_allele(_key(raw_genetics.get("blendability"), "ordinary"), locus="handling.blendability")],
            "inheritability": [_allele(_key(raw_genetics.get("inheritability"), "ordinary"), locus="handling.inheritability")],
        },
        "effects": {
            "traits": [
                _allele(
                    trait,
                    locus="effects.traits",
                    dominance=0.55,
                    expression_chance=0.75,
                    stability_cost=STABILITY_COST_BY_TRAIT.get(trait, 0.12 if trait.startswith("+") else 0.0),
                    tags=("effect", trait),
                )
                for trait in effects
            ],
        },
        "social": {
            "notability": [_allele(_key(raw_genetics.get("notability"), "ordinary"), locus="social.notability")],
        },
    }


def _normalize_genes(raw_genes, plant_id, row, raw_genetics, seed):
    fallback = _legacy_genes_for_row(plant_id, row, raw_genetics, seed)
    if not isinstance(raw_genes, Mapping):
        return fallback
    result = {}
    for group, loci in fallback.items():
        result[group] = {}
        raw_group = raw_genes.get(group) if isinstance(raw_genes.get(group), Mapping) else {}
        for locus, fallback_alleles in loci.items():
            raw_locus = raw_group.get(locus)
            if group == "effects" and locus == "traits" and raw_locus == []:
                result[group][locus] = []
                continue
            if raw_locus is None and not fallback_alleles:
                result[group][locus] = []
                continue
            result[group][locus] = _normalize_allele_list(
                raw_locus if raw_locus is not None else fallback_alleles,
                locus=f"{group}.{locus}",
                fallback_value=fallback_alleles[0].get("value") if fallback_alleles else "",
            )
    for group, raw_group in raw_genes.items():
        group_key = _key(group)
        if group_key in result or not isinstance(raw_group, Mapping):
            continue
        result[group_key] = {}
        for locus, raw_locus in raw_group.items():
            locus_key = _key(locus)
            result[group_key][locus_key] = _normalize_allele_list(
                raw_locus,
                locus=f"{group_key}.{locus_key}",
                fallback_value="",
            )
    return result


def _lineage_for(plant_id, raw_genetics, seed):
    lineage = _deepcopy_dict(raw_genetics.get("lineage") if isinstance(raw_genetics, Mapping) else {})
    lineage.setdefault("plant_id", plant_id)
    lineage.setdefault("parents", list(raw_genetics.get("parents", ())) if isinstance(raw_genetics, Mapping) else [])
    lineage.setdefault("generation", _safe_int(raw_genetics.get("generation"), 0) if isinstance(raw_genetics, Mapping) else 0)
    lineage.setdefault("lineage_depth", _safe_int(raw_genetics.get("lineage_depth"), lineage.get("generation", 0)))
    lineage.setdefault("lineage_hash", raw_genetics.get("lineage_hash") if isinstance(raw_genetics, Mapping) else "")
    if not lineage.get("lineage_hash"):
        lineage["lineage_hash"] = _stable_hash(seed, plant_id, lineage.get("generation", 0), "flora-lineage", length=12)
    return lineage


def normalize_flora_genetics(plant_id, row, *, seed=0):
    plant_key = _key(plant_id or (row or {}).get("id") or (row or {}).get("plant_id"), "unknown")
    row = dict(row or {})
    raw_genetics = row.get("genetics") if isinstance(row.get("genetics"), Mapping) else {}
    is_schema_v1 = _safe_int(raw_genetics.get("schema_version"), 0) == GENETICS_SCHEMA_VERSION and isinstance(raw_genetics.get("genes"), Mapping)
    genome = copy.deepcopy(dict(raw_genetics)) if is_schema_v1 else {}
    genome["schema_version"] = GENETICS_SCHEMA_VERSION
    genome["genome_id"] = str(genome.get("genome_id") or f"flora:{plant_key}:v1")
    genome["lineage"] = _lineage_for(plant_key, raw_genetics, seed)
    genome["genes"] = _normalize_genes(genome.get("genes"), plant_key, row, raw_genetics, seed)
    genome["effect_budget"] = max(
        1,
        _safe_int(raw_genetics.get("effect_budget", row.get("effect_budget")), DEFAULT_EFFECT_BUDGET),
    )

    expressed_state = express_flora_genetics(
        genome,
        seed=seed,
        generation=_safe_int(genome.get("lineage", {}).get("generation"), 0),
        lineage_hash=str(genome.get("lineage", {}).get("lineage_hash") or ""),
    )
    expressed_state = _apply_effect_budget(
        genome,
        expressed_state,
        seed=seed,
        lineage_hash=str(genome.get("lineage", {}).get("lineage_hash") or ""),
    )
    genome["expressed"] = expressed_state["expressed"]
    genome["carried"] = expressed_state["carried"]
    genome["stability_score"] = expressed_state["stability_score"]
    genome["stability_band"] = expressed_state["stability_band"]

    visual = genome.get("expressed", {}).get("visual", {}) if isinstance(genome.get("expressed"), Mapping) else {}
    color = visual.get("color", {}) if isinstance(visual.get("color"), Mapping) else {}
    shape = visual.get("shape", {}) if isinstance(visual.get("shape"), Mapping) else {}
    if color.get("word"):
        genome["hue_family"] = color["word"]
    for axis in SHAPE_AXES:
        if shape.get(axis):
            genome[axis] = shape[axis]
    genome["growth_form"] = shape.get("growth_form") or row.get("growth_form")
    genome["glyph"] = shape.get("glyph") or row.get("glyph")
    return genome


def _passes_generation(allele, generation):
    skip = max(1, _safe_int(allele.get("generation_skip"), 1))
    if skip <= 1 or int(generation or 0) <= 0:
        return True
    return int(generation) % skip == 0


def _passes_parent_role(allele):
    gate = _normalize_parent_role_gate(allele.get("parent_role_gate"))
    source = _normalize_source(allele.get("source"))
    return gate == PARENT_ROLE_ANY or source == gate or source == PARENT_ROLE_CATALOG


def _roll_allows(allele, kind, threshold, seed, generation, lineage_hash, group, locus):
    threshold = _clamp(threshold)
    if threshold >= 1.0:
        return True
    if threshold <= 0.0:
        return False
    roll = _stable_unit(seed, lineage_hash, generation, group, locus, allele.get("id"), kind)
    return roll <= threshold


def _stability_pressure(genetics):
    total = 0.0
    for group in (genetics.get("genes") or {}).values():
        if not isinstance(group, Mapping):
            continue
        for alleles in group.values():
            for allele in tuple(alleles or ()):
                if isinstance(allele, Mapping):
                    total += max(0.0, _safe_float(allele.get("stability_cost"), 0.0))
    return total / 10.0


def _expression_score(allele, *, stability_pressure=0.0):
    source = _normalize_source(allele.get("source"))
    role_bonus = 0.06 if source in {PARENT_ROLE_SEED, PARENT_ROLE_POLLEN} else 0.0
    compatibility_bonus = 0.04 if "binder" in set(allele.get("tags") or ()) else 0.0
    return _safe_float(allele.get("dominance"), 1.0) + role_bonus + compatibility_bonus - float(stability_pressure)


def _allele_value(allele):
    return copy.deepcopy(allele.get("value")) if isinstance(allele, Mapping) else allele


def _best_allele(alleles, *, stability_pressure=0.0):
    rows = [allele for allele in tuple(alleles or ()) if isinstance(allele, Mapping)]
    if not rows:
        return None
    return max(rows, key=lambda allele: (_expression_score(allele, stability_pressure=stability_pressure), str(allele.get("id", ""))))


def _blend_color_alleles(alleles):
    rows = [allele for allele in tuple(alleles or ()) if isinstance(allele, Mapping)]
    if not rows:
        return {"word": "green", "rgb": [90, 176, 94], "render_key_hint": "flora_leaf"}
    weighted = []
    for allele in rows:
        value = allele.get("value") if isinstance(allele.get("value"), Mapping) else {}
        rgb = parse_color_value(value.get("rgb") or value.get("word") or value, fallback=(90, 176, 94))
        if rgb is None:
            rgb = (90, 176, 94)
        weight = max(0.01, _safe_float(allele.get("dominance"), 1.0))
        weighted.append((rgb, weight, value))
    total = sum(weight for _rgb, weight, _value in weighted) or 1.0
    blended = tuple(
        int(round(sum(rgb[idx] * weight for rgb, weight, _value in weighted) / total))
        for idx in range(3)
    )
    word = find_nearest_color_word(blended, default=str(weighted[0][2].get("word") or "green"))
    render_key = flora_render_key_for_color_word(word, fallback=str(weighted[0][2].get("render_key_hint") or "flora_leaf"))
    return {
        "word": word,
        "rgb": [int(channel) for channel in blended],
        "render_key_hint": render_key,
    }


def _stability_score_and_band(inherited, expressed):
    cost = 0.0
    for group in (inherited, expressed):
        for loci in group.values():
            if not isinstance(loci, Mapping):
                continue
            for value in loci.values():
                alleles = value if isinstance(value, list) else ()
                for allele in alleles:
                    if isinstance(allele, Mapping):
                        cost += _safe_float(allele.get("stability_cost"), 0.0)
    score = max(0.0, min(100.0, 100.0 - (cost * 22.0)))
    if score >= 80:
        band = "stable"
    elif score >= 60:
        band = "temperamental"
    elif score >= 40:
        band = "volatile"
    elif score >= 20:
        band = "feral"
    else:
        band = "collapsed"
    return round(score, 2), band


def express_flora_genetics(genetics, *, seed, generation=0, lineage_hash=""):
    if not isinstance(genetics, Mapping):
        genetics = {}
    genes = genetics.get("genes") if isinstance(genetics.get("genes"), Mapping) else {}
    lineage_hash = str(lineage_hash or (genetics.get("lineage") or {}).get("lineage_hash") or genetics.get("genome_id") or "")
    generation = _safe_int(generation, 0)
    inheritance_resolved = bool(genetics.get("inheritance_resolved"))
    stability_pressure = _stability_pressure(genetics)
    inherited: dict[str, dict[str, list[dict]]] = {}
    carried: dict[str, dict[str, list[dict]]] = {}
    expressed_alleles: dict[str, dict[str, list[dict]]] = {}
    expressed: dict[str, dict[str, object]] = {}

    for group, loci in genes.items():
        if not isinstance(loci, Mapping):
            continue
        group_key = _key(group)
        inherited[group_key] = {}
        carried[group_key] = {}
        expressed_alleles[group_key] = {}
        expressed[group_key] = {}
        for locus, alleles in loci.items():
            locus_key = _key(locus)
            inherited_rows = []
            carried_rows = []
            expressed_rows = []
            for allele in tuple(alleles or ()):
                if not isinstance(allele, Mapping):
                    continue
                normalized = _normalize_allele(allele, locus=f"{group_key}.{locus_key}", fallback_value=allele.get("value"))
                if (
                    not inheritance_resolved
                    and not _roll_allows(normalized, "inherit", normalized.get("inherit_chance"), seed, generation, lineage_hash, group_key, locus_key)
                ):
                    continue
                inherited_rows.append(normalized)
                can_express = (
                    _passes_parent_role(normalized)
                    and _passes_generation(normalized, generation)
                    and _roll_allows(normalized, "express", normalized.get("expression_chance"), seed, generation, lineage_hash, group_key, locus_key)
                    and not _roll_allows(normalized, "descendant-skip", normalized.get("descendant_skip_chance"), seed, generation, lineage_hash, group_key, locus_key)
                )
                if can_express:
                    expressed_rows.append(normalized)
                else:
                    carried_rows.append(normalized)
            if not expressed_rows and inherited_rows and not (group_key == "effects" and locus_key == "traits"):
                best = _best_allele(inherited_rows, stability_pressure=stability_pressure)
                expressed_rows = [best] if best is not None else []
                carried_rows.extend(row for row in inherited_rows if row is not best)
            inherited[group_key][locus_key] = inherited_rows
            carried[group_key][locus_key] = carried_rows
            expressed_alleles[group_key][locus_key] = expressed_rows
            if group_key == "visual" and locus_key == "color":
                expressed[group_key][locus_key] = _blend_color_alleles(expressed_rows or inherited_rows)
            elif group_key == "effects" and locus_key == "traits":
                expressed[group_key][locus_key] = tuple(
                    dict.fromkeys(_key(_allele_value(row)) for row in expressed_rows if _key(_allele_value(row)))
                )
            else:
                best = _best_allele(expressed_rows or inherited_rows, stability_pressure=stability_pressure)
                expressed[group_key][locus_key] = _allele_value(best) if best is not None else None

    score, band = _stability_score_and_band(inherited, expressed_alleles)
    expressed.setdefault("handling", {})["stability"] = band
    return {
        "expressed": expressed,
        "carried": carried,
        "stability_score": score,
        "stability_band": band,
    }


def _genetics_from_parent(value, *, seed=0):
    if isinstance(value, Mapping) and _safe_int(value.get("schema_version"), 0) == GENETICS_SCHEMA_VERSION and isinstance(value.get("genes"), Mapping):
        genetics = copy.deepcopy(dict(value))
        parent_row = {}
    elif isinstance(value, Mapping):
        parent_row = copy.deepcopy(dict(value))
        raw_genetics = parent_row.get("genetics") if isinstance(parent_row.get("genetics"), Mapping) else {}
        if _safe_int(raw_genetics.get("schema_version"), 0) == GENETICS_SCHEMA_VERSION and isinstance(raw_genetics.get("genes"), Mapping):
            genetics = normalize_flora_genetics(
                parent_row.get("plant_id") or parent_row.get("id") or raw_genetics.get("lineage", {}).get("plant_id"),
                parent_row,
                seed=seed,
            )
        else:
            genetics = normalize_flora_genetics(parent_row.get("plant_id") or parent_row.get("id") or "unknown_parent", parent_row, seed=seed)
    else:
        parent_row = {}
        genetics = normalize_flora_genetics("unknown_parent", {}, seed=seed)
    traits = parent_row.get("secondary_traits") if isinstance(parent_row.get("secondary_traits"), (list, tuple, set)) else ()
    if traits:
        genetics = _ensure_effect_trait_alleles(genetics, traits)
    return genetics


def _lineage_depth(genetics):
    lineage = genetics.get("lineage") if isinstance(genetics, Mapping) and isinstance(genetics.get("lineage"), Mapping) else {}
    return max(_safe_int(lineage.get("lineage_depth"), 0), _safe_int(lineage.get("generation"), 0))


def _parent_alleles_for_locus(genetics, group, locus):
    rows = []
    genes = genetics.get("genes") if isinstance(genetics.get("genes"), Mapping) else {}
    gene_group = genes.get(group) if isinstance(genes.get(group), Mapping) else {}
    rows.extend(row for row in tuple(gene_group.get(locus, ()) or ()) if isinstance(row, Mapping))
    carried = genetics.get("carried") if isinstance(genetics.get("carried"), Mapping) else {}
    carried_group = carried.get(group) if isinstance(carried.get(group), Mapping) else {}
    rows.extend(row for row in tuple(carried_group.get(locus, ()) or ()) if isinstance(row, Mapping))
    deduped = []
    seen = set()
    for row in rows:
        token = (str(row.get("id", "")), repr(row.get("value")), str(row.get("source", "")))
        if token in seen:
            continue
        seen.add(token)
        deduped.append(row)
    return tuple(deduped)


def _child_allele_from_parent(allele, *, role, group, locus, parent_genome_id):
    normalized = _normalize_allele(allele, locus=f"{group}.{locus}", fallback_value=allele.get("value"))
    normalized["source"] = role
    normalized["id"] = _stable_hash(
        "child-allele",
        group,
        locus,
        role,
        parent_genome_id,
        allele.get("id"),
        normalized.get("value"),
        length=10,
    )
    return normalized


def _inherit_roll_allows(allele, *, seed, generation, lineage_hash, group, locus, role):
    threshold = _clamp(allele.get("inherit_chance", 1.0))
    if threshold >= 1.0:
        return True
    if threshold <= 0.0:
        return False
    roll = _stable_unit(seed, lineage_hash, generation, group, locus, role, allele.get("id"), "child-inherit")
    return roll <= threshold


def _best_parent_allele(rows):
    if not rows:
        return None
    return max(
        rows,
        key=lambda allele: (
            _safe_float(allele.get("dominance"), 1.0),
            _safe_float(allele.get("inherit_chance"), 1.0),
            str(allele.get("id", "")),
        ),
    )


def _all_parent_loci(seed_parent, pollen_parent):
    loci = set()
    for genetics in (seed_parent, pollen_parent):
        genes = genetics.get("genes") if isinstance(genetics.get("genes"), Mapping) else {}
        carried = genetics.get("carried") if isinstance(genetics.get("carried"), Mapping) else {}
        for source in (genes, carried):
            for group, group_loci in source.items():
                if not isinstance(group_loci, Mapping):
                    continue
                for locus in group_loci:
                    loci.add((_key(group), _key(locus)))
    for group, locus in (
        ("visual", "color"),
        ("visual", "shape"),
        ("chemistry", "main_class"),
        ("handling", "strength_class"),
        ("handling", "stability"),
        ("handling", "spoilability"),
        ("handling", "blendability"),
        ("handling", "inheritability"),
        ("effects", "traits"),
        ("social", "notability"),
    ):
        loci.add((group, locus))
    return tuple(sorted(loci))


def _safe_render_key_for_color_value(color_value, fallback="flora_leaf"):
    if isinstance(color_value, Mapping):
        word = color_value.get("word")
        hint = color_value.get("render_key_hint")
    else:
        word = color_value
        hint = ""
    return flora_render_key_for_color_word(word, fallback=str(hint or fallback or "flora_leaf"))


def _gentle_mutation(genome, *, seed, generation, lineage_hash):
    if _stable_unit(seed, lineage_hash, generation, "gentle-mutation", "present") > 0.06:
        return None
    choice = int(_stable_unit(seed, lineage_hash, generation, "gentle-mutation", "kind") * 4) % 4
    if choice == 0:
        color = _blend_color_alleles(tuple((genome.get("genes", {}).get("visual", {}) or {}).get("color", ()) or ()))
        rgb = parse_color_value(color.get("rgb") or color.get("word"), fallback=(90, 176, 94)) or (90, 176, 94)
        drifted = []
        for index, channel in enumerate(rgb):
            drift = int(round((_stable_unit(seed, lineage_hash, generation, "gentle-mutation", "color", index) - 0.5) * 24))
            drifted.append(max(0, min(255, int(channel) + drift)))
        word = find_nearest_color_word(tuple(drifted), default=color.get("word") or "green")
        return (
            "visual",
            "color",
            _allele(
                {
                    "word": word,
                    "rgb": [int(channel) for channel in drifted],
                    "render_key_hint": flora_render_key_for_color_word(word, fallback=color.get("render_key_hint") or "flora_leaf"),
                },
                locus="visual.color",
                source=PARENT_ROLE_MUTATION,
                dominance=0.22,
                inherit_chance=0.35,
                expression_chance=0.45,
                stability_cost=0.03,
                tags=("mutation", "color"),
            ),
        )
    if choice == 1:
        locus = "blendability" if _stable_unit(seed, lineage_hash, generation, "gentle-mutation", "handling") < 0.5 else "inheritability"
        values = BLENDABILITY_BANDS if locus == "blendability" else INHERITABILITY_BANDS
        value = values[int(_stable_unit(seed, lineage_hash, generation, "gentle-mutation", locus) * len(values)) % len(values)]
        return (
            "handling",
            locus,
            _allele(
                value,
                locus=f"handling.{locus}",
                source=PARENT_ROLE_MUTATION,
                dominance=0.24,
                inherit_chance=0.3,
                expression_chance=0.4,
                stability_cost=0.04,
                tags=("mutation", "handling"),
            ),
        )
    if choice == 2:
        traits = ("binder", "fader", "potentiator", "diluter", "stabilizer", "spoiler")
        trait = traits[int(_stable_unit(seed, lineage_hash, generation, "gentle-mutation", "effect") * len(traits)) % len(traits)]
        return (
            "effects",
            "traits",
            _allele(
                trait,
                locus="effects.traits",
                source=PARENT_ROLE_MUTATION,
                dominance=0.28,
                inherit_chance=0.28,
                expression_chance=0.35,
                stability_cost=STABILITY_COST_BY_TRAIT.get(trait, 0.08),
                tags=("mutation", "effect", trait),
            ),
        )
    notability = NOTABILITY_BANDS[int(_stable_unit(seed, lineage_hash, generation, "gentle-mutation", "social") * len(NOTABILITY_BANDS)) % len(NOTABILITY_BANDS)]
    return (
        "social",
        "notability",
        _allele(
            notability,
            locus="social.notability",
            source=PARENT_ROLE_MUTATION,
            dominance=0.2,
            inherit_chance=0.25,
            expression_chance=0.35,
            stability_cost=0.03,
            tags=("mutation", "social"),
        ),
    )


def _apply_genetics_aliases(genome, row=None):
    row = row if isinstance(row, Mapping) else {}
    visual = genome.get("expressed", {}).get("visual", {}) if isinstance(genome.get("expressed"), Mapping) else {}
    color = visual.get("color", {}) if isinstance(visual.get("color"), Mapping) else {}
    shape = visual.get("shape", {}) if isinstance(visual.get("shape"), Mapping) else {}
    if color.get("word"):
        genome["hue_family"] = color["word"]
    for axis in SHAPE_AXES:
        if shape.get(axis):
            genome[axis] = shape[axis]
    genome["growth_form"] = shape.get("growth_form") or row.get("growth_form")
    genome["glyph"] = shape.get("glyph") or row.get("glyph")
    return genome


def inherit_flora_genetics(seed_parent, pollen_parent, *, seed, child_plant_id, generation, lineage_hash, mutation_profile="gentle"):
    seed_genetics = _genetics_from_parent(seed_parent, seed=seed)
    pollen_genetics = _genetics_from_parent(pollen_parent, seed=seed)
    generation = max(1, _safe_int(generation, 1))
    lineage_hash = str(lineage_hash or _stable_hash(seed, child_plant_id, generation, "flora-child-lineage", length=12))
    child_genes: dict[str, dict[str, list[dict]]] = {}

    for group, locus in _all_parent_loci(seed_genetics, pollen_genetics):
        selected = []
        parent_rows = (
            (PARENT_ROLE_SEED, seed_genetics, _parent_alleles_for_locus(seed_genetics, group, locus)),
            (PARENT_ROLE_POLLEN, pollen_genetics, _parent_alleles_for_locus(pollen_genetics, group, locus)),
        )
        for role, parent, rows in parent_rows:
            parent_genome_id = str(parent.get("genome_id") or role)
            normalized_rows = tuple(
                _child_allele_from_parent(row, role=role, group=group, locus=locus, parent_genome_id=parent_genome_id)
                for row in rows
            )
            if group == "visual" and locus == "color":
                best = _best_parent_allele(normalized_rows)
                if best is not None:
                    selected.append(best)
                continue
            for row in normalized_rows:
                if _inherit_roll_allows(row, seed=seed, generation=generation, lineage_hash=lineage_hash, group=group, locus=locus, role=role):
                    selected.append(row)
        if not selected and not (group == "effects" and locus == "traits"):
            fallback_rows = []
            for role, parent, rows in parent_rows:
                parent_genome_id = str(parent.get("genome_id") or role)
                fallback_rows.extend(
                    _child_allele_from_parent(row, role=role, group=group, locus=locus, parent_genome_id=parent_genome_id)
                    for row in rows
                )
            best = _best_parent_allele(fallback_rows)
            if best is not None:
                selected.append(best)
        child_genes.setdefault(group, {})[locus] = selected

    genome = {
        "schema_version": GENETICS_SCHEMA_VERSION,
        "genome_id": f"flora:{_key(child_plant_id, 'hybrid')}:v1",
        "inheritance_resolved": True,
        "lineage": {
            "plant_id": _key(child_plant_id, "hybrid"),
            "parents": [
                (seed_genetics.get("lineage") or {}).get("plant_id") or seed_genetics.get("genome_id"),
                (pollen_genetics.get("lineage") or {}).get("plant_id") or pollen_genetics.get("genome_id"),
            ],
            "seed_parent": (seed_genetics.get("lineage") or {}).get("plant_id") or seed_genetics.get("genome_id"),
            "pollen_parent": (pollen_genetics.get("lineage") or {}).get("plant_id") or pollen_genetics.get("genome_id"),
            "generation": generation,
            "lineage_depth": max(_lineage_depth(seed_genetics), _lineage_depth(pollen_genetics)) + 1,
            "lineage_hash": lineage_hash,
        },
        "genes": child_genes,
        "mutation_profile": str(mutation_profile or "none").strip().lower() or "none",
        "effect_budget": max(
            1,
            min(
                _safe_int(seed_genetics.get("effect_budget"), DEFAULT_EFFECT_BUDGET),
                _safe_int(pollen_genetics.get("effect_budget"), DEFAULT_EFFECT_BUDGET),
            ),
        ),
    }
    if str(mutation_profile or "").strip().lower() == "gentle":
        mutation = _gentle_mutation(genome, seed=seed, generation=generation, lineage_hash=lineage_hash)
        if mutation is not None:
            group, locus, allele = mutation
            genome["genes"].setdefault(group, {}).setdefault(locus, []).append(allele)
            genome["mutation"] = {
                "group": group,
                "locus": locus,
                "allele_id": allele.get("id"),
                "value": copy.deepcopy(allele.get("value")),
            }

    expressed_state = express_flora_genetics(
        genome,
        seed=seed,
        generation=generation,
        lineage_hash=lineage_hash,
    )
    expressed_state = _apply_effect_budget(
        genome,
        expressed_state,
        seed=seed,
        lineage_hash=lineage_hash,
    )
    genome["expressed"] = expressed_state["expressed"]
    genome["carried"] = expressed_state["carried"]
    genome["stability_score"] = expressed_state["stability_score"]
    genome["stability_band"] = expressed_state["stability_band"]
    return _apply_genetics_aliases(genome)


def _color_from_genetics(value):
    genetics = value.get("genetics") if isinstance(value, Mapping) and isinstance(value.get("genetics"), Mapping) else value
    if not isinstance(genetics, Mapping):
        return {"word": "green", "rgb": [90, 176, 94], "render_key_hint": "flora_leaf"}
    expressed = genetics.get("expressed") if isinstance(genetics.get("expressed"), Mapping) else {}
    visual = expressed.get("visual") if isinstance(expressed.get("visual"), Mapping) else {}
    color = visual.get("color") if isinstance(visual.get("color"), Mapping) else {}
    if color:
        return copy.deepcopy(color)
    genes = genetics.get("genes") if isinstance(genetics.get("genes"), Mapping) else {}
    alleles = ((genes.get("visual") or {}).get("color") or ()) if isinstance(genes.get("visual"), Mapping) else ()
    return _blend_color_alleles(tuple(alleles or ()))


def blend_color_genes(seed_parent, pollen_parent, *, seed, lineage_hash):
    seed_color = _color_from_genetics(seed_parent)
    pollen_color = _color_from_genetics(pollen_parent)
    seed_rgb = parse_color_value(seed_color.get("rgb") or seed_color.get("word"), fallback=(90, 176, 94)) or (90, 176, 94)
    pollen_rgb = parse_color_value(pollen_color.get("rgb") or pollen_color.get("word"), fallback=(90, 176, 94)) or (90, 176, 94)
    drift = (_stable_unit(seed, lineage_hash, seed_color.get("word"), pollen_color.get("word"), "color-blend") - 0.5) * 0.12
    seed_weight = max(0.2, min(0.8, 0.5 + drift))
    pollen_weight = 1.0 - seed_weight
    rgb = tuple(int(round((seed_rgb[idx] * seed_weight) + (pollen_rgb[idx] * pollen_weight))) for idx in range(3))
    word = find_nearest_color_word(rgb, default=seed_color.get("word") or pollen_color.get("word") or "green")
    render_key = flora_render_key_for_color_word(word, fallback=seed_color.get("render_key_hint") or pollen_color.get("render_key_hint") or "flora_leaf")
    return {
        "word": word,
        "rgb": [int(channel) for channel in rgb],
        "render_key_hint": render_key,
        "parent_words": [seed_color.get("word"), pollen_color.get("word")],
    }


def validate_flora_genetics(genetics) -> list[str]:
    errors: list[str] = []
    if not isinstance(genetics, Mapping):
        return ["genetics must be an object"]
    if _safe_int(genetics.get("schema_version"), 0) != GENETICS_SCHEMA_VERSION:
        return [f"genetics.schema_version must be {GENETICS_SCHEMA_VERSION}"]
    if not str(genetics.get("genome_id") or "").strip():
        errors.append("genetics.genome_id must be a non-empty string")
    effect_budget = max(0, _safe_int(genetics.get("effect_budget"), 0))
    expressed = genetics.get("expressed") if isinstance(genetics.get("expressed"), Mapping) else {}
    effects = expressed.get("effects") if isinstance(expressed.get("effects"), Mapping) else {}
    effect_cost = sum(flora_effect_trait_cost(trait) for trait in tuple(effects.get("traits") or ()))
    if effect_budget < 1:
        errors.append("genetics.effect_budget must be at least 1")
    if effect_cost > effect_budget:
        errors.append(f"genetics expressed effect cost {effect_cost} exceeds budget {effect_budget}")
    if _safe_int(genetics.get("effect_cost_used"), effect_cost) != effect_cost:
        errors.append("genetics.effect_cost_used does not match expressed effects")
    genes = genetics.get("genes")
    if not isinstance(genes, Mapping):
        errors.append("genetics.genes must be an object")
        return errors
    required = (
        ("visual", "color"),
        ("visual", "shape"),
        ("chemistry", "main_class"),
        ("handling", "strength_class"),
        ("handling", "stability"),
        ("handling", "spoilability"),
        ("handling", "blendability"),
        ("handling", "inheritability"),
        ("effects", "traits"),
        ("social", "notability"),
    )
    for group, locus in required:
        if not isinstance(genes.get(group), Mapping) or locus not in genes[group]:
            errors.append(f"genetics.genes.{group}.{locus} is required")
    for group, loci in genes.items():
        if not isinstance(loci, Mapping):
            errors.append(f"genetics.genes.{group} must be an object")
            continue
        for locus, alleles in loci.items():
            if not isinstance(alleles, list):
                errors.append(f"genetics.genes.{group}.{locus} must be a list of alleles")
                continue
            for index, allele in enumerate(alleles):
                prefix = f"genetics.genes.{group}.{locus}[{index}]"
                if not isinstance(allele, Mapping):
                    errors.append(f"{prefix} must be an object")
                    continue
                if "value" not in allele:
                    errors.append(f"{prefix}.value is required")
                if _normalize_source(allele.get("source")) != allele.get("source", PARENT_ROLE_CATALOG):
                    errors.append(f"{prefix}.source must be one of {sorted(SOURCE_VALUES)}")
                if _normalize_parent_role_gate(allele.get("parent_role_gate")) != allele.get("parent_role_gate", PARENT_ROLE_ANY):
                    errors.append(f"{prefix}.parent_role_gate must be one of {sorted(PARENT_ROLE_VALUES)}")
                for field in ("dominance", "inherit_chance", "expression_chance", "descendant_skip_chance"):
                    value = _safe_float(allele.get(field), 0.0)
                    if not (0.0 <= value <= 1.0):
                        errors.append(f"{prefix}.{field} must be between 0 and 1")
                if _safe_int(allele.get("generation_skip"), 1) < 1:
                    errors.append(f"{prefix}.generation_skip must be at least 1")
                value = allele.get("value")
                if group == "visual" and locus == "color":
                    word = value.get("word") if isinstance(value, Mapping) else value
                    if not normalize_color_word(word):
                        errors.append(f"{prefix}.value.word must be a known color word")
                elif group == "chemistry" and locus == "main_class":
                    if _key(value) not in CHEMISTRY_CLASSES:
                        errors.append(f"{prefix}.value must be a known chemistry class")
                elif group == "handling" and locus == "strength_class":
                    if _key(value) not in STRENGTH_CLASSES:
                        errors.append(f"{prefix}.value must be one of {STRENGTH_CLASSES}")
                elif group == "handling" and locus == "stability":
                    if _key(value) not in STABILITY_BANDS:
                        errors.append(f"{prefix}.value must be one of {STABILITY_BANDS}")
                elif group == "handling" and locus == "spoilability":
                    if _key(value) not in SPOILABILITY_BANDS:
                        errors.append(f"{prefix}.value must be one of {SPOILABILITY_BANDS}")
                elif group == "handling" and locus == "blendability":
                    if _key(value) not in BLENDABILITY_BANDS:
                        errors.append(f"{prefix}.value must be one of {BLENDABILITY_BANDS}")
                elif group == "handling" and locus == "inheritability":
                    if _key(value) not in INHERITABILITY_BANDS:
                        errors.append(f"{prefix}.value must be one of {INHERITABILITY_BANDS}")
                elif group == "social" and locus == "notability":
                    if _key(value) not in NOTABILITY_BANDS:
                        errors.append(f"{prefix}.value must be one of {NOTABILITY_BANDS}")
    return errors
