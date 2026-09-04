"""Declarative content-root registry shared by Workbench modes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContentDomainSpec:
    domain_id: str
    label: str
    relative_root: Path
    extensions: tuple[str, ...]
    writable: bool = True
    single_file: bool = False


CONTENT_DOMAIN_REGISTRY: dict[str, ContentDomainSpec] = {}


def register_content_domain(spec: ContentDomainSpec) -> ContentDomainSpec:
    if not spec.domain_id:
        raise ValueError("Content domain needs domain_id")
    if spec.domain_id in CONTENT_DOMAIN_REGISTRY:
        raise ValueError(f"Duplicate content domain: {spec.domain_id}")
    CONTENT_DOMAIN_REGISTRY[spec.domain_id] = spec
    return spec


DRAWABLE_DOMAIN = register_content_domain(
    ContentDomainSpec(
        domain_id="drawables",
        label="Drawable geometry",
        relative_root=Path("game/drawables"),
        extensions=(".bkdraw",),
    )
)

BUILDING_STAMP_DOMAIN = register_content_domain(
    ContentDomainSpec(
        domain_id="building_stamps",
        label="Building shell stamps",
        relative_root=Path("game/building_stamps"),
        extensions=(".json",),
    )
)

ITEM_DOMAIN = register_content_domain(
    ContentDomainSpec(
        domain_id="items",
        label="Item catalog",
        relative_root=Path("game/items.json"),
        extensions=(".json",),
        single_file=True,
    )
)
