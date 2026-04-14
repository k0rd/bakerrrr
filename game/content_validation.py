from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GAME_DIR = Path(__file__).resolve().parent

ITEMS_PATH = GAME_DIR / "items.json"
LOOT_TABLES_PATH = GAME_DIR / "loot_tables.json"
WEAPONS_PATH = GAME_DIR / "weapons.json"
OFFENSE_PROFILE_PATH = GAME_DIR / "offense_profile.json"
BUSINESS_NAMES_PATH = GAME_DIR / "business_names.json"
FIXTURES_PATH = GAME_DIR / "fixtures.json"
VEHICLES_PATH = GAME_DIR / "vehicles.json"
NPC_NAMES_PATH = GAME_DIR / "npc_names.json"
TILE_MAP_PATH = REPO_ROOT / "assets" / "tiles" / "tile_map.json"

ALLOWED_ITEM_EFFECTS = {"modify_need", "restore_hp", "status", "credits", "add_ammo"}
ALLOWED_ITEM_NEEDS = {"energy", "safety", "social"}
ALLOWED_LEGAL_STATUS = {"legal", "restricted", "illegal"}
ALLOWED_WEAPON_TRAJECTORIES = {"ballistic", "lobbed", "beam"}
ALLOWED_FIXTURE_KINDS = {"fixture", "asset"}
ALLOWED_FIXTURE_COVER = {"none", "low", "full"}
ALLOWED_FIXTURE_BUCKETS = {"path_side", "path_tile", "entry_side", "street_side", "edge", "open"}
ALLOWED_LIGHT_PHASES = {"dawn", "day", "dusk", "night"}
IDENTIFIER_RE = re.compile(r"^[a-z0-9_]+$")
RESERVED_GLYPH_POLICIES = {
    "+": {
        "allowed_semantics": {"feature_door"},
        "meaning": "door",
    },
    '"': {
        "allowed_semantics": {"feature_window"},
        "meaning": "window",
    },
    "~": {
        "allowed_semantics": {"terrain_water"},
        "meaning": "liquid",
    },
}


class TrackedDict(dict):
    def __init__(self, pairs):
        super().__init__()
        self.duplicate_keys = []
        for key, value in pairs:
            if key in self:
                self.duplicate_keys.append(key)
            self[key] = value


@dataclass
class ValidationIssue:
    severity: str
    source: str
    path: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    files_checked: set[str] = field(default_factory=set)

    def add(self, severity, source, path, message):
        self.files_checked.add(str(source))
        self.issues.append(
            ValidationIssue(
                severity=str(severity),
                source=str(source),
                path=_format_path(path),
                message=str(message),
            )
        )

    def error(self, source, path, message):
        self.add("error", source, path, message)

    def warn(self, source, path, message):
        self.add("warning", source, path, message)

    def extend(self, other):
        if not isinstance(other, ValidationReport):
            return
        self.files_checked.update(other.files_checked)
        self.issues.extend(other.issues)

    @property
    def errors(self):
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self):
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def error_count(self):
        return len(self.errors)

    @property
    def warning_count(self):
        return len(self.warnings)

    @property
    def ok(self):
        return self.error_count == 0


def _rel_path(path):
    path = Path(path)
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _format_path(parts):
    if isinstance(parts, str):
        return parts

    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
            continue

        label = str(part)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", label):
            path += f".{label}"
        else:
            path += f"[{json.dumps(label)}]"
    return path


def format_issue(issue):
    return f"{issue.severity.upper()} {issue.source} {issue.path}: {issue.message}"


def _is_bool(value):
    return isinstance(value, bool)


def _is_int(value):
    return isinstance(value, int) and not _is_bool(value)


def _is_number(value):
    return (isinstance(value, int) or isinstance(value, float)) and not _is_bool(value)


def _collect_duplicate_keys(node, path=None):
    if path is None:
        path = []

    duplicates = []
    if isinstance(node, TrackedDict):
        for key in node.duplicate_keys:
            duplicates.append((list(path), key))
        for key, value in node.items():
            duplicates.extend(_collect_duplicate_keys(value, path + [key]))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            duplicates.extend(_collect_duplicate_keys(value, path + [index]))
    return duplicates


def _load_json_file(path, report):
    source = _rel_path(path)
    report.files_checked.add(source)

    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        report.error(source, [], "file is missing")
        return None
    except OSError as exc:
        report.error(source, [], f"could not read file: {exc}")
        return None

    try:
        data = json.loads(text, object_pairs_hook=TrackedDict)
    except json.JSONDecodeError as exc:
        report.error(
            source,
            [],
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
        )
        return None

    for dup_path, key in _collect_duplicate_keys(data):
        report.error(source, dup_path, f"duplicate key {key!r}")

    return data


def _expect_type(report, source, path, value, expected_type, description):
    if not isinstance(value, expected_type):
        report.error(source, path, f"expected {description}")
        return False
    return True


def _validate_reserved_glyph_literal(report, source, path, value, *, owner_label="content"):
    glyph = str(value or "")[:1]
    policy = RESERVED_GLYPH_POLICIES.get(glyph)
    if policy is None:
        return
    meaning = str(policy["meaning"])
    report.error(
        source,
        path,
        f"glyph {glyph!r} is reserved for {meaning} semantics and cannot be used by {owner_label}",
    )


def _warn_if_duplicates(report, source, path, values, *, label="value"):
    seen = set()
    for value in values:
        token = str(value)
        if token in seen:
            report.warn(source, path, f"duplicate {label} {token!r}")
            return
        seen.add(token)


def _validate_non_empty_string(report, source, path, value, *, field_name="value"):
    if not isinstance(value, str):
        report.error(source, path, f"{field_name} must be a string")
        return False
    if not value.strip():
        report.error(source, path, f"{field_name} must not be blank")
        return False
    return True


def _validate_identifier(report, source, path, value, *, field_name="id"):
    if not _validate_non_empty_string(report, source, path, value, field_name=field_name):
        return False
    if not IDENTIFIER_RE.match(str(value).strip()):
        report.warn(source, path, f"{field_name} should stay lowercase snake_case for stable references")
    return True


def _validate_string_list(report, source, path, value, *, field_name="list", allow_scalar=False, require_non_empty=False):
    if allow_scalar and isinstance(value, str):
        values = [value]
    else:
        if not isinstance(value, list):
            report.error(source, path, f"{field_name} must be a list")
            return []
        values = list(value)

    parsed = []
    for index, item in enumerate(values):
        entry_path = path + [index]
        if not _validate_non_empty_string(report, source, entry_path, item, field_name="entry"):
            continue
        parsed.append(str(item).strip())

    if require_non_empty and not parsed:
        report.error(source, path, f"{field_name} must contain at least one entry")

    _warn_if_duplicates(report, source, path, parsed, label="entry")
    return parsed


def _validate_int(report, source, path, value, *, minimum=None, maximum=None, field_name="value"):
    if not _is_int(value):
        report.error(source, path, f"{field_name} must be an integer")
        return False
    if minimum is not None and value < minimum:
        report.error(source, path, f"{field_name} must be >= {minimum}")
        return False
    if maximum is not None and value > maximum:
        report.error(source, path, f"{field_name} must be <= {maximum}")
        return False
    return True


def _validate_number(report, source, path, value, *, minimum=None, maximum=None, field_name="value"):
    if not _is_number(value):
        report.error(source, path, f"{field_name} must be numeric")
        return False
    if minimum is not None and value < minimum:
        report.error(source, path, f"{field_name} must be >= {minimum}")
        return False
    if maximum is not None and value > maximum:
        report.error(source, path, f"{field_name} must be <= {maximum}")
        return False
    return True


def _validate_int_pair(report, source, path, value, *, minimum=None, maximum=None, allow_negative=False, field_name="range"):
    if not isinstance(value, list) or len(value) != 2:
        report.error(source, path, f"{field_name} must be a two-item integer list")
        return False

    local_min = minimum if minimum is not None else (None if allow_negative else 0)
    if not _validate_int(report, source, path + [0], value[0], minimum=local_min, maximum=maximum, field_name="minimum"):
        return False
    if not _validate_int(report, source, path + [1], value[1], minimum=value[0], maximum=maximum, field_name="maximum"):
        return False
    return True


def _validate_float_pair(report, source, path, value, *, minimum=None, maximum=None, field_name="range"):
    if not isinstance(value, list) or len(value) != 2:
        report.error(source, path, f"{field_name} must be a two-item numeric list")
        return False

    if not _validate_number(report, source, path + [0], value[0], minimum=minimum, maximum=maximum, field_name="minimum"):
        return False
    if not _validate_number(report, source, path + [1], value[1], minimum=value[0], maximum=maximum, field_name="maximum"):
        return False
    return True


def _validate_items(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return set()
    if not _expect_type(report, source, [], data, dict, "an object keyed by item id"):
        return set()

    item_ids = set()
    for item_id, item in data.items():
        item_path = [item_id]
        if not _validate_identifier(report, source, item_path, item_id, field_name="item id"):
            continue
        item_ids.add(str(item_id))

        if not _expect_type(report, source, item_path, item, dict, "an object"):
            continue

        if "name" in item:
            _validate_non_empty_string(report, source, item_path + ["name"], item["name"], field_name="name")

        if "glyph" in item:
            if _validate_non_empty_string(report, source, item_path + ["glyph"], item["glyph"], field_name="glyph"):
                if len(str(item["glyph"])) > 1:
                    report.warn(source, item_path + ["glyph"], "glyph will be truncated to the first character at runtime")
                _validate_reserved_glyph_literal(report, source, item_path + ["glyph"], item["glyph"], owner_label="items")

        if "stack_max" in item:
            _validate_int(report, source, item_path + ["stack_max"], item["stack_max"], minimum=1, field_name="stack_max")

        if "tags" in item:
            _validate_string_list(report, source, item_path + ["tags"], item["tags"], field_name="tags")

        if "legal_status" in item:
            if _validate_non_empty_string(report, source, item_path + ["legal_status"], item["legal_status"], field_name="legal_status"):
                status = str(item["legal_status"]).strip().lower()
                if status not in ALLOWED_LEGAL_STATUS:
                    report.error(source, item_path + ["legal_status"], f"legal_status must be one of {sorted(ALLOWED_LEGAL_STATUS)}")

        if "effects" in item:
            effects = item["effects"]
            if not isinstance(effects, list):
                report.error(source, item_path + ["effects"], "effects must be a list")
            else:
                for index, effect in enumerate(effects):
                    effect_path = item_path + ["effects", index]
                    if not _expect_type(report, source, effect_path, effect, dict, "an object"):
                        continue
                    effect_type = effect.get("type")
                    if not _validate_non_empty_string(report, source, effect_path + ["type"], effect_type, field_name="type"):
                        continue
                    effect_type = str(effect_type).strip().lower()
                    if effect_type not in ALLOWED_ITEM_EFFECTS:
                        report.error(source, effect_path + ["type"], f"unknown effect type {effect_type!r}")
                        continue
                    if effect_type == "modify_need":
                        need = effect.get("need")
                        if _validate_non_empty_string(report, source, effect_path + ["need"], need, field_name="need"):
                            if str(need).strip().lower() not in ALLOWED_ITEM_NEEDS:
                                report.error(source, effect_path + ["need"], f"need must be one of {sorted(ALLOWED_ITEM_NEEDS)}")
                        if "delta" not in effect:
                            report.error(source, effect_path, "modify_need effect requires delta")
                        else:
                            _validate_number(report, source, effect_path + ["delta"], effect["delta"], field_name="delta")
                    elif effect_type == "restore_hp":
                        if "delta" not in effect:
                            report.error(source, effect_path, "restore_hp effect requires delta")
                        else:
                            _validate_int(
                                report,
                                source,
                                effect_path + ["delta"],
                                effect["delta"],
                                minimum=1,
                                field_name="delta",
                            )
                    elif effect_type == "status":
                        _validate_non_empty_string(report, source, effect_path + ["status"], effect.get("status"), field_name="status")
                        if "duration" not in effect:
                            report.error(source, effect_path, "status effect requires duration")
                        else:
                            _validate_int(report, source, effect_path + ["duration"], effect["duration"], minimum=1, field_name="duration")
                        modifiers = effect.get("modifiers", {})
                        if modifiers is not None:
                            if not isinstance(modifiers, dict):
                                report.error(source, effect_path + ["modifiers"], "modifiers must be an object")
                            else:
                                for modifier_key, modifier_value in modifiers.items():
                                    _validate_number(
                                        report,
                                        source,
                                        effect_path + ["modifiers", modifier_key],
                                        modifier_value,
                                        field_name="modifier value",
                                    )
                    elif effect_type == "credits":
                        if "delta" not in effect:
                            report.error(source, effect_path, "credits effect requires delta")
                        else:
                            _validate_int(report, source, effect_path + ["delta"], effect["delta"], field_name="delta")
                    elif effect_type == "add_ammo":
                        if "amount" not in effect:
                            report.error(source, effect_path, "add_ammo effect requires amount")
                        else:
                            _validate_int(
                                report,
                                source,
                                effect_path + ["amount"],
                                effect["amount"],
                                minimum=1,
                                field_name="amount",
                            )
                        if "weapon_tags" in effect:
                            _validate_string_list(
                                report,
                                source,
                                effect_path + ["weapon_tags"],
                                effect.get("weapon_tags"),
                                field_name="weapon_tags",
                                allow_scalar=False,
                            )
                        if "weapon_ids" in effect:
                            _validate_string_list(
                                report,
                                source,
                                effect_path + ["weapon_ids"],
                                effect.get("weapon_ids"),
                                field_name="weapon_ids",
                                allow_scalar=False,
                            )

        if "tool_profiles" in item:
            raw_profiles = item["tool_profiles"]
            if isinstance(raw_profiles, dict):
                raw_profiles = [raw_profiles]
            if not isinstance(raw_profiles, list):
                report.error(source, item_path + ["tool_profiles"], "tool_profiles must be a list or object")
            else:
                for index, profile in enumerate(raw_profiles):
                    profile_path = item_path + ["tool_profiles", index]
                    if not _expect_type(report, source, profile_path, profile, dict, "an object"):
                        continue
                    contexts = _validate_string_list(
                        report,
                        source,
                        profile_path + ["contexts"],
                        profile.get("contexts"),
                        field_name="contexts",
                        allow_scalar=True,
                        require_non_empty=True,
                    )
                    if not contexts:
                        report.error(source, profile_path + ["contexts"], "tool profile must define at least one context")
                    if "enable_contexts" in profile:
                        _validate_string_list(
                            report,
                            source,
                            profile_path + ["enable_contexts"],
                            profile.get("enable_contexts"),
                            field_name="enable_contexts",
                            allow_scalar=True,
                        )
                    for key in ("intrusion_bonus", "mechanics_bonus", "perception_bonus", "score_bonus", "requirement_delta"):
                        if key in profile:
                            _validate_number(report, source, profile_path + [key], profile[key], field_name=key)

        if "disguise" in item:
            disguise = item["disguise"]
            if not _expect_type(report, source, item_path + ["disguise"], disguise, dict, "an object"):
                continue
            if "role_id" not in disguise:
                report.error(source, item_path + ["disguise"], "disguise profile requires role_id")
            else:
                _validate_non_empty_string(
                    report,
                    source,
                    item_path + ["disguise", "role_id"],
                    disguise["role_id"],
                    field_name="role_id",
                )
            if "strength" not in disguise:
                report.error(source, item_path + ["disguise"], "disguise profile requires strength")
            else:
                _validate_number(
                    report,
                    source,
                    item_path + ["disguise", "strength"],
                    disguise["strength"],
                    minimum=0.01,
                    field_name="strength",
                )

        if "container" in item:
            container = item["container"]
            if not _expect_type(report, source, item_path + ["container"], container, dict, "an object"):
                continue
            if "bonus_slots" not in container:
                report.error(source, item_path + ["container"], "container profile requires bonus_slots")
            else:
                _validate_int(
                    report,
                    source,
                    item_path + ["container", "bonus_slots"],
                    container["bonus_slots"],
                    minimum=1,
                    field_name="bonus_slots",
                )

    if not item_ids:
        report.error(source, [], "item catalog must contain at least one valid item")
    return item_ids


def _validate_loot_tables(path, item_ids, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "an object keyed by loot table id"):
        return

    if "default" not in data:
        report.error(source, [], "loot tables must define a default table")

    for table_key, entries in data.items():
        table_path = [table_key]
        if not _validate_non_empty_string(report, source, table_path, table_key, field_name="table key"):
            continue
        if table_key != "default" and not (
            str(table_key).startswith("kind:") or str(table_key).startswith("archetype:")
        ):
            report.warn(source, table_path, "table key does not follow default/kind:/archetype: conventions")

        if not isinstance(entries, list):
            report.error(source, table_path, "loot table entries must be a list")
            continue
        if not entries:
            report.error(source, table_path, "loot table must contain at least one entry")
            continue

        for index, entry in enumerate(entries):
            entry_path = table_path + [index]
            if not _expect_type(report, source, entry_path, entry, dict, "an object"):
                continue
            item_id = entry.get("item_id")
            if _validate_identifier(report, source, entry_path + ["item_id"], item_id, field_name="item_id"):
                if str(item_id) not in item_ids:
                    report.error(source, entry_path + ["item_id"], f"unknown item reference {item_id!r}")
            if "weight" not in entry:
                report.warn(source, entry_path, "weight is omitted and will default to 1")
            else:
                _validate_int(report, source, entry_path + ["weight"], entry["weight"], minimum=1, field_name="weight")


def _validate_weapons(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, list, "a list of weapon objects"):
        return

    seen_ids = set()
    for index, weapon in enumerate(data):
        weapon_path = [index]
        if not _expect_type(report, source, weapon_path, weapon, dict, "an object"):
            continue

        weapon_id = weapon.get("id")
        if not _validate_identifier(report, source, weapon_path + ["id"], weapon_id, field_name="weapon id"):
            continue
        weapon_id = str(weapon_id).strip()
        if weapon_id in seen_ids:
            report.error(source, weapon_path + ["id"], f"duplicate weapon id {weapon_id!r}")
        seen_ids.add(weapon_id)

        if "name" in weapon:
            _validate_non_empty_string(report, source, weapon_path + ["name"], weapon.get("name"), field_name="name")

        for key in ("glyph", "projectile_glyph"):
            if key in weapon and _validate_non_empty_string(report, source, weapon_path + [key], weapon.get(key), field_name=key):
                if len(str(weapon.get(key))) > 1:
                    report.warn(source, weapon_path + [key], f"{key} will be truncated to the first character at runtime")
                _validate_reserved_glyph_literal(report, source, weapon_path + [key], weapon.get(key), owner_label="weapons")

        if "trajectory" in weapon:
            trajectory = weapon.get("trajectory")
            if _validate_non_empty_string(report, source, weapon_path + ["trajectory"], trajectory, field_name="trajectory"):
                if str(trajectory).strip().lower() not in ALLOWED_WEAPON_TRAJECTORIES:
                    report.error(source, weapon_path + ["trajectory"], f"trajectory must be one of {sorted(ALLOWED_WEAPON_TRAJECTORIES)}")

        if "speed" in weapon:
            _validate_number(report, source, weapon_path + ["speed"], weapon.get("speed"), minimum=0.1, field_name="speed")
        if "range" in weapon:
            _validate_int(report, source, weapon_path + ["range"], weapon.get("range"), minimum=1, field_name="range")
        if "pellets" in weapon:
            _validate_int(report, source, weapon_path + ["pellets"], weapon.get("pellets"), minimum=1, field_name="pellets")
        if "spread" in weapon:
            _validate_int(report, source, weapon_path + ["spread"], weapon.get("spread"), minimum=0, field_name="spread")
        if "base_damage" in weapon:
            _validate_int(report, source, weapon_path + ["base_damage"], weapon.get("base_damage"), minimum=1, field_name="base_damage")
        if "cooldown_ticks" in weapon:
            _validate_int(report, source, weapon_path + ["cooldown_ticks"], weapon.get("cooldown_ticks"), minimum=1, field_name="cooldown_ticks")
        if "noise_radius" in weapon:
            _validate_int(report, source, weapon_path + ["noise_radius"], weapon.get("noise_radius"), minimum=1, field_name="noise_radius")
        if "explosion_radius" in weapon:
            _validate_int(report, source, weapon_path + ["explosion_radius"], weapon.get("explosion_radius"), minimum=0, field_name="explosion_radius")
        if "aoe_falloff" in weapon:
            _validate_number(report, source, weapon_path + ["aoe_falloff"], weapon.get("aoe_falloff"), minimum=0.0, maximum=1.0, field_name="aoe_falloff")
        if "cover_penetration" in weapon:
            _validate_number(report, source, weapon_path + ["cover_penetration"], weapon.get("cover_penetration"), minimum=0.0, maximum=1.0, field_name="cover_penetration")
        if "tags" in weapon:
            _validate_string_list(report, source, weapon_path + ["tags"], weapon.get("tags"), field_name="tags")
        if "named_prefixes" in weapon:
            _validate_string_list(report, source, weapon_path + ["named_prefixes"], weapon.get("named_prefixes"), field_name="named_prefixes")
        if "named_suffixes" in weapon:
            _validate_string_list(report, source, weapon_path + ["named_suffixes"], weapon.get("named_suffixes"), field_name="named_suffixes")


def _validate_offense_profile(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "an offense-profile object"):
        return

    for key in ("action_base", "context_bonus"):
        if key not in data:
            continue
        value = data.get(key)
        if not _expect_type(report, source, [key], value, dict, "an object"):
            continue
        for action_key, score in value.items():
            _validate_non_empty_string(report, source, [key, action_key], action_key, field_name="key")
            _validate_int(report, source, [key, action_key], score, minimum=0, maximum=100, field_name="score")

    tiers = data.get("tiers")
    if tiers is not None:
        if not isinstance(tiers, list):
            report.error(source, ["tiers"], "tiers must be a list")
        else:
            tier_maxes = []
            tier_labels = []
            for index, tier in enumerate(tiers):
                tier_path = ["tiers", index]
                if not _expect_type(report, source, tier_path, tier, dict, "an object"):
                    continue
                label = tier.get("label")
                max_value = tier.get("max")
                if _validate_non_empty_string(report, source, tier_path + ["label"], label, field_name="label"):
                    label = str(label).strip().lower()
                    if label in tier_labels:
                        report.error(source, tier_path + ["label"], f"duplicate tier label {label!r}")
                    tier_labels.append(label)
                if _validate_int(report, source, tier_path + ["max"], max_value, minimum=0, maximum=100, field_name="max"):
                    tier_maxes.append(int(max_value))
            if tier_maxes and tier_maxes != sorted(tier_maxes):
                report.warn(source, ["tiers"], "tiers are not ordered by ascending max; runtime will sort them")

    radius = data.get("notice_radius")
    if radius is not None:
        if not _expect_type(report, source, ["notice_radius"], radius, dict, "an object"):
            return
        base = radius.get("base")
        min_radius = radius.get("min")
        max_radius = radius.get("max")
        step_divisor = radius.get("step_divisor")
        base_ok = _validate_int(report, source, ["notice_radius", "base"], base, field_name="base")
        min_ok = _validate_int(report, source, ["notice_radius", "min"], min_radius, minimum=1, field_name="min")
        max_ok = _validate_int(report, source, ["notice_radius", "max"], max_radius, minimum=1, field_name="max")
        _validate_int(report, source, ["notice_radius", "step_divisor"], step_divisor, minimum=1, field_name="step_divisor")
        if min_ok and max_ok and int(max_radius) < int(min_radius):
            report.error(source, ["notice_radius"], "max must be >= min")
        if base_ok and min_ok and max_ok and not (int(min_radius) <= int(base) <= int(max_radius)):
            report.warn(source, ["notice_radius", "base"], "base falls outside min/max bounds")


def _validate_word_pools(path, required_keys, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "an object"):
        return

    for key in required_keys:
        if key not in data:
            report.error(source, [], f"missing required pool {key!r}")
            continue
        _validate_string_list(
            report,
            source,
            [key],
            data.get(key),
            field_name=key,
            require_non_empty=True,
        )


def _validate_fixtures(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "an object keyed by area"):
        return

    for required_area in ("city", "non_city"):
        if required_area not in data:
            report.error(source, [], f"missing required area {required_area!r}")

    seen_ids = set()
    for area_key, specs in data.items():
        area_path = [area_key]
        if not _validate_non_empty_string(report, source, area_path, area_key, field_name="area key"):
            continue
        if not isinstance(specs, list):
            report.error(source, area_path, "fixture specs must be a list")
            continue
        for index, spec in enumerate(specs):
            spec_path = area_path + [index]
            if not _expect_type(report, source, spec_path, spec, dict, "an object"):
                continue
            fixture_id = spec.get("id")
            if not _validate_identifier(report, source, spec_path + ["id"], fixture_id, field_name="fixture id"):
                continue
            fixture_id = str(fixture_id).strip()
            if fixture_id in seen_ids:
                report.error(source, spec_path + ["id"], f"duplicate fixture id {fixture_id!r}")
            seen_ids.add(fixture_id)

            if "name" in spec:
                _validate_non_empty_string(report, source, spec_path + ["name"], spec["name"], field_name="name")
            kind = spec.get("kind")
            if _validate_non_empty_string(report, source, spec_path + ["kind"], kind, field_name="kind"):
                if str(kind).strip().lower() not in ALLOWED_FIXTURE_KINDS:
                    report.error(source, spec_path + ["kind"], f"kind must be one of {sorted(ALLOWED_FIXTURE_KINDS)}")

            display = spec.get("display", {})
            if display:
                if not _expect_type(report, source, spec_path + ["display"], display, dict, "an object"):
                    continue
                if "glyph" in display:
                    if _validate_non_empty_string(report, source, spec_path + ["display", "glyph"], display["glyph"], field_name="glyph"):
                        if len(str(display["glyph"])) > 1:
                            report.warn(source, spec_path + ["display", "glyph"], "glyph will be truncated to the first character at runtime")
                        _validate_reserved_glyph_literal(report, source, spec_path + ["display", "glyph"], display["glyph"], owner_label="fixtures")
                if "color" in display:
                    _validate_non_empty_string(report, source, spec_path + ["display", "color"], display["color"], field_name="color")

            cover = spec.get("cover", {})
            if cover:
                if not _expect_type(report, source, spec_path + ["cover"], cover, dict, "an object"):
                    continue
                cover_kind = cover.get("kind")
                if _validate_non_empty_string(report, source, spec_path + ["cover", "kind"], cover_kind, field_name="cover.kind"):
                    if str(cover_kind).strip().lower() not in ALLOWED_FIXTURE_COVER:
                        report.error(source, spec_path + ["cover", "kind"], f"cover kind must be one of {sorted(ALLOWED_FIXTURE_COVER)}")
                if "value" in cover:
                    _validate_number(report, source, spec_path + ["cover", "value"], cover["value"], minimum=0.0, maximum=0.9, field_name="cover.value")

            placement = spec.get("placement", {})
            if placement:
                if not _expect_type(report, source, spec_path + ["placement"], placement, dict, "an object"):
                    continue
                if "weight" in placement:
                    _validate_number(report, source, spec_path + ["placement", "weight"], placement["weight"], minimum=0.1, field_name="placement.weight")
                priorities = placement.get("priorities")
                if priorities is not None:
                    values = _validate_string_list(report, source, spec_path + ["placement", "priorities"], priorities, field_name="priorities")
                    for value in values:
                        if str(value).strip().lower() not in ALLOWED_FIXTURE_BUCKETS:
                            report.error(
                                source,
                                spec_path + ["placement", "priorities"],
                                f"priority {value!r} must be one of {sorted(ALLOWED_FIXTURE_BUCKETS)}",
                            )

            if "public" in spec and not isinstance(spec["public"], bool):
                report.error(source, spec_path + ["public"], "public must be a boolean")

            if "services" in spec:
                _validate_string_list(report, source, spec_path + ["services"], spec["services"], field_name="services")

            if "family" in spec:
                _validate_non_empty_string(report, source, spec_path + ["family"], spec["family"], field_name="family")

            light = spec.get("light", {})
            if light:
                if not _expect_type(report, source, spec_path + ["light"], light, dict, "an object"):
                    continue
                if "enabled" in light and not isinstance(light["enabled"], bool):
                    report.error(source, spec_path + ["light", "enabled"], "light.enabled must be a boolean")
                if "radius" in light:
                    _validate_int(report, source, spec_path + ["light", "radius"], light["radius"], minimum=0, field_name="light.radius")
                if "intensity" in light:
                    _validate_number(report, source, spec_path + ["light", "intensity"], light["intensity"], minimum=0.0, maximum=1.0, field_name="light.intensity")
                if "phases" in light:
                    phases = _validate_string_list(report, source, spec_path + ["light", "phases"], light["phases"], field_name="light.phases")
                    for phase in phases:
                        if str(phase).strip().lower() not in ALLOWED_LIGHT_PHASES:
                            report.error(source, spec_path + ["light", "phases"], f"unknown light phase {phase!r}")


def _validate_vehicles(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "a vehicle catalog object"):
        return

    if "vehicle_symbol" in data:
        if _validate_non_empty_string(report, source, ["vehicle_symbol"], data["vehicle_symbol"], field_name="vehicle_symbol"):
            if len(str(data["vehicle_symbol"])) > 1:
                report.warn(source, ["vehicle_symbol"], "vehicle_symbol will be truncated to the first character at runtime")
            _validate_reserved_glyph_literal(report, source, ["vehicle_symbol"], data["vehicle_symbol"], owner_label="vehicles")

    makes = data.get("makes")
    if makes is None:
        report.error(source, [], "vehicle catalog must define makes")
    else:
        _validate_string_list(report, source, ["makes"], makes, field_name="makes", require_non_empty=True)

    models = data.get("models")
    if not isinstance(models, list):
        report.error(source, ["models"], "models must be a list")
    else:
        seen_models = set()
        for index, model in enumerate(models):
            model_path = ["models", index]
            if not _expect_type(report, source, model_path, model, dict, "an object"):
                continue
            name = model.get("name")
            if _validate_non_empty_string(report, source, model_path + ["name"], name, field_name="name"):
                key = str(name).strip().lower()
                if key in seen_models:
                    report.error(source, model_path + ["name"], f"duplicate model name {name!r}")
                seen_models.add(key)
            _validate_non_empty_string(report, source, model_path + ["vehicle_class"], model.get("vehicle_class"), field_name="vehicle_class")
            _validate_int_pair(report, source, model_path + ["power"], model.get("power"), minimum=1, maximum=10, field_name="power")
            _validate_int_pair(report, source, model_path + ["durability"], model.get("durability"), minimum=1, maximum=10, field_name="durability")
            _validate_int_pair(report, source, model_path + ["fuel_efficiency"], model.get("fuel_efficiency"), minimum=1, maximum=10, field_name="fuel_efficiency")
            _validate_int_pair(report, source, model_path + ["fuel_capacity"], model.get("fuel_capacity"), minimum=1, maximum=9999, field_name="fuel_capacity")
            _validate_int(report, source, model_path + ["base_price"], model.get("base_price"), minimum=100, maximum=5000, field_name="base_price")

    quality_profiles = data.get("quality_profiles")
    if not isinstance(quality_profiles, dict):
        report.error(source, ["quality_profiles"], "quality_profiles must be an object")
    else:
        for key in ("used", "new"):
            profile = quality_profiles.get(key)
            if not isinstance(profile, dict):
                report.error(source, ["quality_profiles", key], f"missing quality profile {key!r}")
                continue
            _validate_float_pair(report, source, ["quality_profiles", key, "price_mult"], profile.get("price_mult"), minimum=0.01, maximum=10.0, field_name="price_mult")
            _validate_int_pair(
                report,
                source,
                ["quality_profiles", key, "durability_shift"],
                profile.get("durability_shift"),
                minimum=None,
                maximum=9999,
                allow_negative=True,
                field_name="durability_shift",
            )
            _validate_float_pair(report, source, ["quality_profiles", key, "fuel_mult"], profile.get("fuel_mult"), minimum=0.01, maximum=10.0, field_name="fuel_mult")

    service_archetypes = data.get("service_archetypes")
    if not isinstance(service_archetypes, dict):
        report.error(source, ["service_archetypes"], "service_archetypes must be an object")
    else:
        for key in ("fuel", "repair", "new_sales", "used_sales", "fetch"):
            values = service_archetypes.get(key)
            if values is None:
                report.error(source, ["service_archetypes"], f"missing service_archetypes key {key!r}")
                continue
            _validate_string_list(
                report,
                source,
                ["service_archetypes", key],
                values,
                field_name=key,
                require_non_empty=True,
            )


def _validate_npc_names(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "an object"):
        return

    human = data.get("human")
    if not isinstance(human, dict):
        report.error(source, [], "npc name catalog must define a human object")
        return

    for key in ("first_names", "last_names"):
        if key not in human:
            report.error(source, ["human"], f"missing human.{key}")
            continue
        _validate_string_list(
            report,
            source,
            ["human", key],
            human.get(key),
            field_name=f"human.{key}",
            require_non_empty=True,
        )


def _validate_tile_map(path, report):
    source = _rel_path(path)
    data = _load_json_file(path, report)
    if data is None:
        return
    if not _expect_type(report, source, [], data, dict, "an object"):
        return

    for category_name, category in data.items():
        if str(category_name).startswith("_"):
            continue
        if not isinstance(category, dict):
            continue

        for glyph, mapping in category.items():
            policy = RESERVED_GLYPH_POLICIES.get(str(glyph))
            if policy is None:
                continue
            if not isinstance(mapping, dict):
                continue

            allowed = set(policy["allowed_semantics"])
            meaning = str(policy["meaning"])
            for color_key, semantic_id in mapping.items():
                semantic = str(semantic_id or "").strip()
                if not semantic:
                    continue
                if semantic not in allowed:
                    report.error(
                        source,
                        [category_name, glyph, color_key],
                        f"glyph {glyph!r} is reserved for {meaning} semantics only",
                    )


def validate_repo_content():
    report = ValidationReport()

    item_ids = _validate_items(ITEMS_PATH, report)
    _validate_loot_tables(LOOT_TABLES_PATH, item_ids, report)
    _validate_weapons(WEAPONS_PATH, report)
    _validate_offense_profile(OFFENSE_PROFILE_PATH, report)
    _validate_word_pools(
        BUSINESS_NAMES_PATH,
        (
            "adjectives",
            "nouns",
            "street_terms",
        ),
        report,
    )
    _validate_fixtures(FIXTURES_PATH, report)
    _validate_vehicles(VEHICLES_PATH, report)
    _validate_npc_names(NPC_NAMES_PATH, report)
    _validate_tile_map(TILE_MAP_PATH, report)

    return report
