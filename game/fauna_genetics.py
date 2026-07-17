"""Durable, budgeted fauna genetics and inherited phenotype helpers.

Fauna compatibility is anchored to a small vocabulary of generic root animals,
not to Earth taxonomy.  A root is a reproductive body plan.  Descendants may
change color, pattern, build, behavior, and costly biological abilities without
ceasing to belong to that root.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping

from game.color_words import (
    color_word_rgb,
    curated_color_words,
    find_nearest_color_word,
    normalize_color_word,
)
from game.components import AnimalGenome


FAUNA_GENETICS_SCHEMA_VERSION = 1
DEFAULT_TRAIT_BUDGET = 6

ABILITY_TRAIT_COSTS = {
    "keen_senses": 1,
    "herd_mind": 1,
    "fleet_limb": 2,
    "camouflage": 2,
    "fright_display": 2,
    "exoskeleton": 3,
    "toxic_hide": 3,
    "venomous_bite": 3,
    "shock_glands": 4,
}

ABILITY_CHANNELS = {
    "keen_senses": "senses",
    "herd_mind": "social",
    "fleet_limb": "locomotion",
    "camouflage": "skin",
    "fright_display": "display",
    "exoskeleton": "skin",
    "toxic_hide": "skin",
    "venomous_bite": "mouth",
    "shock_glands": "skin",
}

GENERIC_BODY_CHANNELS = frozenset(("display", "locomotion", "mouth", "senses", "skin", "social"))

PATTERN_VALUES = (
    "plain",
    "dappled",
    "masked",
    "mottled",
    "spotted",
    "striped",
    "warning_bands",
)
BUILD_VALUES = ("slight", "lean", "balanced", "heavy", "broad")
DISPLAY_VALUES = ("none", "crest", "fan", "horns", "plates", "quills", "sail")


# Current authored animals are presentations of these generic roots.  Future
# content can provide ``root_animal_id`` directly and need not use these names.
ROOT_ANIMAL_BY_PROFILE = {
    "stray_dog": "street_pack",
    "gray_wolf": "street_pack",
    "coyote": "street_pack",
    "alley_cat": "small_prowler",
    "cougar": "great_prowler",
    "alley_pigeon": "flock_forager",
    "gull": "flock_forager",
    "crow": "clever_flier",
    "red_tailed_hawk": "sky_hunter",
    "sewer_rat": "burrow_scavenger",
    "wharf_rat": "burrow_scavenger",
    "roach_swarm": "swarm_scuttler",
    "dust_moth": "dust_flier",
    "stag_beetle": "horned_scuttler",
    "fence_lizard": "scrub_crawler",
    "water_moccasin": "long_crawler",
    "rattlesnake": "long_crawler",
    "alligator": "marsh_ambusher",
    "tree_frog": "soft_leaper",
    "deer": "herd_grazer",
    "feral_boar": "rooting_tank",
    "black_bear": "heavy_forager",
    "shore_crab": "shore_scuttler",
    "raccoon": "masked_scavenger",
    "alley_possum": "masked_scavenger",
}

PROFILE_COLOR_WORDS = {
    "stray_dog": ("brown", "tan", "charcoal"),
    "gray_wolf": ("gray", "charcoal", "white"),
    "coyote": ("tan", "rust", "gray"),
    "alley_cat": ("orange", "black", "gray", "white"),
    "cougar": ("tan", "sand"),
    "alley_pigeon": ("gray", "slate", "white"),
    "gull": ("white", "gray", "slate"),
    "crow": ("black", "indigo"),
    "red_tailed_hawk": ("rust", "brown", "cream"),
    "sewer_rat": ("brown", "gray", "charcoal"),
    "wharf_rat": ("charcoal", "brown", "gray"),
    "roach_swarm": ("rust", "brown", "black"),
    "dust_moth": ("ash", "cream", "tan"),
    "stag_beetle": ("black", "brown", "wine"),
    "fence_lizard": ("moss", "brown", "sage"),
    "water_moccasin": ("olive", "brown", "black"),
    "rattlesnake": ("tan", "brown", "rust"),
    "alligator": ("olive", "moss", "charcoal"),
    "tree_frog": ("green", "lime", "yellow"),
    "deer": ("brown", "tan", "rust"),
    "feral_boar": ("charcoal", "brown", "black"),
    "black_bear": ("black", "brown", "charcoal"),
    "shore_crab": ("coral", "rust", "sand"),
    "raccoon": ("gray", "charcoal", "black"),
    "alley_possum": ("gray", "white", "charcoal"),
}

PROFILE_BASE_ABILITIES = {
    "roach_swarm": ("exoskeleton",),
    "stag_beetle": ("exoskeleton",),
    "shore_crab": ("exoskeleton",),
    "water_moccasin": ("venomous_bite",),
    "rattlesnake": ("venomous_bite",),
}


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
    if text:
        return text
    return str(fallback or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _stable_hash(*parts, length=16):
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[: max(8, int(length))]


def _stable_unit(*parts):
    return int(_stable_hash(*parts, length=16), 16) / float(0xFFFFFFFFFFFFFFFF)


def _stable_pick(values, *parts):
    values = tuple(values or ())
    if not values:
        return None
    index = int(_stable_unit(*parts) * len(values)) % len(values)
    return values[index]


def _string_tuple(value):
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(dict.fromkeys(_key(item) for item in value if _key(item)))


def _allele(value, *, dominance=0.5, source="founder", generation=0):
    try:
        dominance = float(dominance)
    except (TypeError, ValueError):
        dominance = 0.5
    return {
        "value": _key(value),
        "dominance": max(0.0, min(1.0, dominance)),
        "source": _key(source, "founder"),
        "generation": max(0, _safe_int(generation, 0)),
    }


def _normalize_alleles(value, *, fallback=()):
    if isinstance(value, Mapping):
        value = (value,)
    elif isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple, set, frozenset)):
        value = fallback
    rows = []
    for raw in tuple(value or ()):
        if isinstance(raw, Mapping):
            allele_value = _key(raw.get("value"))
            if not allele_value:
                continue
            rows.append(_allele(
                allele_value,
                dominance=raw.get("dominance", 0.5),
                source=raw.get("source", "inherited"),
                generation=raw.get("generation", 0),
            ))
        else:
            allele_value = _key(raw)
            if allele_value:
                rows.append(_allele(allele_value, dominance=0.55, source="legacy"))
    return tuple(rows)


def _axis_alleles(genome, axis, fallback_value):
    genes = getattr(genome, "genes", {}) if genome is not None else {}
    raw = genes.get(axis) if isinstance(genes, Mapping) else None
    rows = _normalize_alleles(raw)
    if rows:
        return rows
    expressed = getattr(genome, "expressed", {}) if genome is not None else {}
    value = _key((expressed or {}).get(fallback_value)) if isinstance(expressed, Mapping) else ""
    return (_allele(value or "unknown", dominance=0.6, source="legacy"),)


def _pick_parent_allele(genome, axis, fallback_value, *, token):
    alleles = _axis_alleles(genome, axis, fallback_value)
    return copy.deepcopy(_stable_pick(alleles, token, axis, "meiotic-pick") or alleles[0])


def _express_allele_pair(alleles, *, token, fallback=""):
    rows = list(_normalize_alleles(alleles))
    if not rows:
        return _key(fallback)
    counts = {}
    for row in rows:
        counts[row["value"]] = int(counts.get(row["value"], 0)) + 1
    homozygous = [value for value, count in counts.items() if count >= 2]
    if homozygous:
        return sorted(
            homozygous,
            key=lambda value: max(float(row["dominance"]) for row in rows if row["value"] == value),
            reverse=True,
        )[0]
    scored = []
    for row in rows:
        score = float(row["dominance"]) + ((_stable_unit(token, row["value"], "expression") - 0.5) * 0.16)
        scored.append((score, row["value"]))
    scored.sort(reverse=True)
    return scored[0][1] if scored else _key(fallback)


def _express_color_alleles(alleles, *, token, fallback="gray"):
    rows = list(_normalize_alleles(alleles))
    if not rows:
        return normalize_color_word(fallback, default="gray") or "gray"
    if len({row["value"] for row in rows}) == 1:
        return normalize_color_word(rows[0]["value"], default=fallback) or fallback
    ranked = sorted(rows, key=lambda row: float(row["dominance"]), reverse=True)
    dominant = ranked[0]
    recessive = ranked[1]
    # Close dominance is codominant and produces a stable palette blend.
    if abs(float(dominant["dominance"]) - float(recessive["dominance"])) <= 0.18:
        return _blend_parent_color(dominant["value"], recessive["value"], token=token, mutate=False)
    return normalize_color_word(dominant["value"], default=fallback) or fallback


def _ability_alleles(genome):
    genes = getattr(genome, "genes", {}) if genome is not None else {}
    raw = genes.get("abilities") if isinstance(genes, Mapping) else None
    rows = _normalize_alleles(raw)
    if rows:
        return rows
    expressed = getattr(genome, "expressed", {}) if genome is not None else {}
    return tuple(
        _allele(trait, dominance=0.72, source="legacy")
        for trait in _string_tuple((expressed or {}).get("abilities") if isinstance(expressed, Mapping) else ())
    )


def _express_ability_alleles(alleles, *, token, budget):
    rows = list(_normalize_alleles(alleles))
    by_trait = {}
    for row in rows:
        if row["value"] not in ABILITY_TRAIT_COSTS:
            continue
        by_trait.setdefault(row["value"], []).append(row)
    expressed = []
    carried = []
    for trait, trait_rows in sorted(by_trait.items()):
        copy_count = len(trait_rows)
        dominance = max(float(row["dominance"]) for row in trait_rows)
        # Matching copies are how low-dominance traits resurface.  A single
        # recessive copy remains a carrier, while two inherited copies express
        # reliably; this is the important bit that makes hidden founder
        # variety matter several generations later.
        homozygous = copy_count >= 2 and len({row["value"] for row in trait_rows}) == 1
        expression_roll = _stable_unit(token, trait, "ability-expression")
        if homozygous or (dominance >= 0.68 and expression_roll <= min(0.96, dominance)):
            expressed.append(trait)
        else:
            carried.append(trait)
    kept, used = _fit_traits_to_budget(expressed, budget, seed_token=token)
    carried.extend(trait for trait in expressed if trait not in set(kept))
    return kept, tuple(dict.fromkeys(carried)), used


def root_animal_id_for_profile(profile):
    profile = profile if isinstance(profile, Mapping) else {}
    explicit = _key(profile.get("root_animal_id") or profile.get("breeding_root"))
    if explicit:
        return explicit
    profile_id = _key(profile.get("id") or profile.get("profile_id"))
    if profile_id in ROOT_ANIMAL_BY_PROFILE:
        return ROOT_ANIMAL_BY_PROFILE[profile_id]
    taxonomy = _key(profile.get("taxonomy_class"), "other")
    # Unknown authored creatures remain reproductively isolated until their
    # content declares a shared root explicitly.
    return f"{taxonomy}_root_{_stable_hash(profile_id or profile.get('species') or taxonomy, length=8)}"


def fauna_trait_cost(trait_id):
    return max(0, int(ABILITY_TRAIT_COSTS.get(_key(trait_id), 0)))


def fauna_trait_cost_used(traits):
    return sum(fauna_trait_cost(trait) for trait in _string_tuple(traits))


def _fit_traits_to_budget(traits, budget, *, seed_token):
    budget = max(0, _safe_int(budget, DEFAULT_TRAIT_BUDGET))
    ranked = sorted(
        _string_tuple(traits),
        key=lambda trait: (_stable_unit(seed_token, trait, "budget-order"), trait),
    )
    kept = []
    used = 0
    for trait in ranked:
        cost = fauna_trait_cost(trait)
        if cost <= 0 or used + cost > budget:
            continue
        kept.append(trait)
        used += cost
    return tuple(kept), used


def _profile_color_words(profile):
    profile = profile if isinstance(profile, Mapping) else {}
    authored = _string_tuple(profile.get("genetic_colors") or profile.get("color_words"))
    authored = tuple(word for word in authored if normalize_color_word(word))
    if authored:
        return authored
    profile_id = _key(profile.get("id") or profile.get("profile_id"))
    if profile_id in PROFILE_COLOR_WORDS:
        return PROFILE_COLOR_WORDS[profile_id]
    direct = normalize_color_word(profile.get("color") or "")
    if direct:
        return (direct,)
    taxonomy = _key(profile.get("taxonomy_class"), "other")
    return {
        "avian": ("gray", "white", "brown"),
        "canine": ("brown", "tan", "gray"),
        "feline": ("rust", "gray", "black"),
        "insect": ("brown", "black", "green"),
        "reptile": ("olive", "moss", "brown"),
        "rodent": ("brown", "gray", "charcoal"),
        "ungulate": ("brown", "tan", "rust"),
    }.get(taxonomy, ("gray", "brown", "moss"))


def _profile_pattern(profile, token):
    explicit = _string_tuple((profile or {}).get("genetic_patterns"))
    if explicit:
        return _stable_pick(explicit, token, "founder-pattern")
    profile_id = _key((profile or {}).get("id") or (profile or {}).get("profile_id"))
    if profile_id in {"raccoon", "alley_possum"}:
        return "masked"
    if profile_id in {"rattlesnake", "water_moccasin"}:
        return "warning_bands"
    if profile_id in {"deer", "cougar", "fence_lizard"}:
        return _stable_pick(("plain", "dappled", "mottled"), token, "founder-pattern")
    return _stable_pick(("plain", "mottled", "striped"), token, "founder-pattern")


def _profile_display(profile, abilities, token):
    explicit = _string_tuple((profile or {}).get("genetic_displays"))
    if explicit:
        return _stable_pick(explicit, token, "founder-display")
    if "exoskeleton" in set(abilities):
        return "plates"
    profile_id = _key((profile or {}).get("id") or (profile or {}).get("profile_id"))
    if profile_id in {"deer", "stag_beetle"}:
        return "horns"
    if profile_id in {"alley_pigeon", "crow", "red_tailed_hawk", "gull"}:
        return "crest"
    return "none"


def founder_animal_genome(profile, *, seed, identity_token, native_record=None):
    """Create one deterministic founder genome from authored or native content."""

    if isinstance(native_record, Mapping):
        payload = native_record.get("genome") if isinstance(native_record.get("genome"), Mapping) else native_record
        genome = animal_genome_from_payload(payload, seed=seed, identity_token=identity_token)
        if genome is not None:
            return genome

    profile = profile if isinstance(profile, Mapping) else {}
    profile_id = _key(profile.get("id") or profile.get("profile_id"), "animal")
    root_id = root_animal_id_for_profile(profile)
    token = f"{seed}:{identity_token}:{profile_id}:{root_id}"
    local_colors = _profile_color_words(profile)
    color = _stable_pick(local_colors, token, "founder-color") or "gray"
    rich_colors = curated_color_words(include_reserved=False)
    recessive_color_pool = local_colors
    if _stable_unit(token, "rare-color-carrier") < 0.28:
        recessive_color_pool = rich_colors
    recessive_color = _stable_pick(
        tuple(word for word in recessive_color_pool if word != color) or (color,),
        token,
        "founder-recessive-color",
    ) or color
    accent_pool = tuple(word for word in local_colors if word != color) or (color,)
    accent = _stable_pick(accent_pool, token, "founder-accent") or color
    recessive_accent = _stable_pick(
        tuple(word for word in rich_colors if word not in {accent, color}) or (recessive_color,),
        token,
        "founder-recessive-accent",
    ) or recessive_color
    base_abilities = _string_tuple(profile.get("genetic_abilities") or PROFILE_BASE_ABILITIES.get(profile_id, ()))
    budget = max(1, _safe_int(profile.get("trait_budget"), DEFAULT_TRAIT_BUDGET))
    pattern = _profile_pattern(profile, token)
    recessive_pattern = _stable_pick(tuple(value for value in PATTERN_VALUES if value != pattern), token, "founder-recessive-pattern") or pattern
    build = _stable_pick(("lean", "balanced", "heavy"), token, "founder-build") or "balanced"
    recessive_build = _stable_pick(tuple(value for value in BUILD_VALUES if value != build), token, "founder-recessive-build") or build
    display = _profile_display(profile, base_abilities, token)
    recessive_display = display
    if _stable_unit(token, "display-carrier") < 0.36:
        recessive_display = _stable_pick(tuple(value for value in DISPLAY_VALUES if value != display), token, "founder-recessive-display") or display
    ability_alleles = []
    for trait in base_abilities:
        # Two copies make authored baseline biology reliable rather than a
        # probabilistic phenotype.
        ability_alleles.extend((
            _allele(trait, dominance=0.84, source="founder"),
            _allele(trait, dominance=0.78, source="founder"),
        ))
    carried_candidates = [trait for trait in _ability_candidates(GENERIC_BODY_CHANNELS) if trait not in set(base_abilities)]
    if carried_candidates and _stable_unit(token, "recessive-ability-carrier") < 0.42:
        carried_trait = _stable_pick(carried_candidates, token, "recessive-ability")
        ability_alleles.append(_allele(carried_trait, dominance=0.22, source="founder_recessive"))
    abilities, carried_abilities, used = _express_ability_alleles(ability_alleles, token=token, budget=budget)
    genes = {
        "visual_color": [
            _allele(color, dominance=0.78, source="founder"),
            _allele(recessive_color, dominance=0.28, source="founder_recessive"),
        ],
        "accent_color": [
            _allele(accent, dominance=0.7, source="founder"),
            _allele(recessive_accent, dominance=0.24, source="founder_recessive"),
        ],
        "pattern": [
            _allele(pattern, dominance=0.72, source="founder"),
            _allele(recessive_pattern, dominance=0.3, source="founder_recessive"),
        ],
        "build": [
            _allele(build, dominance=0.68, source="founder"),
            _allele(recessive_build, dominance=0.34, source="founder_recessive"),
        ],
        "display": [
            _allele(display, dominance=0.7, source="founder"),
            _allele(recessive_display, dominance=0.26, source="founder_recessive"),
        ],
        "abilities": list(ability_alleles),
    }
    expressed = {
        "color_word": color,
        "accent_color_word": accent,
        "pattern": pattern,
        "build": build,
        "display": display,
        "abilities": list(abilities),
        "carried_abilities": list(carried_abilities),
        "mark_seed": int(_stable_unit(token, "mark") * 9973) % 9973,
    }
    phenotype_stamp = _stable_hash(root_id, expressed, genes, length=14)
    lineage_id = f"fauna:{root_id}:{phenotype_stamp}"
    genome_id = f"genome:{root_id}:{_stable_hash(token, phenotype_stamp, length=18)}"
    return AnimalGenome(
        genome_id=genome_id,
        root_animal_id=root_id,
        lineage_id=lineage_id,
        genes=genes,
        expressed=expressed,
        generation=0,
        trait_budget=budget,
        trait_cost_used=used,
        native_lineage_id=_key(profile.get("native_lineage_id")),
    )


def animal_genome_payload(genome):
    if genome is None:
        return {}
    return {
        "schema_version": FAUNA_GENETICS_SCHEMA_VERSION,
        "genome_id": str(getattr(genome, "genome_id", "") or ""),
        "root_animal_id": _key(getattr(genome, "root_animal_id", ""), "other_root"),
        "lineage_id": str(getattr(genome, "lineage_id", "") or ""),
        "genes": copy.deepcopy(dict(getattr(genome, "genes", {}) or {})),
        "expressed": copy.deepcopy(dict(getattr(genome, "expressed", {}) or {})),
        "parent_genome_ids": list(getattr(genome, "parent_genome_ids", ()) or ()),
        "parent_lineage_ids": list(getattr(genome, "parent_lineage_ids", ()) or ()),
        "generation": max(0, _safe_int(getattr(genome, "generation", 0), 0)),
        "trait_budget": max(0, _safe_int(getattr(genome, "trait_budget", DEFAULT_TRAIT_BUDGET), DEFAULT_TRAIT_BUDGET)),
        "trait_cost_used": max(0, _safe_int(getattr(genome, "trait_cost_used", 0), 0)),
        "mutation_signature": _key(getattr(genome, "mutation_signature", "")),
        "native_lineage_id": _key(getattr(genome, "native_lineage_id", "")),
    }


def animal_genome_from_payload(payload, *, seed=0, identity_token="native"):
    if not isinstance(payload, Mapping):
        return None
    root_id = _key(payload.get("root_animal_id"), "other_root")
    expressed = dict(payload.get("expressed") or {}) if isinstance(payload.get("expressed"), Mapping) else {}
    genes = dict(payload.get("genes") or {}) if isinstance(payload.get("genes"), Mapping) else {}
    budget = max(1, _safe_int(payload.get("trait_budget"), DEFAULT_TRAIT_BUDGET))
    for axis, fallback_field in (
        ("visual_color", "color_word"),
        ("accent_color", "accent_color_word"),
        ("pattern", "pattern"),
        ("build", "build"),
        ("display", "display"),
    ):
        alleles = _normalize_alleles(genes.get(axis))
        if not alleles:
            fallback = _key(expressed.get(fallback_field), "gray" if "color" in axis else "none")
            alleles = (_allele(fallback, dominance=0.7, source="legacy"),)
        genes[axis] = list(alleles)
    ability_alleles = _normalize_alleles(genes.get("abilities"))
    if not ability_alleles:
        ability_alleles = tuple(
            _allele(trait, dominance=0.74, source="legacy")
            for trait in _string_tuple(expressed.get("abilities"))
        )
    abilities = _string_tuple(expressed.get("abilities"))
    abilities, used = _fit_traits_to_budget(abilities, budget, seed_token=f"{seed}:{identity_token}:{root_id}")
    expressed["abilities"] = list(abilities)
    expressed["carried_abilities"] = list(_string_tuple(expressed.get("carried_abilities")))
    genes["abilities"] = list(ability_alleles)
    lineage_id = str(payload.get("lineage_id") or "").strip()
    if not lineage_id:
        lineage_id = f"fauna:{root_id}:{_stable_hash(root_id, expressed, length=14)}"
    source_genome_id = str(payload.get("genome_id") or lineage_id).strip()
    genome_id = f"genome:{root_id}:{_stable_hash(source_genome_id, seed, identity_token, length=18)}"
    return AnimalGenome(
        genome_id=genome_id,
        root_animal_id=root_id,
        lineage_id=lineage_id,
        genes=genes,
        expressed=expressed,
        parent_genome_ids=payload.get("parent_genome_ids"),
        parent_lineage_ids=payload.get("parent_lineage_ids"),
        generation=payload.get("generation", 0),
        trait_budget=budget,
        trait_cost_used=used,
        mutation_signature=payload.get("mutation_signature", ""),
        native_lineage_id=payload.get("native_lineage_id") or lineage_id,
    )


def fauna_genomes_compatible(left, right):
    if left is None or right is None:
        return False
    return bool(
        _key(getattr(left, "root_animal_id", ""))
        and _key(getattr(left, "root_animal_id", "")) == _key(getattr(right, "root_animal_id", ""))
        and str(getattr(left, "genome_id", "") or "") != str(getattr(right, "genome_id", "") or "")
    )


def _blend_parent_color(left_word, right_word, *, token, mutate=False):
    left_word = normalize_color_word(left_word, default="gray") or "gray"
    right_word = normalize_color_word(right_word, default=left_word) or left_word
    left_rgb = color_word_rgb(left_word, fallback=(140, 140, 140)) or (140, 140, 140)
    right_rgb = color_word_rgb(right_word, fallback=left_rgb) or left_rgb
    bias = 0.38 + (_stable_unit(token, "color-bias") * 0.24)
    rgb = [int(round((left_rgb[index] * bias) + (right_rgb[index] * (1.0 - bias)))) for index in range(3)]
    if mutate:
        for index in range(3):
            rgb[index] = max(0, min(255, rgb[index] + int(round((_stable_unit(token, "color-drift", index) - 0.5) * 76))))
    return find_nearest_color_word(tuple(rgb), default=left_word)


def _ability_candidates(channels):
    channels = set(_string_tuple(channels)) or set(GENERIC_BODY_CHANNELS)
    return tuple(
        trait
        for trait in sorted(ABILITY_TRAIT_COSTS)
        if ABILITY_CHANNELS.get(trait) in channels
    )


def inherit_animal_genome(
    left,
    right,
    *,
    seed,
    birth_token,
    mutation_rate=0.12,
    force_mutation=None,
    body_channels=GENERIC_BODY_CHANNELS,
):
    """Build one budget-valid child genome from compatible parents."""

    if not fauna_genomes_compatible(left, right):
        return None
    root_id = _key(getattr(left, "root_animal_id", ""), "other_root")
    generation = max(_safe_int(getattr(left, "generation", 0), 0), _safe_int(getattr(right, "generation", 0), 0)) + 1
    token = f"{seed}:{birth_token}:{root_id}:{left.genome_id}:{right.genome_id}:{generation}"
    left_exp = dict(getattr(left, "expressed", {}) or {})
    right_exp = dict(getattr(right, "expressed", {}) or {})
    budget = max(
        1,
        min(
            max(_safe_int(getattr(left, "trait_budget", DEFAULT_TRAIT_BUDGET), DEFAULT_TRAIT_BUDGET), 1),
            max(_safe_int(getattr(right, "trait_budget", DEFAULT_TRAIT_BUDGET), DEFAULT_TRAIT_BUDGET), 1),
        ),
    )
    mutation_kind = _key(force_mutation)
    forced_ability = mutation_kind if mutation_kind in ABILITY_TRAIT_COSTS else ""
    if forced_ability:
        mutation_kind = "ability"
    if not mutation_kind and _stable_unit(token, "mutation-present") < max(0.0, min(1.0, float(mutation_rate))):
        mutation_kind = _stable_pick(("ability", "color", "pattern", "build", "display"), token, "mutation-kind") or "color"

    child_axis_alleles = {}
    for axis, fallback_field in (
        ("visual_color", "color_word"),
        ("accent_color", "accent_color_word"),
        ("pattern", "pattern"),
        ("build", "build"),
        ("display", "display"),
    ):
        child_axis_alleles[axis] = [
            _pick_parent_allele(left, axis, fallback_field, token=f"{token}:left"),
            _pick_parent_allele(right, axis, fallback_field, token=f"{token}:right"),
        ]

    if mutation_kind == "color":
        mutation_word = _stable_pick(
            curated_color_words(include_reserved=False),
            token,
            "color-mutation-word",
        ) or "violet"
        mutate_index = int(_stable_unit(token, "color-mutation-side") * 2) % 2
        child_axis_alleles["visual_color"][mutate_index] = _allele(
            mutation_word,
            dominance=0.42 + (_stable_unit(token, "color-mutation-dominance") * 0.34),
            source="mutation",
            generation=generation,
        )
    elif mutation_kind == "pattern":
        mutation_value = _stable_pick(PATTERN_VALUES, token, "pattern-mutation") or "dappled"
        child_axis_alleles["pattern"][int(_stable_unit(token, "pattern-mutation-side") * 2) % 2] = _allele(
            mutation_value,
            dominance=0.38 + (_stable_unit(token, "pattern-mutation-dominance") * 0.4),
            source="mutation",
            generation=generation,
        )
    elif mutation_kind == "build":
        mutation_value = _stable_pick(BUILD_VALUES, token, "build-mutation") or "balanced"
        child_axis_alleles["build"][int(_stable_unit(token, "build-mutation-side") * 2) % 2] = _allele(
            mutation_value,
            dominance=0.38 + (_stable_unit(token, "build-mutation-dominance") * 0.4),
            source="mutation",
            generation=generation,
        )
    elif mutation_kind == "display":
        mutation_value = _stable_pick(DISPLAY_VALUES, token, "display-mutation") or "crest"
        child_axis_alleles["display"][int(_stable_unit(token, "display-mutation-side") * 2) % 2] = _allele(
            mutation_value,
            dominance=0.38 + (_stable_unit(token, "display-mutation-dominance") * 0.4),
            source="mutation",
            generation=generation,
        )

    color_word = _express_color_alleles(child_axis_alleles["visual_color"], token=f"{token}:color", fallback="gray")
    accent_word = _express_color_alleles(child_axis_alleles["accent_color"], token=f"{token}:accent", fallback=color_word)
    pattern = _express_allele_pair(child_axis_alleles["pattern"], token=f"{token}:pattern", fallback="plain") or "plain"
    build = _express_allele_pair(child_axis_alleles["build"], token=f"{token}:build", fallback="balanced") or "balanced"
    display = _express_allele_pair(child_axis_alleles["display"], token=f"{token}:display", fallback="none") or "none"

    ability_alleles = []
    left_abilities = _ability_alleles(left)
    right_abilities = _ability_alleles(right)
    for trait in sorted({row["value"] for row in left_abilities + right_abilities}):
        for parent_name, parent_rows in (("left", left_abilities), ("right", right_abilities)):
            copies = tuple(row for row in parent_rows if row["value"] == trait)
            if not copies:
                continue
            transmitted = _stable_pick(copies, token, trait, parent_name, "ability-transmit")
            if transmitted is not None:
                inherited = copy.deepcopy(transmitted)
                inherited["source"] = parent_name
                inherited["generation"] = generation
                ability_alleles.append(inherited)

    if mutation_kind == "ability":
        candidates = [
            trait
            for trait in _ability_candidates(body_channels)
            if trait not in {row["value"] for row in ability_alleles}
        ]
        mutation_trait = forced_ability or (_stable_pick(candidates, token, "ability-mutation") if candidates else "")
        if mutation_trait:
            ability_alleles.append(_allele(
                mutation_trait,
                dominance=0.2 + (_stable_unit(token, mutation_trait, "mutation-dominance") * 0.72),
                source="mutation",
                generation=generation,
            ))

    abilities, carried_abilities, used = _express_ability_alleles(ability_alleles, token=token, budget=budget)
    if "toxic_hide" in abilities and pattern == "plain":
        pattern = "warning_bands"
    if "exoskeleton" in abilities and display == "none":
        display = "plates"
    if "fleet_limb" in abilities and build in {"heavy", "broad"}:
        build = "lean"
    if "fright_display" in abilities and display == "none":
        display = _stable_pick(("crest", "fan", "quills", "sail"), token, "fright-display") or "crest"

    expressed = {
        "color_word": color_word,
        "accent_color_word": accent_word,
        "pattern": pattern,
        "build": build,
        "display": display,
        "abilities": list(abilities),
        "carried_abilities": list(carried_abilities),
        "mark_seed": int(_stable_unit(token, "lineage-mark") * 9973) % 9973,
    }
    genes = {
        "visual_color": child_axis_alleles["visual_color"],
        "accent_color": child_axis_alleles["accent_color"],
        "pattern": child_axis_alleles["pattern"],
        "build": child_axis_alleles["build"],
        "display": child_axis_alleles["display"],
        "abilities": ability_alleles,
    }
    # Hidden carrier alleles are part of a durable line even when two siblings
    # happen to look identical.  Otherwise registry replacement would silently
    # erase the very recessive variety the installation is meant to remember.
    lineage_stamp = _stable_hash(
        root_id,
        expressed,
        genes,
        tuple(sorted((left.lineage_id, right.lineage_id))),
        length=14,
    )
    lineage_id = f"fauna:{root_id}:{lineage_stamp}"
    mutation_signature = _stable_hash(token, mutation_kind, expressed, length=12) if mutation_kind else ""
    return AnimalGenome(
        genome_id=f"genome:{root_id}:{_stable_hash(token, expressed, length=18)}",
        root_animal_id=root_id,
        lineage_id=lineage_id,
        genes=genes,
        expressed=expressed,
        parent_genome_ids=(left.genome_id, right.genome_id),
        parent_lineage_ids=(left.lineage_id, right.lineage_id),
        generation=generation,
        trait_budget=budget,
        trait_cost_used=used,
        mutation_signature=mutation_signature,
        native_lineage_id=lineage_id,
    )


def animal_render_effects(genome):
    expressed = dict(getattr(genome, "expressed", {}) or {}) if genome is not None else {}
    effects = [
        f"genetic_pattern:{_key(expressed.get('pattern'), 'plain')}",
        f"genetic_build:{_key(expressed.get('build'), 'balanced')}",
        f"genetic_display:{_key(expressed.get('display'), 'none')}",
        f"genetic_accent:{normalize_color_word(expressed.get('accent_color_word'), default='gray') or 'gray'}",
        f"genetic_mark:{_safe_int(expressed.get('mark_seed'), 0) % 11}",
    ]
    effects.extend(f"genetic_ability:{trait}" for trait in _string_tuple(expressed.get("abilities")))
    return tuple(effects)


def apply_animal_genome_expression(sim, eid, genome=None, *, baseline_is_expressed=False):
    """Apply one genome once to the actor's live profiles and appearance.

    Native installation records retain their already-realized physical and
    ecological profile.  ``baseline_is_expressed`` prevents a future spawn
    from multiplying those inherited changes a second time while still
    restoring its visible phenotype and lineage identity.
    """

    from game.components import (
        AnimalPhysicalProfile,
        AnimalSocialProfile,
        CreatureIdentity,
        EcologyProfile,
        MovementThrottle,
        Render,
        Vitality,
    )

    genome = genome or sim.ecs.get(AnimalGenome).get(eid)
    if genome is None:
        return False
    physical = sim.ecs.get(AnimalPhysicalProfile).get(eid)
    if physical is not None and str(getattr(physical, "genome_applied_id", "")) == str(genome.genome_id):
        return True
    expressed = dict(getattr(genome, "expressed", {}) or {})
    abilities = set(_string_tuple(expressed.get("abilities")))
    build = _key(expressed.get("build"), "balanced")
    build_size_mult = {"slight": 0.82, "lean": 0.92, "balanced": 1.0, "heavy": 1.12, "broad": 1.18}.get(build, 1.0)
    build_speed_mult = {"slight": 1.08, "lean": 1.12, "balanced": 1.0, "heavy": 0.92, "broad": 0.88}.get(build, 1.0)

    if physical is not None and not baseline_is_expressed:
        physical.size_score = max(1.0, float(physical.size_score) * build_size_mult)
        physical.speed_score = max(1.0, float(physical.speed_score) * build_speed_mult)
        if "fleet_limb" in abilities:
            physical.speed_score *= 1.16
        physical.genome_applied_id = str(genome.genome_id)

    throttle = sim.ecs.get(MovementThrottle).get(eid)
    if throttle is not None and not baseline_is_expressed:
        throttle.speed_multiplier = max(0.25, float(getattr(throttle, "speed_multiplier", 1.0) or 1.0) * build_speed_mult)
        if "fleet_limb" in abilities:
            throttle.speed_multiplier *= 1.12

    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and not baseline_is_expressed:
        hp_mult = build_size_mult
        if "exoskeleton" in abilities:
            hp_mult += 0.22
        new_max = max(1, int(round(float(vitality.max_hp) * hp_mult)))
        vitality.max_hp = new_max
        vitality.hp = min(new_max, max(1, int(round(float(vitality.hp) * hp_mult))))

    ecology = sim.ecs.get(EcologyProfile).get(eid)
    if ecology is not None and not baseline_is_expressed:
        if "camouflage" in abilities:
            # Predator selection already values prey_score.  Lowering that
            # signal makes camouflage matter to the live ecology loop without
            # granting a magical universal invisibility flag.
            ecology.prey_score = max(0.0, float(ecology.prey_score) - 14.0)
        if "keen_senses" in abilities:
            ecology.flee_bias = min(100.0, float(ecology.flee_bias) + 8.0)
            ecology.chase_bias = min(100.0, float(ecology.chase_bias) + 5.0)
        if "herd_mind" in abilities:
            ecology.pack_score = min(100.0, float(ecology.pack_score) + 18.0)
        if "fright_display" in abilities:
            ecology.territorial_score = min(100.0, float(ecology.territorial_score) + 12.0)

    social = sim.ecs.get(AnimalSocialProfile).get(eid)
    if social is not None and not baseline_is_expressed and "herd_mind" in abilities:
        social.sociability = min(100.0, float(social.sociability) + 12.0)
        social.same_species_affinity = min(100.0, float(social.same_species_affinity) + 16.0)

    color_word = normalize_color_word(expressed.get("color_word"), default="gray") or "gray"
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is not None:
        identity.phenotype_color_word = color_word
        identity.root_animal_id = str(genome.root_animal_id)
        identity.fauna_lineage_id = str(genome.lineage_id)
        # Keep authored coat prose on founders when it exists, but descendants
        # and native lines have a direct phenotype color for Look/UI copy.
        if int(getattr(genome, "generation", 0) or 0) > 0 or not getattr(identity, "coat_variant", None):
            identity.coat_variant = color_word

    render = sim.ecs.get(Render).get(eid)
    if render is not None:
        render.set_appearance(
            color_word=color_word,
            effects=tuple(dict.fromkeys(tuple(getattr(render, "effects", ()) or ()) + animal_render_effects(genome))),
        )
    if physical is not None:
        physical.genome_applied_id = str(genome.genome_id)
    return True


def validate_animal_genome(genome):
    errors = []
    if genome is None:
        return ["animal genome is missing"]
    if _safe_int(getattr(genome, "schema_version", 0), 0) != FAUNA_GENETICS_SCHEMA_VERSION:
        errors.append(f"schema_version must be {FAUNA_GENETICS_SCHEMA_VERSION}")
    if not str(getattr(genome, "genome_id", "") or "").strip():
        errors.append("genome_id is required")
    if not _key(getattr(genome, "root_animal_id", "")):
        errors.append("root_animal_id is required")
    expressed = getattr(genome, "expressed", {})
    if not isinstance(expressed, Mapping):
        errors.append("expressed phenotype must be an object")
        return errors
    color = normalize_color_word(expressed.get("color_word"), default="")
    if not color:
        errors.append("expressed.color_word must be known")
    abilities = _string_tuple(expressed.get("abilities"))
    unknown = sorted(set(abilities) - set(ABILITY_TRAIT_COSTS))
    if unknown:
        errors.append(f"unknown ability traits: {', '.join(unknown)}")
    used = fauna_trait_cost_used(abilities)
    budget = max(0, _safe_int(getattr(genome, "trait_budget", 0), 0))
    if used > budget:
        errors.append(f"ability cost {used} exceeds trait budget {budget}")
    if _safe_int(getattr(genome, "trait_cost_used", used), used) != used:
        errors.append("trait_cost_used does not match expressed abilities")
    return errors


__all__ = [
    "ABILITY_TRAIT_COSTS",
    "DEFAULT_TRAIT_BUDGET",
    "FAUNA_GENETICS_SCHEMA_VERSION",
    "GENERIC_BODY_CHANNELS",
    "animal_genome_from_payload",
    "animal_genome_payload",
    "animal_render_effects",
    "apply_animal_genome_expression",
    "fauna_genomes_compatible",
    "fauna_trait_cost",
    "fauna_trait_cost_used",
    "founder_animal_genome",
    "inherit_animal_genome",
    "root_animal_id_for_profile",
    "validate_animal_genome",
]
