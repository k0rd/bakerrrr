from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_MAP_PATH = REPO_ROOT / "assets" / "tiles" / "semantic_map.json"
DEFAULT_TILE_MAP_PATH = REPO_ROOT / "assets" / "tiles" / "tile_map.json"
DEFAULT_SEMANTIC_MAPPING_PATH = REPO_ROOT / "assets" / "tiles" / "atlas" / "semantic_mapping.json"

RUNTIME_CATEGORIES = (
    "terrain",
    "features",
    "infrastructure",
    "properties",
    "vehicles",
    "items",
    "projectiles",
    "entities",
    "ui_markers",
)

DEFAULT_RENDER_LAYERS = {
    "terrain": 0,
    "ground_overlay": 10,
    "item": 20,
    "actor": 30,
    "fx": 40,
    "ui_overlay": 50,
}

DEFAULT_CATEGORY_RENDER_DEFAULTS = {
    "terrain": {"layer": "terrain", "priority": 0},
    "features": {"layer": "ground_overlay", "priority": 0},
    "infrastructure": {"layer": "ground_overlay", "priority": 5},
    "properties": {"layer": "ground_overlay", "priority": 10},
    "vehicles": {"layer": "ground_overlay", "priority": 20},
    "items": {"layer": "item", "priority": 0},
    "projectiles": {"layer": "fx", "priority": 0},
    "entities": {"layer": "actor", "priority": 0},
    "ui_markers": {"layer": "ui_overlay", "priority": 0},
}

DEFAULT_SEMANTIC_RENDER_DEFAULTS = {
    "entity_player": {"layer": "actor", "priority": 100},
    "transit": {"layer": "ground_overlay", "priority": 10},
    "item_objective": {"layer": "item", "priority": 10},
    "objective": {"layer": "ground_overlay", "priority": 20},
    "ui_cursor": {"layer": "ui_overlay", "priority": 100},
    "ui_look_cursor": {"layer": "ui_overlay", "priority": 110},
    "ui_objective_marker": {"layer": "ui_overlay", "priority": 90},
    "ui_overworld_marker": {"layer": "ui_overlay", "priority": 80},
    "ui_overworld_marker_nearest": {"layer": "ui_overlay", "priority": 85},
}


def _load_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalize_render_layers(raw: dict | None = None) -> dict[str, int]:
    layers = {}
    for name, value in DEFAULT_RENDER_LAYERS.items():
        layers[str(name)] = int(value)
    if not isinstance(raw, dict):
        return layers
    for name, value in raw.items():
        layer_name = str(name or "").strip().lower()
        if not layer_name:
            continue
        try:
            layers[layer_name] = int(value)
        except (TypeError, ValueError):
            continue
    return layers


def _normalize_render_profile(profile, render_layers=None, *, fallback_layer="ground_overlay", fallback_priority=0):
    known_layers = render_layers or DEFAULT_RENDER_LAYERS
    raw = profile if isinstance(profile, dict) else {}
    layer = str(raw.get("layer", fallback_layer) or fallback_layer).strip().lower() or fallback_layer
    if layer not in known_layers:
        layer = str(fallback_layer or "ground_overlay").strip().lower() or "ground_overlay"
    try:
        priority = int(raw.get("priority", fallback_priority))
    except (TypeError, ValueError):
        priority = int(fallback_priority)
    return {
        "layer": layer,
        "priority": priority,
    }


def _normalize_category_render_defaults(raw: dict | None = None, render_layers=None) -> dict[str, dict]:
    layers = _normalize_render_layers(render_layers)
    defaults = {
        str(category_name): _normalize_render_profile(profile, layers)
        for category_name, profile in DEFAULT_CATEGORY_RENDER_DEFAULTS.items()
    }
    if not isinstance(raw, dict):
        return defaults
    for category_name, profile in raw.items():
        category_key = str(category_name or "").strip()
        if not category_key:
            continue
        defaults[category_key] = _normalize_render_profile(profile, layers)
    return defaults


def _normalize_semantic_render_defaults(raw: dict | None = None, render_layers=None) -> dict[str, dict]:
    layers = _normalize_render_layers(render_layers)
    defaults = {
        str(semantic_id): _normalize_render_profile(profile, layers)
        for semantic_id, profile in DEFAULT_SEMANTIC_RENDER_DEFAULTS.items()
    }
    if not isinstance(raw, dict):
        return defaults
    for semantic_id, profile in raw.items():
        semantic_key = str(semantic_id or "").strip()
        if not semantic_key:
            continue
        defaults[semantic_key] = _normalize_render_profile(profile, layers)
    return defaults


def _render_sort_tuple(profile, render_layers=None):
    layers = _normalize_render_layers(render_layers)
    normalized = _normalize_render_profile(profile, layers)
    layer_order = int(layers.get(normalized["layer"], max(layers.values(), default=0) + 10))
    return (layer_order, int(normalized["priority"]))


def _derived_semantic_render_profile(
    semantic_id,
    sources,
    *,
    category_render_defaults,
    semantic_render_defaults,
    render_layers,
):
    semantic_key = str(semantic_id or "").strip()
    explicit = semantic_render_defaults.get(semantic_key)
    if isinstance(explicit, dict):
        return dict(explicit)

    best = None
    for source in sources or ():
        if not isinstance(source, dict):
            continue
        category_name = str(source.get("category", "") or "").strip()
        if not category_name:
            continue
        profile = category_render_defaults.get(category_name)
        if not isinstance(profile, dict):
            continue
        if best is None or _render_sort_tuple(profile, render_layers) > _render_sort_tuple(best, render_layers):
            best = profile
    if best is None:
        return None
    return dict(best)


def build_runtime_semantic_map(
    tile_map_path: Path | None = None,
    semantic_mapping_path: Path | None = None,
) -> dict:
    tile_map = _load_json(Path(tile_map_path) if tile_map_path else DEFAULT_TILE_MAP_PATH)
    semantic_mapping = _load_json(
        Path(semantic_mapping_path) if semantic_mapping_path else DEFAULT_SEMANTIC_MAPPING_PATH
    )

    render_layers = _normalize_render_layers(tile_map.get("_render_layers", {}))
    category_render_defaults = _normalize_category_render_defaults(
        tile_map.get("_category_render_defaults", {}),
        render_layers,
    )
    semantic_render_defaults = _normalize_semantic_render_defaults(
        tile_map.get("_semantic_render_defaults", {}),
        render_layers,
    )

    categories = {}
    for category_name in RUNTIME_CATEGORIES:
        category = tile_map.get(category_name)
        if isinstance(category, dict):
            categories[category_name] = category

    assignments = semantic_mapping.get("assignments", {}) if isinstance(semantic_mapping, dict) else {}
    semantics = {}
    for semantic_id, atlas_id in assignments.items():
        semantic_key = str(semantic_id or "").strip()
        atlas_key = str(atlas_id or "").strip()
        if not semantic_key:
            continue
        semantics[semantic_key] = {
            "atlas_id": atlas_key or None,
            "sources": [],
        }

    for category_name, category in categories.items():
        for source_key, mapping in category.items():
            if str(source_key).startswith("_"):
                continue
            source_name = str(source_key)
            semantic_ids = []
            if isinstance(mapping, dict):
                semantic_ids = [
                    str(semantic_id or "").strip()
                    for semantic_id in mapping.values()
                    if str(semantic_id or "").strip()
                ]
            elif isinstance(mapping, str):
                semantic_value = str(mapping).strip()
                if semantic_value:
                    semantic_ids = [semantic_value]
            for semantic_id in semantic_ids:
                entry = semantics.setdefault(
                    semantic_id,
                    {
                        "atlas_id": str(assignments.get(semantic_id, "") or "").strip() or None,
                        "sources": [],
                    },
                )
                source_entry = {
                    "category": category_name,
                    "source_key": source_name,
                }
                if source_entry not in entry["sources"]:
                    entry["sources"].append(source_entry)

    for semantic_id, entry in semantics.items():
        if not isinstance(entry, dict):
            continue
        render_profile = _derived_semantic_render_profile(
            semantic_id,
            entry.get("sources", ()),
            category_render_defaults=category_render_defaults,
            semantic_render_defaults=semantic_render_defaults,
            render_layers=render_layers,
        )
        if render_profile is not None:
            entry["render"] = render_profile

    return {
        "_comment": "Runtime semantic catalog combining render semantics and atlas aliases.",
        "sources": {
            "tile_map": str(Path(tile_map_path) if tile_map_path else DEFAULT_TILE_MAP_PATH),
            "semantic_mapping": str(
                Path(semantic_mapping_path) if semantic_mapping_path else DEFAULT_SEMANTIC_MAPPING_PATH
            ),
        },
        "color_aliases": tile_map.get("_color_aliases", {}),
        "asset_color_families": tile_map.get("_asset_color_families", {}),
        "render_layers": render_layers,
        "category_render_defaults": category_render_defaults,
        "semantic_render_defaults": semantic_render_defaults,
        "categories": categories,
        "semantics": semantics,
    }


def write_runtime_semantic_map(
    output_path: Path | None = None,
    *,
    tile_map_path: Path | None = None,
    semantic_mapping_path: Path | None = None,
) -> Path:
    path = Path(output_path) if output_path else DEFAULT_RUNTIME_MAP_PATH
    data = build_runtime_semantic_map(
        tile_map_path=tile_map_path,
        semantic_mapping_path=semantic_mapping_path,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


class RuntimeSemanticCatalog:
    def __init__(self, path: Path | None = None, data: dict | None = None):
        self.path = Path(path) if path else DEFAULT_RUNTIME_MAP_PATH
        if data is None:
            if self.path.exists():
                data = _load_json(self.path)
            else:
                data = build_runtime_semantic_map()
        self.data = data if isinstance(data, dict) else {}
        self.categories = self.data.get("categories", {}) if isinstance(self.data.get("categories"), dict) else {}
        self.color_aliases = (
            self.data.get("color_aliases", {}) if isinstance(self.data.get("color_aliases"), dict) else {}
        )
        self.asset_color_families = (
            self.data.get("asset_color_families", {})
            if isinstance(self.data.get("asset_color_families"), dict)
            else {}
        )
        self.render_layers = _normalize_render_layers(self.data.get("render_layers", {}))
        self.category_render_defaults = _normalize_category_render_defaults(
            self.data.get("category_render_defaults", {}),
            self.render_layers,
        )
        self.semantic_render_defaults = _normalize_semantic_render_defaults(
            self.data.get("semantic_render_defaults", {}),
            self.render_layers,
        )
        self.semantics = self.data.get("semantics", {}) if isinstance(self.data.get("semantics"), dict) else {}

    def atlas_id_for_semantic(self, semantic_id):
        semantic_key = str(semantic_id or "").strip()
        if not semantic_key:
            return None
        entry = self.semantics.get(semantic_key)
        if not isinstance(entry, dict):
            return None
        atlas_id = str(entry.get("atlas_id", "") or "").strip()
        return atlas_id or None

    def render_layer_order(self, layer_name):
        layer_key = str(layer_name or "").strip().lower() or "ground_overlay"
        if layer_key in self.render_layers:
            return int(self.render_layers[layer_key])
        return max(self.render_layers.values(), default=0) + 10

    def render_defaults_for_category(self, category_name):
        category_key = str(category_name or "").strip()
        profile = self.category_render_defaults.get(category_key)
        if isinstance(profile, dict):
            return dict(profile)
        return _normalize_render_profile(None, self.render_layers)

    def render_defaults_for_semantic(self, semantic_id, *, fallback_categories=()):
        semantic_key = str(semantic_id or "").strip()
        if semantic_key:
            entry = self.semantics.get(semantic_key)
            if isinstance(entry, dict):
                render_profile = entry.get("render")
                if isinstance(render_profile, dict):
                    return _normalize_render_profile(render_profile, self.render_layers)
            explicit = self.semantic_render_defaults.get(semantic_key)
            if isinstance(explicit, dict):
                return dict(explicit)

        best = None
        if semantic_key:
            entry = self.semantics.get(semantic_key)
            if isinstance(entry, dict):
                for source in entry.get("sources", ()):
                    if not isinstance(source, dict):
                        continue
                    category_name = str(source.get("category", "") or "").strip()
                    if not category_name:
                        continue
                    profile = self.category_render_defaults.get(category_name)
                    if not isinstance(profile, dict):
                        continue
                    if best is None or _render_sort_tuple(profile, self.render_layers) > _render_sort_tuple(best, self.render_layers):
                        best = profile

        for category_name in fallback_categories or ():
            profile = self.category_render_defaults.get(str(category_name or "").strip())
            if not isinstance(profile, dict):
                continue
            if best is None or _render_sort_tuple(profile, self.render_layers) > _render_sort_tuple(best, self.render_layers):
                best = profile

        if isinstance(best, dict):
            return dict(best)
        return _normalize_render_profile(None, self.render_layers)

    def category_order_for_color(self, color_key):
        key = str(color_key or "default").strip().lower() or "default"
        default_order = list(RUNTIME_CATEGORIES)

        if key in {
            "player",
            "human",
            "guard",
            "scout",
            "feline",
            "canine",
            "avian",
            "insect",
            "rodent",
            "reptile",
            "amphibian",
            "fish",
            "ungulate",
            "other",
        } or key.startswith("cat_"):
            return ["entities"] + [name for name in default_order if name != "entities"]
        if key.startswith("item_"):
            return ["items"] + [name for name in default_order if name != "items"]
        if key.startswith("vehicle_"):
            return ["vehicles"] + [name for name in default_order if name != "vehicles"]
        if key.startswith("feature_"):
            return ["features"] + [name for name in default_order if name != "features"]
        if key.startswith("terrain_") or key.startswith("floor_") or key in {"building_edge", "building_fill"}:
            return ["terrain"] + [name for name in default_order if name != "terrain"]
        if key.startswith("property_") or key.startswith("building_roof_"):
            return ["properties"] + [name for name in default_order if name != "properties"]
        if key == "projectile":
            return ["projectiles"] + [name for name in default_order if name != "projectiles"]
        if key.startswith("ui_"):
            return ["ui_markers"] + [name for name in default_order if name != "ui_markers"]
        if key == "transit":
            return ["features", "terrain"] + [name for name in default_order if name not in {"features", "terrain"}]
        return default_order

    def strict_categories_for_color(self, color_key):
        key = str(color_key or "default").strip().lower() or "default"
        if key.startswith("item_"):
            return ("items",)
        if key.startswith("vehicle_"):
            return ("vehicles",)
        return ()

    def semantic_id_for_key(self, category_name, source_key, color_key=None, allow_defaults=True):
        category = self.categories.get(str(category_name or "").strip())
        if not isinstance(category, dict):
            return None

        entry = category.get(source_key)
        if isinstance(entry, str):
            semantic_id = str(entry).strip()
            return semantic_id or None
        if not isinstance(entry, dict):
            return None

        requested_color = str(color_key or "default").strip() or "default"
        semantic_id = str(entry.get(requested_color, "") or "").strip()
        if semantic_id:
            return semantic_id
        if allow_defaults:
            semantic_id = str(entry.get("default", "") or "").strip()
            if semantic_id:
                return semantic_id
        return None

    def semantic_id_for(
        self,
        glyph,
        color_key=None,
        *,
        preferred_categories=(),
        strict_categories=(),
        allow_defaults=True,
    ):
        glyph_key = str(glyph or "")[:1]
        if not glyph_key:
            return None

        color_name = str(color_key or "default").strip() or "default"
        strict = tuple(
            category_name
            for category_name in strict_categories
            if isinstance(self.categories.get(category_name), dict)
        )
        if not strict:
            strict = self.strict_categories_for_color(color_name)

        ordered_categories = []
        for category_name in preferred_categories:
            category_key = str(category_name or "").strip()
            if category_key and category_key not in ordered_categories and isinstance(self.categories.get(category_key), dict):
                ordered_categories.append(category_key)
        for category_name in self.category_order_for_color(color_name):
            if category_name not in ordered_categories and isinstance(self.categories.get(category_name), dict):
                ordered_categories.append(category_name)

        if strict:
            ordered_categories = [category_name for category_name in ordered_categories if category_name in strict]

        for category_name in ordered_categories:
            semantic_id = self.semantic_id_for_key(
                category_name,
                glyph_key,
                color_name,
                allow_defaults=False,
            )
            if semantic_id:
                return semantic_id

        if not allow_defaults:
            return None

        for category_name in ordered_categories:
            semantic_id = self.semantic_id_for_key(
                category_name,
                glyph_key,
                color_name,
                allow_defaults=True,
            )
            if semantic_id:
                return semantic_id
        return None


@lru_cache(maxsize=4)
def get_runtime_semantic_catalog(path: str | None = None) -> RuntimeSemanticCatalog:
    catalog_path = Path(path) if path else DEFAULT_RUNTIME_MAP_PATH
    return RuntimeSemanticCatalog(path=catalog_path)
