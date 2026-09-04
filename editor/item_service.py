"""Shared, cached item-catalog state for Workbench modes."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from game.content_validation import ValidationIssue
from game.item_content import (
    ItemDocument,
    ItemDocumentError,
    ItemReferenceSet,
    atomic_write_item_document,
    file_digest,
    format_item_issue,
    load_item_references,
    validate_item_document,
    validate_item_file,
)

if TYPE_CHECKING:
    from editor.workbench import DrawableCatalogService, GameSource


@dataclass
class ItemCatalogService:
    document: ItemDocument | None = None
    normalized: dict[str, dict] = field(default_factory=dict)
    references: ItemReferenceSet = field(default_factory=ItemReferenceSet)
    issues: list[ValidationIssue] = field(default_factory=list)
    root: Path | None = None
    path: Path | None = None
    error: str = ""
    revision: int = 0
    source_digest: str = ""

    def reload(self, game: "GameSource", drawables: "DrawableCatalogService") -> bool:
        previous_root = self.root
        self.root = game.root
        self.path = None if game.root is None else game.root / "game/items.json"
        self.error = ""
        if self.path is None:
            self.document = None
            self.normalized = {}
            self.references = ItemReferenceSet()
            self.issues = []
            self.source_digest = ""
            self.revision += 1
            return True
        try:
            document = ItemDocument.load(self.path)
            references = load_item_references(
                game.root,
                drawable_ids=drawables.catalog.definitions,
                ground_drawable_ids=(
                    drawable_id
                    for drawable_id, definition in drawables.catalog.definitions.items()
                    if definition.presentation("ground") is not None
                ),
                item_ids=document.items,
            )
            if references.scan_errors:
                raise ItemDocumentError(references.scan_errors[0])
            normalized = document.normalized()
            issues = validate_item_document(
                document,
                references,
                normalized_catalog=normalized,
            )
            source_digest = file_digest(self.path)
        except (OSError, ValueError, ItemDocumentError) as exc:
            self.error = str(exc)
            if previous_root != game.root:
                self.document = None
                self.normalized = {}
                self.references = ItemReferenceSet()
                self.issues = []
                self.source_digest = ""
                self.revision += 1
            return False
        self.document = document
        self.references = references
        self.normalized = normalized
        self.issues = issues
        self.source_digest = source_digest
        self.revision += 1
        return True

    def save(self, document: ItemDocument) -> None:
        if self.path is None or self.root is None:
            raise ItemDocumentError("set a Bakerrrr root before saving items")
        expected = (self.root / "game/items.json").resolve()
        if self.path.resolve() != expected:
            raise ItemDocumentError("item catalog saves are restricted to game/items.json")
        if document.path is None or document.path.resolve() != self.path.resolve():
            raise ItemDocumentError(
                "this item draft belongs to a different game root; switch back or reload before saving"
            )
        try:
            current_digest = file_digest(self.path)
        except OSError as exc:
            raise ItemDocumentError(f"could not verify game/items.json before saving: {exc}") from exc
        if not self.source_digest or current_digest != self.source_digest:
            raise ItemDocumentError(
                "game/items.json changed outside this editor; reload before saving so no work is overwritten"
            )

        current_references = load_item_references(
            self.root,
            drawable_ids=self.references.drawable_ids,
            ground_drawable_ids=self.references.ground_drawable_ids,
            item_ids=document.items,
        )
        if current_references.scan_errors:
            raise ItemDocumentError(current_references.scan_errors[0])
        if current_references.fingerprint != self.references.fingerprint:
            raise ItemDocumentError(
                "an item dependency changed outside this editor; reload before renaming, deleting, or saving"
            )

        normalized = document.normalized()
        issues = validate_item_document(
            document,
            current_references,
            normalized_catalog=normalized,
        )
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            raise ItemDocumentError(format_item_issue(errors[0]))

        descriptor, candidate_name = tempfile.mkstemp(
            prefix=".items-candidate.", suffix=".json", dir=self.path.parent,
        )
        candidate = Path(candidate_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(document.dumps())
                handle.flush()
                os.fsync(handle.fileno())
            report = validate_item_file(candidate, references=current_references)
            if report.errors:
                raise ItemDocumentError(format_item_issue(report.errors[0]))
        finally:
            try:
                candidate.unlink()
            except OSError:
                pass

        atomic_write_item_document(self.path, document)
        # Reload what was actually written.  Every consumer sees one revision.
        replacement = ItemDocument.load(self.path)
        self.document = replacement
        self.references = current_references
        self.normalized = replacement.normalized()
        self.issues = validate_item_document(
            replacement,
            self.references,
            normalized_catalog=self.normalized,
        )
        self.source_digest = file_digest(self.path)
        self.error = ""
        self.revision += 1

    def external_references_to(self, item_id: str) -> tuple[str, ...]:
        return self.references.references_to(item_id)
