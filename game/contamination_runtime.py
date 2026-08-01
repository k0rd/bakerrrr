"""Source-neutral contamination releases and sparse underground remediation beds.

Contamination is inert unless something releases it.  Settled sediment remains
world-generation history; this module never grows or spreads it on a tick.
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from game.flora_genetics import fungal_mutation_glow_color, preroll_fungal_mutation_glow
from game.flora_runtime import load_flora_catalog, register_flora_patch, update_flora_patch
from game.system_support.environment_hazard_runtime import (
    environment_hazard_asset_metadata,
    environment_hazard_profile,
    normalize_environment_hazard_specs,
)


BLACKWASH_PROFILE = "spent_cell_blackwash"
REMEDIATION_SPECIES = ("cellar_cap", "gray_oyster")
INDICATOR_SPECIES = "glassgill"
ACCUMULATOR_CAPACITY = 3.0
ACCUMULATOR_ABSORPTION_PER_RELEASE = 0.8
CONTAMINANT_INDICATOR_CLASSES = (
    "heavy_metals",
    "biological",
    "chemical_toxins",
    "petrochemical",
    "radiological",
)
CONTAMINANT_INDICATOR_COLOR_KEYS = (
    "flora_indicator_glow_amber",
    "flora_indicator_glow_blue",
    "flora_indicator_glow_green",
    "flora_indicator_glow_violet",
    "flora_indicator_glow_rose",
)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def contamination_release_load(spec):
    """Scale a release so higher-grade corporate tech has a dirtier shadow."""

    spec = spec if isinstance(spec, dict) else {}
    base_load = max(0.05, _safe_float(spec.get("contamination_load"), 1.0))
    technology_grade = max(1.0, _safe_float(spec.get("technology_grade"), 1.0))
    multiplier = 1.0 + ((technology_grade - 1.0) * 0.5)
    return round(base_load * multiplier, 3), round(multiplier, 3)


def contamination_indicator_legend(sim):
    """Return the stable, run-specific contaminant-class color permutation."""

    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        traits = {}
        sim.world_traits = traits
    stored = traits.get("contamination_indicator_legend")
    if isinstance(stored, dict) and all(
        str(stored.get(class_id, "") or "") in CONTAMINANT_INDICATOR_COLOR_KEYS
        for class_id in CONTAMINANT_INDICATOR_CLASSES
    ):
        return {class_id: str(stored[class_id]) for class_id in CONTAMINANT_INDICATOR_CLASSES}

    colors = list(CONTAMINANT_INDICATOR_COLOR_KEYS)
    random.Random(f"{getattr(sim, 'seed', 0)}:contamination-indicator-legend:v1").shuffle(colors)
    legend = dict(zip(CONTAMINANT_INDICATOR_CLASSES, colors))
    traits["contamination_indicator_legend"] = dict(legend)
    return legend


def contamination_indicator_color(sim, contaminant_class):
    class_id = str(contaminant_class or "").strip().lower()
    if class_id not in CONTAMINANT_INDICATOR_CLASSES:
        class_id = "chemical_toxins"
    return contamination_indicator_legend(sim)[class_id]


def _invalidate_lighting_cache(sim):
    traits = getattr(sim, "world_traits", None)
    lighting = traits.get("lighting") if isinstance(traits, dict) else None
    if not isinstance(lighting, dict):
        return
    for key in ("source_cache_key", "source_spatial_cache_key"):
        lighting.pop(key, None)


def _take_contamination_load(hazard, *, capacity_remaining=ACCUMULATOR_CAPACITY):
    if not isinstance(hazard, dict):
        return 0.0
    metadata = hazard.get("metadata") if isinstance(hazard.get("metadata"), dict) else {}
    free_load = max(0.0, _safe_float(metadata.get("contamination_load")))
    absorbed = min(
        free_load,
        max(0.0, _safe_float(capacity_remaining)),
        ACCUMULATOR_ABSORPTION_PER_RELEASE,
    )
    if absorbed <= 0.0:
        return 0.0
    metadata["contamination_load"] = round(free_load - absorbed, 3)
    metadata["remediation_absorbed_load"] = round(
        max(0.0, _safe_float(metadata.get("remediation_absorbed_load"))) + absorbed,
        3,
    )
    metadata["remediation_last_absorption_tick"] = int(metadata.get("last_release_tick", 0) or 0)
    return round(absorbed, 3)


def _absorb_with_existing_accumulator(sim, hazard):
    if not isinstance(hazard, dict):
        return 0.0
    for record in tuple(getattr(sim, "flora_patches", {}).values()):
        if not isinstance(record, dict):
            continue
        if str(record.get("contamination_property_id", "") or "") != str(hazard.get("id", "") or ""):
            continue
        if str(record.get("environmental_morph", "") or "").strip().lower() != "accumulator":
            continue
        stored = max(0.0, _safe_float(record.get("absorbed_toxin_load")))
        capacity = max(stored, _safe_float(record.get("toxin_absorption_capacity"), ACCUMULATOR_CAPACITY))
        absorbed = _take_contamination_load(hazard, capacity_remaining=capacity - stored)
        if absorbed <= 0.0:
            return 0.0
        stored = round(stored + absorbed, 3)
        update_flora_patch(sim, record.get("id"), {
            "absorbed_toxin_load": stored,
            "bioluminescent_intensity": round(min(0.52, 0.2 + (stored * 0.1)), 3),
            "last_absorption_tick": int(getattr(sim, "tick", 0) or 0),
        })
        _invalidate_lighting_cache(sim)
        return absorbed
    return 0.0


def _existing_contamination(sim, spec):
    key = (int(spec["x"]), int(spec["y"]), int(spec["z"]))
    for property_id in tuple(getattr(sim, "property_anchor_index", {}).get(key, ()) or ()):
        prop = getattr(sim, "properties", {}).get(property_id)
        metadata = prop.get("metadata") if isinstance(prop, dict) else None
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("hazard_profile", "") or "").strip().lower() == str(spec.get("profile", "")).strip().lower():
            return prop
    return None


def _append_property_record(sim, prop, records=None):
    if not isinstance(prop, dict):
        return
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    record = {
        "id": prop.get("id"),
        "kind": prop.get("kind", "asset"),
        "x": int(prop.get("x", 0) or 0),
        "y": int(prop.get("y", 0) or 0),
        "z": int(prop.get("z", 0) or 0),
        "archetype": metadata.get("archetype"),
        "building_id": None,
    }
    if isinstance(records, list):
        if not any(isinstance(row, dict) and str(row.get("id")) == str(prop.get("id")) for row in records):
            records.append(record)
        return
    sync = getattr(sim, "_sync_property_chunk_record", None)
    if callable(sync):
        sync(prop.get("id"), prop)
        return
    key = tuple(sim.chunk_coords(record["x"], record["y"]))
    bucket = getattr(sim, "chunk_property_records", {}).setdefault(key, [])
    if not any(isinstance(row, dict) and str(row.get("id")) == str(prop.get("id")) for row in bucket):
        bucket.append(record)


def materialize_contamination_release(sim, spec, *, key=None, linked_property_id=None, records=None):
    """Create or intensify one exact-cell contamination hazard."""

    normalized = normalize_environment_hazard_specs((spec,))
    if not normalized:
        return None
    spec = dict(normalized[0])
    profile = environment_hazard_profile(spec.get("profile"))
    if not isinstance(profile.get("contaminant"), dict):
        return None
    load, technology_multiplier = contamination_release_load(spec)
    existing = _existing_contamination(sim, spec)
    if isinstance(existing, dict):
        metadata = existing.setdefault("metadata", {})
        metadata["contamination_load"] = round(
            max(0.0, _safe_float(metadata.get("contamination_load"))) + load,
            3,
        )
        metadata["release_count"] = int(metadata.get("release_count", 1) or 1) + 1
        metadata["active_release"] = True
        metadata["last_release_tick"] = int(getattr(sim, "tick", 0) or 0)
        absorbed = _absorb_with_existing_accumulator(sim, existing)
        _append_property_record(sim, existing, records=records)
        sim.emit(Event(
            "contamination_materialized",
            property_id=existing.get("id"),
            profile=spec.get("profile"),
            contamination_load=metadata["contamination_load"],
            absorbed_load=absorbed,
            intensified=True,
        ))
        return existing.get("id")

    chunk_key = tuple(key) if isinstance(key, (tuple, list)) and len(key) == 2 else tuple(sim.chunk_coords(spec["x"], spec["y"]))
    metadata = environment_hazard_asset_metadata(spec, key=chunk_key, linked_property_id=linked_property_id)
    metadata.update({
        "contamination_load": load,
        "technology_pollution_multiplier": technology_multiplier,
        "pollution_yield_rule": "increases_with_manufacturing_grade",
        "active_release": True,
        "release_count": 1,
        "last_release_tick": int(getattr(sim, "tick", 0) or 0),
        "source_accountability": "corporate_manufacturing_externality",
        "remediation_stewardship": "underground_residents",
    })
    property_id = sim.register_property(
        name=str(spec.get("name", profile.get("name", "Contamination"))).strip() or "Contamination",
        kind="asset",
        x=int(spec["x"]),
        y=int(spec["y"]),
        z=int(spec["z"]),
        owner_eid=None,
        owner_tag="unowned",
        metadata=metadata,
    )
    prop = getattr(sim, "properties", {}).get(property_id)
    _append_property_record(sim, prop, records=records)
    sim.emit(Event(
        "contamination_materialized",
        property_id=property_id,
        profile=spec.get("profile"),
        contamination_load=load,
        absorbed_load=0.0,
        intensified=False,
    ))
    return property_id


def _property_cells(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    z = int(prop.get("z", 0) or 0) if isinstance(prop, dict) else 0
    cells = []
    for cell in tuple(metadata.get("footprint_cells", ()) or ()):
        if not isinstance(cell, dict):
            continue
        try:
            cells.append((int(cell.get("x")), int(cell.get("y")), z))
        except (TypeError, ValueError):
            continue
    if cells:
        return tuple(dict.fromkeys(cells))
    footprint = metadata.get("footprint") if isinstance(metadata.get("footprint"), dict) else {}
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return ()
    excluded = {
        (int(cell.get("x")), int(cell.get("y")))
        for cell in tuple(metadata.get("footprint_excluded_cells", ()) or ())
        if isinstance(cell, dict) and cell.get("x") is not None and cell.get("y") is not None
    }
    return tuple(
        (x, y, z)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        if (x, y) not in excluded
    )


def _remediation_candidates(sim, hazard, linked_prop):
    hx, hy = int(hazard["x"]), int(hazard["y"])
    occupied_flora = {
        (int(row.get("x", 0) or 0), int(row.get("y", 0) or 0), int(row.get("z", 0) or 0))
        for row in getattr(sim, "flora_patches", {}).values()
        if isinstance(row, dict)
    }
    properties = getattr(sim, "properties", {})
    rows = []
    for x, y, z in _property_cells(linked_prop):
        distance = abs(x - hx) + abs(y - hy)
        property_ids = tuple(getattr(sim, "property_anchor_index", {}).get((x, y, z), ()) or ())
        has_asset = any(
            str((properties.get(property_id) or {}).get("kind", "")).strip().lower() == "asset"
            for property_id in property_ids
        )
        if distance <= 0 or (x, y, z) in occupied_flora or has_asset:
            continue
        tile = sim.tilemap.tile_at(x, y, z)
        if tile is None or not bool(getattr(tile, "walkable", False)):
            continue
        rows.append((distance, y, x, (x, y, z)))
    return tuple(row[3] for row in sorted(rows))


def _fungus_record(
    row,
    *,
    record_id,
    position,
    chunk_key,
    hazard,
    role,
    genetics,
    absorbed_load=0.0,
    indicator_color_key=None,
):
    x, y, z = position
    metadata = hazard.get("metadata") if isinstance(hazard.get("metadata"), dict) else {}
    accumulator = role == "accumulator"
    indicator = role == "contaminant_indicator"
    variant_seed = random.Random(record_id).randrange(1, 2**31 - 1)
    genetics = preroll_fungal_mutation_glow(genetics, seed=variant_seed)
    glow_color_key = fungal_mutation_glow_color(genetics)
    name = str(row.get("name", row.get("id", "mushroom"))).strip()
    tags = list(row.get("tags", ()))
    if accumulator:
        tags = [tag for tag in tags if str(tag).strip().lower() != "edible"]
        tags.extend(("toxin_accumulator", "bioluminescent"))
    elif indicator:
        tags.extend(("contaminant_indicator", "bioluminescent"))
    display_color_key = (
        glow_color_key
        if accumulator
        else str(indicator_color_key or "flora_indicator_glow_blue")
        if indicator
        else str((tuple(row.get("colors", ())) or (row.get("render_key"),))[0])
    )
    record = {
        "id": record_id,
        "plant_id": row.get("id"),
        "name": f"black-veined {name}" if accumulator else name,
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "chunk": [int(chunk_key[0]), int(chunk_key[1])],
        "stage": "mature",
        "variant_seed": variant_seed,
        "color_key": display_color_key,
        "growth_form": "fungus",
        "glyph": "*",
        "render_key": row.get("render_key", "flora_flower_white"),
        "spread_state": "rooted",
        "spread_direction": None,
        "cluster_id": f"flora:remediation:{hazard.get('id')}",
        "tags": list(dict.fromkeys(tuple(tags) + ("tended", "filter_bed"))),
        "rarity": row.get("rarity", "common"),
        "genetics": dict(genetics),
        "harvest_potential": {} if accumulator else dict(row.get("harvest_potential", {}) or {}),
        "wild_spawn": False,
        "cultivation_allowed": False,
        "crossbreed_allowed": False,
        "ecology_origin": "resident_remediation",
        "tended_filter_bed": True,
        "filter_bed_role": role,
        "contamination_property_id": hazard.get("id"),
        "contaminant_signature": metadata.get("contaminant_signature"),
        "contaminant_load_snapshot": metadata.get("contamination_load"),
        "source_accountability": metadata.get("source_accountability"),
        "remediation_stewardship": "underground_residents",
        "ecology_note": (
            "Dark veins gather toward the seep, holding a cool light under each cap."
            if accumulator
            else ""
            if indicator
            else "The caps remain pale and firm on the clean side of the filter line."
        ),
    }
    if accumulator:
        record.update({
            "environmental_morph": "accumulator",
            "environmental_reaction": "electrochemical_waste_accumulation",
            "mutation_kind": "environmental_expression",
            "harvest_locked": True,
            "harvest_lock_reason": "working_filter_bed",
            "absorbed_toxin_load": round(max(0.0, _safe_float(absorbed_load)), 3),
            "toxin_absorption_capacity": ACCUMULATOR_CAPACITY,
            "toxin_absorption_per_release": ACCUMULATOR_ABSORPTION_PER_RELEASE,
            "metabolic_role": "toxin_absorption_only",
            "energy_conversion": "absorbed_toxin_to_bioluminescence",
            "bioluminescent": True,
            "bioluminescent_color_key": glow_color_key,
            "bioluminescent_light_profile": glow_color_key.removeprefix("flora_"),
            "bioluminescent_radius": 2,
            "bioluminescent_intensity": round(min(0.52, 0.2 + (max(0.0, _safe_float(absorbed_load)) * 0.1)), 3),
        })
    elif indicator:
        record.update({
            "environmental_morph": "contaminant_indicator",
            "harvest_locked": True,
            "harvest_lock_reason": "tended_fungal_bed",
            "metabolic_role": "contaminant_indication_only",
            "contamination_load_effect": 0.0,
            "indicator_contaminant_class": str(metadata.get("contaminant_class", "") or "chemical_toxins"),
            "indicator_legend_version": 1,
            "bioluminescent": True,
            "bioluminescent_color_key": display_color_key,
            "bioluminescent_light_profile": display_color_key.removeprefix("flora_"),
            "bioluminescent_radius": 1,
            "bioluminescent_intensity": 0.22,
            "bioluminescent_signal_strength": 1.0,
        })
    else:
        record["harvest_item_id"] = "mushroom_caps"
    return record


def ensure_underground_remediation_flora(sim, chunk, *, property_records=None):
    """Lay a sparse four-mushroom arrangement around eligible old seepage."""

    if not isinstance(chunk, dict):
        return ()
    key = (int(chunk.get("cx", 0) or 0), int(chunk.get("cy", 0) or 0))
    completed = getattr(sim, "underground_remediation_chunks", None)
    if not isinstance(completed, set):
        completed = set(tuple(value) for value in tuple(completed or ()) if isinstance(value, (tuple, list)) and len(value) == 2)
        sim.underground_remediation_chunks = completed
    if key in completed:
        return ()
    catalog = load_flora_catalog()
    if not all(species in catalog for species in REMEDIATION_SPECIES + (INDICATOR_SPECIES,)):
        return ()
    made = []
    record_ids = tuple(
        str(record.get("id", "") or "")
        for record in tuple(property_records or ())
        if isinstance(record, dict) and str(record.get("id", "") or "")
    )
    if record_ids:
        properties = tuple(
            prop
            for property_id in record_ids
            for prop in (getattr(sim, "properties", {}).get(property_id),)
            if isinstance(prop, dict)
        )
    else:
        properties = tuple(getattr(sim, "properties", {}).values())
    for hazard in properties:
        if not isinstance(hazard, dict):
            continue
        metadata = hazard.get("metadata") if isinstance(hazard.get("metadata"), dict) else {}
        if str(metadata.get("hazard_profile", "") or "").strip().lower() != BLACKWASH_PROFILE:
            continue
        if not bool(metadata.get("resident_remediation_eligible")):
            continue
        if tuple(sim.chunk_coords(int(hazard.get("x", 0) or 0), int(hazard.get("y", 0) or 0))) != key:
            continue
        linked_prop = getattr(sim, "properties", {}).get(str(metadata.get("linked_property_id", "") or ""))
        if not isinstance(linked_prop, dict):
            continue
        candidates = list(_remediation_candidates(sim, hazard, linked_prop))
        hx, hy = int(hazard.get("x", 0) or 0), int(hazard.get("y", 0) or 0)
        near = [cell for cell in candidates if abs(cell[0] - hx) + abs(cell[1] - hy) <= 2]
        far = [cell for cell in candidates if abs(cell[0] - hx) + abs(cell[1] - hy) >= 3]
        if not near or len(far) < 2:
            continue
        positions = [near[0], far[0], far[-1]]
        indicator_position = next((cell for cell in candidates if cell not in positions), None)
        if indicator_position is None:
            continue
        positions.append(indicator_position)
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:{hazard.get('id')}:remediation")
        base_id = REMEDIATION_SPECIES[rng.randrange(len(REMEDIATION_SPECIES))]
        other_id = next(species for species in REMEDIATION_SPECIES if species != base_id)
        roles = (
            ("accumulator", base_id),
            ("clean_same_species", base_id),
            ("clean_companion", other_id),
            ("contaminant_indicator", INDICATOR_SPECIES),
        )
        base_genetics = dict(catalog[base_id].get("genetics", {}) or {})
        absorbed_load = _take_contamination_load(hazard)
        contaminant_class = str(metadata.get("contaminant_class", "") or "chemical_toxins").strip().lower()
        indicator_color_key = contamination_indicator_color(sim, contaminant_class)
        for index, ((role, species), position) in enumerate(zip(roles, positions)):
            record_id = f"flora:remediation:{hazard.get('id')}:{index}"
            if record_id in getattr(sim, "flora_patches", {}):
                continue
            genetics = base_genetics if species == base_id else dict(catalog[species].get("genetics", {}) or {})
            record = _fungus_record(
                catalog[species],
                record_id=record_id,
                position=position,
                chunk_key=key,
                hazard=hazard,
                role=role,
                genetics=genetics,
                absorbed_load=absorbed_load if role == "accumulator" else 0.0,
                indicator_color_key=indicator_color_key if role == "contaminant_indicator" else None,
            )
            if register_flora_patch(sim, record):
                made.append(record_id)
        if absorbed_load > 0.0:
            _invalidate_lighting_cache(sim)
    completed.add(key)
    return tuple(made)


class ContaminationSystem(System):
    """Materialize explicit releases; it intentionally has no update loop."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("contamination_released", self.on_contamination_released)

    def on_contamination_released(self, event):
        payload = dict(getattr(event, "data", {}) or {})
        payload.setdefault("profile", BLACKWASH_PROFILE)
        payload.setdefault("name", "Spent-cell Blackwash")
        return materialize_contamination_release(self.sim, payload)
