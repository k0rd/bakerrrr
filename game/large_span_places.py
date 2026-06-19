"""Helpers for registering naturally generated multi-property places."""

from __future__ import annotations

from game.organizations import ensure_property_organization, seed_property_organization_defaults
from game.property_access import (
    COMMON_AREA_ROOM_KINDS,
    FINANCE_SERVICE_FALLBACKS,
    default_site_services_for_archetype,
)
from game.vehicles import vehicle_services_for_archetype


def _clean(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _text(value):
    return str(value or "").strip()


def _slug(value):
    clean = _clean(value)
    return clean.replace(":", "_").replace("/", "_") or "span"


def _span_association_spec(span_kind, span_id, span_name, parent_name):
    span_kind = _clean(span_kind)
    if span_kind not in {"indoor_city_market", "non_city_compound_market", "vertical_mixed_use"}:
        return None
    base_name = _text(span_name) or _text(parent_name) or "Shared Market"
    if span_kind == "vertical_mixed_use":
        suffix = "Tenant Association"
    else:
        suffix = "Market Association"
    return {
        "organization_key": f"span_association:{_slug(span_id)}",
        "organization_name": f"{base_name} {suffix}",
        "organization_kind": "community",
        "tags": ("trade_guild", "market_association", "org_role:collective", span_kind),
        "link_kind": "service_host",
        "membership_kind": "membership",
        "membership_title": "market member",
        "membership_roles": ("owner", "manager", "staff"),
        "allow_owner_membership": True,
    }


def _dedupe(values):
    out = []
    seen = set()
    for value in values:
        clean = _text(value)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _bounds_for_cells(cells):
    xs = [int(cell[0]) for cell in cells]
    ys = [int(cell[1]) for cell in cells]
    if not xs or not ys:
        return {}
    return {
        "left": min(xs),
        "right": max(xs),
        "top": min(ys),
        "bottom": max(ys),
    }


def _structure_cells_for_building(sim, building_id):
    building_id = _text(building_id)
    if not building_id:
        return []
    rows = []
    for key, info in getattr(sim, "structure_cells", {}).items():
        if not isinstance(key, tuple) or len(key) < 3 or not isinstance(info, dict):
            continue
        if _text(info.get("building_id")) != building_id:
            continue
        x, y, z = int(key[0]), int(key[1]), int(key[2])
        room_kind = _clean(info.get("room_kind"))
        common_kind = _clean(info.get("common_area_kind"))
        common = bool(common_kind or room_kind in COMMON_AREA_ROOM_KINDS)
        rows.append({
            "x": x,
            "y": y,
            "z": z,
            "room_kind": room_kind,
            "common": common,
        })
    rows.sort(key=lambda row: (int(row["z"]), int(row["y"]), int(row["x"])))
    return rows


def _partition_cells(cells, count):
    cells = list(cells)
    count = max(1, int(count))
    if not cells:
        return []
    xs = [int(row["x"]) for row in cells]
    ys = [int(row["y"]) for row in cells]
    if (max(xs) - min(xs)) >= (max(ys) - min(ys)):
        cells.sort(key=lambda row: (int(row["x"]), int(row["y"])))
    else:
        cells.sort(key=lambda row: (int(row["y"]), int(row["x"])))
    count = min(count, len(cells))
    base = len(cells) // count
    extra = len(cells) % count
    parts = []
    cursor = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        parts.append(cells[cursor:cursor + size])
        cursor += size
    return parts


def _anchor_for_cells(cells):
    if not cells:
        return None
    cx = sum(int(row["x"]) for row in cells) / float(len(cells))
    cy = sum(int(row["y"]) for row in cells) / float(len(cells))
    return min(
        cells,
        key=lambda row: (
            abs(int(row["x"]) - cx) + abs(int(row["y"]) - cy),
            int(row["y"]),
            int(row["x"]),
        ),
    )


def _specs_by_floor(specs, available_floors):
    floors = tuple(sorted(int(floor) for floor in set(available_floors)))
    if not floors:
        floors = (0,)
    grouped = {}
    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            continue
        try:
            floor = int(spec.get("floor", floors[index % len(floors)]))
        except (TypeError, ValueError):
            floor = floors[index % len(floors)]
        if floor not in floors:
            floor = min(floors, key=lambda candidate: (abs(candidate - floor), candidate))
        grouped.setdefault(floor, []).append(spec)
    return grouped


def _service_seed_token(parent_building_id, archetype, index):
    return f"{_text(parent_building_id)}:span-child:{int(index)}:{_clean(archetype)}"


def _child_services(archetype, parent_building_id, index):
    archetype = _clean(archetype)
    seed_token = _service_seed_token(parent_building_id, archetype, index)
    site_services = list(default_site_services_for_archetype(archetype, seed_token=seed_token))
    site_services.extend(vehicle_services_for_archetype(archetype))
    return _dedupe(FINANCE_SERVICE_FALLBACKS.get(archetype, ())), _dedupe(site_services), seed_token


def _ensure_anchor(ensure_walkable, sim, x, y, z):
    if ensure_walkable is None:
        return
    try:
        ensure_walkable(sim, x, y, z, glyph=".")
        return
    except TypeError:
        pass
    try:
        ensure_walkable(x, y, z, glyph=".")
        return
    except TypeError:
        pass
    ensure_walkable(x, y, z)


def register_large_span_child_properties(
    sim,
    *,
    parent_source,
    parent_layout,
    parent_building_id,
    chunk_key,
    area_type,
    rng,
    ensure_walkable,
    district=None,
):
    """Register real child properties for generated span metadata."""

    if not isinstance(parent_source, dict) or not isinstance(parent_layout, dict):
        return []
    span_kind = _clean(parent_source.get("span_kind"))
    span_id = _text(parent_source.get("span_id"))
    if not span_kind or not span_id:
        return []

    specs = []
    for raw in tuple(parent_source.get("tenant_specs", ()) or ()):
        if isinstance(raw, dict):
            specs.append(dict(raw))
    for raw in tuple(parent_source.get("housing_specs", ()) or ()):
        if isinstance(raw, dict):
            specs.append(dict(raw))
    if not specs:
        return []

    structure_rows = _structure_cells_for_building(sim, parent_building_id)
    usable_rows = [row for row in structure_rows if not bool(row.get("common"))]
    if not usable_rows:
        usable_rows = list(structure_rows)
    if not usable_rows:
        return []

    available_floors = sorted({int(row["z"]) for row in usable_rows})
    grouped_specs = _specs_by_floor(specs, available_floors)
    parent_archetype = _clean(parent_source.get("archetype") or parent_source.get("kind"))
    span_name = _text(parent_source.get("span_name"))
    parent_name = span_name or _text(parent_source.get("business_name") or parent_source.get("name") or parent_archetype)
    parent_placement = dict(parent_layout.get("placement", {})) if isinstance(parent_layout.get("placement"), dict) else {}
    parent_entry = dict(parent_layout.get("entry", {})) if isinstance(parent_layout.get("entry"), dict) else {}
    parent_profile = dict(parent_source.get("placement_profile", {})) if isinstance(parent_source.get("placement_profile"), dict) else None
    common_kinds = sorted(COMMON_AREA_ROOM_KINDS)
    association_spec = _span_association_spec(span_kind, span_id, span_name, parent_name)
    records = []
    child_index = 0

    for floor, floor_specs in sorted(grouped_specs.items()):
        floor_rows = [row for row in usable_rows if int(row["z"]) == int(floor)]
        if not floor_rows:
            continue
        partitions = _partition_cells(floor_rows, len(floor_specs))
        for spec, cells in zip(floor_specs, partitions):
            if not cells:
                continue
            anchor = _anchor_for_cells(cells)
            if not anchor:
                continue
            archetype = _clean(spec.get("archetype"))
            if not archetype:
                continue
            child_kind = _clean(spec.get("child_kind")) or "tenant"
            child_name = _text(spec.get("name") or spec.get("business_name")) or archetype.replace("_", " ").title()
            business_name = _text(spec.get("business_name")) or (child_name if child_kind == "tenant" else "")
            finance_services, site_services, seed_token = _child_services(archetype, parent_building_id, child_index)
            is_storefront = bool(spec.get("is_storefront")) or child_kind == "tenant"
            public = bool(spec.get("public")) or bool(is_storefront and child_kind == "tenant")
            if child_kind == "housing":
                public = bool(spec.get("public"))
            if child_kind == "shelter":
                public = True

            cell_pairs = [(int(row["x"]), int(row["y"])) for row in cells]
            bounds = _bounds_for_cells(cell_pairs)
            metadata = {
                "archetype": archetype,
                "building_id": _text(parent_building_id),
                "parent_building_id": _text(parent_building_id),
                "span_id": span_id,
                "span_kind": span_kind,
                "span_name": span_name or parent_name or None,
                "span_child": True,
                "span_child_kind": child_kind,
                "span_parent_archetype": parent_archetype,
                "span_parent_name": parent_name or None,
                "floor": int(floor),
                "floors": 1,
                "basement_levels": 0,
                "rooms": sorted({row.get("room_kind") for row in cells if row.get("room_kind")}) or [archetype],
                "common_area_room_kinds": common_kinds,
                "common_area_kinds": common_kinds,
                "shared_area_interests": [{
                    "building_id": _text(parent_building_id),
                    "common_area_kinds": common_kinds,
                    "authority_reason": "shared_interest",
                    "protects": True,
                    "warns": True,
                }],
                "footprint": bounds,
                "footprint_cells": [
                    {"x": int(cell_x), "y": int(cell_y)}
                    for cell_x, cell_y in sorted(set(cell_pairs))
                ],
                "placement": parent_placement,
                "placement_profile": parent_profile,
                "entry": parent_entry,
                "purchase_cost": int(rng.randint(95, 260)),
                "finance_services": finance_services,
                "site_services": site_services,
                "site_service_seed_token": seed_token,
                "is_storefront": bool(is_storefront),
                "public": bool(public),
                "business_name": business_name or None,
                "business_founder_name": _text(spec.get("business_founder_name")) or None,
                "business_founder_first_name": _text(spec.get("business_founder_first_name")) or None,
                "business_founder_last_name": _text(spec.get("business_founder_last_name")) or None,
                "chunk": tuple(chunk_key),
            }
            if isinstance(association_spec, dict):
                metadata["affiliate_organizations"] = [dict(association_spec)]
            if child_kind in {"housing", "shelter"}:
                metadata["is_storefront"] = False

            x = int(anchor["x"])
            y = int(anchor["y"])
            z = int(anchor["z"])
            _ensure_anchor(ensure_walkable, sim, x, y, z)
            property_id = sim.register_property(
                name=child_name,
                kind="building",
                x=x,
                y=y,
                z=z,
                owner_eid=None,
                owner_tag="public" if public else area_type,
                metadata=metadata,
            )
            prop = sim.properties.get(property_id)
            seed_property_organization_defaults(prop, district=district)
            ensure_property_organization(sim, prop)
            records.append({
                "id": property_id,
                "kind": "building",
                "x": x,
                "y": y,
                "z": z,
                "archetype": archetype,
                "building_id": _text(parent_building_id),
                "span_id": span_id,
                "span_kind": span_kind,
                "span_child": True,
                "span_child_kind": child_kind,
            })
            child_index += 1
    return records
