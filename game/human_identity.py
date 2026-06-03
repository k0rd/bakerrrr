import random


_REQUIRED_FIELDS = (
    "assigned_sex",
    "gender_identity",
    "pronoun_set",
    "name_gender_score",
    "gender_inference_source",
)


_NAME_SCORE_OVERRIDES = {
    "ada": 0.9,
    "adri": 0.0,
    "amy": 0.9,
    "ari": 0.0,
    "bea": 0.9,
    "cal": -0.7,
    "dara": 0.7,
    "dax": -0.8,
    "eli": -0.7,
    "ena": 0.8,
    "faye": 0.9,
    "finn": -0.9,
    "gale": 0.0,
    "hana": 0.9,
    "ima": 0.0,
    "iona": 0.9,
    "ira": 0.0,
    "iris": 0.9,
    "ivo": -0.9,
    "jax": -0.9,
    "jules": 0.0,
    "june": 0.9,
    "juno": 0.0,
    "kade": -0.8,
    "kell": 0.0,
    "kira": 0.9,
    "len": 0.0,
    "lena": 0.9,
    "lina": 0.9,
    "mara": 0.9,
    "marek": -0.9,
    "mika": 0.0,
    "milo": -0.9,
    "mira": 0.9,
    "nia": 0.9,
    "nico": 0.0,
    "noah": -0.9,
    "noel": 0.0,
    "nora": 0.9,
    "ona": 0.8,
    "orin": -0.7,
    "pia": 0.8,
    "quin": 0.0,
    "rae": 0.0,
    "remy": 0.0,
    "rhea": 0.9,
    "rina": 0.9,
    "sana": 0.8,
    "tao": -0.2,
    "tess": 0.9,
    "tessa": 0.9,
    "toma": -0.8,
    "uma": 0.8,
    "vera": 0.9,
    "vex": 0.0,
    "wren": 0.0,
    "xena": 0.9,
    "yara": 0.9,
    "zane": -0.9,
}

_FEMININE_SUFFIXES = (
    "elle",
    "ette",
    "ina",
    "lia",
    "ria",
    "ia",
    "ie",
    "a",
    "y",
)
_MASCULINE_SUFFIXES = (
    "ius",
    "ion",
    "ior",
    "ian",
    "ar",
    "en",
    "er",
    "on",
    "or",
    "os",
    "us",
    "o",
)

_PRONOUN_FORMS = {
    "he": {
        "subject": "he",
        "object": "him",
        "possessive_adj": "his",
        "possessive": "his",
        "reflexive": "himself",
        "be": "is",
        "have": "has",
    },
    "she": {
        "subject": "she",
        "object": "her",
        "possessive_adj": "her",
        "possessive": "hers",
        "reflexive": "herself",
        "be": "is",
        "have": "has",
    },
    "they": {
        "subject": "they",
        "object": "them",
        "possessive_adj": "their",
        "possessive": "theirs",
        "reflexive": "themself",
        "be": "are",
        "have": "have",
    },
}
_PRONOUN_ALIASES = {
    "him": "he",
    "his": "he",
    "her": "she",
    "hers": "she",
    "them": "they",
    "their": "they",
    "theirs": "they",
}
_IDENTITY_ALIASES = {
    "male": "man",
    "man": "man",
    "masc": "man",
    "masculine": "man",
    "female": "woman",
    "woman": "woman",
    "femme": "woman",
    "feminine": "woman",
    "neutral": "nonbinary",
    "nb": "nonbinary",
    "nonbinary": "nonbinary",
    "non-binary": "nonbinary",
    "they": "nonbinary",
}
_PRONOUN_DISPLAY = {
    "he": "he/him",
    "she": "she/her",
    "they": "they/them",
}
_PLAYER_PRONOUN_BY_IDENTITY = {
    "man": "he",
    "woman": "she",
    "nonbinary": "they",
}
_PLAYER_ADDRESS_BY_IDENTITY = {
    "man": "sir",
    "woman": "ma'am",
    "nonbinary": "",
}


def _normalize_first_name(personal_name):
    text = " ".join(str(personal_name or "").replace("_", " ").split()).strip()
    if not text:
        return ""
    token = text.split(" ", 1)[0]
    return "".join(ch for ch in token if str(ch).isalpha()).casefold()


def normalize_gender_identity(value, *, default="nonbinary"):
    fallback = str(default or "nonbinary").strip().lower() or "nonbinary"
    fallback = _IDENTITY_ALIASES.get(fallback, fallback)
    if fallback not in {"man", "woman", "nonbinary"}:
        fallback = "nonbinary"
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    normalized = _IDENTITY_ALIASES.get(text, text)
    if normalized not in {"man", "woman", "nonbinary"}:
        return fallback
    return normalized


def is_human_identity(identity):
    if identity is None:
        return False
    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    return taxonomy == "hominid" or creature_type == "human"


def infer_name_gender_score(personal_name):
    token = _normalize_first_name(personal_name)
    if not token:
        return 0.0, "unknown"
    if token in _NAME_SCORE_OVERRIDES:
        return float(_NAME_SCORE_OVERRIDES[token]), "override"
    for suffix in _FEMININE_SUFFIXES:
        if token.endswith(suffix):
            return (0.4 if len(suffix) > 1 else 0.3), "suffix"
    for suffix in _MASCULINE_SUFFIXES:
        if token.endswith(suffix):
            return (-0.4 if len(suffix) > 1 else -0.3), "suffix"
    return 0.0, "unknown"


def resolve_pronoun_set(value=None, *, default="they", personal_name=None, seed_token=None):
    default_key = str(default or "they").strip().lower() or "they"
    if default_key not in _PRONOUN_FORMS:
        default_key = "they"

    raw_value = value
    if raw_value is not None and hasattr(raw_value, "pronoun_set"):
        raw_pronoun = str(getattr(raw_value, "pronoun_set", "") or "").strip().lower()
        if raw_pronoun:
            raw_value = raw_pronoun
        elif is_human_identity(raw_value):
            resolved_name = str(personal_name or getattr(raw_value, "personal_name", "") or "").strip()
            if resolved_name:
                preview = seed_human_identity_profile(seed_token or resolved_name, resolved_name)
                raw_value = str(preview.get("pronoun_set", "") or "").strip().lower()
            else:
                raw_value = ""

    text = str(raw_value or "").strip().lower()
    if text in _PRONOUN_FORMS:
        return text
    if text in _PRONOUN_ALIASES:
        return _PRONOUN_ALIASES[text]
    if text in {"nb", "nonbinary", "non-binary"}:
        return "they"
    if text == "woman":
        return "she"
    if text == "man":
        return "he"
    if not text and personal_name:
        preview = seed_human_identity_profile(seed_token or personal_name, personal_name)
        guessed = str(preview.get("pronoun_set", "") or "").strip().lower()
        if guessed in _PRONOUN_FORMS:
            return guessed
    return default_key


def pronoun_display_text(value=None, *, default="they", personal_name=None, seed_token=None):
    pronoun_key = resolve_pronoun_set(
        value,
        default=default,
        personal_name=personal_name,
        seed_token=seed_token,
    )
    return str(_PRONOUN_DISPLAY.get(pronoun_key, _PRONOUN_DISPLAY["they"]))


def pronoun_forms(value=None, *, default="they", personal_name=None, seed_token=None):
    pronoun_key = resolve_pronoun_set(
        value,
        default=default,
        personal_name=personal_name,
        seed_token=seed_token,
    )
    return dict(_PRONOUN_FORMS.get(pronoun_key, _PRONOUN_FORMS["they"]))


def pronoun_format_slots(value=None, *, prefix="person", default="they", personal_name=None, seed_token=None):
    forms = pronoun_forms(
        value,
        default=default,
        personal_name=personal_name,
        seed_token=seed_token,
    )
    pronoun_key = resolve_pronoun_set(
        value,
        default=default,
        personal_name=personal_name,
        seed_token=seed_token,
    )
    slots = {
        f"{prefix}_set": pronoun_key,
    }
    for key, resolved in forms.items():
        slots[f"{prefix}_{key}"] = resolved
        slots[f"{prefix}_{key}_cap"] = resolved[:1].upper() + resolved[1:] if resolved else ""
    return slots


def conjugate_present(value=None, verb="", *, default="they", personal_name=None, seed_token=None):
    verb_text = str(verb or "").strip().lower()
    if not verb_text:
        return ""
    if verb_text == "be":
        return pronoun_forms(
            value,
            default=default,
            personal_name=personal_name,
            seed_token=seed_token,
        ).get("be", "are")
    if verb_text == "have":
        return pronoun_forms(
            value,
            default=default,
            personal_name=personal_name,
            seed_token=seed_token,
        ).get("have", "have")
    pronoun_key = resolve_pronoun_set(
        value,
        default=default,
        personal_name=personal_name,
        seed_token=seed_token,
    )
    if pronoun_key == "they":
        return verb_text
    if verb_text.endswith("y") and len(verb_text) > 1 and verb_text[-2] not in "aeiou":
        return f"{verb_text[:-1]}ies"
    if verb_text.endswith(("s", "sh", "ch", "x", "z", "o")):
        return f"{verb_text}es"
    return f"{verb_text}s"


def seed_human_identity_profile(seed_token, personal_name):
    score, source = infer_name_gender_score(personal_name)
    rng = random.Random(f"{seed_token}|human_identity|{personal_name or ''}")
    female_probability = max(0.08, min(0.92, 0.5 + (0.4 * float(score))))
    assigned_sex = "female" if rng.random() < female_probability else "male"
    roll = rng.random()
    if assigned_sex == "female":
        if roll < 0.96:
            gender_identity = "woman"
            pronoun_set = "she"
        elif roll < 0.98:
            gender_identity = "man"
            pronoun_set = "he"
        else:
            gender_identity = "nonbinary"
            pronoun_set = "they"
    else:
        if roll < 0.96:
            gender_identity = "man"
            pronoun_set = "he"
        elif roll < 0.98:
            gender_identity = "woman"
            pronoun_set = "she"
        else:
            gender_identity = "nonbinary"
            pronoun_set = "they"
    return {
        "assigned_sex": assigned_sex,
        "gender_identity": gender_identity,
        "pronoun_set": pronoun_set,
        "name_gender_score": float(score),
        "gender_inference_source": source,
    }


def seed_player_identity_profile(seed_token, gender_identity):
    normalized_identity = normalize_gender_identity(gender_identity, default="nonbinary")
    rng = random.Random(f"{seed_token}|player_identity|assigned_sex")
    assigned_sex = "female" if rng.random() < 0.5 else "male"
    return {
        "assigned_sex": assigned_sex,
        "gender_identity": normalized_identity,
        "pronoun_set": _PLAYER_PRONOUN_BY_IDENTITY.get(normalized_identity, "they"),
        "name_gender_score": None,
        "gender_inference_source": None,
    }


def player_address_term(value=None, *, default="nonbinary"):
    identity = normalize_gender_identity(
        getattr(value, "gender_identity", value),
        default=default,
    )
    return str(_PLAYER_ADDRESS_BY_IDENTITY.get(identity, "") or "")


def apply_human_identity_profile(identity, profile, *, force=False):
    if identity is None or not isinstance(profile, dict):
        return identity
    for field in _REQUIRED_FIELDS:
        if force or getattr(identity, field, None) is None:
            setattr(identity, field, profile.get(field))
    return identity


def identity_debug_summary(identity, *, personal_name=None, seed_token=None):
    if not is_human_identity(identity):
        return None
    stored_ready = all(getattr(identity, field, None) is not None for field in _REQUIRED_FIELDS)
    if stored_ready:
        return {
            "mode": "stored",
            "assigned_sex": str(getattr(identity, "assigned_sex", "") or "").strip().lower() or None,
            "gender_identity": str(getattr(identity, "gender_identity", "") or "").strip().lower() or None,
            "pronoun_set": str(getattr(identity, "pronoun_set", "") or "").strip().lower() or None,
            "name_gender_score": float(getattr(identity, "name_gender_score", 0.0) or 0.0),
            "gender_inference_source": str(getattr(identity, "gender_inference_source", "") or "").strip().lower() or "unknown",
        }
    resolved_name = str(personal_name or getattr(identity, "personal_name", "") or "").strip()
    if not resolved_name:
        return {
            "mode": "unavailable",
            "assigned_sex": None,
            "gender_identity": None,
            "pronoun_set": None,
            "name_gender_score": 0.0,
            "gender_inference_source": "unknown",
        }
    preview = seed_human_identity_profile(seed_token or resolved_name, resolved_name)
    preview["mode"] = "preview"
    return preview
