"""Grounded procedural names for individual fauna and emerging lineages."""

from __future__ import annotations

import hashlib

from game.color_words import normalize_color_word
from game.fauna_genetics import MAJOR_SPECIATION_ABILITIES, morphology_for_root


DISPLAY_DESCRIPTOR_WORDS = {
    "crest": "crested",
    "fan": "fan-tailed",
    "horns": "horned",
    "plates": "plated",
    "quills": "quilled",
    "sail": "sail-backed",
}

PATTERN_DESCRIPTOR_WORDS = {
    "dappled": "dappled",
    "masked": "masked",
    "mottled": "mottled",
    "spotted": "spotted",
    "striped": "striped",
    "warning_bands": "banded",
}

MORPHOLOGY_DESCRIPTOR_WORDS = {
    "banded_armor": "banded-armored",
    "broad_fan": "broad-tailed",
    "broad_wings": "broad-winged",
    "crab_claws": "pincer-armed",
    "digging_claws": "digging-clawed",
    "display_fan": "fan-tailed",
    "forked_fan": "fork-tailed",
    "hare_long_ears": "long-eared",
    "heavy_tapered": "heavy-tailed",
    "hooked_beak": "hook-beaked",
    "long_beak": "long-beaked",
    "long_hopping": "long-legged",
    "membrane_wings": "membrane-winged",
    "paddle": "paddle-tailed",
    "quills": "quilled",
    "rattle": "rattle-tailed",
    "ringed": "ring-tailed",
    "shell": "shell-backed",
    "talons": "taloned",
    "webbed": "web-footed",
    "warning_plume": "plume-tailed",
}

MORPHOLOGY_LINEAGE_STEMS = {
    "banded_armor": "band",
    "broad_fan": "broadtail",
    "broad_wings": "broadwing",
    "crab_claws": "pincer",
    "digging_claws": "digger",
    "display_fan": "fan",
    "forked_fan": "forktail",
    "hare_long_ears": "longear",
    "heavy_tapered": "heavytail",
    "hooked_beak": "hookbill",
    "long_beak": "longbill",
    "long_hopping": "longleg",
    "membrane_wings": "veilwing",
    "paddle": "paddletail",
    "quills": "quill",
    "rattle": "rattle",
    "ringed": "ringtail",
    "shell": "shell",
    "talons": "talon",
    "webbed": "webfoot",
    "warning_plume": "plume",
}

MORPHOLOGY_SALIENCE_ORDER = ("surface", "forelimbs", "tail", "head", "hindlimbs", "body_frame")

SPECIES_COIN_STEMS = (
    "briar",
    "cinder",
    "dusk",
    "ember",
    "glass",
    "hollow",
    "moss",
    "reed",
    "river",
    "rust",
    "silver",
    "storm",
    "tide",
    "umber",
    "veil",
)

SPECIES_TRAIT_STEMS = {
    **MORPHOLOGY_LINEAGE_STEMS,
    "bare": "baretail",
    "bristles": "bristle",
    "broad_snake": "broadhead",
    "curled": "curltail",
    "dense_fur": "thickcoat",
    "domed_crawler": "domeback",
    "domed_quadruped": "domeback",
    "eye_stalks": "stalkeye",
    "heavy_tapered": "heavytail",
    "long_jaw": "longjaw",
    "masked": "maskface",
    "paddle": "paddletail",
    "powdered_wings": "dustwing",
    "rattle": "rattle",
    "scales": "scalehide",
    "serpentine": "coil",
    "streamlined_aquatic": "streamfin",
    "wide_crustacean": "broadclaw",
    "winged_mammal": "veilwing",
}

LINEAGE_COLOR_STEMS = {
    "amber": ("amber", "honey"),
    "ash": ("ash", "dust"),
    "black": ("night", "sable"),
    "blue": ("blue", "rain"),
    "bronze": ("bronze", "copper"),
    "brown": ("umber", "earth"),
    "charcoal": ("cinder", "smoke"),
    "coral": ("coral", "tide"),
    "cream": ("ivory", "pale"),
    "gray": ("ash", "mist"),
    "green": ("moss", "fern"),
    "indigo": ("dusk", "indigo"),
    "lime": ("lime", "spring"),
    "olive": ("reed", "olive"),
    "orange": ("flame", "sun"),
    "rust": ("ember", "russet"),
    "sand": ("sand", "dune"),
    "silver": ("silver", "moon"),
    "slate": ("slate", "storm"),
    "tan": ("dun", "sand"),
    "white": ("frost", "pale"),
    "yellow": ("gold", "sun"),
}

LINEAGE_TRAIT_STEMS = {
    "dappled": "dapple",
    "masked": "mask",
    "mottled": "mottle",
    "spotted": "spot",
    "striped": "stripe",
    "warning_bands": "band",
    "crest": "crest",
    "fan": "fan",
    "horns": "horn",
    "plates": "plate",
    "quills": "quill",
    "sail": "sail",
    "keen_senses": "keen",
    "herd_mind": "chorus",
    "fleet_limb": "swift",
    "camouflage": "veil",
    "fright_display": "flare",
    "exoskeleton": "shell",
    "toxic_hide": "bane",
    "venomous_bite": "fang",
    "shock_glands": "spark",
    "slight": "wisp",
    "lean": "quick",
    "heavy": "stone",
    "broad": "broad",
}

LINEAGE_NOUNS_BY_ROOT = {
    "armored_crawler": ("crawler", "turtle"),
    "armored_forager": ("forager", "roller"),
    "burrow_grazer": ("burrower", "grazer"),
    "burrow_scavenger": ("rat", "burrower"),
    "clever_flier": ("crow", "wing"),
    "dust_flier": ("moth", "flier"),
    "echo_flier": ("bat", "nightwing"),
    "flock_forager": ("bird", "flockwing"),
    "great_prowler": ("greatcat", "prowler"),
    "ground_flock": ("groundbird", "runner"),
    "heavy_forager": ("bear", "forager"),
    "herd_grazer": ("grazer", "hart"),
    "horned_scuttler": ("beetle", "scuttler"),
    "long_crawler": ("serpent", "crawler"),
    "marsh_ambusher": ("marshjaw", "ambusher"),
    "masked_scavenger": ("scavenger", "masktail"),
    "mid_prowler": ("brushcat", "prowler"),
    "night_hunter": ("nightwing", "owl"),
    "quilled_forager": ("quillback", "forager"),
    "rooting_tank": ("rooter", "boar"),
    "scrub_crawler": ("lizard", "crawler"),
    "shore_scuttler": ("tidecrawler", "crab"),
    "sky_hunter": ("hawk", "skyhunter"),
    "small_grazer": ("hare", "cottontail"),
    "small_prowler": ("smallcat", "prowler"),
    "soft_leaper": ("frog", "leaper"),
    "solitary_canid": ("fox", "brushhound"),
    "street_pack": ("hound", "wolf"),
    "swarm_scuttler": ("swarm", "scuttler"),
    "tree_forager": ("treeforager", "brushtail"),
    "warning_scavenger": ("warningtail", "scavenger"),
    "water_prowler": ("riverprowler", "otter"),
}


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or str(fallback or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _stable_index(size, *parts):
    if int(size) <= 0:
        return 0
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16) % int(size)


def _stable_pick(values, *parts):
    values = tuple(values or ())
    return values[_stable_index(len(values), *parts)] if values else None


def _novel_morphology_values(genome):
    """Return visible descendant anatomy that departs from its root plan."""

    if genome is None or _safe_int(getattr(genome, "generation", 0), 0) <= 0:
        return ()
    expressed = dict(getattr(genome, "expressed", {}) or {})
    root = morphology_for_root(getattr(genome, "root_animal_id", ""))
    values = []
    for axis in MORPHOLOGY_SALIENCE_ORDER:
        value = _key(expressed.get(axis))
        if value and value != _key(root.get(axis)) and value in MORPHOLOGY_DESCRIPTOR_WORDS:
            values.append(value)
    return tuple(dict.fromkeys(values))


def fauna_phenotype_descriptor(identity, genome):
    """Name one animal using only its outwardly expressed phenotype."""

    if identity is None:
        return "animal"
    base_name = str(
        getattr(identity, "common_name", "")
        or getattr(identity, "creature_type", "")
        or "animal"
    ).replace("_", " ").strip().lower() or "animal"
    age_prefix = ""
    if base_name.startswith("young "):
        age_prefix = "young"
        base_name = base_name[6:].strip() or "animal"

    line_name = str(getattr(identity, "fauna_line_name", "") or "").replace("_", " ").strip().lower()
    if line_name and base_name == line_name:
        return " ".join(value for value in (age_prefix, line_name) if value)

    expressed = dict(getattr(genome, "expressed", {}) or {}) if genome is not None else {}
    color = normalize_color_word(expressed.get("color_word"), default="") or ""
    pattern = PATTERN_DESCRIPTOR_WORDS.get(_key(expressed.get("pattern")))
    build = _key(expressed.get("build"))
    display = DISPLAY_DESCRIPTOR_WORDS.get(_key(expressed.get("display")))
    morphology = tuple(MORPHOLOGY_DESCRIPTOR_WORDS[value] for value in _novel_morphology_values(genome))
    collective = "swarm" in base_name or base_name.endswith((" moths", " roaches"))

    salient = list(morphology[:1])
    if display and display not in base_name.split():
        salient.append(display)
    if pattern and pattern not in base_name.split():
        salient.append(pattern)
    if build and build != "balanced" and not collective and build not in base_name.split():
        salient.append(build)

    base_words = set(base_name.replace("-", " ").split())
    color_word = color if color and color not in base_words else None
    modifiers = []
    if salient:
        modifiers.append(salient[0])
        mark_seed = _safe_int(expressed.get("mark_seed"), 0)
        if len(salient) > 1 and (not color_word or mark_seed % 3 == 0):
            modifiers.append(salient[1])
        elif color_word:
            modifiers.append(color_word)
    elif color_word:
        modifiers.append(color_word)

    words = ([age_prefix] if age_prefix else []) + modifiers[:2] + [base_name]
    return " ".join(word for word in words if word).strip() or "animal"


def apply_fauna_phenotype_descriptor(identity, genome):
    if identity is None:
        return ""
    descriptor = fauna_phenotype_descriptor(identity, genome)
    identity.phenotype_descriptor = descriptor
    return descriptor


def generate_fauna_line_name(genome, *, parent_names=(), seed_token=""):
    """Coin a stable readable name for one newly realized genetic line."""

    expressed = dict(getattr(genome, "expressed", {}) or {}) if genome is not None else {}
    root_id = _key(getattr(genome, "root_animal_id", ""), "other_root")
    mark_seed = _safe_int(expressed.get("mark_seed"), 0)
    stable_token = (
        str(getattr(genome, "lineage_id", "") or ""),
        str(getattr(genome, "genome_id", "") or ""),
        str(seed_token or ""),
        mark_seed,
    )

    color = normalize_color_word(expressed.get("color_word"), default="gray") or "gray"
    color_stems = LINEAGE_COLOR_STEMS.get(color, (color.replace("_", ""),))
    color_stem = _stable_pick(color_stems, *stable_token, "color") or "wild"

    trait_stems = []
    for value in (
        *_novel_morphology_values(genome),
        _key(expressed.get("display")),
        _key(expressed.get("pattern")),
        *tuple(_key(value) for value in tuple(expressed.get("abilities") or ())),
        _key(expressed.get("build")),
    ):
        stem = MORPHOLOGY_LINEAGE_STEMS.get(value) or LINEAGE_TRAIT_STEMS.get(value)
        if stem and stem not in trait_stems:
            trait_stems.append(stem)
    # Plate/shell and quill/flare describe the same salient anatomy twice.
    if "plate" in trait_stems and "shell" in trait_stems:
        trait_stems.remove("shell")
    if "quill" in trait_stems and "flare" in trait_stems:
        trait_stems.remove("flare")

    if trait_stems:
        trait_stem = _stable_pick(trait_stems, *stable_token, "trait")
        prefix = f"{color_stem}{trait_stem}"
    else:
        prefix = color_stem
    if len(prefix) > 18:
        prefix = prefix[:18].rstrip("-_ ")

    nouns = LINEAGE_NOUNS_BY_ROOT.get(root_id)
    if not nouns:
        parent_bases = []
        for raw in tuple(parent_names or ()):
            base = str(raw or "").replace("_", " ").strip().lower()
            if base.startswith("young "):
                base = base[6:].strip()
            if base:
                parent_bases.append(base.split()[-1])
        nouns = tuple(dict.fromkeys(parent_bases)) or (root_id.replace("_", " "),)
    noun = _stable_pick(nouns, *stable_token, "noun") or "creature"
    return f"{prefix} {noun}".strip().lower()


def generate_fauna_species_name(genome, *, parent_species_ids=(), mixed_parent_species=False):
    """Coin one stable color-insensitive common name for an emergent species."""

    expressed = dict(getattr(genome, "expressed", {}) or {}) if genome is not None else {}
    root_id = _key(getattr(genome, "root_animal_id", ""), "other_root")
    parent_ids = tuple(sorted({_key(value) for value in tuple(parent_species_ids or ()) if _key(value)}))
    stable_token = ("fauna-species", root_id, parent_ids)
    if mixed_parent_species:
        # Mixed-parent siblings can vary in small anatomy. Their species name
        # must not flicker with each individual phenotype.
        prefix = _stable_pick(SPECIES_COIN_STEMS, *stable_token, "mixed-prefix") or "mosaic"
    else:
        root_morphology = morphology_for_root(root_id)
        trait_stems = []
        for axis in MORPHOLOGY_SALIENCE_ORDER:
            value = _key(expressed.get(axis))
            if value and value != _key(root_morphology.get(axis)):
                stem = SPECIES_TRAIT_STEMS.get(value)
                if stem and stem not in trait_stems:
                    trait_stems.append(stem)
        for ability in tuple(expressed.get("abilities") or ()):
            value = _key(ability)
            if value in MAJOR_SPECIATION_ABILITIES:
                stem = LINEAGE_TRAIT_STEMS.get(value)
                if stem and stem not in trait_stems:
                    trait_stems.append(stem)
        if trait_stems:
            first = _stable_pick(trait_stems, *stable_token, tuple(sorted(trait_stems)), "first-trait") or trait_stems[0]
            remaining = tuple(stem for stem in trait_stems if stem != first)
            second = _stable_pick(remaining, *stable_token, tuple(sorted(trait_stems)), "second-trait") if remaining else ""
            prefix = f"{first}{second}" if second and len(first) + len(second) <= 17 else first
        else:
            prefix = _stable_pick(SPECIES_COIN_STEMS, *stable_token, "fallback-prefix") or "mosaic"
    nouns = LINEAGE_NOUNS_BY_ROOT.get(root_id, (root_id.replace("_", " "),))
    noun = _stable_pick(nouns, *stable_token, "noun") or "creature"
    return f"{prefix} {noun}".strip().lower()


__all__ = [
    "apply_fauna_phenotype_descriptor",
    "fauna_phenotype_descriptor",
    "generate_fauna_line_name",
    "generate_fauna_species_name",
]
