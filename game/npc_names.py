import json
from pathlib import Path

from game.content_warnings import warn_content_fallback
from game.components import CreatureIdentity


NPC_NAMES_PATH = Path(__file__).resolve().parent / "npc_names.json"


DEFAULT_NAME_CATALOG = {
    "human": {
        "first_names": (
            "Ada", "Adri", "Bea", "Cal", "Dara", "Dax", "Eli", "Ena", "Faye", "Finn",
            "Gale", "Hana", "Ira", "Jax", "Juno", "Kade", "Kira", "Lena", "Mara", "Milo",
            "Nia", "Noel", "Ona", "Orin", "Pia", "Quin", "Rae", "Remy", "Sana", "Tao",
            "Tess", "Uma", "Vera", "Wren", "Xena", "Yara", "Zane",
        ),
        "last_names": (
            "Alder", "Barrow", "Bennett", "Black", "Briar", "Calder", "Cross", "Darrow", "Dunn",
            "Eames", "Fletcher", "Frost", "Gage", "Hale", "Harrow", "Hawk", "Hayes", "Iverson",
            "Keene", "Kerr", "Lang", "Lowe", "Maddox", "Marlow", "Mercer", "Nash", "North",
            "Ortega", "Pike", "Quill", "Renn", "Rhodes", "Rook", "Sable", "Sawyer", "Sloan",
            "Stone", "Thorne", "Vale", "Voss", "Ward", "West", "Wilder", "Wynn",
        ),
    },
}


def _string_list(raw, fallback):
    if not isinstance(raw, (list, tuple)):
        raw = fallback
    values = [str(item).strip() for item in raw if str(item).strip()]
    if not values:
        values = [str(item).strip() for item in fallback if str(item).strip()]
    return tuple(values)


def load_npc_name_catalog(path=NPC_NAMES_PATH):
    raw = None
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        warn_content_fallback(path, "built-in NPC name defaults", exc=exc)
        raw = None

    if raw is not None and not isinstance(raw, dict):
        warn_content_fallback(path, "built-in NPC name defaults", problem="top-level JSON must be an object")
    if not isinstance(raw, dict):
        raw = {}

    human = raw.get("human") if isinstance(raw.get("human"), dict) else {}
    fallback = DEFAULT_NAME_CATALOG["human"]
    return {
        "human": {
            "first_names": _string_list(human.get("first_names"), fallback["first_names"]),
            "last_names": _string_list(human.get("last_names"), fallback["last_names"]),
        },
    }


CATALOG = load_npc_name_catalog()


def _normalize_name(value):
    return " ".join(str(value or "").replace("_", " ").split()).strip()


def human_descriptor(role=None, career=None):
    role_label = _normalize_name(role).lower()
    if role_label in {"thief", "drunk"}:
        return role_label
    label = _normalize_name(career or role or "resident").lower()
    return label or "resident"


def _human_name_pool(catalog=None):
    source = catalog if isinstance(catalog, dict) else CATALOG
    human = source.get("human", {}) if isinstance(source, dict) else {}
    fallback = DEFAULT_NAME_CATALOG["human"]
    first_names = _string_list(human.get("first_names"), fallback["first_names"])
    last_names = _string_list(human.get("last_names"), fallback["last_names"])
    return first_names, last_names


def _existing_personal_names(sim):
    names = set()
    identities = sim.ecs.get(CreatureIdentity)
    for identity in identities.values():
        if not identity:
            continue
        personal_name = _normalize_name(getattr(identity, "personal_name", None))
        if personal_name:
            names.add(personal_name.lower())
    return names


def random_human_last_name(rng, catalog=None):
    _, last_names = _human_name_pool(catalog=catalog)
    return rng.choice(last_names)


def generate_human_personal_name(sim, rng, surname=None, avoid_names=None, catalog=None):
    first_names, last_names = _human_name_pool(catalog=catalog)
    fixed_surname = _normalize_name(surname)
    surname_pool = (fixed_surname,) if fixed_surname else last_names

    reserved = _existing_personal_names(sim)
    for item in avoid_names or ():
        normalized = _normalize_name(item)
        if normalized:
            reserved.add(normalized.lower())

    for _ in range(max(24, len(first_names) * 2)):
        candidate = f"{rng.choice(first_names)} {rng.choice(surname_pool)}"
        if candidate.lower() not in reserved:
            return candidate

    for first in first_names:
        for last in surname_pool:
            candidate = f"{first} {last}"
            if candidate.lower() not in reserved:
                return candidate

    return f"{first_names[0]} {surname_pool[0]}"


def generate_human_household_names(sim, rng, count, surname=None, avoid_names=None, catalog=None):
    count = max(0, int(count))
    if count <= 0:
        return ()

    shared_surname = _normalize_name(surname) or random_human_last_name(rng, catalog=catalog)
    reserved = {_normalize_name(name) for name in (avoid_names or ()) if _normalize_name(name)}
    names = []
    for _ in range(count):
        name = generate_human_personal_name(
            sim,
            rng,
            surname=shared_surname,
            avoid_names=reserved.union(names),
            catalog=catalog,
        )
        names.append(name)
    return tuple(names)
