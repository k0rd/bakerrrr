"""Runtime loader for narrow player-authored custom content."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from game.items import (
    LEGAL_STATUSES,
    load_item_catalog,
    normalize_item_definitions,
    refresh_item_runtime,
)
from game.json_metadata import METADATA_KEY, SCHEMA_VERSION, split_object_document
from game.public_content import (
    PUBLIC_DENSITY_LEVELS,
    PUBLIC_ITEM_EFFECT_TYPES,
    PUBLIC_ITEM_NEEDS,
    PUBLIC_STATUS_MODIFIERS,
    PUBLIC_WATER_LEVELS,
    PUBLIC_WORLD_PROFILE_FIELDS,
    public_area_types,
    public_building_archetype_ids,
    public_district_types,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOM_CONTENT_SCHEMA_VERSION = SCHEMA_VERSION
CUSTOM_CONTENT_ROOT = REPO_ROOT / "config" / "custom_content"
ITEM_DOMAIN = "items"
WORLD_PROFILE_DOMAIN = "world_profiles"
CUSTOM_CONTENT_DOMAINS = (ITEM_DOMAIN, WORLD_PROFILE_DOMAIN)
IDENTIFIER_RE = re.compile(r"^[a-z0-9_]+$")

CUSTOM_ITEM_ALLOWED_FIELDS = {
    "name",
    "glyph",
    "stack_max",
    "tags",
    "category",
    "legal_status",
    "effects",
    "appearance_family",
    "appearance_slots",
    "identification_profile",
    "substance_profile",
    "lead_profile",
}

CUSTOM_ITEM_DISALLOWED_FIELDS = {
    "weapon_id",
    "armor",
    "disguise",
    "container",
    "throw_profile",
    "tool_profiles",
    "condition_profile",
}


@dataclass(frozen=True)
class CustomContentIssue:
    severity: str
    domain: str
    source: str
    path: str
    message: str


@dataclass
class CustomContentResult:
    manifest: dict = field(default_factory=dict)
    item_definitions: dict = field(default_factory=dict)
    world_profiles: dict = field(default_factory=dict)
    notices: list[dict] = field(default_factory=list)
    blocking: bool = False


def _repo_display_path(path, *, root=CUSTOM_CONTENT_ROOT):
    path = Path(path)
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        pass
    try:
        return str(path.relative_to(Path(root)))
    except ValueError:
        return str(path)


def _manifest_rel_path(path, *, root=CUSTOM_CONTENT_ROOT):
    return Path(path).relative_to(Path(root)).as_posix()


def _source_for_manifest_path(rel_path, *, root=CUSTOM_CONTENT_ROOT):
    safe_parts = [part for part in Path(str(rel_path)).parts if part not in {"", ".", ".."}]
    return Path(root).joinpath(*safe_parts)


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_version_from_meta(meta):
    if not isinstance(meta, dict):
        return CUSTOM_CONTENT_SCHEMA_VERSION
    try:
        return int(meta.get("schema_version", CUSTOM_CONTENT_SCHEMA_VERSION))
    except (TypeError, ValueError):
        return CUSTOM_CONTENT_SCHEMA_VERSION


def _issue(issues, severity, domain, source, path, message, *, root=CUSTOM_CONTENT_ROOT):
    issues.append(CustomContentIssue(
        severity=str(severity),
        domain=str(domain),
        source=_repo_display_path(source, root=root),
        path=str(path or "$"),
        message=str(message),
    ))


def _json_path(parts):
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif IDENTIFIER_RE.match(str(part)):
            path += f".{part}"
        else:
            path += f"[{json.dumps(str(part))}]"
    return path


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clean_identifier(value):
    token = str(value or "").strip().lower()
    return token if IDENTIFIER_RE.match(token) else ""


def discover_custom_content_files(*, root=CUSTOM_CONTENT_ROOT):
    root = Path(root)
    discovered = {}
    for domain in CUSTOM_CONTENT_DOMAINS:
        domain_dir = root / domain
        if not domain_dir.is_dir():
            discovered[domain] = []
            continue
        discovered[domain] = sorted(path for path in domain_dir.rglob("*.json") if path.is_file())
    return discovered


def _read_json_object(path, issues, domain, *, root=CUSTOM_CONTENT_ROOT):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        _issue(issues, "error", domain, path, "$", "file is missing", root=root)
        return None
    except OSError as exc:
        _issue(issues, "error", domain, path, "$", f"file could not be read: {exc}", root=root)
        return None
    except json.JSONDecodeError as exc:
        _issue(issues, "error", domain, path, "$", f"invalid JSON: {exc.msg}", root=root)
        return None
    if not isinstance(raw, dict):
        _issue(issues, "error", domain, path, "$", "top-level JSON must be an object", root=root)
        return None
    meta = raw.get(METADATA_KEY)
    if not isinstance(meta, dict):
        _issue(issues, "error", domain, path, "$._meta", "missing _meta object with schema_version", root=root)
    else:
        schema_version = meta.get("schema_version")
        if schema_version != CUSTOM_CONTENT_SCHEMA_VERSION:
            _issue(
                issues,
                "error",
                domain,
                path,
                "$._meta.schema_version",
                f"schema_version must be {CUSTOM_CONTENT_SCHEMA_VERSION}",
                root=root,
            )
    return raw


def _validate_number(issues, domain, source, path, value, *, minimum=None, root=CUSTOM_CONTENT_ROOT):
    if not _is_number(value):
        _issue(issues, "error", domain, source, path, "value must be a number", root=root)
        return False
    if minimum is not None and float(value) < float(minimum):
        _issue(issues, "error", domain, source, path, f"value must be >= {minimum}", root=root)
        return False
    return True


def _validate_string_list(issues, domain, source, path, value, allowed=None, *, root=CUSTOM_CONTENT_ROOT):
    if value is None:
        return []
    if not isinstance(value, list):
        _issue(issues, "error", domain, source, path, "value must be a list of strings", root=root)
        return []
    result = []
    allowed_set = {str(item).strip().lower() for item in allowed or () if str(item).strip()}
    for index, raw in enumerate(value):
        token = str(raw or "").strip().lower()
        if not token:
            _issue(issues, "error", domain, source, f"{path}[{index}]", "value must be a non-empty string", root=root)
            continue
        if allowed_set and token not in allowed_set:
            _issue(
                issues,
                "error",
                domain,
                source,
                f"{path}[{index}]",
                f"value must be one of {sorted(allowed_set)}",
                root=root,
            )
            continue
        result.append(token)
    return list(dict.fromkeys(result))


def _validate_modifier_map(issues, domain, source, path, modifiers, *, root=CUSTOM_CONTENT_ROOT):
    if modifiers is None:
        return {}
    if not isinstance(modifiers, dict):
        _issue(issues, "error", domain, source, path, "modifiers must be an object", root=root)
        return {}
    result = {}
    for raw_key, raw_value in modifiers.items():
        key = str(raw_key or "").strip().lower()
        item_path = f"{path}.{key}" if IDENTIFIER_RE.match(key) else f"{path}[{json.dumps(str(raw_key))}]"
        if key not in PUBLIC_STATUS_MODIFIERS:
            _issue(
                issues,
                "error",
                domain,
                source,
                item_path,
                f"unknown public status modifier {key!r}",
                root=root,
            )
            continue
        if not _validate_number(issues, domain, source, item_path, raw_value, root=root):
            continue
        result[key] = float(raw_value)
    return result


def _validate_item_effects(issues, domain, source, item_id, effects, *, root=CUSTOM_CONTENT_ROOT):
    path = f"$.{item_id}.effects"
    if effects is None:
        return []
    if not isinstance(effects, list):
        _issue(issues, "error", domain, source, path, "effects must be a list", root=root)
        return []
    result = []
    for index, effect in enumerate(effects):
        effect_path = f"{path}[{index}]"
        if not isinstance(effect, dict):
            _issue(issues, "error", domain, source, effect_path, "effect must be an object", root=root)
            continue
        effect_type = str(effect.get("type", "") or "").strip().lower()
        if effect_type not in PUBLIC_ITEM_EFFECT_TYPES:
            _issue(
                issues,
                "error",
                domain,
                source,
                f"{effect_path}.type",
                f"effect type must be one of {sorted(PUBLIC_ITEM_EFFECT_TYPES)}",
                root=root,
            )
            continue
        clean = dict(effect)
        clean["type"] = effect_type
        if effect_type == "modify_need":
            need = str(effect.get("need", "") or "").strip().lower()
            if need not in PUBLIC_ITEM_NEEDS:
                _issue(issues, "error", domain, source, f"{effect_path}.need", f"need must be one of {sorted(PUBLIC_ITEM_NEEDS)}", root=root)
            _validate_number(issues, domain, source, f"{effect_path}.delta", effect.get("delta"), root=root)
        elif effect_type == "restore_hp":
            _validate_number(issues, domain, source, f"{effect_path}.delta", effect.get("delta"), minimum=1, root=root)
        elif effect_type == "credits":
            _validate_number(issues, domain, source, f"{effect_path}.delta", effect.get("delta"), root=root)
        elif effect_type == "add_ammo":
            _validate_number(issues, domain, source, f"{effect_path}.amount", effect.get("amount"), minimum=1, root=root)
        elif effect_type == "status":
            status = _clean_identifier(effect.get("status"))
            if not status:
                _issue(issues, "error", domain, source, f"{effect_path}.status", "status must be a lowercase identifier", root=root)
            duration = effect.get("duration")
            if not isinstance(duration, int) or isinstance(duration, bool) or int(duration) < 1:
                _issue(issues, "error", domain, source, f"{effect_path}.duration", "duration must be an integer >= 1", root=root)
            clean["modifiers"] = _validate_modifier_map(
                issues,
                domain,
                source,
                f"{effect_path}.modifiers",
                effect.get("modifiers", {}),
                root=root,
            )
        result.append(clean)
    return result


def _validate_custom_item(issues, source, item_id, item, *, root=CUSTOM_CONTENT_ROOT):
    domain = ITEM_DOMAIN
    if not isinstance(item, dict):
        _issue(issues, "error", domain, source, f"$.{item_id}", "item definition must be an object", root=root)
        return None
    clean = dict(item)
    for key in sorted(item):
        key_text = str(key or "").strip()
        if key_text in CUSTOM_ITEM_DISALLOWED_FIELDS:
            _issue(issues, "error", domain, source, f"$.{item_id}.{key_text}", "field is not allowed for v1 custom items", root=root)
        elif key_text not in CUSTOM_ITEM_ALLOWED_FIELDS:
            _issue(issues, "error", domain, source, f"$.{item_id}.{key_text}", "unknown field for v1 custom items", root=root)
    name = str(item.get("name", "") or "").strip()
    if not name:
        _issue(issues, "error", domain, source, f"$.{item_id}.name", "name is required", root=root)
    glyph = str(item.get("glyph", "?") or "?")
    if len(glyph) != 1:
        _issue(issues, "error", domain, source, f"$.{item_id}.glyph", "glyph must be one character", root=root)
    stack_max = item.get("stack_max", 1)
    if not isinstance(stack_max, int) or isinstance(stack_max, bool) or stack_max < 1:
        _issue(issues, "error", domain, source, f"$.{item_id}.stack_max", "stack_max must be an integer >= 1", root=root)
    tags = item.get("tags", [])
    if tags is not None and not isinstance(tags, list):
        _issue(issues, "error", domain, source, f"$.{item_id}.tags", "tags must be a list of strings", root=root)
    legal_status = str(item.get("legal_status", "legal") or "").strip().lower()
    if legal_status not in LEGAL_STATUSES:
        _issue(issues, "error", domain, source, f"$.{item_id}.legal_status", f"legal_status must be one of {sorted(LEGAL_STATUSES)}", root=root)
    clean["effects"] = _validate_item_effects(issues, domain, source, item_id, item.get("effects", []), root=root)
    substance = item.get("substance_profile")
    if isinstance(substance, dict) and "withdrawal_modifiers" in substance:
        withdrawal = dict(substance)
        withdrawal["withdrawal_modifiers"] = _validate_modifier_map(
            issues,
            domain,
            source,
            f"$.{item_id}.substance_profile.withdrawal_modifiers",
            substance.get("withdrawal_modifiers"),
            root=root,
        )
        clean["substance_profile"] = withdrawal
    elif substance is not None and not isinstance(substance, dict):
        _issue(issues, "error", domain, source, f"$.{item_id}.substance_profile", "substance_profile must be an object", root=root)
    return clean


def _built_in_item_ids():
    return set(load_item_catalog().keys())


def _validate_item_domain(files, *, root=CUSTOM_CONTENT_ROOT):
    issues = []
    items = {}
    file_records = []
    seen_custom = set()
    built_in_ids = _built_in_item_ids()
    for path in files:
        raw = _read_json_object(path, issues, ITEM_DOMAIN, root=root)
        if not isinstance(raw, dict):
            continue
        payload, meta = split_object_document(raw)
        file_ids = []
        if not isinstance(payload, dict):
            _issue(issues, "error", ITEM_DOMAIN, path, "$", "item document payload must be an object", root=root)
            continue
        for raw_id, raw_item in payload.items():
            item_id = _clean_identifier(raw_id)
            item_path = _json_path([raw_id])
            if not item_id:
                _issue(issues, "error", ITEM_DOMAIN, path, item_path, "item id must be a lowercase identifier", root=root)
                continue
            if item_id in built_in_ids:
                _issue(issues, "error", ITEM_DOMAIN, path, item_path, "custom item id collides with built-in item id", root=root)
                continue
            if item_id in seen_custom:
                _issue(issues, "error", ITEM_DOMAIN, path, item_path, "custom item id is duplicated by another custom item file", root=root)
                continue
            seen_custom.add(item_id)
            clean = _validate_custom_item(issues, path, item_id, raw_item, root=root)
            if clean is not None:
                items[item_id] = clean
                file_ids.append(item_id)
        try:
            sha = _sha256_file(path)
        except OSError:
            sha = ""
        file_records.append({
            "path": _manifest_rel_path(path, root=root),
            "schema_version": _schema_version_from_meta(meta),
            "sha256": sha,
            "loaded_ids": sorted(file_ids),
        })
    if issues:
        return {}, [], issues
    normalized = normalize_item_definitions(items)
    return normalized, file_records, issues


def _validate_weight_map(issues, domain, source, path, value, valid_ids, *, root=CUSTOM_CONTENT_ROOT):
    if value is None:
        return {}
    if not isinstance(value, dict):
        _issue(issues, "error", domain, source, path, "weights must be an object", root=root)
        return {}
    result = {}
    valid = set(valid_ids or ())
    for raw_key, raw_weight in value.items():
        key = str(raw_key or "").strip().lower()
        item_path = f"{path}.{key}" if IDENTIFIER_RE.match(key) else f"{path}[{json.dumps(str(raw_key))}]"
        if key not in valid:
            _issue(issues, "error", domain, source, item_path, "building archetype id is not public", root=root)
            continue
        if not _validate_number(issues, domain, source, item_path, raw_weight, minimum=0.01, root=root):
            continue
        result[key] = float(raw_weight)
    return result


def _validate_world_profile(issues, source, profile_id, profile, *, root=CUSTOM_CONTENT_ROOT):
    domain = WORLD_PROFILE_DOMAIN
    if not isinstance(profile, dict):
        _issue(issues, "error", domain, source, f"$.{profile_id}", "world profile must be an object", root=root)
        return None
    for key in sorted(profile):
        if str(key) not in PUBLIC_WORLD_PROFILE_FIELDS:
            _issue(issues, "error", domain, source, f"$.{profile_id}.{key}", "unknown field for v1 world profiles", root=root)
    label = str(profile.get("label", profile_id.replace("_", " ").title()) or "").strip()
    if not label:
        _issue(issues, "error", domain, source, f"$.{profile_id}.label", "label cannot be empty", root=root)
    selection_weight = profile.get("selection_weight", 1.0)
    if not _validate_number(issues, domain, source, f"$.{profile_id}.selection_weight", selection_weight, minimum=0.01, root=root):
        selection_weight = 1.0
    area_types = _validate_string_list(
        issues,
        domain,
        source,
        f"$.{profile_id}.area_types",
        profile.get("area_types", []),
        public_area_types(),
        root=root,
    )
    district_types = _validate_string_list(
        issues,
        domain,
        source,
        f"$.{profile_id}.district_types",
        profile.get("district_types", []),
        public_district_types(),
        root=root,
    )
    clean = {
        "id": profile_id,
        "label": label,
        "selection_weight": float(selection_weight),
        "area_types": area_types,
        "district_types": district_types,
    }
    for field_name in ("population_density", "building_density"):
        value = str(profile.get(field_name, "none") or "none").strip().lower()
        if value not in PUBLIC_DENSITY_LEVELS:
            _issue(issues, "error", domain, source, f"$.{profile_id}.{field_name}", f"value must be one of {list(PUBLIC_DENSITY_LEVELS)}", root=root)
            value = "none"
        clean[field_name] = value
    water = str(profile.get("water", "none") or "none").strip().lower()
    if water not in PUBLIC_WATER_LEVELS:
        _issue(issues, "error", domain, source, f"$.{profile_id}.water", f"water must be one of {list(PUBLIC_WATER_LEVELS)}", root=root)
        water = "none"
    clean["water"] = water
    building_ids = public_building_archetype_ids()
    clean["building_weights"] = _validate_weight_map(
        issues,
        domain,
        source,
        f"$.{profile_id}.building_weights",
        profile.get("building_weights", {}),
        building_ids,
        root=root,
    )
    clean["service_building_weights"] = _validate_weight_map(
        issues,
        domain,
        source,
        f"$.{profile_id}.service_building_weights",
        profile.get("service_building_weights", {}),
        building_ids,
        root=root,
    )
    return clean


def _validate_world_profile_domain(files, *, root=CUSTOM_CONTENT_ROOT):
    issues = []
    profiles = {}
    file_records = []
    seen = set()
    for path in files:
        raw = _read_json_object(path, issues, WORLD_PROFILE_DOMAIN, root=root)
        if not isinstance(raw, dict):
            continue
        payload, meta = split_object_document(raw)
        file_ids = []
        if not isinstance(payload, dict):
            _issue(issues, "error", WORLD_PROFILE_DOMAIN, path, "$", "world profile payload must be an object", root=root)
            continue
        for raw_id, raw_profile in payload.items():
            profile_id = _clean_identifier(raw_id)
            profile_path = _json_path([raw_id])
            if not profile_id:
                _issue(issues, "error", WORLD_PROFILE_DOMAIN, path, profile_path, "profile id must be a lowercase identifier", root=root)
                continue
            if profile_id in seen:
                _issue(issues, "error", WORLD_PROFILE_DOMAIN, path, profile_path, "profile id is duplicated by another custom profile file", root=root)
                continue
            seen.add(profile_id)
            clean = _validate_world_profile(issues, path, profile_id, raw_profile, root=root)
            if clean is not None:
                profiles[profile_id] = clean
                file_ids.append(profile_id)
        try:
            sha = _sha256_file(path)
        except OSError:
            sha = ""
        file_records.append({
            "path": _manifest_rel_path(path, root=root),
            "schema_version": _schema_version_from_meta(meta),
            "sha256": sha,
            "loaded_ids": sorted(file_ids),
        })
    if issues:
        return {}, [], issues
    return profiles, file_records, issues


def _empty_manifest():
    return {
        "schema_version": int(CUSTOM_CONTENT_SCHEMA_VERSION),
        "domains": {
            ITEM_DOMAIN: {"files": [], "loaded_ids": []},
            WORLD_PROFILE_DOMAIN: {"files": [], "loaded_ids": []},
        },
    }


def _notice_from_issues(title, issues, *, severity="warning", stream="stderr", tail=None):
    lines = []
    for issue in issues[:8]:
        lines.append(f"{issue.source} {issue.path}: {issue.message}")
    if len(issues) > 8:
        lines.append(f"...and {len(issues) - 8} more problem(s).")
    if tail:
        lines.extend(str(line) for line in tail if str(line).strip())
    return {
        "title": str(title),
        "severity": str(severity),
        "stream": str(stream),
        "lines": lines,
    }


def _domain_manifest(file_records):
    loaded = []
    for record in file_records:
        loaded.extend(record.get("loaded_ids", ()) or ())
    return {
        "files": list(file_records),
        "loaded_ids": sorted(dict.fromkeys(str(item) for item in loaded if str(item).strip())),
    }


def load_custom_content_for_new_run(*, root=CUSTOM_CONTENT_ROOT):
    root = Path(root)
    discovered = discover_custom_content_files(root=root)
    manifest = _empty_manifest()
    notices = []
    item_definitions = {}
    world_profiles = {}

    item_files = discovered.get(ITEM_DOMAIN, [])
    if item_files:
        parsed_items, file_records, issues = _validate_item_domain(item_files, root=root)
        if issues:
            notices.append(_notice_from_issues(
                "Custom item content was rejected",
                issues,
                severity="warning",
                tail=("No custom item files were loaded for this run.",),
            ))
        else:
            item_definitions = parsed_items
            manifest["domains"][ITEM_DOMAIN] = _domain_manifest(file_records)

    profile_files = discovered.get(WORLD_PROFILE_DOMAIN, [])
    if profile_files:
        parsed_profiles, file_records, issues = _validate_world_profile_domain(profile_files, root=root)
        if issues:
            notices.append(_notice_from_issues(
                "Custom world profiles were rejected",
                issues,
                severity="warning",
                tail=("No custom world-profile files were loaded for this run.",),
            ))
        else:
            world_profiles = parsed_profiles
            manifest["domains"][WORLD_PROFILE_DOMAIN] = _domain_manifest(file_records)

    return CustomContentResult(
        manifest=manifest,
        item_definitions=item_definitions,
        world_profiles=world_profiles,
        notices=notices,
        blocking=False,
    )


def _manifest_domain_files(manifest, domain):
    domains = manifest.get("domains") if isinstance(manifest, dict) else None
    domain_data = domains.get(domain) if isinstance(domains, dict) else None
    files = domain_data.get("files") if isinstance(domain_data, dict) else None
    return [record for record in files or () if isinstance(record, dict)]


def _validate_required_manifest_files(manifest, domain, *, root=CUSTOM_CONTENT_ROOT):
    issues = []
    required = _manifest_domain_files(manifest, domain)
    paths = []
    for record in required:
        rel_path = str(record.get("path", "") or "").strip()
        if not rel_path:
            _issue(issues, "error", domain, root, "$.path", "manifest file record is missing path", root=root)
            continue
        path = _source_for_manifest_path(rel_path, root=root)
        paths.append(path)
        if not path.is_file():
            _issue(issues, "error", domain, path, "$", "required custom content file is missing", root=root)
            continue
        expected_sha = str(record.get("sha256", "") or "").strip().lower()
        try:
            actual_sha = _sha256_file(path)
        except OSError as exc:
            _issue(issues, "error", domain, path, "$", f"required custom content file could not be read: {exc}", root=root)
            continue
        if expected_sha and actual_sha != expected_sha:
            _issue(issues, "error", domain, path, "$", "required custom content file SHA-256 does not match the saved run", root=root)
        schema_version = record.get("schema_version")
        if schema_version != CUSTOM_CONTENT_SCHEMA_VERSION:
            _issue(issues, "error", domain, path, "$._meta.schema_version", f"manifest schema_version must be {CUSTOM_CONTENT_SCHEMA_VERSION}", root=root)
    return paths, issues


def _extra_file_notice(saved_manifest, *, root=CUSTOM_CONTENT_ROOT):
    required = set()
    for domain in CUSTOM_CONTENT_DOMAINS:
        for record in _manifest_domain_files(saved_manifest, domain):
            rel_path = str(record.get("path", "") or "").strip()
            if rel_path:
                required.add((domain, rel_path))
    extras = []
    discovered = discover_custom_content_files(root=root)
    for domain, files in discovered.items():
        for path in files:
            rel_path = _manifest_rel_path(path, root=root)
            if (domain, rel_path) not in required:
                extras.append(f"{domain}: {rel_path}")
    if not extras:
        return None
    return {
        "title": "Current custom content was ignored for this save",
        "severity": "warning",
        "stream": "stderr",
        "lines": [
            "This saved run is locked to the custom content manifest it started with.",
            "Extra files were ignored for this resume:",
            *extras[:12],
            *([f"...and {len(extras) - 12} more file(s)."] if len(extras) > 12 else []),
        ],
    }


def validate_custom_content_for_resume(saved_manifest, *, root=CUSTOM_CONTENT_ROOT):
    root = Path(root)
    if not isinstance(saved_manifest, dict) or int(saved_manifest.get("schema_version", 0) or 0) == 0:
        notices = []
        extra_notice = _extra_file_notice(_empty_manifest(), root=root)
        if extra_notice:
            notices.append(extra_notice)
        return CustomContentResult(manifest=_empty_manifest(), notices=notices, blocking=False)

    manifest = copy.deepcopy(saved_manifest)
    notices = []
    blocking_issues = []
    item_definitions = {}
    world_profiles = {}

    if int(manifest.get("schema_version", 0) or 0) != CUSTOM_CONTENT_SCHEMA_VERSION:
        blocking_issues.append(CustomContentIssue(
            severity="error",
            domain="manifest",
            source="save manifest",
            path="$.schema_version",
            message=f"custom content manifest version must be {CUSTOM_CONTENT_SCHEMA_VERSION}",
        ))

    item_files, issues = _validate_required_manifest_files(manifest, ITEM_DOMAIN, root=root)
    blocking_issues.extend(issues)
    profile_files, issues = _validate_required_manifest_files(manifest, WORLD_PROFILE_DOMAIN, root=root)
    blocking_issues.extend(issues)

    if not blocking_issues and item_files:
        parsed_items, _file_records, issues = _validate_item_domain(item_files, root=root)
        if issues:
            blocking_issues.extend(issues)
        else:
            item_definitions = parsed_items

    if not blocking_issues and profile_files:
        parsed_profiles, _file_records, issues = _validate_world_profile_domain(profile_files, root=root)
        if issues:
            blocking_issues.extend(issues)
        else:
            world_profiles = parsed_profiles

    if blocking_issues:
        notices.append(_notice_from_issues(
            "Saved run cannot resume until custom content matches",
            blocking_issues,
            severity="error",
            tail=(
                "The save file was not deleted.",
                "Restore the listed files exactly, or resume a save that was made without them.",
            ),
        ))
        return CustomContentResult(
            manifest=manifest,
            item_definitions={},
            world_profiles={},
            notices=notices,
            blocking=True,
        )

    extra_notice = _extra_file_notice(manifest, root=root)
    if extra_notice:
        notices.append(extra_notice)

    return CustomContentResult(
        manifest=manifest,
        item_definitions=item_definitions,
        world_profiles=world_profiles,
        notices=notices,
        blocking=False,
    )


def apply_custom_content(result, sim=None):
    if not isinstance(result, CustomContentResult):
        return None
    refresh_item_runtime(result.item_definitions)
    if sim is not None:
        sim.custom_content_manifest = copy.deepcopy(result.manifest)
        world = getattr(sim, "world", None)
        if world is not None and hasattr(world, "set_custom_world_profiles"):
            world.set_custom_world_profiles(result.world_profiles)
    return result


def reset_custom_content_runtime():
    refresh_item_runtime({})
