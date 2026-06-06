"""Deterministic, lightweight visible-description generation for human NPCs."""

import random

from game.human_identity import (
    is_human_identity,
    normalize_gender_identity,
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

# Keep the render buckets deliberately small so the curses frontend stays legible.
_HUMAN_RENDER_PALETTE_ROWS = (
    ("mostly charcoal and black", "charcoal and black", "human_charcoal"),
    ("all muted browns and olive", "brown and olive", "human_olive"),
    ("a washed-out mix of gray and denim", "gray and denim", "human_denim"),
    ("cut through with one bright accent", "bright accent", "human_accent"),
    ("all clean monochrome lines", "clean monochrome", "human_monochrome"),
    ("full of rust, cream, and smoke-dark cloth", "rust and cream", "human_rust"),
    ("kept to quiet blues and slate", "blue and slate", "human_slate"),
    ("set off with brass and wine-dark touches", "brass and wine-dark", "human_wine"),
)

HUMAN_RENDER_COLOR_KEYS = frozenset(row[2] for row in _HUMAN_RENDER_PALETTE_ROWS)

_HAIR_RENDER_COLOR_KEYS = {
    "black": "human_charcoal",
    "dark brown": "human_olive",
    "chestnut": "human_rust",
    "warm brown": "human_rust",
    "ash blond": "human_accent",
    "honey blond": "human_accent",
    "platinum blond": "human_monochrome",
    "auburn": "human_wine",
    "copper-red": "human_rust",
    "silver": "human_monochrome",
    "charcoal": "human_charcoal",
}

_EYE_RENDER_COLOR_KEYS = {
    "dark brown": "human_olive",
    "brown": "human_rust",
    "hazel": "human_olive",
    "gray": "human_monochrome",
    "green": "human_olive",
    "blue": "human_slate",
    "amber": "human_accent",
}

_COMPLEXION_RENDER_COLOR_KEYS = {
    "deep brown complexion": "human_rust",
    "rich brown complexion": "human_rust",
    "warm brown complexion": "human_rust",
    "olive complexion": "human_olive",
    "golden complexion": "human_accent",
    "freckled fair complexion": "human_monochrome",
    "pale complexion": "human_monochrome",
}

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
    ("a chipped front tooth when the mouth shifts", "chipped front tooth"),
)

_FACIAL_HAIR_STANDOUT_ROWS = (
    ("close-trimmed stubble kept exact", "trimmed stubble"),
    ("a clean shave that somehow still looks recent", "fresh clean shave"),
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


def _indefinite_article_phrase(text):
    text = str(text or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("a ", "an ", "the ", "some ", "one ")):
        return text
    article = "an" if lowered[:1] in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {text}"


def _identity_noun(gender_identity):
    return {
        "woman": "woman",
        "man": "man",
        "nonbinary": "person",
    }.get(str(gender_identity or "").strip().lower(), "person")


def _standout_rows_for(gender_identity, style_axis):
    gender_identity = normalize_gender_identity(gender_identity, default="nonbinary")
    style_axis = str(style_axis or "").strip().lower()
    if gender_identity == "woman":
        return _STANDOUT_ROWS
    if gender_identity == "man" or style_axis == "masc":
        return _STANDOUT_ROWS + _FACIAL_HAIR_STANDOUT_ROWS
    return _STANDOUT_ROWS


def build_human_description_profile(seed, *, eid=None, identity=None, personal_name=None):
    if identity is not None and not is_human_identity(identity):
        return None
    resolved_name = str(personal_name or getattr(identity, "personal_name", "") or "").strip()
    resolved_eid = 0 if eid is None else int(eid)
    preview = _identity_preview(seed, resolved_eid, resolved_name, identity)
    gender_identity = normalize_gender_identity(
        getattr(identity, "gender_identity", "") or preview.get("gender_identity", "") or "nonbinary"
    )

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
    palette_phrase, palette_compact, render_color_key = _pick_row(rng, _HUMAN_RENDER_PALETTE_ROWS)
    condition_phrase = _pick_row(rng, _CONDITION_PHRASES)
    accessory_phrase, accessory_compact = _pick_row(rng, _ACCESSORY_ROWS[style_axis])
    standout_phrase, standout_compact = _pick_row(rng, _standout_rows_for(gender_identity, style_axis))
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
        "palette_compact": palette_compact,
        "render_color_key": render_color_key,
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


def human_self_physical_summary(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_description_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return ""
    identity_noun = _identity_noun(profile.get("gender_identity"))
    stature = str(profile.get("stature_phrase", "") or "").strip()
    features = []
    eye_color = str(profile.get("eye_color", "") or "").strip()
    if eye_color:
        features.append(f"{eye_color} eyes")
    complexion = str(profile.get("complexion_phrase", "") or "").strip()
    if complexion:
        features.append(_indefinite_article_phrase(complexion))
    hair = str(profile.get("hair_phrase", "") or "").strip()
    if hair:
        features.append(hair)
    standout = str(profile.get("standout_phrase", "") or "").strip()
    if standout:
        features.append(standout)

    opening = f"I am a {identity_noun}"
    if stature:
        opening = f"{opening}, {stature}"
    feature_text = _join_with_and(features)
    if feature_text:
        return f"{opening}, with {feature_text}."
    return f"{opening}."


def _conversation_segment(text, *, color=None, attrs=0):
    return {
        "text": str(text or ""),
        "color": color,
        "attrs": int(attrs or 0),
    }


def _conversation_text(segments):
    return "".join(str(segment.get("text", "")) for segment in segments or () if isinstance(segment, dict))


def _hair_descriptor_color_key(profile):
    return _HAIR_RENDER_COLOR_KEYS.get(str(profile.get("hair_color", "")).strip().lower()) or str(
        profile.get("render_color_key", "") or ""
    ).strip() or None


def _eye_descriptor_color_key(profile):
    return _EYE_RENDER_COLOR_KEYS.get(str(profile.get("eye_color", "")).strip().lower()) or None


def _complexion_descriptor_color_key(profile):
    return _COMPLEXION_RENDER_COLOR_KEYS.get(str(profile.get("complexion_phrase", "")).strip().lower()) or None


def human_conversation_presentation(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_description_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return {"text": "", "segments": []}

    rng = random.Random(f"{profile['seed_token']}:conversation")
    slots = pronoun_format_slots(
        str(getattr(identity, "pronoun_set", "") or "").strip().lower() or profile["gender_identity"],
        prefix="person",
        personal_name=personal_name,
        seed_token=profile["seed_token"],
    )
    identity_noun = _identity_noun(profile.get("gender_identity"))
    eye_phrase = f"{profile['eye_color']} eyes" if str(profile.get("eye_color", "")).strip() else ""
    demeanor_tail = ""
    if rng.random() < 0.54:
        demeanor_tail = f", and the whole look feels {profile['demeanor_phrase']}"
    elif rng.random() < 0.24:
        demeanor_tail = f", with {profile['accessory_phrase']} finishing the look"
    attire_bits = [
        str(profile.get("attire_phrase", "")).strip(),
        str(profile.get("palette_phrase", "")).strip(),
        str(profile.get("condition_phrase", "")).strip(),
    ]
    attire_bits = [bit for bit in attire_bits if bit]

    segments = [
        _conversation_segment(f"You see a {identity_noun} here. "),
        _conversation_segment(
            f"{slots['person_subject_cap']} {slots['person_be']} {profile['stature_phrase']} and {slots['person_have']} "
        ),
        _conversation_segment(profile.get("hair_phrase", ""), color=_hair_descriptor_color_key(profile)),
    ]
    standout_phrase = str(profile.get("standout_phrase", "")).strip()
    if standout_phrase:
        segments.append(_conversation_segment(" and "))
        segments.append(_conversation_segment(standout_phrase))
    segments.append(_conversation_segment(". "))
    segments.append(_conversation_segment(f"{slots['person_possessive_adj_cap']} "))
    if eye_phrase:
        segments.append(_conversation_segment(eye_phrase, color=_eye_descriptor_color_key(profile)))
    complexion_phrase = str(profile.get("complexion_phrase", "")).strip()
    if complexion_phrase:
        if eye_phrase:
            segments.append(_conversation_segment(" and "))
        segments.append(_conversation_segment(complexion_phrase, color=_complexion_descriptor_color_key(profile)))
    segments.append(_conversation_segment(" stand out against "))
    for idx, bit in enumerate(attire_bits):
        bit_color = str(profile.get("render_color_key", "") or "").strip() or None
        if idx == len(attire_bits) - 1:
            bit_color = None if bit == str(profile.get("condition_phrase", "")).strip() else bit_color
        if idx > 0:
            segments.append(_conversation_segment(", "))
        segments.append(_conversation_segment(bit, color=bit_color))
    if demeanor_tail:
        segments.append(_conversation_segment(demeanor_tail))
    segments.append(_conversation_segment("."))
    plain = _conversation_text(segments).strip()
    return {
        "text": plain,
        "segments": [segment for segment in segments if str(segment.get("text", ""))],
    }


def human_conversation_description(seed, *, eid=None, identity=None, personal_name=None):
    presentation = human_conversation_presentation(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    return str(presentation.get("text", "")).strip()


def human_render_color_key(seed, *, eid=None, identity=None, personal_name=None):
    profile = build_human_description_profile(
        seed,
        eid=eid,
        identity=identity,
        personal_name=personal_name,
    )
    if not profile:
        return None
    color_key = str(profile.get("render_color_key", "")).strip()
    return color_key or None


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
        profile.get("palette_compact", ""),
        profile["hair_compact"],
        profile["standout_compact"],
        profile["demeanor_compact"],
    )
    return ", ".join(str(bit).strip() for bit in bits if str(bit).strip())
