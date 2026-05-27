import json
import random
from pathlib import Path

from game.content_warnings import warn_content_fallback
from game.npc_names import CATALOG as NPC_NAME_CATALOG, random_human_last_name


ORG_NAME_DATA_PATH = Path(__file__).resolve().parent / "org_names.json"
BUSINESS_NAME_DATA_PATH = Path(__file__).resolve().parent / "business_names.json"


DEFAULT_ORG_NAME_CATALOG = {
    "shared": {
        "roots": (
            "Anchor",
            "Beacon",
            "Cinder",
            "Crown",
            "Signal",
            "Spire",
            "Union",
            "Vertex",
        ),
        "colors": (
            "Black",
            "Blue",
            "Copper",
            "Ember",
            "Gray",
            "Iron",
            "Neon",
            "Red",
            "Rust",
            "Silver",
        ),
        "symbols": (
            "Anchors",
            "Blades",
            "Ghosts",
            "Hands",
            "Kings",
            "Saints",
            "Shadows",
            "Vultures",
        ),
    },
    "gang": {
        "collectives": (
            "Crew",
            "Set",
            "Outfit",
            "Ring",
            "Hands",
            "Boys",
            "Line",
        ),
        "templates": (
            "{street} {collective}",
            "The {street} {collective}",
            "{settlement} {collective}",
            "{surname} {collective}",
            "{color} {symbol}",
        ),
    },
    "corporate": {
        "generic_suffixes": (
            "Group",
            "Holdings",
            "Systems",
            "Industries",
            "Partners",
            "Collective",
        ),
        "domains": {
            "logistics": ("Logistics", "Freight", "Haulage", "Distribution"),
            "finance": ("Capital", "Trust", "Credit", "Holdings"),
            "security": ("Security", "Protective", "Response", "Risk"),
            "media": ("Media", "Signal", "Broadcast", "Studios"),
            "biotech": ("Biotech", "Life Systems", "Vital Labs", "Genetics"),
            "retail": ("Markets", "Supply", "Exchange", "Stores"),
            "hospitality": ("Hospitality", "Suites", "Leisure", "Ventures"),
            "technology": ("Systems", "Networks", "Dynamics", "Informatics"),
        },
        "templates": (
            "{surname} {domain}",
            "{root} {domain}",
            "{settlement} {domain}",
            "{surname} & {surname2} {domain}",
            "{root} {generic_suffix}",
        ),
    },
}
DEFAULT_STREET_TERMS = (
    "Dockside",
    "Market",
    "Northside",
    "Railyard",
    "Signal",
    "Southside",
    "Underpass",
)


def _text(value):
    return str(value or "").strip()


def _string_list(raw, fallback):
    if not isinstance(raw, (list, tuple)):
        raw = fallback
    values = [str(item).strip() for item in raw if str(item).strip()]
    if not values:
        values = [str(item).strip() for item in fallback if str(item).strip()]
    return tuple(values)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        warn_content_fallback(path, "built-in organization naming defaults", exc=exc)
    return None


def load_org_name_catalog(path=ORG_NAME_DATA_PATH):
    raw = _read_json(path)
    if raw is not None and not isinstance(raw, dict):
        warn_content_fallback(path, "built-in organization naming defaults", problem="top-level JSON must be an object")
        raw = None
    if not isinstance(raw, dict):
        raw = {}

    shared_raw = raw.get("shared") if isinstance(raw.get("shared"), dict) else {}
    gang_raw = raw.get("gang") if isinstance(raw.get("gang"), dict) else {}
    corporate_raw = raw.get("corporate") if isinstance(raw.get("corporate"), dict) else {}
    corporate_domains_raw = corporate_raw.get("domains") if isinstance(corporate_raw.get("domains"), dict) else {}

    fallback = DEFAULT_ORG_NAME_CATALOG
    corporate_domains = {}
    for key, values in fallback["corporate"]["domains"].items():
        corporate_domains[str(key).strip().lower()] = _string_list(corporate_domains_raw.get(key), values)

    return {
        "shared": {
            "roots": _string_list(shared_raw.get("roots"), fallback["shared"]["roots"]),
            "colors": _string_list(shared_raw.get("colors"), fallback["shared"]["colors"]),
            "symbols": _string_list(shared_raw.get("symbols"), fallback["shared"]["symbols"]),
        },
        "gang": {
            "collectives": _string_list(gang_raw.get("collectives"), fallback["gang"]["collectives"]),
            "templates": _string_list(gang_raw.get("templates"), fallback["gang"]["templates"]),
        },
        "corporate": {
            "generic_suffixes": _string_list(
                corporate_raw.get("generic_suffixes"),
                fallback["corporate"]["generic_suffixes"],
            ),
            "domains": corporate_domains,
            "templates": _string_list(corporate_raw.get("templates"), fallback["corporate"]["templates"]),
        },
    }


def load_business_street_terms(path=BUSINESS_NAME_DATA_PATH):
    raw = _read_json(path)
    if raw is not None and not isinstance(raw, dict):
        warn_content_fallback(path, "built-in street-term defaults", problem="top-level JSON must be an object")
        raw = None
    if not isinstance(raw, dict):
        raw = {}
    return _string_list(raw.get("street_terms"), DEFAULT_STREET_TERMS)


CATALOG = load_org_name_catalog()
STREET_TERMS = load_business_street_terms()


def _display_token(value, fallback="Metro"):
    raw = _text(value)
    if not raw:
        return fallback
    if raw.islower():
        raw = raw.replace("_", " ").title()
    return " ".join(raw.replace("_", " ").split()) or fallback


def _corporate_domain_pool(catalog, domain_key=None):
    corporate = catalog.get("corporate", {}) if isinstance(catalog, dict) else {}
    domains = corporate.get("domains", {}) if isinstance(corporate.get("domains"), dict) else {}
    normalized_key = _text(domain_key).lower().replace(" ", "_")
    if normalized_key and normalized_key in domains:
        return tuple(domains.get(normalized_key, ()))
    merged = []
    for values in domains.values():
        for value in values or ():
            if value and value not in merged:
                merged.append(value)
    return tuple(merged or DEFAULT_ORG_NAME_CATALOG["corporate"]["domains"]["logistics"])


def _distinct_surnames(rng, catalog=None):
    first = random_human_last_name(rng, catalog=catalog)
    second = first
    for _ in range(8):
        second = random_human_last_name(rng, catalog=catalog)
        if second != first:
            break
    return first, second


def generate_organization_name(
    *,
    world_seed,
    organization_key,
    style,
    settlement_name="",
    region_name="",
    domain_key=None,
    catalog=None,
    street_terms=None,
    npc_catalog=None,
):
    style = _text(style).lower().replace(" ", "_")
    if style not in {"gang", "corporate"}:
        return None

    catalog = catalog if isinstance(catalog, dict) else CATALOG
    street_terms = tuple(street_terms or STREET_TERMS)
    npc_catalog = npc_catalog if isinstance(npc_catalog, dict) else NPC_NAME_CATALOG
    scope_name = _display_token(settlement_name or region_name, fallback="Metro")
    region_name = _display_token(region_name or settlement_name, fallback=scope_name)
    rng = random.Random(f"{world_seed}:org_name:{_text(organization_key)}:{style}")
    surname, surname2 = _distinct_surnames(rng, catalog=npc_catalog)

    if style == "gang":
        gang = catalog.get("gang", {})
        shared = catalog.get("shared", {})
        template = rng.choice(tuple(gang.get("templates", ())) or DEFAULT_ORG_NAME_CATALOG["gang"]["templates"])
        values = {
            "street": _display_token(rng.choice(tuple(street_terms) or DEFAULT_STREET_TERMS), fallback=scope_name),
            "settlement": scope_name,
            "region": region_name,
            "surname": _display_token(surname, fallback="Ward"),
            "surname2": _display_token(surname2, fallback="West"),
            "color": _display_token(
                rng.choice(tuple(shared.get("colors", ())) or DEFAULT_ORG_NAME_CATALOG["shared"]["colors"]),
                fallback="Red",
            ),
            "symbol": _display_token(
                rng.choice(tuple(shared.get("symbols", ())) or DEFAULT_ORG_NAME_CATALOG["shared"]["symbols"]),
                fallback="Hands",
            ),
            "collective": _display_token(
                rng.choice(tuple(gang.get("collectives", ())) or DEFAULT_ORG_NAME_CATALOG["gang"]["collectives"]),
                fallback="Crew",
            ),
        }
        return template.format(**values).strip()

    corporate = catalog.get("corporate", {})
    shared = catalog.get("shared", {})
    template = rng.choice(tuple(corporate.get("templates", ())) or DEFAULT_ORG_NAME_CATALOG["corporate"]["templates"])
    values = {
        "settlement": scope_name,
        "region": region_name,
        "surname": _display_token(surname, fallback="Mercer"),
        "surname2": _display_token(surname2, fallback="West"),
        "root": _display_token(
            rng.choice(tuple(shared.get("roots", ())) or DEFAULT_ORG_NAME_CATALOG["shared"]["roots"]),
            fallback="Anchor",
        ),
        "generic_suffix": _display_token(
            rng.choice(
                tuple(corporate.get("generic_suffixes", ()))
                or DEFAULT_ORG_NAME_CATALOG["corporate"]["generic_suffixes"]
            ),
            fallback="Holdings",
        ),
        "domain": _display_token(
            rng.choice(_corporate_domain_pool(catalog, domain_key=domain_key)),
            fallback="Logistics",
        ),
    }
    return template.format(**values).strip()
