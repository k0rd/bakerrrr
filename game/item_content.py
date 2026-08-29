"""Authoring contract for the built-in item catalog.

The runtime normalizer is intentionally forgiving.  This module is the strict
side of that boundary: it preserves author input, rejects duplicate/unknown
structure, resolves the small set of item cross-references, and exposes the
exact normalized value the game will consume.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from game.content_validation import ValidationIssue, ValidationReport, validate_items_mapping
from game.item_schema import (
    COMMON_ITEM_FIELDS as COMMON_FIELDS,
    ITEM_PROFILE_FIELDS as PROFILE_FIELDS,
    ITEM_PROFILE_KEYS as PROFILE_KEYS,
    KNOWN_ITEM_FIELDS,
    TOOL_PROFILE_KEYS,
)
from game.items import normalize_item_definitions
from game.json_metadata import METADATA_KEY, SCHEMA_VERSION


ITEM_ID_RE = re.compile(r"^[a-z0-9_]+$")
PYTHON_ITEM_LITERAL_RE = re.compile(
    r"(?P<quote>['\"])[ \t]*(?P<item_id>[a-z0-9_]+)[ \t]*(?P=quote)"
)

PROFILE_TEMPLATES: dict[str, Any] = {
    "appearance_profile": {
        "label": "Wearable", "presentation": "mixed", "materials": ["fabric"],
        "styles": [], "details": [], "patterns": [], "emblems": [],
    },
    "armor": {"slot": "body", "damage_reduction": 0.15},
    "container": {"bonus_slots": 2, "slot": "pack", "accepted_item_ids": []},
    "condition_profile": {
        "supports_quality": True, "supports_durability": True,
        "default_quality": "standard", "max_durability": 100,
    },
    "disguise": {"role_id": "worker", "strength": 0.5},
    "identification_profile": {
        "family": "misc", "requires_identification": True,
        "auto_identify_on_use": True, "unidentified_name": "unknown item",
        "appraisal_fields": [],
    },
    "lead_profile": {"lead_kind": "location", "confidence": 0.5, "consume_on_use": False},
    "object_profile": {
        "family": "personal_home", "silhouette": "mug", "material": "ceramic",
        "primary_color": "blue", "accent_color": "white", "motif": "none",
        "condition": "plain", "rarity": "common", "placeable": True,
        "pickup_allowed": True,
    },
    "substance_profile": {"substance_id": "substance", "intoxication_duration": 0},
    "throw_profile": {
        "range": 6, "trajectory": "lobbed", "projectile_glyph": "o",
        "speed": 1.0, "damage": 1, "noise_radius": 2, "consume_on_throw": True,
    },
    "tool_profiles": [{"contexts": ["mechanics"], "mechanics_bonus": 0.25}],
    "trap_profile": {
        "payload_item_id": "", "trigger_kind": "step", "armed_glyph": "^",
        "armed_color": "warning", "noise_radius": 3, "homemade": True,
    },
    "drone_profile": {
        "kind": "module", "module_kind": "utility", "slot_cost": 1,
        "weight": 1, "standby_draw": 0, "active_draw": 1,
        "capabilities": ["utility"], "visible_overlay": {},
        "compatible_chassis": ["A", "B", "C", "D", "E"],
    },
    "wire_profile": {
        "kind": "program", "program_key": "utility_program", "program_family": "utility",
        "storage_points": 1, "ram_cost": 1, "reload_ticks": 1, "noise": 1,
        "trace_cost": 1, "durability_max": 6, "runs_max": 0, "capabilities": [],
    },
    "wire_interface_profile": {
        "kind": "deck", "manufacturer": "independent", "style": "plain",
        "supported_target_classes": ["generic_wire"], "program_slots": 2,
        "buffer_size": 2,
    },
    "world_distribution": {"weight": 10, "store_archetypes": ["general"]},
    "fire_profile": {"breakable": True, "flammability": 0.75, "hp": 5},
}


class ItemDocumentError(ValueError):
    pass


class _TrackedDict(dict):
    def __init__(self, pairs: Iterable[tuple[str, Any]]) -> None:
        super().__init__()
        self.duplicates: list[str] = []
        for key, value in pairs:
            if key in self:
                self.duplicates.append(str(key))
            self[key] = value


def _duplicate_paths(node: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(node, _TrackedDict):
        found.extend(f"{path}.{key}" for key in node.duplicates)
        for key, value in node.items():
            found.extend(_duplicate_paths(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_duplicate_paths(value, f"{path}[{index}]"))
    return found


@dataclass(frozen=True)
class ItemReferenceSet:
    drawable_ids: frozenset[str] = frozenset()
    weapon_ids: frozenset[str] = frozenset()
    external_item_references: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    fingerprint: str = ""
    scan_errors: tuple[str, ...] = ()

    def references_to(self, item_id: str) -> tuple[str, ...]:
        return tuple(self.external_item_references.get(str(item_id), ()))


@dataclass
class ItemDocument:
    items: dict[str, dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=lambda: {"schema_version": SCHEMA_VERSION})
    path: Path | None = None

    @classmethod
    def loads(cls, text: str, *, path: Path | None = None) -> "ItemDocument":
        try:
            raw = json.loads(text, object_pairs_hook=_TrackedDict)
        except json.JSONDecodeError as exc:
            raise ItemDocumentError(
                f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        duplicates = _duplicate_paths(raw)
        if duplicates:
            raise ItemDocumentError(f"duplicate JSON key at {duplicates[0]}")
        if not isinstance(raw, dict):
            raise ItemDocumentError("top-level item document must be an object")
        metadata = raw.get(METADATA_KEY)
        if not isinstance(metadata, dict) or metadata.get("schema_version") != SCHEMA_VERSION:
            raise ItemDocumentError(f"{METADATA_KEY}.schema_version must be {SCHEMA_VERSION}")
        items: dict[str, dict[str, Any]] = {}
        for item_id, value in raw.items():
            if item_id == METADATA_KEY:
                continue
            if not isinstance(value, dict):
                raise ItemDocumentError(f"$.{item_id} must be an object")
            items[str(item_id)] = copy.deepcopy(dict(value))
        if not items:
            raise ItemDocumentError("item catalog must contain at least one item")
        return cls(items=items, metadata=copy.deepcopy(dict(metadata)), path=path)

    @classmethod
    def load(cls, path: Path) -> "ItemDocument":
        resolved = Path(path).resolve()
        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise ItemDocumentError(f"could not read {resolved}: {exc}") from exc
        return cls.loads(text, path=resolved)

    def clone(self) -> "ItemDocument":
        return ItemDocument(copy.deepcopy(self.items), copy.deepcopy(self.metadata), self.path)

    def mapping(self) -> dict[str, Any]:
        return {METADATA_KEY: copy.deepcopy(self.metadata), **copy.deepcopy(self.items)}

    def dumps(self) -> str:
        return json.dumps(self.mapping(), indent=2, ensure_ascii=False) + "\n"

    def normalized(self) -> dict[str, dict[str, Any]]:
        return normalize_item_definitions(copy.deepcopy(self.items))

    def add(self, item_id: str, value: Mapping[str, Any] | None = None) -> None:
        item_id = str(item_id).strip().lower()
        if not ITEM_ID_RE.fullmatch(item_id):
            raise ItemDocumentError("item id must match [a-z0-9_]+")
        if item_id in self.items:
            raise ItemDocumentError(f"item {item_id!r} already exists")
        self.items[item_id] = copy.deepcopy(dict(value or {
            "name": item_id.replace("_", " ").title(), "glyph": "?", "stack_max": 1,
            "tags": [], "legal_status": "legal", "effects": [],
        }))

    def duplicate(self, source_id: str, new_id: str) -> None:
        if source_id not in self.items:
            raise ItemDocumentError(f"unknown source item {source_id!r}")
        self.add(new_id, self.items[source_id])
        self.items[new_id]["name"] = str(self.items[new_id].get("name") or new_id).strip() + " Copy"

    def rename(self, old_id: str, new_id: str) -> None:
        new_id = str(new_id).strip().lower()
        if old_id not in self.items:
            raise ItemDocumentError(f"unknown item {old_id!r}")
        if not ITEM_ID_RE.fullmatch(new_id):
            raise ItemDocumentError("item id must match [a-z0-9_]+")
        if new_id != old_id and new_id in self.items:
            raise ItemDocumentError(f"item {new_id!r} already exists")
        rebuilt: dict[str, dict[str, Any]] = {}
        for item_id, value in self.items.items():
            rebuilt[new_id if item_id == old_id else item_id] = value
        self.items = rebuilt
        self.rewrite_internal_reference(old_id, new_id)

    def remove(self, item_id: str) -> None:
        if item_id not in self.items:
            raise ItemDocumentError(f"unknown item {item_id!r}")
        if len(self.items) <= 1:
            raise ItemDocumentError("the catalog must retain at least one item")
        del self.items[item_id]

    def rewrite_internal_reference(self, old_id: str, new_id: str) -> None:
        for value in self.items.values():
            trap = value.get("trap_profile")
            if isinstance(trap, dict) and trap.get("payload_item_id") == old_id:
                trap["payload_item_id"] = new_id
            container = value.get("container")
            if isinstance(container, dict) and isinstance(container.get("accepted_item_ids"), list):
                container["accepted_item_ids"] = [
                    new_id if entry == old_id else entry for entry in container["accepted_item_ids"]
                ]


def file_digest(path: Path) -> str:
    """Return a stable digest for one on-disk authoring source."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_item_references(
    root: Path,
    *,
    drawable_ids: Iterable[str] = (),
    item_ids: Iterable[str] = (),
) -> ItemReferenceSet:
    """Scan declared content and conservative Python literals on explicit reload.

    This is deliberately not a draw-time operation.  Its fingerprint lets the
    editor reject a save if a dependency changed after the author began editing.
    """
    root = Path(root).resolve()
    weapon_ids: set[str] = set()
    external: dict[str, list[str]] = {}
    errors: list[str] = []
    digest = hashlib.sha256()
    known_item_ids = {str(value).strip().lower() for value in item_ids if str(value).strip()}

    def relative_label(path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return str(path)

    def read_dependency(path: Path, *, required: bool) -> bytes | None:
        label = relative_label(path)
        digest.update(label.encode("utf-8", errors="replace"))
        try:
            payload = path.read_bytes()
        except OSError as exc:
            digest.update(f"!{type(exc).__name__}:{exc}".encode("utf-8", errors="replace"))
            if required:
                errors.append(f"{label}: could not scan dependency: {exc}")
            return None
        digest.update(payload)
        return payload

    def load_json_dependency(path: Path) -> Any:
        payload = read_dependency(path, required=True)
        if payload is None:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{relative_label(path)}: invalid JSON while scanning references: {exc}")
            return None

    def note(item_id: Any, label: str) -> None:
        key = str(item_id or "").strip().lower()
        if key:
            external.setdefault(key, []).append(label)

    weapons = load_json_dependency(root / "game/weapons.json")
    if isinstance(weapons, dict):
        for row in weapons.get("weapons", ()) if isinstance(weapons, dict) else ():
            if isinstance(row, dict) and str(row.get("id") or "").strip():
                weapon_ids.add(str(row["id"]).strip())

    for filename, fields in (
        ("loot_tables.json", ("item_id",)),
        ("herbal_recipes.json", ("output_item_id",)),
        ("mechanical_recipes.json", ("plan_item_id", "output_item_id")),
    ):
        path = root / "game" / filename
        data = load_json_dependency(path)
        if not isinstance(data, dict):
            continue
        for owner, value in data.items():
            if owner == METADATA_KEY:
                continue
            rows = value if isinstance(value, list) else (value,)
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                for field_name in fields:
                    if field_name in row:
                        suffix = f"[{index}]" if isinstance(value, list) else ""
                        note(row[field_name], f"game/{filename}: {owner}{suffix}.{field_name}")
                if filename == "mechanical_recipes.json":
                    components = row.get("components")
                    if isinstance(components, dict):
                        for item_id in components:
                            note(item_id, f"game/{filename}: {owner}.components.{item_id}")
                    choices = row.get("component_choices")
                    if isinstance(choices, list):
                        for choice_index, choice in enumerate(choices):
                            options = choice.get("options") if isinstance(choice, dict) else None
                            if isinstance(options, dict):
                                for item_id in options:
                                    note(
                                        item_id,
                                        f"game/{filename}: {owner}.component_choices[{choice_index}].options.{item_id}",
                                    )

    ignored_parts = {".git", ".venv", "venv", "__pycache__", "build", "dist"}
    for path in sorted(root.rglob("*.py")):
        if any(part in ignored_parts for part in path.relative_to(root).parts):
            continue
        payload = read_dependency(path, required=False)
        if payload is None:
            errors.append(f"{relative_label(path)}: could not scan Python item references")
            continue
        try:
            source_text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{relative_label(path)}: could not decode Python item references: {exc}")
            continue
        # Exact quoted identifiers are intentionally conservative: a candidate
        # in a test, fallback catalog, or comment still blocks silent rewrites.
        # This fast source scan only runs on explicit reload/save, never redraw.
        for line_number, line in enumerate(source_text.splitlines(), start=1):
            for match in PYTHON_ITEM_LITERAL_RE.finditer(line):
                item_id = match.group("item_id").lower()
                if item_id in known_item_ids:
                    note(
                        item_id,
                        f"{relative_label(path)}:{line_number} (Python source literal candidate)",
                    )

    drawable_root = root / "game/drawables"
    if drawable_root.is_dir():
        for path in sorted(value for value in drawable_root.rglob("*") if value.is_file()):
            read_dependency(path, required=False)

    return ItemReferenceSet(
        drawable_ids=frozenset(str(value) for value in drawable_ids),
        weapon_ids=frozenset(weapon_ids),
        external_item_references={
            key: tuple(dict.fromkeys(sorted(values))) for key, values in external.items()
        },
        fingerprint=digest.hexdigest(),
        scan_errors=tuple(dict.fromkeys(errors)),
    )


def _issue(severity: str, item_id: str, field_name: str, message: str) -> ValidationIssue:
    path = f"$.{item_id}" + (f".{field_name}" if field_name else "")
    return ValidationIssue(severity, "game/items.json", path, message)


def validate_item_document(
    document: ItemDocument,
    references: ItemReferenceSet | None = None,
    *,
    normalized_catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[ValidationIssue]:
    references = references or ItemReferenceSet()
    drawable_ids = set(references.drawable_ids) if references.drawable_ids else None
    issues = list(validate_items_mapping(
        document.items,
        drawable_ids=drawable_ids,
        source="game/items.json",
    ).issues)
    item_ids = set(document.items)
    if normalized_catalog is None:
        normalized_catalog = document.normalized()
    for item_id, item in document.items.items():
        runtime_item = normalized_catalog.get(item_id, {})
        if not ITEM_ID_RE.fullmatch(item_id):
            issues.append(_issue("error", item_id, "", "item id must match [a-z0-9_]+"))
        unknown = sorted(set(item) - KNOWN_ITEM_FIELDS)
        for field_name in unknown:
            issues.append(_issue(
                "error", item_id, field_name,
                "unknown item field; the runtime would discard it",
            ))
        if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
            issues.append(_issue("error", item_id, "name", "name must be a non-empty string"))
        if "description" in item and not isinstance(item["description"], str):
            issues.append(_issue("error", item_id, "description", "description must be a string"))
        for field_name in (
            "category", "legal_status", "weapon_id", "appearance_family", "appearance_drawable",
        ):
            if field_name in item and not isinstance(item[field_name], str):
                issues.append(_issue("error", item_id, field_name, "must be a string"))
        if not isinstance(item.get("glyph"), str) or not item.get("glyph"):
            issues.append(_issue("error", item_id, "glyph", "glyph must be a non-empty string"))
        elif len(item["glyph"]) != 1:
            issues.append(_issue("warning", item_id, "glyph", "runtime uses only the first character"))
        for field_name, minimum in (("stack_max", 1), ("inventory_slot_cost", 0)):
            if field_name in item and (
                not isinstance(item[field_name], int) or isinstance(item[field_name], bool)
                or item[field_name] < minimum
            ):
                issues.append(_issue("error", item_id, field_name, f"must be an integer >= {minimum}"))
        for field_name in ("tags", "appearance_slots"):
            if field_name in item and (
                not isinstance(item[field_name], list)
                or any(not isinstance(value, str) or not value.strip() for value in item[field_name])
            ):
                issues.append(_issue("error", item_id, field_name, "must be a list of non-empty strings"))
        if "effects" in item and (
            not isinstance(item["effects"], list)
            or any(not isinstance(value, dict) for value in item["effects"])
        ):
            issues.append(_issue("error", item_id, "effects", "must be a list of objects"))

        for profile_name in PROFILE_FIELDS:
            if profile_name not in item:
                continue
            value = item[profile_name]
            if profile_name in {"tool_profiles", "scratch_payout_table"}:
                if not isinstance(value, list):
                    issues.append(_issue("error", item_id, profile_name, "must be a JSON list"))
                    continue
                if profile_name == "tool_profiles":
                    for index, row in enumerate(value):
                        if not isinstance(row, dict):
                            issues.append(_issue("error", item_id, profile_name, f"entry {index} must be an object"))
                        else:
                            for key in sorted(set(row) - TOOL_PROFILE_KEYS):
                                issues.append(_issue("error", item_id, f"{profile_name}[{index}].{key}", "unknown tool-profile field"))
                elif item_id != "scratch_ticket":
                    issues.append(_issue("error", item_id, profile_name, "scratch payout tables only run on scratch_ticket"))
                continue
            if not isinstance(value, dict):
                issues.append(_issue("error", item_id, profile_name, "must be a JSON object"))
                continue
            allowed = PROFILE_KEYS.get(profile_name)
            if allowed is not None:
                for key in sorted(set(value) - allowed):
                    issues.append(_issue("error", item_id, f"{profile_name}.{key}", "unknown profile field; the runtime would discard it"))

        for profile_name in (
            "tool_profiles", "armor", "disguise", "container", "throw_profile",
            "trap_profile", "substance_profile", "lead_profile", "world_distribution",
        ):
            if item.get(profile_name) and not runtime_item.get(profile_name):
                issues.append(_issue(
                    "error", item_id, profile_name,
                    "profile has no usable runtime result and would be discarded",
                ))

        armor = item.get("armor")
        if isinstance(armor, dict):
            reduction = armor.get("damage_reduction")
            if not isinstance(reduction, (int, float)) or isinstance(reduction, bool) or not 0 < float(reduction) <= 0.85:
                issues.append(_issue("error", item_id, "armor.damage_reduction", "must be a number greater than 0 and no more than 0.85"))

        identification = item.get("identification_profile")
        if isinstance(identification, dict):
            for key in ("requires_identification", "auto_identify_on_use"):
                if key in identification and not isinstance(identification[key], bool):
                    issues.append(_issue("error", item_id, f"identification_profile.{key}", "must be boolean"))
            appraisal = identification.get("appraisal_fields")
            if appraisal is not None and (
                not isinstance(appraisal, list) or any(not isinstance(value, str) or not value.strip() for value in appraisal)
            ):
                issues.append(_issue("error", item_id, "identification_profile.appraisal_fields", "must be a list of non-empty strings"))

        condition = item.get("condition_profile")
        if isinstance(condition, dict):
            for key in ("supports_quality", "supports_durability"):
                if key in condition and not isinstance(condition[key], bool):
                    issues.append(_issue("error", item_id, f"condition_profile.{key}", "must be boolean"))
            if "default_quality" in condition and condition["default_quality"] not in {"poor", "standard", "good", "excellent"}:
                issues.append(_issue("error", item_id, "condition_profile.default_quality", "must be poor, standard, good, or excellent"))
            durability = condition.get("max_durability")
            if durability is not None and (
                not isinstance(durability, int) or isinstance(durability, bool) or durability < 0
            ):
                issues.append(_issue("error", item_id, "condition_profile.max_durability", "must be an integer >= 0"))

        fire = item.get("fire_profile")
        if isinstance(fire, dict):
            if "breakable" in fire and not isinstance(fire["breakable"], bool):
                issues.append(_issue("error", item_id, "fire_profile.breakable", "must be boolean"))
            flammability = fire.get("flammability")
            if flammability is not None and (
                not isinstance(flammability, (int, float)) or isinstance(flammability, bool)
                or not 0 <= float(flammability) <= 3
            ):
                issues.append(_issue("error", item_id, "fire_profile.flammability", "must be a number from 0 through 3"))
            for key in ("hp", "max_hp"):
                value = fire.get(key)
                if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                    issues.append(_issue("error", item_id, f"fire_profile.{key}", "must be an integer >= 0"))

        world = item.get("world_distribution")
        if isinstance(world, dict):
            weight = world.get("weight", 10)
            if not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= 100:
                issues.append(_issue("error", item_id, "world_distribution.weight", "must be an integer from 1 through 100"))
            channels = ("store_archetypes", "loot_archetypes", "carrier_archetypes")
            if not any(world.get(key) for key in channels):
                issues.append(_issue("error", item_id, "world_distribution", "requires at least one non-empty distribution channel"))
            for key in channels:
                value = world.get(key)
                if value is not None and (
                    not isinstance(value, list) or any(not isinstance(entry, str) or not entry.strip() for entry in value)
                ):
                    issues.append(_issue("error", item_id, f"world_distribution.{key}", "must be a list of non-empty strings"))

        scratch = item.get("scratch_payout_table")
        if isinstance(scratch, list):
            for index, row in enumerate(scratch):
                if not isinstance(row, dict):
                    issues.append(_issue("error", item_id, f"scratch_payout_table[{index}]", "must be an object"))
                    continue
                for key, minimum in (("credits", 0), ("weight", 1)):
                    value = row.get(key)
                    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                        issues.append(_issue("error", item_id, f"scratch_payout_table[{index}].{key}", f"must be an integer >= {minimum}"))

        drawable_id = str(item.get("appearance_drawable") or "").strip()
        if drawable_id and references.drawable_ids and drawable_id not in references.drawable_ids:
            issues.append(_issue("error", item_id, "appearance_drawable", f"unknown drawable id {drawable_id!r}"))
        weapon_id = str(item.get("weapon_id") or "").strip()
        if weapon_id and references.weapon_ids and weapon_id not in references.weapon_ids:
            issues.append(_issue("error", item_id, "weapon_id", f"unknown weapon id {weapon_id!r}"))
        trap = item.get("trap_profile")
        if isinstance(trap, dict):
            payload_id = str(trap.get("payload_item_id") or "").strip()
            if not payload_id:
                issues.append(_issue("error", item_id, "trap_profile.payload_item_id", "trap payload is required"))
            elif payload_id not in item_ids:
                issues.append(_issue("error", item_id, "trap_profile.payload_item_id", f"unknown item id {payload_id!r}"))
        container = item.get("container")
        if isinstance(container, dict) and isinstance(container.get("accepted_item_ids"), list):
            for target in container["accepted_item_ids"]:
                if isinstance(target, str) and target not in item_ids:
                    issues.append(_issue("error", item_id, "container.accepted_item_ids", f"unknown item id {target!r}"))
    deduplicated: list[ValidationIssue] = []
    seen: set[tuple[str, str, str, str]] = set()
    for issue in issues:
        key = (issue.severity, issue.source, issue.path, issue.message)
        if key not in seen:
            seen.add(key)
            deduplicated.append(issue)
    return deduplicated


def validate_item_file(
    path: Path,
    *,
    references: ItemReferenceSet | None = None,
) -> ValidationReport:
    references = references or ItemReferenceSet()
    report = ValidationReport()
    try:
        document = ItemDocument.load(Path(path))
    except ItemDocumentError as exc:
        report.error(str(Path(path)), "$", str(exc))
        return report
    report.issues.extend(validate_item_document(document, references))
    report.files_checked.add(str(Path(path)))
    return report


def atomic_write_item_document(path: Path, document: ItemDocument) -> None:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(document.dumps())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def profile_template(name: str, *, trap_payload_item_id: str = "") -> Any:
    if name not in PROFILE_TEMPLATES:
        raise ItemDocumentError(f"no template for profile {name!r}")
    template = copy.deepcopy(PROFILE_TEMPLATES[name])
    if name == "trap_profile" and trap_payload_item_id:
        template["payload_item_id"] = str(trap_payload_item_id).strip().lower()
    return template


def format_item_issue(issue: ValidationIssue) -> str:
    return f"{issue.severity.upper()} {issue.path}: {issue.message}"
