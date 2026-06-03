"""Deterministic, lightweight visible-description generation for human NPCs."""

import random

from game.human_identity import (
    is_human_identity,
    pronoun_format_slots,
    seed_human_identity_profile,
)


_STYLE_WEIGHTS = {
    "woman": (
        ("femme", 0.48),
        ("mixed", 0.22),
        ("androgynous", 0.16),
        ("masc", 0.14),
    ),
    "man": (
        ("masc", 0.48),
        ("mixed", 0.22),
        ("androgynous", 0.16),
        ("femme", 0.14),
    ),
    "nonbinary": (
        ("androgynous", 0.36),
        ("mixed", 0.28),
        ("femme", 0.18),
        ("masc", 0.18),
    ),
}

_STATURE_ROWS = (
    ("short and compact", "short"),
    ("short and lightly built", "short"),
    ("about average height and narrow-framed", "average"),
    ("about average height and long-limbed", "average"),
    ("about average height and solidly built", "sturdy"),
    ("a little above average height and broad-shouldered", "tall"),
    ("tall and rangy", "tall"),
    ("tall and square-shouldered", "tall"),
    ("compact and sturdy", "compact"),
    ("lean and wiry", "lean"),
)

_HAIR_COLORS = (
    "black",
    "dark brown",
    "chestnut",
    "warm brown",
    "ash blond",
    "honey blond",
    "platinum blond",
    "auburn",
    "copper-red",
    "silver",
    "charcoal",
)

_EYE_COLORS = (
    "dark brown",
    "brown",
    "hazel",
    "gray",
    "green",
    "blue",
    "amber",
)

_COMPLEXION_ROWS = (
    "deep brown complexion",
    "rich brown complexion",
    "warm brown complexion",
    "olive complexion",
    "golden complexion",
    "freckled fair complexion",
    "pale complexion",
)

_HAIR_TEXTURES = (
    "straight",
    "wavy",
    "curly",
    "coiled",
)

_HAIR_LENGTHS_BY_STYLE = {
    "femme": ("cropped", "short", "jaw-length", "shoulder-length", "long"),
    "masc": ("cropped", "short", "short", "jaw-length", "shoulder-length"),
    "androgynous": ("cropped", "short", "jaw-length", "shoulder-length"),
    "mixed": ("short", "jaw-length", "shoulder-length", "long"),
}

_HAIR_STYLE_ROWS = {
    "femme": (
        ("worn loose", "loose hair"),
        ("pinned back with a clip", "pinned-back hair"),
        ("braided over one shoulder", "side braid"),
        ("cut in a sharp bob", "sharp bob"),
        ("gathered into a high tail", "high tail"),
        ("swept behind one ear", "swept-back hair"),
    ),
    "masc": (
        ("cut close at the sides", "close sides"),
        ("slicked back", "slicked-back hair"),
        ("left a little unruly", "unruly hair"),
        ("trimmed into a rough crop", "rough crop"),
        ("parted neatly", "neat part"),
        ("tied back at the nape", "tied-back hair"),
    ),
    "androgynous": (
        ("cut blunt at the jaw", "jaw-cut hair"),
        ("shaved at one side", "one-sided shave"),
        ("tucked beneath a cap", "capped hair"),
        ("gathered at the nape", "nape tie"),
        ("falling across the brow", "brow-falling hair"),
        ("cut uneven on purpose", "uneven cut"),
    ),
    "mixed": (
        ("worn loose with one side clipped back", "clipped-back hair"),
        ("tied up carelessly", "careless tie"),
        ("let down in a heavy wave", "heavy wave"),
        ("worked into tight braids", "tight braids"),
        ("cut short but styled sharply", "sharp short cut"),
        ("kept in a loose knot", "loose knot"),
    ),
}

_ATTIRE_ROWS = {
    "femme": (
        ("a fitted dark coat over layered street clothes", "dark fitted coat"),
        ("a tailored jacket with slim trousers and polished boots", "tailored jacket"),
        ("a long cardigan over neat layers and heavy boots", "long cardigan"),
        ("a sharp blouse under a weatherproof coat", "sharp blouse and coat"),
        ("a clean-cut jacket and narrow skirt worn with practical shoes", "clean-cut jacket"),
        ("a soft sweater under a structured coat", "structured coat"),
    ),
    "masc": (
        ("a weathered bomber jacket over work clothes", "weathered bomber jacket"),
        ("a heavy coat with rolled sleeves and practical boots", "heavy coat"),
        ("a dark blazer over lived-in street layers", "dark blazer"),
        ("a field jacket and sturdy trousers", "field jacket"),
        ("a denim jacket over a plain button-up", "denim jacket"),
        ("a thick overshirt with rough work boots", "thick overshirt"),
    ),
    "androgynous": (
        ("a boxy coat over loose layered clothes", "boxy coat"),
        ("a long straight-cut jacket and severe boots", "straight-cut jacket"),
        ("an oversized overshirt with sharp dark layers under it", "oversized overshirt"),
        ("a cropped jacket over a clean turtleneck", "cropped jacket"),
        ("a sleeveless vest over neat monochrome layers", "sleeveless vest"),
        ("a severe long coat with loose trousers", "severe long coat"),
    ),
    "mixed": (
        ("a dark fitted coat mixed with rough street layers", "mixed dark coat"),
        ("a sharp jacket softened by loose scarves and work boots", "sharp jacket"),
        ("a weathered coat over polished layers", "weathered coat"),
        ("a structured blazer with a heavy cross-body strap", "structured blazer"),
        ("a neat overshirt with jewelry and scuffed boots", "neat overshirt"),
        ("a long coat over layered denim and soft knitwear", "layered long coat"),
    ),
}

_PALETTE_PHRASES = (
    "mostly charcoal and black",
    "all muted browns and olive",
    "a washed-out mix of gray and denim",
    "cut through with one bright accent",
    "all clean monochrome lines",
    "full of rust, cream, and smoke-dark cloth",
    "kept to quiet blues and slate",
    "set off with brass and wine-dark touches",
)

_CONDITION_PHRASES = (
    "kept surprisingly neat",
    "a little worn at the cuffs",
    "pressed sharp",
    "patched here and there",
    "weathered but looked after",
    "cleaner than the street around it",
    "scuffed in a way that looks lived-in",
    "put together with obvious care",
)

_ACCESSORY_ROWS = {
    "femme": (
        ("silver rings at the knuckles", "silver rings"),
        ("small earrings that catch the light", "small earrings"),
        ("a narrow scarf knotted close", "narrow scarf"),
        ("careful nail color, a little chipped at the edges", "chipped nail color"),
        ("a chain-strap bag tucked tight under one arm", "chain-strap bag"),
    ),
    "masc": (
        ("a watch chain worn smooth with use", "watch chain"),
        ("fingerless gloves tucked into a pocket", "fingerless gloves"),
        ("a satchel strap crossing the chest", "satchel strap"),
        ("a battered lighter clipped at the belt", "belt-clipped lighter"),
        ("heavy rings worn like habit, not decoration", "heavy rings"),
    ),
    "androgynous": (
        ("a stack of pins and tags at the lapel", "lapel pins"),
        ("a thin chain and a severe cuff", "chain and cuff"),
        ("a soft scarf wrapped close to the throat", "wrapped scarf"),
        ("a canvas strap cutting diagonally across the chest", "canvas strap"),
        ("small metal studs along one ear", "ear studs"),
    ),
    "mixed": (
        ("silver rings and a weathered watchband", "rings and watchband"),
        ("a scarf and a clipped ID tag", "scarf and ID tag"),
        ("bracelets mixed with work-rough gloves", "bracelets and gloves"),
        ("one bright pin against dark cloth", "bright pin"),
        ("a narrow shoulder bag and polished rings", "bag and rings"),
    ),
}

_STANDOUT_ROWS = (
    ("a scar on the right cheek", "scarred right cheek"),
    ("a nick through one eyebrow", "nicked eyebrow"),
    ("paint caught under the nails", "paint-stained nails"),
    ("grease darkening the cuffs", "grease-dark cuffs"),
    ("an old burn mark near one wrist", "burn-marked wrist"),
    ("a split knuckle or two", "split knuckles"),
    ("tired eyes that give the whole face away", "tired eyes"),
    ("a tattoo line disappearing under the collar", "collarline tattoo"),
    ("careful eyeliner sharp enough to read at a distance", "sharp eyeliner"),
    ("close-trimmed stubble kept exact", "trimmed stubble"),
    ("a clean shave that somehow still looks recent", "fresh clean shave"),
    ("a chipped front tooth when the mouth shifts", "chipped front tooth"),
)

_DEMEANOR_ROWS = (
    ("watchful and self-contained", "watchful"),
    ("brisk and hard to slow down", "brisk"),
    ("warm in spite of the edges", "warm"),
    ("guarded without looking afraid", "guarded"),
    ("restless and ready to move", "restless"),
    ("tired but carefully put together", "tired"),
    ("sharp in a practiced way", "sharp"),
    ("unhurried and quietly confident", "calm"),
    ("deliberate about every small motion", "deliberate"),
)

_GROOMING_ROWS = {
    "femme": (
        "Hair and makeup both look deliberate.",
        "There is care in the grooming, even where the clothes are worn.",
        "Every visible detail looks chosen rather than accidental.",
    ),
    "masc": (
        "The grooming is neat, but not soft about it.",
        "The whole presentation reads maintained out of discipline more than vanity.",
        "Nothing looks sloppy, even where it looks rough.",
    ),
    "androgynous": (
        "The presentation is controlled enough to feel intentional from a distance.",
        "Nothing about the look reads accidental.",
        "The styling lands sharp without settling into one easy lane.",
    ),
    "mixed": (
        "The styling mixes polish and wear in a way that looks entirely on purpose.",
        "The whole look holds together through contrast more than uniformity.",
        "The presentation feels chosen piece by piece.",
    ),
}


def _identity_preview(seed, eid, personal_name, identity):
    if identity is None:
        return {}
    if str(getattr(identity, "gender_identity", "") or "").strip():
        return {
            "gender_identity": str(getattr(identity, "gender_identity", "") or "").strip().lower(),
        }
    resolved_name = str(personal_name or getattr(identity, "personal_name", "") or "").strip()
    if not resolved_name:
        return {}
    preview = seed_human_identity_profile(
        f"{seed}:human-description-preview:{eid}:{resolved_name}",
        resolved_name,
    )
    return {
        "gender_identity": str(preview.get("gender_identity", "") or "").strip().lower(),
    }


def _weighted_choice(rng, weighted_rows):
    total = 0.0
    for _, weight in weighted_rows:
        total += max(0.0, float(weight))
    if total <= 0.0:
        return weighted_rows[0][0]
    pick = rng.random() * total
    seen = 0.0
    for value, weight in weighted_rows:
        seen += max(0.0, float(weight))
        if pick <= seen:
            return value
    return weighted_rows[-1][0]


def _pick_row(rng, rows):
    return rows[rng.randrange(len(rows))]


def _capitalize(text):
    text = str(text or "").strip()
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def _join_with_and(parts):
    bits = [str(part).strip() for part in tuple(parts or ()) if str(part).strip()]
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} and {bits[1]}"
    return f"{', '.join(bits[:-1])}, and {bits[-1]}"


def build_human_description_profile(seed, *, eid=None, identity=None, personal_name=None):
    if identity is not None and not is_human_identity(identity):
        return None
    resolved_name = str(personal_name or getattr(identity, "personal_name", "") or "").strip()
    resolved_eid = 0 if eid is None else int(eid)
    preview = _identity_preview(seed, resolved_eid, resolved_name, identity)
    gender_identity = str(
        getattr(identity, "gender_identity", "") or preview.get("gender_identity", "") or "nonbinary"
    ).strip().lower() or "nonbinary"
    if gender_identity not in _STYLE_WEIGHTS:
        gender_identity = "nonbinary"

    seed_token = f"{seed}:human-description:{resolved_eid}:{resolved_name}:{gender_identity}"
    rng = random.Random(seed_token)
    style_axis = _weighted_choice(rng, _STYLE_WEIGHTS[gender_identity])
    stature_phrase, stature_compact = _pick_row(rng, _STATURE_ROWS)
    hair_length = _pick_row(rng, _HAIR_LENGTHS_BY_STYLE[style_axis])
    hair_color = _pick_row(rng, _HAIR_COLORS)
    hair_texture = _pick_row(rng, _HAIR_TEXTURES)
    eye_color = _pick_row(rng, _EYE_COLORS)
    complexion_phrase = _pick_row(rng, _COMPLEXION_ROWS)
    hair_style_phrase, hair_style_compact = _pick_row(rng, _HAIR_STYLE_ROWS[style_axis])
    attire_phrase, attire_compact = _pick_row(rng, _ATTIRE_ROWS[style_axis])
    palette_phrase = _pick_row(rng, _PALETTE_PHRASES)
    condition_phrase = _pick_row(rng, _CONDITION_PHRASES)
    accessory_phrase, accessory_compact = _pick_row(rng, _ACCESSORY_ROWS[style_axis])
    standout_phrase, standout_compact = _pick_row(rng, _STANDOUT_ROWS)
    demeanor_phrase, demeanor_compact = _pick_row(rng, _DEMEANOR_ROWS)
    grooming_sentence = _pick_row(rng, _GROOMING_ROWS[style_axis])

    hair_phrase = f"{hair_length} {hair_color} {hair_texture} hair {hair_style_phrase}"
    hair_compact = f"{hair_length} {hair_color} hair"

    return {
        "seed_token": seed_token,
        "gender_identity": gender_identity,
        "style_axis": style_axis,
        "stature_phrase": stature_phrase,
        "stature_compact": stature_compact,
        "hair_color": hair_color,
        "hair_texture": hair_texture,
        "hair_length": hair_length,
        "eye_color": eye_color,
        "complexion_phrase": complexion_phrase,
        "hair_phrase": hair_phrase,
        "hair_compact": hair_compact,
        "hair_style_compact": hair_style_compact,
        "attire_phrase": attire_phrase,
        "attire_compact": attire_compact,
        "palette_phrase": palette_phrase,
        "condition_phrase": condition_phrase,
        "accessory_phrase": accessory_phrase,
        "accessory_compact": accessory_compact,
        "standout_phrase": standout_phrase,
        "standout_compact": standout_compact,
        "demeanor_phrase": demeanor_phrase,
        "demeanor_compact": demeanor_compact,
        "grooming_sentence": grooming_sentence,
    }


def build_human_physical_profile(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_description_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return None
    return {
        "stature_phrase": str(profile.get("stature_phrase", "")).strip(),
        "stature_compact": str(profile.get("stature_compact", "")).strip(),
        "hair_color": str(profile.get("hair_color", "")).strip(),
        "hair_texture": str(profile.get("hair_texture", "")).strip(),
        "hair_length": str(profile.get("hair_length", "")).strip(),
        "hair_phrase": str(profile.get("hair_phrase", "")).strip(),
        "eye_color": str(profile.get("eye_color", "")).strip(),
        "complexion_phrase": str(profile.get("complexion_phrase", "")).strip(),
        "standout_phrase": str(profile.get("standout_phrase", "")).strip(),
        "standout_compact": str(profile.get("standout_compact", "")).strip(),
    }


def human_physical_summary(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_physical_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return ""
    parts = [
        _capitalize(profile.get("stature_phrase", "")),
        _join_with_and(
            (
                f"{profile.get('eye_color', '').strip()} eyes" if profile.get("eye_color") else "",
                profile.get("complexion_phrase", ""),
            )
        ),
        profile.get("hair_phrase", ""),
        profile.get("standout_phrase", ""),
    ]
    summary = "; ".join(str(part).strip() for part in parts if str(part).strip())
    if not summary:
        return ""
    return f"{summary}."


def human_conversation_description(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_description_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return ""

    rng = random.Random(f"{profile['seed_token']}:conversation")
    slots = pronoun_format_slots(
        str(getattr(identity, "pronoun_set", "") or "").strip().lower() or profile["gender_identity"],
        prefix="person",
        personal_name=personal_name,
        seed_token=profile["seed_token"],
    )
    identity_noun = {
        "woman": "woman",
        "man": "man",
        "nonbinary": "person",
    }.get(str(profile.get("gender_identity", "") or "").strip().lower(), "person")
    first_tail = _join_with_and((profile["hair_phrase"], profile["standout_phrase"]))
    demeanor_tail = ""
    if rng.random() < 0.54:
        demeanor_tail = f", and the whole look feels {profile['demeanor_phrase']}"
    elif rng.random() < 0.24:
        demeanor_tail = f", with {profile['accessory_phrase']} finishing the look"
    sentences = [
        f"You see a {identity_noun} here.",
        f"{slots['person_subject_cap']} {slots['person_be']} {profile['stature_phrase']} and {slots['person_have']} {first_tail}.",
        (
            f"{slots['person_possessive_adj_cap']} {profile['eye_color']} eyes and "
            f"{profile['complexion_phrase']} stand out against {profile['attire_phrase']}"
            f"{demeanor_tail}."
        ),
    ]
    return " ".join(sentence for sentence in sentences[:3] if str(sentence).strip())


def human_look_description_clause(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_description_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return ""
    bits = (
        profile["stature_compact"],
        profile["attire_compact"],
        profile["hair_compact"],
        profile["standout_compact"],
        profile["demeanor_compact"],
    )
    return ", ".join(str(bit).strip() for bit in bits if str(bit).strip())
