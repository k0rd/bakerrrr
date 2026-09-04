#!/usr/bin/python
"""
Bakerrrr Content Workbench
==========================

Bakerrrr's private, first-party Tkinter content editor. Features are isolated
behind registered EditorMode classes so new content domains can be added
without teaching existing modes about one another.

Current real modes:
- GFX: 16x16 q()-scaled procedural Pygame drawcode authoring
- Drawables: symbolic worn/on-ground drawable DSL authoring and preview
- Items: lossless structured item authoring with normalized runtime preview
- Viewer: static Python/JSON content browsing and GFX handoff
- Paper Doll: item-aware appearance/loadout preview from game/items.json
- Building Stamps: semantic shell-stamp authoring and preview

Shared services:
- read-only Bakerrrr source access / AST parsing
- shared JSON palette vocabulary
- revisioned drawable, item, and building-stamp catalogs

Game Python is parsed statically. The workbench imports only Bakerrrr's pure,
side-effect-free authoring libraries; it never imports or executes a target
checkout's game source merely to inspect content.
"""

from __future__ import annotations

import ast
import copy
import json
import math
import os
import re
import tkinter as tk
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any, Iterable


from engine.building_stamp import BuildingStampCatalog, BuildingStampError, load_building_stamp_catalog
from game.drawable_dsl import DrawableCatalog, DrawableError, load_drawable_catalog
from editor.content_domains import CONTENT_DOMAIN_REGISTRY
from editor.item_service import ItemCatalogService
from editor.mode_api import MODE_REGISTRY, EditorMode, register_mode
from editor.modes import register_packaged_modes


APP_NAME = "Bakerrrr Content Workbench"
GFX_PROJECT_VERSION = 1
LOGICAL_SIZE = 16.0
DEFAULT_ZOOM = 32
MIN_ZOOM = 16
MAX_ZOOM = 64
DEFAULT_SNAP = 0.25

HANDLE_RADIUS = 5
SELECTION_PAD = 3

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


DUMMY_PALETTE: dict[str, tuple[int, int, int]] = {
    "fill": (204, 126, 156),
    "edge": (74, 42, 56),
    "shade": (151, 82, 110),
    "highlight": (241, 192, 209),
    "accent": (95, 156, 214),
    "dark": (35, 37, 44),
    "light": (226, 229, 235),
    "white": (245, 245, 245),
    "black": (18, 18, 20),
    "skin": (213, 168, 142),
    "hair": (161, 62, 39),
    "metal": (116, 124, 132),
    "wood": (132, 86, 55),
    "red": (196, 57, 57),
    "green": (70, 145, 91),
    "blue": (63, 112, 184),
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def snap_value(value: float, snap: float) -> float:
    if snap <= 0:
        return value
    return round(value / snap) * snap


def fmt_num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (int(clamp(v, 0, 255)) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_hex_color(value: str) -> tuple[int, int, int] | None:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3 and all(c in "0123456789abcdefABCDEF" for c in text):
        text = "".join(c * 2 for c in text)
    if len(text) != 6 or not all(c in "0123456789abcdefABCDEF" for c in text):
        return None
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def normalize_rgb(value: Any) -> tuple[int, int, int] | None:
    """Accept several common color JSON representations."""
    if isinstance(value, str):
        return parse_hex_color(value)

    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            vals = [float(value[i]) for i in range(3)]
        except (TypeError, ValueError):
            return None
        if all(0.0 <= v <= 1.0 for v in vals):
            vals = [round(v * 255) for v in vals]
        return tuple(int(clamp(round(v), 0, 255)) for v in vals)

    if isinstance(value, dict):
        for key in ("rgb", "color", "value"):
            if key in value:
                parsed = normalize_rgb(value[key])
                if parsed is not None:
                    return parsed

        for key in ("hex", "hex_value", "hexValue"):
            if isinstance(value.get(key), str):
                parsed = parse_hex_color(value[key])
                if parsed is not None:
                    return parsed

        if all(k in value for k in ("r", "g", "b")):
            return normalize_rgb([value["r"], value["g"], value["b"]])

    return None


def palette_from_json(data: Any) -> dict[str, tuple[int, int, int]]:
    """
    Flexible adapter for a few likely palette schemas.

    Supported examples:
        {"fill": [200, 100, 120], "edge": "#302028"}

        {"colors": {
            "fill": {"rgb": [200, 100, 120]},
            "edge": {"hex": "#302028"}
        }}

        {"colors": [
            {"name": "fill", "rgb": [200, 100, 120]},
            {"name": "edge", "hex": "#302028"}
        ]}

    It also recursively inspects nested dictionaries for named color records.
    """
    result: dict[str, tuple[int, int, int]] = {}

    def add(name: Any, value: Any) -> None:
        if not isinstance(name, str) or not name.strip():
            return
        rgb = normalize_rgb(value)
        if rgb is not None:
            result[name.strip()] = rgb

    def walk(node: Any, hinted_name: str | None = None, depth: int = 0) -> None:
        if depth > 6:
            return

        if hinted_name:
            rgb = normalize_rgb(node)
            if rgb is not None:
                result.setdefault(hinted_name, rgb)

        if isinstance(node, dict):
            record_name = None
            for name_key in ("name", "id", "key", "token", "slug"):
                if isinstance(node.get(name_key), str):
                    record_name = node[name_key].strip()
                    break
            if record_name:
                rgb = normalize_rgb(node)
                if rgb is not None:
                    result[record_name] = rgb

            # A plain mapping of token -> color is the nicest schema.
            for key, value in node.items():
                if key in {"name", "id", "key", "token", "slug"}:
                    continue
                add(key, value)

            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    walk(value, str(key) if isinstance(key, str) else None, depth + 1)

        elif isinstance(node, list):
            for entry in node:
                walk(entry, None, depth + 1)

    root = data.get("colors", data) if isinstance(data, dict) else data
    walk(root)
    return result




class PaletteService:
    """Shared color vocabulary for every editor mode."""

    def __init__(self) -> None:
        self.colors: dict[str, tuple[int, int, int]] = dict(DUMMY_PALETTE)
        self.path: str | None = None

    def load(self, path: Path) -> int:
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded = palette_from_json(data)
        if not loaded:
            raise ValueError("I couldn't find any RGB/hex color records in that JSON.")
        merged = dict(DUMMY_PALETTE)
        merged.update(loaded)
        self.colors = merged
        self.path = str(path)
        return len(loaded)


class GameSource:
    """
    Read-only gateway into a Bakerrrr checkout.

    Modes ask this object for source files, JSON, or parsed Python. Nothing here
    imports or executes game code. That makes content inspection safe and keeps
    source-discovery logic out of individual editor modes.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root: Path | None = None
        if root is not None:
            self.set_root(root)
        else:
            self.root = self._autodetect_root()

    @staticmethod
    def _looks_like_root(path: Path) -> bool:
        return path.is_dir() and ((path / "game").is_dir() or (path / "bakerrrr").exists())

    def _autodetect_root(self) -> Path | None:
        candidates: list[Path] = []
        env = os.environ.get("BAKERRRR_ROOT")
        if env:
            candidates.append(Path(env).expanduser())
        cwd = Path.cwd()
        candidates.extend([cwd, cwd.parent])
        for candidate in candidates:
            try:
                candidate = candidate.resolve()
            except OSError:
                continue
            if self._looks_like_root(candidate):
                return candidate
        return None

    def set_root(self, root: Path) -> None:
        candidate = root.expanduser().resolve()
        if not candidate.is_dir():
            raise ValueError(f"Not a directory: {candidate}")
        self.root = candidate

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            if self.root is None:
                raise ValueError("No Bakerrrr root is set.")
            candidate = self.root / candidate
        return candidate.resolve()

    def parse_python(self, path: str | Path) -> tuple[Path, str, ast.AST]:
        resolved = self.resolve(path)
        source = resolved.read_text(encoding="utf-8")
        return resolved, source, ast.parse(source, filename=str(resolved))

    def load_json(self, path: str | Path) -> Any:
        resolved = self.resolve(path)
        return json.loads(resolved.read_text(encoding="utf-8"))

    def python_files(self) -> list[Path]:
        if self.root is None:
            return []
        ignored = {".git", ".venv", "venv", "__pycache__", ".cache"}
        return sorted(
            p for p in self.root.rglob("*.py")
            if not any(part in ignored for part in p.parts)
        )

    def json_files(self) -> list[Path]:
        if self.root is None:
            return []
        ignored = {".git", ".venv", "venv", "__pycache__", ".cache"}
        return sorted(
            p for p in self.root.rglob("*.json")
            if not any(part in ignored for part in p.parts)
        )

    def drawable_files(self) -> list[Path]:
        return self.domain_files("drawables")

    def domain_files(self, domain_id: str) -> list[Path]:
        if self.root is None:
            return []
        spec = CONTENT_DOMAIN_REGISTRY.get(str(domain_id))
        if spec is None:
            raise KeyError(f"Unknown content domain: {domain_id}")
        root = self.root / spec.relative_root
        if spec.single_file:
            return [root] if root.is_file() and root.suffix in set(spec.extensions) else []
        if not root.is_dir():
            return []
        extensions = set(spec.extensions)
        return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in extensions)

    def content_files(self) -> list[Path]:
        files = self.python_files() + self.json_files() + self.drawable_files()
        return sorted(files, key=lambda p: self.display_path(p).lower())

    def display_path(self, path: Path) -> str:
        if self.root is None:
            return str(path)
        try:
            return str(path.resolve().relative_to(self.root))
        except (OSError, ValueError):
            return str(path)


@dataclass
class DrawableCatalogService:
    """Validated drawable definitions for editor modes in the selected root."""

    catalog: DrawableCatalog = field(default_factory=lambda: load_drawable_catalog(()))
    root: Path | None = None
    error: str = ""

    def reload(self, game: GameSource) -> bool:
        previous_root = self.root
        self.root = game.root
        self.error = ""
        domain = CONTENT_DOMAIN_REGISTRY["drawables"]
        roots = () if game.root is None else (game.root / domain.relative_root,)
        try:
            replacement = load_drawable_catalog(roots)
        except DrawableError as exc:
            if previous_root != game.root:
                self.catalog = load_drawable_catalog(())
            self.error = str(exc)
            return False
        self.catalog = replacement
        return True


@dataclass
class BuildingStampCatalogService:
    """Validated semantic shell stamps for the selected checkout."""

    catalog: BuildingStampCatalog = field(default_factory=lambda: load_building_stamp_catalog(()))
    root: Path | None = None
    error: str = ""

    def reload(self, game: GameSource) -> bool:
        previous_root = self.root
        self.root = game.root
        self.error = ""
        domain = CONTENT_DOMAIN_REGISTRY["building_stamps"]
        roots = () if game.root is None else (game.root / domain.relative_root,)
        try:
            replacement = load_building_stamp_catalog(roots)
        except BuildingStampError as exc:
            if previous_root != game.root:
                self.catalog = load_building_stamp_catalog(())
            self.error = str(exc)
            return False
        self.catalog = replacement
        return True


@dataclass
class WorkbenchServices:
    game: GameSource = field(default_factory=GameSource)
    palette: PaletteService = field(default_factory=PaletteService)
    drawables: DrawableCatalogService = field(default_factory=DrawableCatalogService)
    building_stamps: BuildingStampCatalogService = field(default_factory=BuildingStampCatalogService)
    items: ItemCatalogService = field(default_factory=ItemCatalogService)

    def reload_root_content(self) -> bool:
        drawable_ok = self.drawables.reload(self.game)
        building_ok = self.building_stamps.reload(self.game)
        item_ok = self.items.reload(self.game, self.drawables)
        return drawable_ok and building_ok and item_ok


@dataclass
class Shape:
    kind: str
    name: str
    color: str = "fill"
    outline: str = ""
    width: float = 0.0
    points: list[list[float]] = field(default_factory=list)
    bbox: list[float] = field(default_factory=lambda: [4.0, 4.0, 8.0, 8.0])
    radius: float = 2.0
    visible: bool = True
    closed: bool = False
    filled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Shape":
        return cls(
            kind=str(data.get("kind", "rect")),
            name=str(data.get("name", "shape")),
            color=str(data.get("color", "fill")),
            outline=str(data.get("outline", "")),
            width=float(data.get("width", 0.0)),
            points=[
                [float(p[0]), float(p[1])]
                for p in data.get("points", [])
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ],
            bbox=[
                float(v) for v in (data.get("bbox", [4, 4, 8, 8])[:4])
            ],
            radius=float(data.get("radius", 2.0)),
            visible=bool(data.get("visible", True)),
            closed=bool(data.get("closed", False)),
            filled=bool(data.get("filled", True)),
        )

    def center(self) -> tuple[float, float]:
        if self.kind in {"line", "polygon"} and self.points:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            return sum(xs) / len(xs), sum(ys) / len(ys)
        if self.kind == "circle":
            return self.bbox[0], self.bbox[1]
        x, y, w, h = self.bbox
        return x + w / 2, y + h / 2

    def translate(self, dx: float, dy: float) -> None:
        if self.kind in {"line", "polygon"}:
            for point in self.points:
                point[0] += dx
                point[1] += dy
        elif self.kind == "circle":
            self.bbox[0] += dx
            self.bbox[1] += dy
        else:
            self.bbox[0] += dx
            self.bbox[1] += dy


@dataclass
class ImportCandidate:
    label: str
    calls: list[ast.Call]


class DrawCallCollector(ast.NodeVisitor):
    """Collect pygame.draw calls without importing or executing game code."""

    SUPPORTED = {"rect", "ellipse", "circle", "line", "lines", "polygon"}

    def __init__(self) -> None:
        self.function_stack: list[tuple[str, int]] = []
        self.branch_stack: list[str] = []
        self.function_calls: dict[tuple[str, int], list[ast.Call]] = {}
        self.branch_calls: dict[tuple[str, int, tuple[str, ...]], list[ast.Call]] = {}

    @staticmethod
    def draw_primitive(call: ast.Call) -> str | None:
        func = call.func
        if not isinstance(func, ast.Attribute) or func.attr not in DrawCallCollector.SUPPORTED:
            return None
        owner = func.value
        if not isinstance(owner, ast.Attribute) or owner.attr != "draw":
            return None
        return func.attr

    def _function_key(self) -> tuple[str, int]:
        if self.function_stack:
            return self.function_stack[-1]
        return ("<module>", 1)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append((node.name, node.lineno))
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append((node.name, node.lineno))
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_If(self, node: ast.If) -> None:
        try:
            test_text = ast.unparse(node.test)
        except Exception:
            test_text = f"condition@{node.lineno}"
        if len(test_text) > 84:
            test_text = test_text[:81] + "..."

        self.branch_stack.append(f"if {test_text}")
        for child in node.body:
            self.visit(child)
        self.branch_stack.pop()

        if node.orelse:
            self.branch_stack.append(f"else {test_text}")
            for child in node.orelse:
                self.visit(child)
            self.branch_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if self.draw_primitive(node):
            fkey = self._function_key()
            self.function_calls.setdefault(fkey, []).append(node)
            if self.branch_stack:
                bkey = (fkey[0], fkey[1], tuple(self.branch_stack))
                self.branch_calls.setdefault(bkey, []).append(node)
        self.generic_visit(node)

    def candidates(self) -> list[ImportCandidate]:
        result: list[ImportCandidate] = []
        for (name, line), calls in sorted(self.function_calls.items(), key=lambda row: row[0][1]):
            result.append(ImportCandidate(f"{name} [all]  ({len(calls)} draw calls, line {line})", calls))
            branch_rows = [
                (key, bcalls)
                for key, bcalls in self.branch_calls.items()
                if key[0] == name and key[1] == line
            ]
            for key, bcalls in sorted(branch_rows, key=lambda row: getattr(row[1][0], "lineno", 0)):
                path = " / ".join(key[2])
                result.append(ImportCandidate(f"  {name} :: {path}  ({len(bcalls)})", bcalls))
        return result


class ImportScopeDialog(simpledialog.Dialog):
    """Pick one or more AST scopes to import from a Bakerrrr renderer."""

    def __init__(self, parent: tk.Misc, source_name: str, candidates: list[ImportCandidate]) -> None:
        self.source_name = source_name
        self.candidates = candidates
        self.selected: list[ImportCandidate] = []
        self.replace_existing = False
        super().__init__(parent, title="Import Bakerrrr drawcode")

    def body(self, master: tk.Misc) -> tk.Widget | None:
        ttk.Label(
            master,
            text=f"Drawable scopes in {self.source_name}",
        ).pack(anchor="w", pady=(0, 5))
        ttk.Label(
            master,
            text="Select a function [all], or a narrower branch. No game code is executed.",
        ).pack(anchor="w", pady=(0, 6))

        holder = ttk.Frame(master)
        holder.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(holder, selectmode="extended", width=100, height=20, exportselection=False)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)
        for candidate in self.candidates:
            self.listbox.insert("end", candidate.label)
        if self.candidates:
            self.listbox.selection_set(0)

        controls = ttk.Frame(master)
        controls.pack(fill="x", pady=(6, 0))
        ttk.Button(controls, text="Select all", command=lambda: self.listbox.selection_set(0, "end")).pack(side="left")
        ttk.Button(controls, text="Clear", command=lambda: self.listbox.selection_clear(0, "end")).pack(side="left", padx=(4, 0))
        self.replace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Replace current canvas", variable=self.replace_var).pack(side="right")
        return self.listbox

    def validate(self) -> bool:
        indexes = list(self.listbox.curselection())
        if not indexes:
            messagebox.showwarning("Nothing selected", "Select at least one drawable scope.", parent=self)
            return False
        self.selected = [self.candidates[i] for i in indexes]
        self.replace_existing = bool(self.replace_var.get())
        return True




_UNKNOWN = object()


@dataclass(frozen=True)
class _AssignmentRecord:
    name: str
    node: ast.AST
    value: ast.AST
    function: ast.AST | None
    branch_path: tuple[tuple[int, str], ...]
    target_path: tuple[int, ...] = ()


@dataclass
class _RectValue:
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self):
        return self.x

    @property
    def right(self):
        return self.x + self.w

    @property
    def top(self):
        return self.y

    @property
    def bottom(self):
        return self.y + self.h

    @property
    def centerx(self):
        return self.x + self.w / 2

    @property
    def centery(self):
        return self.y + self.h / 2

    @property
    def center(self):
        return (self.centerx, self.centery)


class StaticDrawResolver:
    """
    Conservative static evaluator for Bakerrrr renderer geometry.

    It never imports or executes game Python. Instead it understands the small,
    ordinary expression language used around pygame.draw calls: local aliases,
    q(), px/mid_x arithmetic, max/min, tuples/lists, indexing, simple pure
    helper functions, comprehensions, and small constant for-loops.

    Coordinates are evaluated at a nominal 16px cell, which makes raw pixel
    offsets and the editor's 16-unit logical artboard share the same scale.
    q(value) intentionally preserves `value` as a logical coordinate.
    """

    NOMINAL_PX = 16.0
    MAX_HELPER_DEPTH = 12
    MAX_LOOP_EXPANSION = 32

    def __init__(self, tree: ast.AST) -> None:
        self.tree = tree
        self.parent: dict[int, ast.AST] = {}
        self.function_of: dict[int, ast.AST | None] = {}
        self.branch_of: dict[int, tuple[tuple[int, str], ...]] = {}
        self.loops_of: dict[int, tuple[ast.For, ...]] = {}
        self.assignments: dict[str, list[_AssignmentRecord]] = {}
        self.function_defs: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        self._default_cache: dict[int, dict[str, Any]] = {}
        self._index(tree, None, None, (), ())
        self._index_assignments(tree)

    # --------------------------------------------------------------
    # AST indexing
    # --------------------------------------------------------------

    def _index(
        self,
        node: ast.AST,
        parent: ast.AST | None,
        function: ast.AST | None,
        branch_path: tuple[tuple[int, str], ...],
        loops: tuple[ast.For, ...],
    ) -> None:
        if parent is not None:
            self.parent[id(node)] = parent

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.function_defs.setdefault(node.name, []).append(node)
            function = node

        self.function_of[id(node)] = function
        self.branch_of[id(node)] = branch_path
        self.loops_of[id(node)] = loops

        if isinstance(node, ast.If):
            self._index(node.test, node, function, branch_path, loops)
            body_path = branch_path + ((id(node), 'body'),)
            else_path = branch_path + ((id(node), 'else'),)
            for child in node.body:
                self._index(child, node, function, body_path, loops)
            for child in node.orelse:
                self._index(child, node, function, else_path, loops)
            return

        if isinstance(node, ast.For):
            self._index(node.target, node, function, branch_path, loops)
            self._index(node.iter, node, function, branch_path, loops)
            body_loops = loops + (node,)
            for child in node.body:
                self._index(child, node, function, branch_path, body_loops)
            for child in node.orelse:
                self._index(child, node, function, branch_path, loops)
            return

        for child in ast.iter_child_nodes(node):
            self._index(child, node, function, branch_path, loops)

    def _index_assignments(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._record_target(target, node.value, node)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                self._record_target(node.target, node.value, node)
            elif isinstance(node, ast.NamedExpr):
                self._record_target(node.target, node.value, node)

        for rows in self.assignments.values():
            rows.sort(key=lambda rec: (getattr(rec.node, 'lineno', 0), getattr(rec.node, 'col_offset', 0)))

    def _record_target(
        self,
        target: ast.AST,
        value: ast.AST,
        owner: ast.AST,
        path: tuple[int, ...] = (),
    ) -> None:
        if isinstance(target, ast.Name):
            record = _AssignmentRecord(
                name=target.id,
                node=owner,
                value=value,
                function=self.function_of.get(id(owner)),
                branch_path=self.branch_of.get(id(owner), ()),
                target_path=path,
            )
            self.assignments.setdefault(target.id, []).append(record)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for index, elt in enumerate(target.elts):
                self._record_target(elt, value, owner, path + (index,))

    # --------------------------------------------------------------
    # Contexts: branch constraints + constant loop expansion
    # --------------------------------------------------------------

    def contexts_for_call(self, call: ast.Call) -> list[dict[str, Any]]:
        base = self._branch_constraints(call)
        contexts = [base]
        for loop in self.loops_of.get(id(call), ()):
            expanded: list[dict[str, Any]] = []
            for context in contexts:
                iterable = self.eval_expr(loop.iter, call, context)
                if iterable is _UNKNOWN:
                    expanded.append(context)
                    continue
                try:
                    values = list(iterable)
                except Exception:
                    expanded.append(context)
                    continue
                if not values or len(values) > self.MAX_LOOP_EXPANSION:
                    expanded.append(context)
                    continue
                for value in values:
                    bound = dict(context)
                    if self._bind_target(loop.target, value, bound):
                        expanded.append(bound)
            contexts = expanded or contexts
        return contexts or [{}]

    def _branch_constraints(self, node: ast.AST) -> dict[str, Any]:
        result: dict[str, Any] = {}
        path = self.branch_of.get(id(node), ())
        if not path:
            return result
        if_nodes = {id(n): n for n in ast.walk(self.tree) if isinstance(n, ast.If)}
        for if_id, side in path:
            if side != 'body':
                continue
            if_node = if_nodes.get(if_id)
            if if_node is not None:
                self._extract_constraints(if_node.test, result)
        return result

    def _extract_constraints(self, test: ast.AST, output: dict[str, Any]) -> None:
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            for value in test.values:
                self._extract_constraints(value, output)
            return
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
            return
        left, op, right = test.left, test.ops[0], test.comparators[0]
        if isinstance(op, ast.Eq):
            if isinstance(left, ast.Name):
                value = self._literalish(right)
                if value is not _UNKNOWN:
                    output[left.id] = value
            elif isinstance(right, ast.Name):
                value = self._literalish(left)
                if value is not _UNKNOWN:
                    output[right.id] = value
            return
        if isinstance(op, ast.In) and isinstance(left, ast.Name):
            choices = self._literalish(right)
            if isinstance(choices, (tuple, list, set, frozenset)) and choices:
                # A branch like garment in {"boxers", "boxer_briefs"} usually
                # shares geometry. Pick a deterministic representative.
                output[left.id] = list(choices)[0]

    def _literalish(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            values = [self._literalish(elt) for elt in node.elts]
            if any(v is _UNKNOWN for v in values):
                return _UNKNOWN
            if isinstance(node, ast.Tuple):
                return tuple(values)
            if isinstance(node, ast.Set):
                return tuple(values)
            return values
        return _UNKNOWN

    @staticmethod
    def _bind_target(target: ast.AST, value: Any, env: dict[str, Any]) -> bool:
        if isinstance(target, ast.Name):
            env[target.id] = value
            return True
        if isinstance(target, (ast.Tuple, ast.List)):
            try:
                values = list(value)
            except Exception:
                return False
            if len(values) != len(target.elts):
                return False
            ok = True
            for child, child_value in zip(target.elts, values):
                ok = StaticDrawResolver._bind_target(child, child_value, env) and ok
            return ok
        return False

    # --------------------------------------------------------------
    # Name lookup
    # --------------------------------------------------------------

    def resolve_name(
        self,
        name: str,
        at_node: ast.AST,
        overrides: dict[str, Any] | None = None,
        local_env: dict[str, Any] | None = None,
        seen: set[tuple[str, int]] | None = None,
    ) -> Any:
        overrides = overrides or {}
        local_env = local_env or {}
        if name in local_env:
            return local_env[name]
        if name in overrides:
            return overrides[name]
        if name == 'px':
            return self.NOMINAL_PX
        if name == 'mid_x':
            return self.NOMINAL_PX / 2

        function = self.function_of.get(id(at_node))
        line = getattr(at_node, 'lineno', 10**9)
        branch = self.branch_of.get(id(at_node), ())
        seen = seen or set()
        marker = (name, line)
        if marker in seen:
            return _UNKNOWN
        seen = set(seen)
        seen.add(marker)

        rows = self.assignments.get(name, ())
        compatible: list[_AssignmentRecord] = []
        for rec in rows:
            rec_line = getattr(rec.node, 'lineno', -1)
            if rec_line >= line:
                continue
            if rec.function is not function:
                continue
            if not self._branch_compatible(rec.branch_path, branch):
                continue
            compatible.append(rec)
        if compatible:
            rec = compatible[-1]
            value = self.eval_expr(rec.value, rec.node, overrides, local_env, seen)
            if value is not _UNKNOWN:
                try:
                    for index in rec.target_path:
                        value = value[index]
                    return value
                except Exception:
                    pass

        default = self._function_default(function, name, at_node, overrides)
        if default is not _UNKNOWN:
            return default
        return _UNKNOWN

    @staticmethod
    def _branch_compatible(
        assignment_path: tuple[tuple[int, str], ...],
        call_path: tuple[tuple[int, str], ...],
    ) -> bool:
        call_map = dict(call_path)
        return all(call_map.get(if_id) == side for if_id, side in assignment_path)

    def _function_default(
        self,
        function: ast.AST | None,
        name: str,
        at_node: ast.AST,
        overrides: dict[str, Any],
    ) -> Any:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return _UNKNOWN
        cache = self._default_cache.get(id(function))
        if cache is None:
            cache = {}
            positional = list(function.args.posonlyargs) + list(function.args.args)
            defaults = list(function.args.defaults)
            start = len(positional) - len(defaults)
            for index, default_node in enumerate(defaults, start=start):
                cache[positional[index].arg] = self.eval_expr(default_node, function, overrides)
            for arg, default_node in zip(function.args.kwonlyargs, function.args.kw_defaults):
                if default_node is not None:
                    cache[arg.arg] = self.eval_expr(default_node, function, overrides)
            self._default_cache[id(function)] = cache
        return cache.get(name, _UNKNOWN)

    # --------------------------------------------------------------
    # Safe expression evaluator
    # --------------------------------------------------------------

    def eval_expr(
        self,
        node: ast.AST | None,
        at_node: ast.AST,
        overrides: dict[str, Any] | None = None,
        local_env: dict[str, Any] | None = None,
        seen: set[tuple[str, int]] | None = None,
        depth: int = 0,
    ) -> Any:
        if node is None or depth > 40:
            return _UNKNOWN
        overrides = overrides or {}
        local_env = local_env or {}

        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.resolve_name(node.id, at_node, overrides, local_env, seen)
        if isinstance(node, ast.UnaryOp):
            value = self.eval_expr(node.operand, at_node, overrides, local_env, seen, depth + 1)
            if value is _UNKNOWN:
                return _UNKNOWN
            try:
                if isinstance(node.op, ast.USub):
                    return -value
                if isinstance(node.op, ast.UAdd):
                    return +value
                if isinstance(node.op, ast.Not):
                    return not value
                if isinstance(node.op, ast.Invert):
                    return ~value
            except Exception:
                return _UNKNOWN
        if isinstance(node, ast.BinOp):
            left = self.eval_expr(node.left, at_node, overrides, local_env, seen, depth + 1)
            right = self.eval_expr(node.right, at_node, overrides, local_env, seen, depth + 1)
            if left is _UNKNOWN or right is _UNKNOWN:
                return _UNKNOWN
            try:
                if isinstance(node.op, ast.Add): return left + right
                if isinstance(node.op, ast.Sub): return left - right
                if isinstance(node.op, ast.Mult): return left * right
                if isinstance(node.op, ast.Div): return left / right
                if isinstance(node.op, ast.FloorDiv): return left // right
                if isinstance(node.op, ast.Mod): return left % right
                if isinstance(node.op, ast.Pow): return left ** right
            except Exception:
                return _UNKNOWN
        if isinstance(node, ast.BoolOp):
            values = []
            for child in node.values:
                value = self.eval_expr(child, at_node, overrides, local_env, seen, depth + 1)
                if value is _UNKNOWN:
                    return _UNKNOWN
                values.append(value)
            if isinstance(node.op, ast.And):
                result = values[0] if values else True
                for value in values:
                    if not result:
                        return result
                    result = value
                return result
            if isinstance(node.op, ast.Or):
                result = values[0] if values else False
                for value in values:
                    if result:
                        return result
                    result = value
                return result
        if isinstance(node, ast.Compare):
            left = self.eval_expr(node.left, at_node, overrides, local_env, seen, depth + 1)
            if left is _UNKNOWN:
                return _UNKNOWN
            for op, comp in zip(node.ops, node.comparators):
                right = self.eval_expr(comp, at_node, overrides, local_env, seen, depth + 1)
                if right is _UNKNOWN:
                    return _UNKNOWN
                try:
                    if isinstance(op, ast.Eq): ok = left == right
                    elif isinstance(op, ast.NotEq): ok = left != right
                    elif isinstance(op, ast.Lt): ok = left < right
                    elif isinstance(op, ast.LtE): ok = left <= right
                    elif isinstance(op, ast.Gt): ok = left > right
                    elif isinstance(op, ast.GtE): ok = left >= right
                    elif isinstance(op, ast.In): ok = left in right
                    elif isinstance(op, ast.NotIn): ok = left not in right
                    elif isinstance(op, ast.Is): ok = left is right
                    elif isinstance(op, ast.IsNot): ok = left is not right
                    else: return _UNKNOWN
                except Exception:
                    return _UNKNOWN
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            test = self.eval_expr(node.test, at_node, overrides, local_env, seen, depth + 1)
            if test is _UNKNOWN:
                return _UNKNOWN
            chosen = node.body if test else node.orelse
            return self.eval_expr(chosen, at_node, overrides, local_env, seen, depth + 1)
        if isinstance(node, ast.Tuple):
            values = [self.eval_expr(e, at_node, overrides, local_env, seen, depth + 1) for e in node.elts]
            return _UNKNOWN if any(v is _UNKNOWN for v in values) else tuple(values)
        if isinstance(node, ast.List):
            values = [self.eval_expr(e, at_node, overrides, local_env, seen, depth + 1) for e in node.elts]
            return _UNKNOWN if any(v is _UNKNOWN for v in values) else values
        if isinstance(node, ast.Set):
            values = [self.eval_expr(e, at_node, overrides, local_env, seen, depth + 1) for e in node.elts]
            return _UNKNOWN if any(v is _UNKNOWN for v in values) else set(values)
        if isinstance(node, ast.Dict):
            keys = [self.eval_expr(k, at_node, overrides, local_env, seen, depth + 1) for k in node.keys]
            vals = [self.eval_expr(v, at_node, overrides, local_env, seen, depth + 1) for v in node.values]
            if any(v is _UNKNOWN for v in keys + vals):
                return _UNKNOWN
            try:
                return dict(zip(keys, vals))
            except Exception:
                return _UNKNOWN
        if isinstance(node, ast.Subscript):
            value = self.eval_expr(node.value, at_node, overrides, local_env, seen, depth + 1)
            index = self.eval_expr(node.slice, at_node, overrides, local_env, seen, depth + 1)
            if value is _UNKNOWN or index is _UNKNOWN:
                return _UNKNOWN
            try:
                return value[index]
            except Exception:
                return _UNKNOWN
        if isinstance(node, ast.Slice):
            lower = self.eval_expr(node.lower, at_node, overrides, local_env, seen, depth + 1) if node.lower else None
            upper = self.eval_expr(node.upper, at_node, overrides, local_env, seen, depth + 1) if node.upper else None
            step = self.eval_expr(node.step, at_node, overrides, local_env, seen, depth + 1) if node.step else None
            if any(v is _UNKNOWN for v in (lower, upper, step)):
                return _UNKNOWN
            return slice(lower, upper, step)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == 'self' and node.attr == 'cell_px':
                return self.NOMINAL_PX
            base = self.eval_expr(node.value, at_node, overrides, local_env, seen, depth + 1)
            if base is _UNKNOWN:
                return _UNKNOWN
            if isinstance(base, _RectValue) and node.attr in {
                'x', 'y', 'w', 'h', 'left', 'right', 'top', 'bottom',
                'centerx', 'centery', 'center'
            }:
                return getattr(base, node.attr)
            return _UNKNOWN
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            values = self._eval_comprehension(node, at_node, overrides, local_env, seen, depth + 1)
            if values is _UNKNOWN:
                return _UNKNOWN
            if isinstance(node, ast.SetComp):
                return set(values)
            if isinstance(node, ast.GeneratorExp):
                return tuple(values)
            return values
        if isinstance(node, ast.Call):
            return self._eval_call(node, at_node, overrides, local_env, seen, depth + 1)
        return _UNKNOWN

    def _eval_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.GeneratorExp,
        at_node: ast.AST,
        overrides: dict[str, Any],
        local_env: dict[str, Any],
        seen: set[tuple[str, int]] | None,
        depth: int,
    ) -> Any:
        results: list[Any] = []
        elt = node.elt

        def walk_generator(index: int, env: dict[str, Any]) -> bool:
            if index >= len(node.generators):
                value = self.eval_expr(elt, at_node, overrides, env, seen, depth + 1)
                if value is _UNKNOWN:
                    return False
                results.append(value)
                return True
            gen = node.generators[index]
            iterable = self.eval_expr(gen.iter, at_node, overrides, env, seen, depth + 1)
            if iterable is _UNKNOWN:
                return False
            try:
                seq = list(iterable)
            except Exception:
                return False
            if len(seq) > self.MAX_LOOP_EXPANSION:
                return False
            any_ok = False
            for item in seq:
                child_env = dict(env)
                if not self._bind_target(gen.target, item, child_env):
                    continue
                filters_ok = True
                for cond in gen.ifs:
                    verdict = self.eval_expr(cond, at_node, overrides, child_env, seen, depth + 1)
                    if verdict is _UNKNOWN or not verdict:
                        filters_ok = False
                        break
                if filters_ok:
                    any_ok = walk_generator(index + 1, child_env) or any_ok
            return any_ok

        return results if walk_generator(0, dict(local_env)) else _UNKNOWN

    def _eval_call(
        self,
        node: ast.Call,
        at_node: ast.AST,
        overrides: dict[str, Any],
        local_env: dict[str, Any],
        seen: set[tuple[str, int]] | None,
        depth: int,
    ) -> Any:
        # q() is not executed at nominal px. Its argument is already a logical
        # coordinate and preserving it gives the best round trip.
        if isinstance(node.func, ast.Name) and node.func.id == 'q' and node.args:
            return self.eval_expr(node.args[0], at_node, overrides, local_env, seen, depth + 1)

        args = [self.eval_expr(arg, at_node, overrides, local_env, seen, depth + 1) for arg in node.args]
        kwargs = {
            kw.arg: self.eval_expr(kw.value, at_node, overrides, local_env, seen, depth + 1)
            for kw in node.keywords if kw.arg is not None
        }

        if isinstance(node.func, ast.Name):
            name = node.func.id
            safe = {
                'max': max, 'min': min, 'abs': abs, 'round': round,
                'int': int, 'float': float, 'str': str, 'len': len,
                'bool': bool, 'sum': sum, 'tuple': tuple, 'list': list,
                'set': set, 'sorted': sorted, 'range': range,
                'reversed': lambda value: tuple(reversed(value)),
                'enumerate': lambda value: tuple(enumerate(value)),
            }
            if name in safe and all(v is not _UNKNOWN for v in args) and all(v is not _UNKNOWN for v in kwargs.values()):
                try:
                    return safe[name](*args, **kwargs)
                except Exception:
                    return _UNKNOWN
            func = self._find_function(name, at_node)
            if func is not None and depth <= self.MAX_HELPER_DEPTH:
                return self._eval_function(func, args, kwargs, at_node, overrides, depth + 1)

        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            # pygame.Rect / self.pygame.Rect
            if attr == 'Rect' and len(args) >= 4 and all(v is not _UNKNOWN for v in args[:4]):
                try:
                    return _RectValue(*(float(v) for v in args[:4]))
                except Exception:
                    return _UNKNOWN

            # Safe methods on already-evaluated ordinary values.
            base = self.eval_expr(node.func.value, at_node, overrides, local_env, seen, depth + 1)
            if base is not _UNKNOWN and attr in {
                'get', 'strip', 'lower', 'upper', 'startswith', 'endswith',
                'removeprefix', 'removesuffix', 'replace', 'count', 'index'
            } and all(v is not _UNKNOWN for v in args) and all(v is not _UNKNOWN for v in kwargs.values()):
                try:
                    method = getattr(base, attr)
                    return method(*args, **kwargs)
                except Exception:
                    return _UNKNOWN

            # Resolve pure helper methods from the same parsed source without
            # executing the module. Static methods and ordinary self methods
            # both land here.
            if self._is_self_attribute(node.func):
                func = self._find_function(attr, at_node)
                if func is not None and depth <= self.MAX_HELPER_DEPTH:
                    return self._eval_function(func, args, kwargs, at_node, overrides, depth + 1, called_as_method=True)

        return _UNKNOWN

    @staticmethod
    def _is_self_attribute(node: ast.Attribute) -> bool:
        value = node.value
        return isinstance(value, ast.Name) and value.id == 'self'

    def _find_function(
        self,
        name: str,
        at_node: ast.AST,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        rows = self.function_defs.get(name, ())
        if not rows:
            return None
        current = self.function_of.get(id(at_node))
        # Prefer a nested helper physically inside the current function.
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for candidate in rows:
                if candidate is current:
                    continue
                if (
                    getattr(current, 'lineno', 0) <= getattr(candidate, 'lineno', -1)
                    <= getattr(current, 'end_lineno', -1)
                ):
                    return candidate
        # Otherwise pick the nearest preceding definition with that name.
        line = getattr(at_node, 'lineno', 10**9)
        preceding = [row for row in rows if getattr(row, 'lineno', 0) <= line]
        return preceding[-1] if preceding else rows[0]

    def _eval_function(
        self,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        args: list[Any],
        kwargs: dict[str, Any],
        caller: ast.AST,
        overrides: dict[str, Any],
        depth: int,
        called_as_method: bool = False,
    ) -> Any:
        if depth > self.MAX_HELPER_DEPTH or any(v is _UNKNOWN for v in args) or any(v is _UNKNOWN for v in kwargs.values()):
            return _UNKNOWN
        params = list(func.args.posonlyargs) + list(func.args.args)
        env: dict[str, Any] = {}
        param_names = [p.arg for p in params]
        if called_as_method and param_names and param_names[0] in {'self', 'cls'}:
            env[param_names.pop(0)] = '<self>'
            params = params[1:]

        for param, value in zip(params, args):
            env[param.arg] = value
        for key, value in kwargs.items():
            env[key] = value

        defaults = list(func.args.defaults)
        start = len(params) - len(defaults)
        for index, default_node in enumerate(defaults, start=start):
            if index < 0 or index >= len(params):
                continue
            name = params[index].arg
            if name not in env:
                value = self.eval_expr(default_node, caller, overrides, env, depth=depth + 1)
                if value is not _UNKNOWN:
                    env[name] = value
        for param, default_node in zip(func.args.kwonlyargs, func.args.kw_defaults):
            if param.arg in env or default_node is None:
                continue
            value = self.eval_expr(default_node, caller, overrides, env, depth=depth + 1)
            if value is not _UNKNOWN:
                env[param.arg] = value

        result, returned = self._eval_statements(func.body, caller, overrides, env, depth + 1)
        return result if returned else _UNKNOWN

    def _eval_statements(
        self,
        statements: list[ast.stmt],
        caller: ast.AST,
        overrides: dict[str, Any],
        env: dict[str, Any],
        depth: int,
    ) -> tuple[Any, bool]:
        if depth > self.MAX_HELPER_DEPTH + 8:
            return _UNKNOWN, False
        for stmt in statements:
            if isinstance(stmt, ast.Return):
                value = self.eval_expr(stmt.value, caller, overrides, env, depth=depth + 1)
                return value, value is not _UNKNOWN
            if isinstance(stmt, ast.Assign):
                value = self.eval_expr(stmt.value, caller, overrides, env, depth=depth + 1)
                if value is _UNKNOWN:
                    continue
                for target in stmt.targets:
                    self._bind_target(target, value, env)
                continue
            if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                value = self.eval_expr(stmt.value, caller, overrides, env, depth=depth + 1)
                if value is not _UNKNOWN:
                    self._bind_target(stmt.target, value, env)
                continue
            if isinstance(stmt, ast.AugAssign):
                if isinstance(stmt.target, ast.Name) and stmt.target.id in env:
                    right = self.eval_expr(stmt.value, caller, overrides, env, depth=depth + 1)
                    if right is _UNKNOWN:
                        continue
                    left = env[stmt.target.id]
                    try:
                        if isinstance(stmt.op, ast.Add): env[stmt.target.id] = left + right
                        elif isinstance(stmt.op, ast.Sub): env[stmt.target.id] = left - right
                        elif isinstance(stmt.op, ast.Mult): env[stmt.target.id] = left * right
                    except Exception:
                        pass
                continue
            if isinstance(stmt, ast.If):
                test = self.eval_expr(stmt.test, caller, overrides, env, depth=depth + 1)
                if test is _UNKNOWN:
                    continue
                chosen = stmt.body if test else stmt.orelse
                result, returned = self._eval_statements(chosen, caller, overrides, env, depth + 1)
                if returned:
                    return result, True
                continue
            if isinstance(stmt, ast.For):
                iterable = self.eval_expr(stmt.iter, caller, overrides, env, depth=depth + 1)
                if iterable is _UNKNOWN:
                    continue
                try:
                    values = list(iterable)
                except Exception:
                    continue
                if len(values) > self.MAX_LOOP_EXPANSION:
                    continue
                for value in values:
                    if not self._bind_target(stmt.target, value, env):
                        continue
                    result, returned = self._eval_statements(stmt.body, caller, overrides, env, depth + 1)
                    if returned:
                        return result, True
                continue
        return _UNKNOWN, False

    # --------------------------------------------------------------
    # Adapter helpers
    # --------------------------------------------------------------

    def number(self, node: ast.AST, call: ast.Call, overrides: dict[str, Any]) -> float | None:
        value = self.eval_expr(node, call, overrides)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    def point(self, node: ast.AST, call: ast.Call, overrides: dict[str, Any]) -> list[float] | None:
        value = self.eval_expr(node, call, overrides)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            x, y = value[0], value[1]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
                return [float(x), float(y)]
        return None

    def points(self, node: ast.AST, call: ast.Call, overrides: dict[str, Any]) -> list[list[float]] | None:
        value = self.eval_expr(node, call, overrides)
        if not isinstance(value, (list, tuple)):
            return None
        result: list[list[float]] = []
        for entry in value:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                return None
            x, y = entry[0], entry[1]
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
                return None
            result.append([float(x), float(y)])
        return result

    def rect(self, node: ast.AST, call: ast.Call, overrides: dict[str, Any]) -> list[float] | None:
        value = self.eval_expr(node, call, overrides)
        if isinstance(value, _RectValue):
            return [value.x, value.y, value.w, value.h]
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            vals = value[:4]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                return [float(v) for v in vals]
        return None


class DrawcodeASTAdapter:
    """Translate the safe, q16-ish subset of pygame.draw AST into Shapes."""

    @staticmethod
    def primitive(call: ast.Call) -> str | None:
        return DrawCallCollector.draw_primitive(call)

    @staticmethod
    def _unparse(node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return "<?>"

    @classmethod
    def logical_number(
        cls,
        node: ast.AST,
        resolver: StaticDrawResolver | None = None,
        call: ast.Call | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> float | None:
        if resolver is not None and call is not None:
            value = resolver.number(node, call, overrides or {})
            if value is not None:
                return value

        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = cls.logical_number(node.operand, resolver, call, overrides)
            if value is None:
                return None
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "q" and node.args:
            return cls.logical_number(node.args[0], resolver, call, overrides)
        if isinstance(node, ast.Name) and node.id == "mid_x":
            return LOGICAL_SIZE / 2
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            left = cls.logical_number(node.left, resolver, call, overrides)
            right = cls.logical_number(node.right, resolver, call, overrides)
            if left is None or right is None:
                return None
            return left + right if isinstance(node.op, ast.Add) else left - right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"max", "min"}:
            for arg in node.args:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "q" and arg.args:
                    value = cls.logical_number(arg.args[0], resolver, call, overrides)
                    if value is not None:
                        return value
            values = [cls.logical_number(arg, resolver, call, overrides) for arg in node.args]
            values = [v for v in values if v is not None]
            if values:
                return max(values) if node.func.id == "max" else min(values)
        return None

    @classmethod
    def point(
        cls,
        node: ast.AST,
        resolver: StaticDrawResolver | None = None,
        call: ast.Call | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> list[float] | None:
        if resolver is not None and call is not None:
            value = resolver.point(node, call, overrides or {})
            if value is not None:
                return value
        if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) < 2:
            return None
        x = cls.logical_number(node.elts[0], resolver, call, overrides)
        y = cls.logical_number(node.elts[1], resolver, call, overrides)
        if x is None or y is None:
            return None
        return [x, y]

    @classmethod
    def points(
        cls,
        node: ast.AST,
        resolver: StaticDrawResolver | None = None,
        call: ast.Call | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> list[list[float]] | None:
        if resolver is not None and call is not None:
            value = resolver.points(node, call, overrides or {})
            if value is not None:
                return value
        if not isinstance(node, (ast.Tuple, ast.List)):
            return None
        result: list[list[float]] = []
        for entry in node.elts:
            point = cls.point(entry, resolver, call, overrides)
            if point is None:
                return None
            result.append(point)
        return result

    @classmethod
    def rect(
        cls,
        node: ast.AST,
        resolver: StaticDrawResolver | None = None,
        call: ast.Call | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> list[float] | None:
        if resolver is not None and call is not None:
            value = resolver.rect(node, call, overrides or {})
            if value is not None:
                return value
        values: list[ast.AST] | None = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Rect":
            if len(node.args) >= 4:
                values = list(node.args[:4])
            elif len(node.args) == 1 and isinstance(node.args[0], (ast.Tuple, ast.List)):
                values = list(node.args[0].elts[:4])
        elif isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) >= 4:
            values = list(node.elts[:4])
        if values is None or len(values) < 4:
            return None
        parsed = [cls.logical_number(v, resolver, call, overrides) for v in values]
        if any(v is None for v in parsed):
            return None
        return [float(v) for v in parsed if v is not None]

    @classmethod
    def color(cls, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) >= 3:
            vals = [cls.logical_number(v) for v in node.elts[:3]]
            if all(v is not None for v in vals):
                rgb = tuple(int(clamp(round(float(v)), 0, 255)) for v in vals)
                return rgb_to_hex(rgb)
        return "expr:" + cls._unparse(node)

    @classmethod
    def width(
        cls,
        call: ast.Call,
        positional_index: int,
        resolver: StaticDrawResolver | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> float:
        node: ast.AST | None = None
        if len(call.args) > positional_index:
            node = call.args[positional_index]
        for kw in call.keywords:
            if kw.arg == "width":
                node = kw.value
        if node is None:
            return 0.0
        value = cls.logical_number(node, resolver, call, overrides)
        return max(0.0, float(value)) if value is not None else 1.0

    @classmethod
    def shape_from_call(
        cls,
        call: ast.Call,
        name: str,
        resolver: StaticDrawResolver | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> Shape | None:
        overrides = overrides or {}
        primitive = cls.primitive(call)
        if primitive is None or len(call.args) < 2:
            return None
        color = cls.color(call.args[1])

        if primitive in {"rect", "ellipse"}:
            if len(call.args) < 3:
                return None
            bbox = cls.rect(call.args[2], resolver, call, overrides)
            if bbox is None:
                return None
            width = cls.width(call, 3, resolver, overrides)
            if width > 0:
                return Shape(kind=primitive, name=name, color=color, outline=color,
                             width=width, bbox=bbox, filled=False)
            return Shape(kind=primitive, name=name, color=color, bbox=bbox, filled=True)

        if primitive == "circle":
            if len(call.args) < 4:
                return None
            center = cls.point(call.args[2], resolver, call, overrides)
            radius = cls.logical_number(call.args[3], resolver, call, overrides)
            if center is None or radius is None:
                return None
            width = cls.width(call, 4, resolver, overrides)
            if width > 0:
                return Shape(kind="circle", name=name, color=color, outline=color,
                             width=width, bbox=[center[0], center[1], 0, 0],
                             radius=radius, filled=False)
            return Shape(kind="circle", name=name, color=color,
                         bbox=[center[0], center[1], 0, 0], radius=radius, filled=True)

        if primitive == "line":
            if len(call.args) < 4:
                return None
            p1 = cls.point(call.args[2], resolver, call, overrides)
            p2 = cls.point(call.args[3], resolver, call, overrides)
            if p1 is None or p2 is None:
                return None
            width = cls.width(call, 4, resolver, overrides) or 1.0
            return Shape(kind="line", name=name, color=color, width=width, points=[p1, p2])

        if primitive == "lines":
            if len(call.args) < 5:
                return None
            closed_node = call.args[2]
            closed_value = resolver.eval_expr(closed_node, call, overrides) if resolver else _UNKNOWN
            closed = bool(closed_value) if closed_value is not _UNKNOWN else (
                bool(closed_node.value) if isinstance(closed_node, ast.Constant) else False
            )
            pts = cls.points(call.args[3], resolver, call, overrides)
            if pts is None:
                return None
            width = cls.width(call, 4, resolver, overrides) or 1.0
            return Shape(kind="line", name=name, color=color, width=width,
                         points=pts, closed=closed)

        if primitive == "polygon":
            if len(call.args) < 3:
                return None
            pts = cls.points(call.args[2], resolver, call, overrides)
            if pts is None:
                return None
            width = cls.width(call, 3, resolver, overrides)
            if width > 0:
                return Shape(kind="polygon", name=name, color=color, outline=color,
                             width=width, points=pts, filled=False)
            return Shape(kind="polygon", name=name, color=color, points=pts, filled=True)
        return None

    @staticmethod
    def geometry_key(shape: Shape) -> tuple[Any, ...]:
        return (
            shape.kind,
            tuple(round(v, 6) for v in shape.bbox),
            round(shape.radius, 6),
            tuple((round(p[0], 6), round(p[1], 6)) for p in shape.points),
        )

    @classmethod
    def merge_fill_outline_pairs(cls, shapes: list[Shape]) -> list[Shape]:
        """Collapse common fill-then-outline draw pairs into one editable shape."""
        result: list[Shape] = []
        for shape in shapes:
            if (
                result
                and not shape.filled
                and shape.outline
                and result[-1].filled
                and not result[-1].outline
                and cls.geometry_key(result[-1]) == cls.geometry_key(shape)
            ):
                result[-1].outline = shape.outline
                result[-1].width = shape.width
                continue
            result.append(shape)
        return result

@register_mode
class GfxMode(EditorMode):
    mode_id = "gfx"
    mode_title = "GFX"
    mode_description = "Procedural Pygame drawcode authoring"

    def __init__(self, app: "WorkbenchApp", parent: tk.Misc) -> None:
        super().__init__(app, parent)

        self.zoom = DEFAULT_ZOOM
        self.snap = DEFAULT_SNAP
        self.grid_visible = True

        self.palette: dict[str, tuple[int, int, int]] = dict(self.services.palette.colors)
        self.palette_path: str | None = self.services.palette.path

        self.shapes: list[Shape] = []
        self.selected_index: int | None = None
        self.selected_vertex: int | None = None

        self.tool = "select"
        self.drag_origin_logical: tuple[float, float] | None = None
        self.drag_last_logical: tuple[float, float] | None = None
        self.creation_start: tuple[float, float] | None = None
        self.creation_preview: tuple[float, float] | None = None
        self.polygon_draft: list[list[float]] = []

        self.project_path: Path | None = None
        self.dirty = False

        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        self._history_lock = False
        self._drag_snapshot_taken = False

        self._build_style()
        self._build_ui()

        self._new_demo()
        self._push_undo("initial")
        self.redraw()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Tool.TButton", padding=(7, 4))
        style.configure("SelectedTool.TButton", padding=(7, 4), relief="sunken")
        style.configure("Inspector.TLabelframe", padding=6)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        toolbar = ttk.Frame(root, padding=(6, 5))
        toolbar.pack(side="top", fill="x")

        self.tool_buttons: dict[str, ttk.Button] = {}
        for tool, label in [
            ("select", "Select"),
            ("rect", "Rect"),
            ("ellipse", "Ellipse"),
            ("circle", "Circle"),
            ("line", "Line"),
            ("polygon", "Polygon"),
        ]:
            button = ttk.Button(
                toolbar,
                text=label,
                style="Tool.TButton",
                command=lambda t=tool: self.set_tool(t),
            )
            button.pack(side="left", padx=(0, 4))
            self.tool_buttons[tool] = button

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=7)

        ttk.Label(toolbar, text="Snap").pack(side="left")
        self.snap_var = tk.StringVar(value=fmt_num(self.snap))
        snap_combo = ttk.Combobox(
            toolbar,
            textvariable=self.snap_var,
            values=("1", "0.5", "0.25", "0.125", "0"),
            width=6,
            state="readonly",
        )
        snap_combo.pack(side="left", padx=(4, 9))
        snap_combo.bind("<<ComboboxSelected>>", self._on_snap_changed)

        ttk.Label(toolbar, text="Zoom").pack(side="left")
        self.zoom_label = ttk.Label(toolbar, text=f"{self.zoom}px/u", width=8)
        self.zoom_label.pack(side="left", padx=(4, 5))
        ttk.Button(toolbar, text="−", width=3, command=lambda: self.change_zoom(-4)).pack(side="left")
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.change_zoom(+4)).pack(side="left", padx=(2, 0))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Button(toolbar, text="Import Bakerrrr…", command=self.import_bakerrrr_python).pack(side="left")
        ttk.Button(toolbar, text="Palette…", command=self.load_palette).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="Copy Code", command=self.copy_code).pack(side="left", padx=(5, 0))

        main_pane = ttk.Panedwindow(root, orient="horizontal")
        main_pane.pack(fill="both", expand=True)

        # Left: layers
        left = ttk.Frame(main_pane, padding=6)
        main_pane.add(left, weight=1)

        ttk.Label(left, text="Layers").pack(anchor="w")

        layer_frame = ttk.Frame(left)
        layer_frame.pack(fill="both", expand=True, pady=(4, 5))

        self.layer_list = tk.Listbox(
            layer_frame,
            exportselection=False,
            activestyle="none",
            width=24,
        )
        self.layer_list.pack(side="left", fill="both", expand=True)
        layer_scroll = ttk.Scrollbar(layer_frame, orient="vertical", command=self.layer_list.yview)
        layer_scroll.pack(side="right", fill="y")
        self.layer_list.configure(yscrollcommand=layer_scroll.set)
        self.layer_list.bind("<<ListboxSelect>>", self._on_layer_select)

        layer_buttons = ttk.Frame(left)
        layer_buttons.pack(fill="x")
        ttk.Button(layer_buttons, text="↑", width=4, command=lambda: self.move_layer(+1)).pack(side="left")
        ttk.Button(layer_buttons, text="↓", width=4, command=lambda: self.move_layer(-1)).pack(side="left", padx=(3, 0))
        ttk.Button(layer_buttons, text="Dup", command=self.duplicate_selected).pack(side="left", padx=(7, 0))
        ttk.Button(layer_buttons, text="Del", command=self.delete_selected).pack(side="left", padx=(3, 0))

        # Center: canvas
        center = ttk.Frame(main_pane, padding=(0, 6))
        main_pane.add(center, weight=5)

        canvas_holder = ttk.Frame(center)
        canvas_holder.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            canvas_holder,
            background="#202329",
            highlightthickness=1,
            highlightbackground="#555a62",
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.change_zoom(+4))
        self.canvas.bind("<Button-5>", lambda e: self.change_zoom(-4))

        # Right: inspector + code
        right = ttk.Frame(main_pane, padding=6)
        main_pane.add(right, weight=3)

        inspector = ttk.LabelFrame(right, text="Inspector", style="Inspector.TLabelframe")
        inspector.pack(fill="x")

        self.name_var = tk.StringVar()
        self.kind_var = tk.StringVar()
        self.color_var = tk.StringVar()
        self.outline_var = tk.StringVar()
        self.width_var = tk.StringVar()
        self.geometry_var = tk.StringVar()
        self.filled_var = tk.BooleanVar(value=True)

        self._row(inspector, 0, "Name", ttk.Entry(inspector, textvariable=self.name_var))
        kind_label = ttk.Label(inspector, textvariable=self.kind_var)
        self._row(inspector, 1, "Kind", kind_label)

        self.color_combo = ttk.Combobox(inspector, textvariable=self.color_var, state="normal")
        self._row(inspector, 2, "Color", self.color_combo)

        self.outline_combo = ttk.Combobox(inspector, textvariable=self.outline_var, state="normal")
        self._row(inspector, 3, "Outline", self.outline_combo)

        width_entry = ttk.Entry(inspector, textvariable=self.width_var)
        self._row(inspector, 4, "Width", width_entry)

        geometry_entry = ttk.Entry(inspector, textvariable=self.geometry_var)
        self._row(inspector, 5, "Geometry", geometry_entry)
        filled_check = ttk.Checkbutton(inspector, text="Filled", variable=self.filled_var)
        self._row(inspector, 6, "Fill mode", filled_check)

        inspector.columnconfigure(1, weight=1)

        apply_row = ttk.Frame(inspector)
        apply_row.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Button(apply_row, text="Apply", command=self.apply_inspector).pack(side="left")
        ttk.Button(apply_row, text="Pick Color…", command=self.pick_preview_color).pack(side="left", padx=(4, 0))
        ttk.Button(apply_row, text="Toggle Visible", command=self.toggle_selected_visibility).pack(side="right")

        code_frame = ttk.LabelFrame(right, text="Live drawcode", padding=5)
        code_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.code_text = tk.Text(
            code_frame,
            wrap="none",
            undo=False,
            font=("TkFixedFont", 10),
            height=20,
            background="#17191d",
            foreground="#e8e8e8",
            insertbackground="#e8e8e8",
        )
        self.code_text.pack(side="left", fill="both", expand=True)
        code_y = ttk.Scrollbar(code_frame, orient="vertical", command=self.code_text.yview)
        code_y.pack(side="right", fill="y")
        self.code_text.configure(yscrollcommand=code_y.set)

        status = ttk.Frame(root, padding=(6, 3))
        status.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")
        self.cursor_var = tk.StringVar(value="")
        ttk.Label(status, textvariable=self.cursor_var).pack(side="right")

        self._refresh_palette_widgets()
        self._update_tool_buttons()

    @staticmethod
    def _row(parent: tk.Widget, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 7), pady=2)
        widget.grid(row=row, column=1, sticky="ew", pady=2)

    def _tool_hotkey(self, event: tk.Event, tool: str) -> None:
        focus = self.focus_get()
        if isinstance(focus, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)):
            return
        self.set_tool(tool)

    def _nudge_amount(self, event: tk.Event) -> float:
        # Shift = one logical unit. Plain arrows = snap quantum.
        if event.state & 0x0001:
            return 1.0
        return self.snap if self.snap > 0 else 0.25

    # ------------------------------------------------------------------
    # Project/history
    # ------------------------------------------------------------------

    def _new_demo(self) -> None:
        self.shapes = [
            Shape(
                kind="polygon",
                name="body",
                color="fill",
                outline="edge",
                width=1,
                points=[[5.0, 5.0], [11.0, 5.0], [12.0, 12.5], [4.0, 12.5]],
            ),
            Shape(
                kind="line",
                name="neckline",
                color="edge",
                width=1,
                points=[[6.0, 5.2], [8.0, 6.5], [10.0, 5.2]],
            ),
            Shape(
                kind="ellipse",
                name="detail",
                color="highlight",
                outline="",
                width=0,
                bbox=[7.25, 8.2, 1.5, 1.0],
            ),
        ]
        self.selected_index = 0
        self.selected_vertex = None
        self.project_path = None
        self.dirty = False

    def project_dict(self) -> dict[str, Any]:
        return {
            "format": "bakerrrr-drawcode-project",
            "version": GFX_PROJECT_VERSION,
            "logical_size": LOGICAL_SIZE,
            "snap": self.snap,
            "palette_path": self.palette_path,
            "shapes": [asdict(shape) for shape in self.shapes],
        }

    def _snapshot(self) -> dict[str, Any]:
        return {
            "shapes": copy.deepcopy(self.shapes),
            "selected_index": self.selected_index,
            "selected_vertex": self.selected_vertex,
        }

    def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._history_lock = True
        try:
            self.shapes = copy.deepcopy(snapshot["shapes"])
            self.selected_index = snapshot.get("selected_index")
            self.selected_vertex = snapshot.get("selected_vertex")
            self.redraw()
            self.mark_dirty(True)
        finally:
            self._history_lock = False

    def _push_undo(self, reason: str = "") -> None:
        if self._history_lock:
            return
        snapshot = self._snapshot()
        if self.undo_stack and self._snapshots_equal(self.undo_stack[-1], snapshot):
            return
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 120:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        if reason:
            self.status_var.set(reason)

    @staticmethod
    def _snapshots_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
        return (
            a.get("selected_index") == b.get("selected_index")
            and a.get("selected_vertex") == b.get("selected_vertex")
            and a.get("shapes") == b.get("shapes")
        )

    def undo(self) -> None:
        if len(self.undo_stack) <= 1:
            self.bell()
            return
        current = self.undo_stack.pop()
        self.redo_stack.append(current)
        self._restore_snapshot(self.undo_stack[-1])
        self.status_var.set("Undo")

    def redo(self) -> None:
        if not self.redo_stack:
            self.bell()
            return
        snapshot = self.redo_stack.pop()
        self.undo_stack.append(copy.deepcopy(snapshot))
        self._restore_snapshot(snapshot)
        self.status_var.set("Redo")

    def mark_dirty(self, dirty: bool = True) -> None:
        self.dirty = dirty
        self.app.refresh_title()

    def project_label(self) -> str:
        return self.project_path.name if self.project_path else self.mode_title

    def maybe_save_changes(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes to the current project?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return bool(self.save_project())
        return True

    def new_project(self) -> None:
        if not self.maybe_save_changes():
            return
        self.shapes = []
        self.selected_index = None
        self.selected_vertex = None
        self.project_path = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.cancel_current_tool()
        self.mark_dirty(False)
        self._push_undo("New project")
        self.redraw()

    def open_project(self) -> None:
        if not self.maybe_save_changes():
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Open Bakerrrr drawcode project",
            filetypes=[("Bakerrrr draw project", "*.json"), ("JSON", "*.json"), ("All files", "*")],
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "shapes" not in data:
                raise ValueError("Not a drawcode project")
            shapes = [Shape.from_dict(row) for row in data.get("shapes", []) if isinstance(row, dict)]
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return

        self.shapes = shapes
        self.snap = float(data.get("snap", DEFAULT_SNAP))
        self.snap_var.set(fmt_num(self.snap))
        self.selected_index = 0 if self.shapes else None
        self.selected_vertex = None
        self.project_path = Path(path)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.cancel_current_tool()

        palette_path = data.get("palette_path")
        if isinstance(palette_path, str) and palette_path:
            candidate = Path(palette_path)
            if candidate.exists():
                self._load_palette_path(candidate, quiet=True)

        self.mark_dirty(False)
        self._push_undo("Project loaded")
        self.redraw()

    def save_project(self) -> bool:
        if self.project_path is None:
            return self.save_project_as()
        try:
            self.project_path.write_text(
                json.dumps(self.project_dict(), indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return False
        self.mark_dirty(False)
        self.status_var.set(f"Saved {self.project_path.name}")
        return True

    def save_project_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Bakerrrr drawcode project",
            defaultextension=".json",
            filetypes=[("Bakerrrr draw project", "*.json"), ("JSON", "*.json")],
        )
        if not path:
            return False
        self.project_path = Path(path)
        return self.save_project()

    # ------------------------------------------------------------------
    # Bakerrrr source import
    # ------------------------------------------------------------------

    def import_bakerrrr_python(self) -> None:
        initial = str(self.services.game.root) if self.services.game.root else str(Path.cwd())
        path = filedialog.askopenfilename(
            parent=self,
            title="Import procedural gfx from Bakerrrr Python",
            initialdir=initial,
            filetypes=[("Python", "*.py"), ("All files", "*")],
        )
        if not path:
            return
        try:
            resolved, source, tree = self.services.game.parse_python(Path(path))
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)
            return

        collector = DrawCallCollector()
        collector.visit(tree)
        candidates = collector.candidates()
        if not candidates:
            messagebox.showinfo(
                "No drawcode found",
                "No supported pygame.draw rect/ellipse/circle/line/lines/polygon calls were found.",
                parent=self,
            )
            return

        dialog = ImportScopeDialog(self, self.services.game.display_path(resolved), candidates)
        if not dialog.selected:
            return

        # One call can appear in both a function-wide and branch candidate.
        calls: list[ast.Call] = []
        seen: set[tuple[int, int, str]] = set()
        for candidate in dialog.selected:
            for call in candidate.calls:
                key = (getattr(call, "lineno", -1), getattr(call, "col_offset", -1),
                       DrawCallCollector.draw_primitive(call) or "")
                if key not in seen:
                    seen.add(key)
                    calls.append(call)
        calls.sort(key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)))

        resolver = StaticDrawResolver(tree)
        imported: list[Shape] = []
        skipped: list[int] = []
        for i, call in enumerate(calls, 1):
            primitive = DrawCallCollector.draw_primitive(call) or "shape"
            contexts = resolver.contexts_for_call(call)
            call_imported = False
            for context_index, context in enumerate(contexts, 1):
                suffix = f"_{context_index}" if len(contexts) > 1 else ""
                shape = DrawcodeASTAdapter.shape_from_call(
                    call,
                    self.unique_shape_name(
                        f"import_{primitive}_{getattr(call, 'lineno', i)}{suffix}"
                    ),
                    resolver=resolver,
                    overrides=context,
                )
                if shape is not None:
                    imported.append(shape)
                    call_imported = True
            if not call_imported:
                skipped.append(getattr(call, "lineno", -1))

        imported = DrawcodeASTAdapter.merge_fill_outline_pairs(imported)
        if not imported:
            lines = ", ".join(str(n) for n in skipped[:20] if n >= 0)
            messagebox.showwarning(
                "Nothing importable",
                "Draw calls were found, but those particular expressions still depend on runtime state the static importer could not resolve."
                + (f"\n\nSkipped lines: {lines}" if lines else ""),
                parent=self,
            )
            return

        self._push_undo("Import Bakerrrr drawcode")
        if dialog.replace_existing:
            self.shapes.clear()
            self.selected_index = None
            self.selected_vertex = None
        self.shapes.extend(imported)
        self.selected_index = len(self.shapes) - len(imported)
        self.selected_vertex = None
        self.mark_dirty(True)
        self._push_undo("Imported Bakerrrr drawcode")
        self.redraw()
        msg = f"Imported {len(imported)} editable shape{'s' if len(imported) != 1 else ''} from {resolved.name}"
        if skipped:
            msg += f"; skipped {len(skipped)} expression{'s' if len(skipped) != 1 else ''}"
        self.status_var.set(msg)
        self.set_shell_status(msg)

    def accept_external_shapes(
        self,
        shapes: list[Shape],
        source_label: str,
        *,
        replace: bool,
    ) -> bool:
        """Receive editable shapes from another workbench mode."""
        incoming = copy.deepcopy(shapes)
        if not incoming:
            return False

        if replace and self.dirty and not self.maybe_save_changes():
            return False

        self._push_undo("Receive shapes")
        if replace:
            self.shapes.clear()
            self.selected_index = None
            self.selected_vertex = None
            self.project_path = None

        used = {shape.name for shape in self.shapes}
        for shape in incoming:
            base = shape.name or shape.kind
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            shape.name = candidate
            used.add(candidate)
            self.shapes.append(shape)

        self.selected_index = len(self.shapes) - len(incoming)
        self.selected_vertex = None
        self.mark_dirty(True)
        self._push_undo("Received shapes")
        self.redraw()

        verb = "Opened" if replace else "Appended"
        msg = f"{verb} {len(incoming)} shape{'s' if len(incoming) != 1 else ''} from {source_label}"
        self.status_var.set(msg)
        self.set_shell_status(msg)
        return True

    # ------------------------------------------------------------------
    # Shell action contract
    # ------------------------------------------------------------------

    def handle_action(self, action: str, event: tk.Event | None = None) -> bool:
        actions = {
            "new": self.new_project,
            "open": self.open_project,
            "import": self.import_bakerrrr_python,
            "save": self.save_project,
            "save_as": self.save_project_as,
            "export": self.export_code_file,
            "copy": self.copy_code,
            "undo": self.undo,
            "redo": self.redo,
            "duplicate": self.duplicate_selected,
            "delete": self.delete_selected,
            "layer_forward": lambda: self.move_layer(+1),
            "layer_backward": lambda: self.move_layer(-1),
            "zoom_in": lambda: self.change_zoom(+4),
            "zoom_out": lambda: self.change_zoom(-4),
            "zoom_reset": self.reset_zoom,
            "toggle_grid": self.toggle_grid,
            "palette": self.load_palette,
            "help": self.show_controls,
        }
        func = actions.get(action)
        if func is None:
            return False
        func()
        return True

    def handle_keypress(self, event: tk.Event) -> bool:
        focus = self.focus_get()
        typing = isinstance(focus, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))

        if event.keysym in {"Up", "Down", "Left", "Right"} and not typing:
            amount = self._nudge_amount(event)
            dx = (-amount if event.keysym == "Left" else amount if event.keysym == "Right" else 0)
            dy = (-amount if event.keysym == "Up" else amount if event.keysym == "Down" else 0)
            self.nudge_selected(dx, dy)
            return True

        if typing:
            return False

        tool_keys = {"v": "select", "r": "rect", "e": "ellipse", "c": "circle", "l": "line", "p": "polygon"}
        char = (event.char or "").lower()
        if char in tool_keys and not (event.state & 0x0004):
            self.set_tool(tool_keys[char])
            return True
        if event.keysym == "Escape":
            self.cancel_current_tool()
            return True
        if event.keysym in {"Return", "KP_Enter"}:
            self.finish_polygon()
            return True
        if event.keysym == "Delete":
            self.delete_selected()
            return True
        if event.keysym == "bracketleft":
            self.move_layer(-1)
            return True
        if event.keysym == "bracketright":
            self.move_layer(+1)
            return True
        return False

    # ------------------------------------------------------------------
    # Palette
    # ------------------------------------------------------------------

    def load_palette(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Load color palette JSON",
            filetypes=[("JSON palette", "*.json"), ("All files", "*")],
        )
        if path:
            self._load_palette_path(Path(path), quiet=False)

    def _load_palette_path(self, path: Path, quiet: bool = False) -> None:
        try:
            count = self.services.palette.load(path)
        except Exception as exc:
            if not quiet:
                messagebox.showerror("Palette load failed", str(exc), parent=self)
            return

        self.palette = dict(self.services.palette.colors)
        self.palette_path = self.services.palette.path
        self._refresh_palette_widgets()
        self.redraw()
        self.status_var.set(f"Loaded {count} palette colors from {path.name}")
        self.set_shell_status(f"Palette: {path.name}")

    def _refresh_palette_widgets(self) -> None:
        names = sorted(self.palette)
        if hasattr(self, "color_combo"):
            self.color_combo.configure(values=names)
            self.outline_combo.configure(values=[""] + names)

    def resolve_color(self, token: str) -> tuple[int, int, int]:
        text = (token or "").strip()
        if text in self.palette:
            return self.palette[text]
        parsed = parse_hex_color(text)
        if parsed:
            return parsed
        # Stable fallback based on token text.
        h = sum((i + 1) * ord(ch) for i, ch in enumerate(text))
        return (
            70 + h % 150,
            70 + (h // 7) % 150,
            70 + (h // 17) % 150,
        )

    def pick_preview_color(self) -> None:
        if self.selected_index is None:
            return
        shape = self.shapes[self.selected_index]
        initial = rgb_to_hex(self.resolve_color(shape.color))
        chosen = colorchooser.askcolor(color=initial, parent=self)
        if not chosen or not chosen[1]:
            return
        token = chosen[1].lower()
        self.color_var.set(token)
        self.apply_inspector()

    # ------------------------------------------------------------------
    # Coordinate transforms / drawing
    # ------------------------------------------------------------------

    def artboard_origin(self) -> tuple[float, float]:
        width = LOGICAL_SIZE * self.zoom
        height = LOGICAL_SIZE * self.zoom
        x = max(10.0, (self.canvas.winfo_width() - width) / 2)
        y = max(10.0, (self.canvas.winfo_height() - height) / 2)
        return x, y

    def logical_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.artboard_origin()
        return ox + x * self.zoom, oy + y * self.zoom

    def canvas_to_logical(self, cx: float, cy: float, do_snap: bool = True) -> tuple[float, float]:
        ox, oy = self.artboard_origin()
        x = (cx - ox) / self.zoom
        y = (cy - oy) / self.zoom
        if do_snap:
            x = snap_value(x, self.snap)
            y = snap_value(y, self.snap)
        return clamp(x, -32, 48), clamp(y, -32, 48)

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self._draw_artboard()

        for index, shape in enumerate(self.shapes):
            if shape.visible:
                self._draw_shape(shape, index == self.selected_index)

        if self.polygon_draft:
            self._draw_polygon_draft()

        if self.tool in {"rect", "ellipse", "circle", "line"} and self.creation_start and self.creation_preview:
            self._draw_creation_preview()

        self._refresh_layers()
        self._refresh_inspector()
        self._refresh_code()

    def _draw_artboard(self) -> None:
        ox, oy = self.artboard_origin()
        size = LOGICAL_SIZE * self.zoom
        self.canvas.create_rectangle(
            ox, oy, ox + size, oy + size,
            fill="#2b2f35",
            outline="#8b929d",
            width=1,
            tags=("artboard",),
        )

        if not self.grid_visible:
            return

        # Quarter-unit subdivision only when zoom makes it useful.
        minor = 0.25 if self.zoom >= 28 else 0.5
        steps = int(LOGICAL_SIZE / minor)
        for i in range(steps + 1):
            u = i * minor
            x, _ = self.logical_to_canvas(u, 0)
            _, y = self.logical_to_canvas(0, u)

            is_major = abs(u - round(u)) < 1e-9
            is_center = abs(u - 8.0) < 1e-9

            if is_center:
                color = "#7a626e"
                width = 2
            elif is_major:
                color = "#454b54"
                width = 1
            else:
                color = "#363b42"
                width = 1

            self.canvas.create_line(x, oy, x, oy + size, fill=color, width=width)
            self.canvas.create_line(ox, y, ox + size, y, fill=color, width=width)

        # Logical boundary labels.
        for value in (0, 4, 8, 12, 16):
            x, _ = self.logical_to_canvas(value, 0)
            _, y = self.logical_to_canvas(0, value)
            self.canvas.create_text(x + 2, oy - 7, text=str(value), fill="#aeb5bf", anchor="s", font=("TkDefaultFont", 8))
            self.canvas.create_text(ox - 6, y, text=str(value), fill="#aeb5bf", anchor="e", font=("TkDefaultFont", 8))

    def _draw_shape(self, shape: Shape, selected: bool = False) -> None:
        fill = rgb_to_hex(self.resolve_color(shape.color)) if shape.filled or shape.kind == "line" else ""
        outline = rgb_to_hex(self.resolve_color(shape.outline)) if shape.outline else ""
        width_px = max(1, int(round(shape.width * max(1, self.zoom / 16)))) if shape.width > 0 else 1

        if shape.kind == "rect":
            x, y, w, h = shape.bbox
            p1 = self.logical_to_canvas(x, y)
            p2 = self.logical_to_canvas(x + w, y + h)
            self.canvas.create_rectangle(*p1, *p2, fill=fill, outline=outline, width=width_px)

        elif shape.kind == "ellipse":
            x, y, w, h = shape.bbox
            p1 = self.logical_to_canvas(x, y)
            p2 = self.logical_to_canvas(x + w, y + h)
            self.canvas.create_oval(*p1, *p2, fill=fill, outline=outline, width=width_px)

        elif shape.kind == "circle":
            cx, cy = shape.bbox[0], shape.bbox[1]
            r = shape.radius
            p1 = self.logical_to_canvas(cx - r, cy - r)
            p2 = self.logical_to_canvas(cx + r, cy + r)
            self.canvas.create_oval(*p1, *p2, fill=fill, outline=outline, width=width_px)

        elif shape.kind == "line":
            coords: list[float] = []
            for x, y in shape.points:
                coords.extend(self.logical_to_canvas(x, y))
            if len(coords) >= 4:
                self.canvas.create_line(
                    *coords,
                    fill=fill,
                    width=max(1, int(round(max(shape.width, 0.5) * self.zoom / 8))),
                    capstyle="round",
                    joinstyle="round",
                )

        elif shape.kind == "polygon":
            coords = []
            for x, y in shape.points:
                coords.extend(self.logical_to_canvas(x, y))
            if len(coords) >= 6:
                self.canvas.create_polygon(
                    *coords,
                    fill=fill,
                    outline=outline,
                    width=width_px,
                    joinstyle="round",
                )

        if selected:
            self._draw_selection(shape)

    def _draw_selection(self, shape: Shape) -> None:
        bounds = self.shape_canvas_bounds(shape)
        if bounds:
            x1, y1, x2, y2 = bounds
            self.canvas.create_rectangle(
                x1 - SELECTION_PAD,
                y1 - SELECTION_PAD,
                x2 + SELECTION_PAD,
                y2 + SELECTION_PAD,
                outline="#ffd45b",
                width=1,
                dash=(4, 3),
            )

        if shape.kind in {"polygon", "line"}:
            for i, (x, y) in enumerate(shape.points):
                cx, cy = self.logical_to_canvas(x, y)
                selected = i == self.selected_vertex
                r = HANDLE_RADIUS + (1 if selected else 0)
                self.canvas.create_rectangle(
                    cx - r, cy - r, cx + r, cy + r,
                    fill="#fff0a8" if selected else "#ffd45b",
                    outline="#332b16",
                    width=1,
                )

    def _draw_polygon_draft(self) -> None:
        coords: list[float] = []
        for x, y in self.polygon_draft:
            coords.extend(self.logical_to_canvas(x, y))

        if len(coords) >= 4:
            self.canvas.create_line(*coords, fill="#ffd45b", width=2, dash=(4, 2))

        if self.creation_preview and self.polygon_draft:
            x1, y1 = self.logical_to_canvas(*self.polygon_draft[-1])
            x2, y2 = self.logical_to_canvas(*self.creation_preview)
            self.canvas.create_line(x1, y1, x2, y2, fill="#ffd45b", width=1, dash=(2, 2))

        for x, y in self.polygon_draft:
            cx, cy = self.logical_to_canvas(x, y)
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#ffd45b", outline="")

    def _draw_creation_preview(self) -> None:
        sx, sy = self.creation_start
        ex, ey = self.creation_preview
        color = "#ffd45b"

        if self.tool in {"rect", "ellipse"}:
            p1 = self.logical_to_canvas(sx, sy)
            p2 = self.logical_to_canvas(ex, ey)
            creator = self.canvas.create_rectangle if self.tool == "rect" else self.canvas.create_oval
            creator(*p1, *p2, outline=color, width=2, dash=(4, 3))

        elif self.tool == "circle":
            r = math.hypot(ex - sx, ey - sy)
            p1 = self.logical_to_canvas(sx - r, sy - r)
            p2 = self.logical_to_canvas(sx + r, sy + r)
            self.canvas.create_oval(*p1, *p2, outline=color, width=2, dash=(4, 3))

        elif self.tool == "line":
            p1 = self.logical_to_canvas(sx, sy)
            p2 = self.logical_to_canvas(ex, ey)
            self.canvas.create_line(*p1, *p2, fill=color, width=2, dash=(4, 3))

    def shape_canvas_bounds(self, shape: Shape) -> tuple[float, float, float, float] | None:
        if shape.kind in {"line", "polygon"}:
            if not shape.points:
                return None
            coords = [self.logical_to_canvas(x, y) for x, y in shape.points]
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            return min(xs), min(ys), max(xs), max(ys)

        if shape.kind == "circle":
            cx, cy = shape.bbox[0], shape.bbox[1]
            r = shape.radius
            x1, y1 = self.logical_to_canvas(cx - r, cy - r)
            x2, y2 = self.logical_to_canvas(cx + r, cy + r)
            return x1, y1, x2, y2

        x, y, w, h = shape.bbox
        x1, y1 = self.logical_to_canvas(x, y)
        x2, y2 = self.logical_to_canvas(x + w, y + h)
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    # ------------------------------------------------------------------
    # Hit testing / canvas interaction
    # ------------------------------------------------------------------

    def hit_test(self, cx: float, cy: float) -> tuple[int | None, int | None]:
        # Selected vertices get first chance.
        if self.selected_index is not None:
            shape = self.shapes[self.selected_index]
            if shape.kind in {"polygon", "line"}:
                for vertex, (x, y) in enumerate(shape.points):
                    vx, vy = self.logical_to_canvas(x, y)
                    if math.hypot(cx - vx, cy - vy) <= HANDLE_RADIUS + 4:
                        return self.selected_index, vertex

        # Top-most visible shape wins.
        for index in range(len(self.shapes) - 1, -1, -1):
            shape = self.shapes[index]
            if not shape.visible:
                continue
            if self.point_hits_shape(cx, cy, shape):
                return index, None
        return None, None

    def point_hits_shape(self, cx: float, cy: float, shape: Shape) -> bool:
        if shape.kind == "line":
            pts = [self.logical_to_canvas(x, y) for x, y in shape.points]
            return any(
                self._point_segment_distance(cx, cy, *pts[i], *pts[i + 1]) <= 7
                for i in range(len(pts) - 1)
            )

        if shape.kind == "polygon":
            pts = [self.logical_to_canvas(x, y) for x, y in shape.points]
            return self._point_in_polygon(cx, cy, pts)

        bounds = self.shape_canvas_bounds(shape)
        if not bounds:
            return False
        x1, y1, x2, y2 = bounds

        if shape.kind == "ellipse" or shape.kind == "circle":
            rx = max(1.0, (x2 - x1) / 2)
            ry = max(1.0, (y2 - y1) / 2)
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            return ((cx - mx) / rx) ** 2 + ((cy - my) / ry) ** 2 <= 1.08

        return x1 - 2 <= cx <= x2 + 2 and y1 - 2 <= cy <= y2 + 2

    @staticmethod
    def _point_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = clamp(((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy), 0, 1)
        qx, qy = x1 + t * dx, y1 + t * dy
        return math.hypot(px - qx, py - qy)

    @staticmethod
    def _point_in_polygon(px: float, py: float, points: list[tuple[float, float]]) -> bool:
        if len(points) < 3:
            return False
        inside = False
        j = len(points) - 1
        for i in range(len(points)):
            xi, yi = points[i]
            xj, yj = points[j]
            intersects = ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    def on_canvas_press(self, event: tk.Event) -> None:
        self.canvas.focus_set()
        logical = self.canvas_to_logical(event.x, event.y, do_snap=True)

        if self.tool == "select":
            index, vertex = self.hit_test(event.x, event.y)
            self.selected_index = index
            self.selected_vertex = vertex
            self.drag_origin_logical = logical
            self.drag_last_logical = logical
            self._drag_snapshot_taken = False
            self.redraw()
            return

        if self.tool == "polygon":
            self.polygon_draft.append([logical[0], logical[1]])
            self.creation_preview = logical
            self.redraw()
            return

        self.creation_start = logical
        self.creation_preview = logical
        self.redraw()

    def on_canvas_drag(self, event: tk.Event) -> None:
        logical = self.canvas_to_logical(event.x, event.y, do_snap=True)

        if self.tool == "select":
            if self.selected_index is None or self.drag_last_logical is None:
                return

            shape = self.shapes[self.selected_index]
            dx = logical[0] - self.drag_last_logical[0]
            dy = logical[1] - self.drag_last_logical[1]
            if dx == 0 and dy == 0:
                return

            if not self._drag_snapshot_taken:
                self._push_undo("Move")
                self._drag_snapshot_taken = True

            if self.selected_vertex is not None and shape.kind in {"polygon", "line"}:
                point = shape.points[self.selected_vertex]
                point[0] = logical[0]
                point[1] = logical[1]
            else:
                shape.translate(dx, dy)

            self.drag_last_logical = logical
            self.mark_dirty(True)
            self.redraw()
            return

        if self.tool in {"rect", "ellipse", "circle", "line"}:
            self.creation_preview = logical
            self.redraw()

    def on_canvas_release(self, event: tk.Event) -> None:
        logical = self.canvas_to_logical(event.x, event.y, do_snap=True)

        if self.tool == "select":
            if self._drag_snapshot_taken:
                self._push_undo("Moved")
            self.drag_origin_logical = None
            self.drag_last_logical = None
            self._drag_snapshot_taken = False
            return

        if self.tool not in {"rect", "ellipse", "circle", "line"} or self.creation_start is None:
            return

        sx, sy = self.creation_start
        ex, ey = logical
        if abs(ex - sx) < 1e-9 and abs(ey - sy) < 1e-9:
            self.creation_start = None
            self.creation_preview = None
            self.redraw()
            return

        self._push_undo("Create")
        name = self.unique_shape_name(self.tool)

        if self.tool in {"rect", "ellipse"}:
            x = min(sx, ex)
            y = min(sy, ey)
            w = abs(ex - sx)
            h = abs(ey - sy)
            shape = Shape(
                kind=self.tool,
                name=name,
                color="fill",
                outline="edge",
                width=0,
                bbox=[x, y, w, h],
            )
        elif self.tool == "circle":
            radius = math.hypot(ex - sx, ey - sy)
            shape = Shape(
                kind="circle",
                name=name,
                color="fill",
                outline="edge",
                width=0,
                bbox=[sx, sy, 0, 0],
                radius=radius,
            )
        else:
            shape = Shape(
                kind="line",
                name=name,
                color="edge",
                width=1,
                points=[[sx, sy], [ex, ey]],
            )

        self.shapes.append(shape)
        self.selected_index = len(self.shapes) - 1
        self.selected_vertex = None
        self.creation_start = None
        self.creation_preview = None
        self.mark_dirty(True)
        self._push_undo("Created")
        self.redraw()

    def on_canvas_double_click(self, event: tk.Event) -> None:
        if self.tool == "polygon":
            logical = self.canvas_to_logical(event.x, event.y, do_snap=True)
            if not self.polygon_draft or self.polygon_draft[-1] != [logical[0], logical[1]]:
                self.polygon_draft.append([logical[0], logical[1]])
            self.finish_polygon()

    def on_canvas_motion(self, event: tk.Event) -> None:
        x, y = self.canvas_to_logical(event.x, event.y, do_snap=False)
        self.cursor_var.set(f"x {x:5.2f}   y {y:5.2f}")
        if self.tool == "polygon" and self.polygon_draft:
            self.creation_preview = self.canvas_to_logical(event.x, event.y, do_snap=True)
            self.redraw()

    def on_mousewheel(self, event: tk.Event) -> None:
        if event.state & 0x0004:  # Ctrl
            self.change_zoom(+4 if event.delta > 0 else -4)

    def finish_polygon(self) -> None:
        if self.tool != "polygon" or len(self.polygon_draft) < 3:
            return
        self._push_undo("Create polygon")
        shape = Shape(
            kind="polygon",
            name=self.unique_shape_name("polygon"),
            color="fill",
            outline="edge",
            width=0,
            points=copy.deepcopy(self.polygon_draft),
        )
        self.shapes.append(shape)
        self.selected_index = len(self.shapes) - 1
        self.selected_vertex = None
        self.polygon_draft.clear()
        self.creation_preview = None
        self.mark_dirty(True)
        self._push_undo("Created polygon")
        self.redraw()

    def cancel_current_tool(self) -> None:
        self.creation_start = None
        self.creation_preview = None
        self.polygon_draft.clear()
        self.selected_vertex = None
        if hasattr(self, "canvas"):
            self.redraw()

    # ------------------------------------------------------------------
    # Selection / layers / inspector
    # ------------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        if tool not in {"select", "rect", "ellipse", "circle", "line", "polygon"}:
            return
        self.cancel_current_tool()
        self.tool = tool
        self._update_tool_buttons()
        self.status_var.set(
            "Polygon: click vertices, Enter/double-click to finish"
            if tool == "polygon"
            else f"Tool: {tool}"
        )

    def _update_tool_buttons(self) -> None:
        for tool, button in self.tool_buttons.items():
            button.configure(style="SelectedTool.TButton" if tool == self.tool else "Tool.TButton")

    def unique_shape_name(self, base: str) -> str:
        used = {shape.name for shape in self.shapes}
        if base not in used:
            return base
        i = 2
        while f"{base}_{i}" in used:
            i += 1
        return f"{base}_{i}"

    def _refresh_layers(self) -> None:
        if not hasattr(self, "layer_list"):
            return
        current = self.selected_index
        self.layer_list.delete(0, "end")
        # Display top layer first.
        for index in range(len(self.shapes) - 1, -1, -1):
            shape = self.shapes[index]
            marker = "●" if shape.visible else "○"
            self.layer_list.insert("end", f"{marker}  {shape.name}  [{shape.kind}]")
        if current is not None and 0 <= current < len(self.shapes):
            display_index = len(self.shapes) - 1 - current
            self.layer_list.selection_set(display_index)
            self.layer_list.see(display_index)

    def _on_layer_select(self, event: tk.Event | None = None) -> None:
        selection = self.layer_list.curselection()
        if not selection:
            return
        display_index = int(selection[0])
        self.selected_index = len(self.shapes) - 1 - display_index
        self.selected_vertex = None
        self.redraw()

    def move_layer(self, direction: int) -> None:
        if self.selected_index is None:
            return
        target = self.selected_index + direction
        if target < 0 or target >= len(self.shapes):
            self.bell()
            return
        self._push_undo("Layer order")
        self.shapes[self.selected_index], self.shapes[target] = self.shapes[target], self.shapes[self.selected_index]
        self.selected_index = target
        self.mark_dirty(True)
        self._push_undo("Layer reordered")
        self.redraw()

    def duplicate_selected(self) -> None:
        if self.selected_index is None:
            return
        self._push_undo("Duplicate")
        clone = copy.deepcopy(self.shapes[self.selected_index])
        clone.name = self.unique_shape_name(clone.name)
        clone.translate(self.snap or 0.25, self.snap or 0.25)
        self.shapes.insert(self.selected_index + 1, clone)
        self.selected_index += 1
        self.selected_vertex = None
        self.mark_dirty(True)
        self._push_undo("Duplicated")
        self.redraw()

    def delete_selected(self) -> None:
        if self.selected_index is None:
            return
        self._push_undo("Delete")
        del self.shapes[self.selected_index]
        if self.shapes:
            self.selected_index = min(self.selected_index, len(self.shapes) - 1)
        else:
            self.selected_index = None
        self.selected_vertex = None
        self.mark_dirty(True)
        self._push_undo("Deleted")
        self.redraw()

    def toggle_selected_visibility(self) -> None:
        if self.selected_index is None:
            return
        self._push_undo("Visibility")
        self.shapes[self.selected_index].visible = not self.shapes[self.selected_index].visible
        self.mark_dirty(True)
        self._push_undo("Visibility changed")
        self.redraw()

    def nudge_selected(self, dx: float, dy: float) -> None:
        # Don't steal arrows while typing in an Entry/Text/Combobox.
        focus = self.focus_get()
        if isinstance(focus, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)):
            return
        if self.selected_index is None:
            return
        self._push_undo("Nudge")
        shape = self.shapes[self.selected_index]
        if self.selected_vertex is not None and shape.kind in {"polygon", "line"}:
            shape.points[self.selected_vertex][0] += dx
            shape.points[self.selected_vertex][1] += dy
        else:
            shape.translate(dx, dy)
        self.mark_dirty(True)
        self._push_undo("Nudged")
        self.redraw()

    def _refresh_inspector(self) -> None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.shapes)):
            self.name_var.set("")
            self.kind_var.set("")
            self.color_var.set("")
            self.outline_var.set("")
            self.width_var.set("")
            self.geometry_var.set("")
            self.filled_var.set(True)
            return

        shape = self.shapes[self.selected_index]
        self.name_var.set(shape.name)
        self.kind_var.set(shape.kind)
        self.color_var.set(shape.color)
        self.outline_var.set(shape.outline)
        self.width_var.set(fmt_num(shape.width))
        self.geometry_var.set(self.geometry_to_text(shape))
        self.filled_var.set(shape.filled)

    def geometry_to_text(self, shape: Shape) -> str:
        if shape.kind in {"rect", "ellipse"}:
            x, y, w, h = shape.bbox
            return ", ".join(fmt_num(v) for v in (x, y, w, h))
        if shape.kind == "circle":
            return ", ".join(fmt_num(v) for v in (shape.bbox[0], shape.bbox[1], shape.radius))
        return "; ".join(f"{fmt_num(x)},{fmt_num(y)}" for x, y in shape.points)

    def apply_inspector(self) -> None:
        if self.selected_index is None:
            return

        shape = self.shapes[self.selected_index]
        try:
            width = float(self.width_var.get().strip() or "0")
            geometry = self.parse_geometry(shape.kind, self.geometry_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid geometry", str(exc), parent=self)
            return

        self._push_undo("Inspector edit")
        shape.name = self.name_var.get().strip() or shape.name
        shape.color = self.color_var.get().strip() or "fill"
        shape.outline = self.outline_var.get().strip()
        shape.width = max(0.0, width)
        shape.filled = bool(self.filled_var.get())

        if shape.kind in {"rect", "ellipse"}:
            shape.bbox = geometry
        elif shape.kind == "circle":
            shape.bbox[0], shape.bbox[1], shape.radius = geometry
        else:
            shape.points = geometry

        self.mark_dirty(True)
        self._push_undo("Inspector applied")
        self.redraw()

    @staticmethod
    def parse_geometry(kind: str, text: str) -> Any:
        raw = text.strip()
        if kind in {"rect", "ellipse"}:
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) != 4:
                raise ValueError("Rect/ellipse geometry is: x, y, width, height")
            vals = [float(p) for p in parts]
            if vals[2] < 0 or vals[3] < 0:
                raise ValueError("Width and height must be non-negative.")
            return vals

        if kind == "circle":
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) != 3:
                raise ValueError("Circle geometry is: center_x, center_y, radius")
            vals = [float(p) for p in parts]
            if vals[2] < 0:
                raise ValueError("Radius must be non-negative.")
            return vals

        points: list[list[float]] = []
        for pair in raw.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            parts = [p.strip() for p in pair.split(",")]
            if len(parts) != 2:
                raise ValueError("Points are written as x,y; x,y; x,y")
            points.append([float(parts[0]), float(parts[1])])

        minimum = 3 if kind == "polygon" else 2
        if len(points) < minimum:
            raise ValueError(f"{kind.title()} needs at least {minimum} points.")
        return points

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _refresh_code(self) -> None:
        code = self.generate_code()
        self.code_text.configure(state="normal")
        self.code_text.delete("1.0", "end")
        self.code_text.insert("1.0", code)
        self.code_text.configure(state="disabled")

    def x_expr(self, x: float) -> str:
        delta = x - LOGICAL_SIZE / 2
        if abs(delta) < 1e-9:
            return "mid_x"
        magnitude = fmt_num(abs(delta))
        sign = "+" if delta > 0 else "-"
        return f"mid_x {sign} q({magnitude})"

    def y_expr(self, y: float) -> str:
        return f"q({fmt_num(y)})"

    def q_expr(self, value: float) -> str:
        return f"q({fmt_num(value)})"

    @staticmethod
    def color_expr(token: str) -> str:
        text = (token or "").strip()
        if not text:
            return "fill"
        if text.startswith("expr:"):
            return text[5:]
        if IDENT_RE.match(text):
            return text
        parsed = parse_hex_color(text)
        if parsed:
            return repr(parsed)
        return f"palette[{text!r}]"

    def point_expr(self, point: Iterable[float]) -> str:
        x, y = point
        return f"({self.x_expr(float(x))}, {self.y_expr(float(y))})"

    def generate_code(self) -> str:
        lines = [
            "# Generated by Bakerrrr Drawcode Editor",
            "# Logical artboard: 16 x 16; x coordinates are centered on mid_x.",
            "",
        ]

        for shape in self.shapes:
            if not shape.visible:
                lines.append(f"# hidden: {shape.name} [{shape.kind}]")
                continue
            lines.append(f"# {shape.name}")

            color = self.color_expr(shape.color)
            outline = self.color_expr(shape.outline) if shape.outline else None
            width = max(0, int(round(shape.width)))

            if shape.kind == "rect":
                x, y, w, h = shape.bbox
                rect = (
                    f"self.pygame.Rect("
                    f"{self.x_expr(x)}, {self.y_expr(y)}, "
                    f"{self.q_expr(w)}, {self.q_expr(h)})"
                )
                if shape.filled:
                    lines.append(f"self.pygame.draw.rect(surface, {color}, {rect})")
                if outline and width > 0:
                    lines.append(
                        f"self.pygame.draw.rect(surface, {outline}, {rect}, "
                        f"max(1, q({fmt_num(shape.width)})))"
                    )

            elif shape.kind == "ellipse":
                x, y, w, h = shape.bbox
                rect = (
                    f"self.pygame.Rect("
                    f"{self.x_expr(x)}, {self.y_expr(y)}, "
                    f"{self.q_expr(w)}, {self.q_expr(h)})"
                )
                if shape.filled:
                    lines.append(f"self.pygame.draw.ellipse(surface, {color}, {rect})")
                if outline and width > 0:
                    lines.append(
                        f"self.pygame.draw.ellipse(surface, {outline}, {rect}, "
                        f"max(1, q({fmt_num(shape.width)})))"
                    )

            elif shape.kind == "circle":
                center = f"({self.x_expr(shape.bbox[0])}, {self.y_expr(shape.bbox[1])})"
                radius = self.q_expr(shape.radius)
                if shape.filled:
                    lines.append(f"self.pygame.draw.circle(surface, {color}, {center}, {radius})")
                if outline and width > 0:
                    lines.append(
                        f"self.pygame.draw.circle(surface, {outline}, {center}, {radius}, "
                        f"max(1, q({fmt_num(shape.width)})))"
                    )

            elif shape.kind == "line":
                if len(shape.points) == 2:
                    p1 = self.point_expr(shape.points[0])
                    p2 = self.point_expr(shape.points[1])
                    lines.append(
                        f"self.pygame.draw.line(surface, {color}, {p1}, {p2}, "
                        f"max(1, q({fmt_num(max(shape.width, 0.25))})))"
                    )
                elif len(shape.points) > 2:
                    points = ", ".join(self.point_expr(p) for p in shape.points)
                    lines.append(
                        f"self.pygame.draw.lines(surface, {color}, {shape.closed}, "
                        f"[{points}], max(1, q({fmt_num(max(shape.width, 0.25))})))"
                    )

            elif shape.kind == "polygon":
                points = ", ".join(self.point_expr(p) for p in shape.points)
                if shape.filled:
                    lines.append(f"self.pygame.draw.polygon(surface, {color}, [{points}])")
                if outline and width > 0:
                    lines.append(
                        f"self.pygame.draw.polygon(surface, {outline}, [{points}], "
                        f"max(1, q({fmt_num(shape.width)})))"
                    )

            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def copy_code(self) -> None:
        code = self.generate_code()
        self.clipboard_clear()
        self.clipboard_append(code)
        self.update_idletasks()
        self.status_var.set("Drawcode copied to clipboard")

    def export_code_file(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Pygame drawcode",
            defaultextension=".py",
            filetypes=[("Python", "*.py"), ("Text", "*.txt"), ("All files", "*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(self.generate_code(), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self.status_var.set(f"Exported {Path(path).name}")

    # ------------------------------------------------------------------
    # View / misc
    # ------------------------------------------------------------------

    def _on_snap_changed(self, event: tk.Event | None = None) -> None:
        try:
            self.snap = float(self.snap_var.get())
        except ValueError:
            self.snap = DEFAULT_SNAP
            self.snap_var.set(fmt_num(self.snap))
        self.mark_dirty(True)
        self.redraw()

    def change_zoom(self, delta: int) -> None:
        self.zoom = int(clamp(self.zoom + delta, MIN_ZOOM, MAX_ZOOM))
        self.zoom_label.configure(text=f"{self.zoom}px/u")
        self.redraw()

    def reset_zoom(self) -> None:
        self.zoom = DEFAULT_ZOOM
        self.zoom_label.configure(text=f"{self.zoom}px/u")
        self.redraw()

    def toggle_grid(self) -> None:
        if hasattr(self, "grid_var"):
            self.grid_visible = bool(self.grid_var.get())
        else:
            self.grid_visible = not self.grid_visible
        self.redraw()

    def show_controls(self) -> None:
        messagebox.showinfo(
            "Controls",
            """
V  Select
R  Rectangle
E  Ellipse
C  Circle
L  Line
P  Polygon

Polygon: click vertices, Enter or double-click to finish.
Escape cancels the current unfinished shape.

Drag selected shapes to move them.
Select a polygon/line, then drag a yellow vertex handle to edit it.
Arrow keys nudge by the current snap amount.
Shift+Arrow nudges by one logical unit.

[ and ] move a shape backward/forward in the layer stack.
Delete removes the selected shape.
Ctrl+D duplicates.
Ctrl+Z / Ctrl+Y undo/redo.
Ctrl+Shift+C copies generated code.

The artboard is 16x16 logical units. Exported x values are expressed
relative to mid_x and dimensions/vertical coordinates use q(...).
""".strip(),
            parent=self,
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Bakerrrr GFX mode\n\n"
            "Procedural Pygame drawcode authoring inside the Bakerrrr Content Workbench.",
            parent=self,
        )

    def on_close(self) -> None:
        self.app.on_close()



@register_mode
class PaperDollMode(EditorMode):
    """Item-aware appearance/loadout preview built from Bakerrrr item data."""

    mode_id = "paper_doll"
    mode_title = "Paper Doll"
    mode_description = "Equip real Bakerrrr items on a layered appearance preview"

    APPEARANCE_ORDER = (
        "base_top", "base_bottom", "top", "bottom", "full_body", "outer",
        "shoes", "hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right",
    )
    SLOT_LABELS = {
        "base_top": "Base top",
        "base_bottom": "Base bottom",
        "top": "Top",
        "bottom": "Bottom",
        "full_body": "Full body",
        "outer": "Outer",
        "shoes": "Shoes",
        "hat": "Hat",
        "earrings": "Earrings",
        "necklace": "Neck",
        "bracelet": "Wrist",
        "ring_left": "Left ring",
        "ring_right": "Right ring",
        "armor_body": "Body armor",
        "armor_head": "Head armor",
    }
    DISPLAY_ORDER = APPEARANCE_ORDER + ("armor_body", "armor_head")
    CONFLICTS = {
        "full_body": ("top", "bottom"),
        "top": ("full_body",),
        "bottom": ("full_body",),
    }
    BODY_PRESETS = {
        "Balanced": (18.0, 16.5),
        "Curvy": (17.0, 21.0),
        "Broad": (22.5, 17.5),
        "Narrow": (15.5, 15.0),
    }
    DEFAULT_SLOT_COLORS = {
        "base_top": "highlight",
        "base_bottom": "fill",
        "top": "blue",
        "bottom": "dark",
        "full_body": "fill",
        "outer": "shade",
        "shoes": "edge",
        "hat": "accent",
        "earrings": "metal",
        "necklace": "metal",
        "bracelet": "metal",
        "ring_left": "metal",
        "ring_right": "metal",
        "armor_body": "metal",
        "armor_head": "metal",
    }

    def __init__(self, app: "WorkbenchApp", parent: tk.Misc) -> None:
        super().__init__(app, parent)
        self._root_seen: Path | None = None
        self._item_revision_seen = -1
        self.catalog: dict[str, dict[str, Any]] = {}
        self.wearables: list[tuple[str, dict[str, Any], tuple[str, ...]]] = []
        self.filtered: list[tuple[str, dict[str, Any], tuple[str, ...]]] = []
        self.loadout: dict[str, dict[str, Any]] = {}
        self.selected_item_id: str | None = None
        self.selected_slot: str | None = None

        self.filter_var = tk.StringVar()
        self.slot_filter_var = tk.StringVar(value="all")
        self.color_var = tk.StringVar(value="fill")
        self.body_var = tk.StringVar(value="Balanced")
        self.show_labels_var = tk.BooleanVar(value=True)
        self.summary_var = tk.StringVar(value="Set a Bakerrrr root to load game/items.json")
        self.item_var = tk.StringVar(value="No item selected")

        self._build_ui()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        self.slot_filter_var.trace_add("write", lambda *_: self._apply_filter())
        self.body_var.trace_add("write", lambda *_: self._draw_doll())
        self.show_labels_var.trace_add("write", lambda *_: self._draw_doll())

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=7)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Item-aware Paper Doll", font=("TkDefaultFont", 13, "bold")).pack(side="left")
        ttk.Button(top, text="Reload Items", command=self.reload_catalog).pack(side="right")
        ttk.Button(top, text="Set Root…", command=self._choose_root).pack(side="right", padx=(0, 5))

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        # Item catalogue.
        left = ttk.Frame(panes, padding=(0, 0, 7, 0))
        panes.add(left, weight=3)
        ttk.Label(left, text="Wearable item catalogue").pack(anchor="w")

        search = ttk.Frame(left)
        search.pack(fill="x", pady=(4, 4))
        ttk.Label(search, text="Find").pack(side="left")
        ttk.Entry(search, textvariable=self.filter_var).pack(side="left", fill="x", expand=True, padx=(5, 0))

        slotrow = ttk.Frame(left)
        slotrow.pack(fill="x", pady=(0, 5))
        ttk.Label(slotrow, text="Slot").pack(side="left")
        self.slot_combo = ttk.Combobox(slotrow, textvariable=self.slot_filter_var, state="readonly", width=18)
        self.slot_combo.pack(side="left", padx=(5, 0))

        list_holder = ttk.Frame(left)
        list_holder.pack(fill="both", expand=True)
        self.item_list = tk.Listbox(list_holder, exportselection=False, activestyle="none", width=42)
        self.item_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_holder, orient="vertical", command=self.item_list.yview)
        sb.pack(side="right", fill="y")
        self.item_list.configure(yscrollcommand=sb.set)
        self.item_list.bind("<<ListboxSelect>>", self._on_item_select)
        self.item_list.bind("<Double-Button-1>", lambda e: self.equip_selected())

        colorrow = ttk.Frame(left)
        colorrow.pack(fill="x", pady=(6, 3))
        ttk.Label(colorrow, text="Preview color").pack(side="left")
        self.color_combo = ttk.Combobox(colorrow, textvariable=self.color_var, state="normal")
        self.color_combo.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.color_combo.bind("<<ComboboxSelected>>", lambda e: self._draw_doll())

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(3, 0))
        ttk.Button(actions, text="Equip / Replace", command=self.equip_selected).pack(side="left")
        ttk.Button(actions, text="Apply Color", command=self.apply_color_to_selected_slot).pack(side="left", padx=(4, 0))

        ttk.Label(left, textvariable=self.item_var, wraplength=360, justify="left").pack(anchor="w", pady=(7, 2))
        self.item_detail = tk.Text(left, height=10, wrap="word", font=("TkFixedFont", 9))
        self.item_detail.pack(fill="x")
        self.item_detail.configure(state="disabled")

        # Doll canvas.
        middle = ttk.Frame(panes, padding=(0, 0, 7, 0))
        panes.add(middle, weight=4)
        control = ttk.Frame(middle)
        control.pack(fill="x", pady=(0, 5))
        ttk.Label(control, text="Body").pack(side="left")
        ttk.Combobox(
            control,
            textvariable=self.body_var,
            values=tuple(self.BODY_PRESETS),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(5, 9))
        ttk.Checkbutton(control, text="Slot labels", variable=self.show_labels_var).pack(side="left")

        self.canvas = tk.Canvas(
            middle,
            background="#202329",
            highlightthickness=1,
            highlightbackground="#555a62",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw_doll())

        # Equipped slots.
        right = ttk.Frame(panes)
        panes.add(right, weight=3)
        ttk.Label(right, text="Equipped / appearance state").pack(anchor="w")
        ttk.Label(right, textvariable=self.summary_var, wraplength=360, justify="left").pack(anchor="w", pady=(3, 6))

        tree_holder = ttk.Frame(right)
        tree_holder.pack(fill="both", expand=True)
        self.slot_tree = ttk.Treeview(tree_holder, columns=("item", "color"), show="tree headings", selectmode="browse")
        self.slot_tree.heading("#0", text="Slot")
        self.slot_tree.heading("item", text="Item")
        self.slot_tree.heading("color", text="Color")
        self.slot_tree.column("#0", width=110, stretch=False)
        self.slot_tree.column("item", width=170, stretch=True)
        self.slot_tree.column("color", width=90, stretch=False)
        self.slot_tree.pack(side="left", fill="both", expand=True)
        ts = ttk.Scrollbar(tree_holder, orient="vertical", command=self.slot_tree.yview)
        ts.pack(side="right", fill="y")
        self.slot_tree.configure(yscrollcommand=ts.set)
        self.slot_tree.bind("<<TreeviewSelect>>", self._on_slot_select)

        row = ttk.Frame(right)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Clear Slot", command=self.clear_selected_slot).pack(side="left")
        ttk.Button(row, text="Clear Outfit", command=self.clear_outfit).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="Copy Loadout", command=self.copy_loadout).pack(side="right")

        hint = (
            "Items come directly from game/items.json. Cosmetic appearance slots and "
            "ArmorLoadout slots stay separate; full-body clothing replaces top/bottom in this authoring preview."
        )
        ttk.Label(right, text=hint, wraplength=360, justify="left").pack(anchor="w", pady=(9, 0))

        self._refresh_palette_tokens()
        self._refresh_slot_tree()

    def activate(self) -> None:
        if (
            self.services.game.root != self._root_seen
            or self.services.items.revision != self._item_revision_seen
        ):
            self.reload_catalog(rescan=False)
        else:
            self._draw_doll()

    def game_root_changed(self) -> None:
        self._root_seen = None
        if self.app.active_mode is self:
            self.reload_catalog()

    def project_label(self) -> str:
        return "Paper Doll"

    def _choose_root(self) -> None:
        before = self.services.game.root
        self.app.choose_game_root()
        if self.services.game.root != before:
            self.reload_catalog()

    # --------------------------------------------------------------
    # Catalogue
    # --------------------------------------------------------------

    def reload_catalog(self, *, rescan: bool = True) -> None:
        self._root_seen = self.services.game.root
        self._item_revision_seen = self.services.items.revision
        self.catalog = {}
        self.wearables = []
        self.filtered = []
        self.selected_item_id = None
        self.item_list.delete(0, "end")

        if self.services.game.root is None:
            self.summary_var.set("No Bakerrrr root set")
            self._refresh_slot_filter_values()
            self._draw_doll()
            return

        drawable_ok = self.services.drawables.reload(self.services.game)
        if rescan:
            self.services.items.reload(self.services.game, self.services.drawables)
            self._item_revision_seen = self.services.items.revision
        if self.services.items.document is None:
            exc = self.services.items.error or "item catalog is unavailable"
            self.summary_var.set(f"Could not load game/items.json: {exc}")
            self.set_shell_status("Paper Doll: items.json unavailable")
            self._draw_doll()
            return

        self.catalog = {
            str(item_id): dict(item_def)
            for item_id, item_def in self.services.items.normalized.items()
            if isinstance(item_def, dict)
        }
        for item_id, item_def in self.catalog.items():
            slots = self._slots_for_item(item_def)
            if slots:
                self.wearables.append((item_id, item_def, slots))

        self.wearables.sort(key=lambda row: (str(row[1].get("name") or row[0]).lower(), row[0]))
        self._refresh_slot_filter_values()
        self._apply_filter()
        drawable_count = len(self.services.drawables.catalog.definitions)
        drawable_note = (
            f"{drawable_count} validated drawable definitions."
            if drawable_ok
            else f"Drawable catalog error: {self.services.drawables.error}"
        )
        self.summary_var.set(
            f"{len(self.wearables)} wearable/appearance items from game/items.json; "
            f"{len(self.catalog)} total item definitions; {drawable_note}"
        )
        self.set_shell_status(f"Paper Doll loaded {len(self.wearables)} wearable items")
        self._draw_doll()

    def focus_item(self, item_id: str) -> bool:
        """Select an item handed off from Items mode when it is wearable."""
        requested = str(item_id or "").strip()
        self.filter_var.set("")
        self.slot_filter_var.set("all")
        self._apply_filter()
        for index, (candidate, _definition, _slots) in enumerate(self.filtered):
            if candidate != requested:
                continue
            self.item_list.selection_clear(0, "end")
            self.item_list.selection_set(index)
            self.item_list.see(index)
            self._on_item_select()
            return True
        return False

    def _slots_for_item(self, item_def: dict[str, Any]) -> tuple[str, ...]:
        raw = item_def.get("appearance_slots")
        if isinstance(raw, str):
            appearance = (raw.strip().lower(),) if raw.strip() else ()
        elif isinstance(raw, (list, tuple)):
            appearance = tuple(str(v).strip().lower() for v in raw if str(v).strip())
        else:
            appearance = ()
        appearance = tuple(slot for slot in appearance if slot in self.APPEARANCE_ORDER)
        if appearance:
            return appearance

        armor = item_def.get("armor")
        if isinstance(armor, dict):
            armor_slot = str(armor.get("slot") or "").strip().lower()
            if armor_slot in {"body", "head"}:
                return (f"armor_{armor_slot}",)
        return ()

    def _refresh_slot_filter_values(self) -> None:
        slots = sorted({slot for _, _, row_slots in self.wearables for slot in row_slots})
        values = ["all"] + [slot for slot in self.DISPLAY_ORDER if slot in slots]
        values.extend(slot for slot in slots if slot not in values)
        self.slot_combo.configure(values=values)
        if self.slot_filter_var.get() not in values:
            self.slot_filter_var.set("all")

    def _apply_filter(self) -> None:
        if not hasattr(self, "item_list"):
            return
        query = self.filter_var.get().strip().lower()
        slot_filter = self.slot_filter_var.get().strip().lower() or "all"
        self.item_list.delete(0, "end")
        self.filtered = []
        for row in self.wearables:
            item_id, item_def, slots = row
            name = str(item_def.get("name") or item_id)
            tags = " ".join(str(v) for v in item_def.get("tags", []) if isinstance(v, (str, int, float)))
            haystack = f"{item_id} {name} {tags} {' '.join(slots)}".lower()
            if query and query not in haystack:
                continue
            if slot_filter != "all" and slot_filter not in slots:
                continue
            self.filtered.append(row)
            slot_text = "/".join(slots)
            self.item_list.insert("end", f"{name}  [{slot_text}]   {item_id}")

        if self.selected_item_id:
            for index, (item_id, _, _) in enumerate(self.filtered):
                if item_id == self.selected_item_id:
                    self.item_list.selection_set(index)
                    self.item_list.see(index)
                    break

    def _on_item_select(self, event: tk.Event | None = None) -> None:
        selection = self.item_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if not (0 <= index < len(self.filtered)):
            return
        item_id, item_def, slots = self.filtered[index]
        self.selected_item_id = item_id
        self.item_var.set(f"{item_def.get('name') or item_id}  •  {item_id}  •  {', '.join(slots)}")
        self._set_item_detail(json.dumps(item_def, indent=2, ensure_ascii=False))
        default_slot = slots[0] if slots else "top"
        if not self.color_var.get().strip():
            self.color_var.set(self.DEFAULT_SLOT_COLORS.get(default_slot, "fill"))

    def _set_item_detail(self, text: str) -> None:
        self.item_detail.configure(state="normal")
        self.item_detail.delete("1.0", "end")
        self.item_detail.insert("1.0", text)
        self.item_detail.configure(state="disabled")

    # --------------------------------------------------------------
    # Loadout rules
    # --------------------------------------------------------------

    def equip_selected(self) -> None:
        if not self.selected_item_id:
            self.bell()
            return
        item_def = self.catalog.get(self.selected_item_id)
        if not item_def:
            return
        slots = self._slots_for_item(item_def)
        if not slots:
            return

        if set(slots) == {"ring_left", "ring_right"}:
            target = "ring_left" if "ring_left" not in self.loadout else "ring_right"
        else:
            target = next((slot for slot in slots if slot not in self.loadout), slots[0])

        # Paper-doll authoring is intentionally replacement-friendly, but it
        # mirrors the game's actual mutually exclusive full-body/top/bottom relationship.
        for conflict in self.CONFLICTS.get(target, ()):
            self.loadout.pop(conflict, None)
        if target == "full_body":
            self.loadout.pop("top", None)
            self.loadout.pop("bottom", None)

        color = self.color_var.get().strip() or self.DEFAULT_SLOT_COLORS.get(target, "fill")
        self.loadout[target] = {
            "item_id": self.selected_item_id,
            "name": str(item_def.get("name") or self.selected_item_id),
            "color": color,
            "slots": list(slots),
        }
        self.selected_slot = target
        self._refresh_slot_tree()
        self._draw_doll()
        self.set_shell_status(f"Paper Doll: equipped {self.loadout[target]['name']} in {target}")

    def _on_slot_select(self, event: tk.Event | None = None) -> None:
        selection = self.slot_tree.selection()
        if not selection:
            return
        slot = selection[0]
        if slot not in self.DISPLAY_ORDER:
            return
        self.selected_slot = slot
        state = self.loadout.get(slot)
        if state:
            self.color_var.set(str(state.get("color") or self.DEFAULT_SLOT_COLORS.get(slot, "fill")))
            item_id = state.get("item_id")
            item_def = self.catalog.get(str(item_id), {})
            self.item_var.set(f"{state.get('name')}  •  {item_id}  •  {self.SLOT_LABELS.get(slot, slot)}")
            self._set_item_detail(json.dumps(item_def, indent=2, ensure_ascii=False))

    def apply_color_to_selected_slot(self) -> None:
        if not self.selected_slot or self.selected_slot not in self.loadout:
            self.bell()
            return
        color = self.color_var.get().strip()
        if not color:
            return
        self.loadout[self.selected_slot]["color"] = color
        self._refresh_slot_tree()
        self._draw_doll()

    def clear_selected_slot(self) -> None:
        if not self.selected_slot:
            return
        if self.selected_slot in self.loadout:
            removed = self.loadout.pop(self.selected_slot)
            self.set_shell_status(f"Paper Doll: cleared {removed.get('name')}")
        self._refresh_slot_tree()
        self._draw_doll()

    def clear_outfit(self) -> None:
        self.loadout.clear()
        self.selected_slot = None
        self._refresh_slot_tree()
        self._draw_doll()
        self.set_shell_status("Paper Doll: outfit cleared")

    def _refresh_slot_tree(self) -> None:
        if not hasattr(self, "slot_tree"):
            return
        for child in self.slot_tree.get_children(""):
            self.slot_tree.delete(child)
        for slot in self.DISPLAY_ORDER:
            state = self.loadout.get(slot)
            self.slot_tree.insert(
                "", "end", iid=slot,
                text=self.SLOT_LABELS.get(slot, slot),
                values=(state.get("name", "") if state else "", state.get("color", "") if state else ""),
            )
        if self.selected_slot in self.DISPLAY_ORDER:
            self.slot_tree.selection_set(self.selected_slot)

    def copy_loadout(self) -> None:
        payload = {
            "body_preset": self.body_var.get(),
            "slots": {slot: dict(state) for slot, state in self.loadout.items()},
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self.set_shell_status("Paper Doll: loadout JSON copied")

    # --------------------------------------------------------------
    # Drawing
    # --------------------------------------------------------------

    def _refresh_palette_tokens(self) -> None:
        if not hasattr(self, "color_combo"):
            return
        values = sorted(self.services.palette.colors)
        self.color_combo.configure(values=values)

    def _rgb_for(self, token: str) -> tuple[int, int, int]:
        token = str(token or "").strip()
        if token in self.services.palette.colors:
            return self.services.palette.colors[token]
        parsed = parse_hex_color(token)
        if parsed is not None:
            return parsed
        h = sum((i + 1) * ord(ch) for i, ch in enumerate(token))
        return (70 + h % 150, 70 + (h // 7) % 150, 70 + (h // 17) % 150)

    def _hex_for(self, token: str) -> str:
        return rgb_to_hex(self._rgb_for(token))

    @staticmethod
    def _mix(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
        if factor >= 1.0:
            return tuple(int(clamp(v + (255 - v) * (factor - 1.0), 0, 255)) for v in rgb)
        return tuple(int(clamp(v * factor, 0, 255)) for v in rgb)

    def _draw_doll(self) -> None:
        if not hasattr(self, "canvas"):
            return
        c = self.canvas
        c.delete("all")
        width = max(360, c.winfo_width())
        height = max(520, c.winfo_height())
        margin = 24
        logical_w, logical_h = 100.0, 180.0
        scale = min((width - margin * 2) / logical_w, (height - margin * 2) / logical_h)
        ox = (width - logical_w * scale) / 2
        oy = (height - logical_h * scale) / 2

        def p(x: float, y: float) -> tuple[float, float]:
            return ox + x * scale, oy + y * scale

        def poly(points: list[tuple[float, float]], **kwargs: Any) -> int:
            coords: list[float] = []
            for x, y in points:
                coords.extend(p(x, y))
            return c.create_polygon(*coords, **kwargs)

        def line(points: list[tuple[float, float]], **kwargs: Any) -> int:
            coords: list[float] = []
            for x, y in points:
                coords.extend(p(x, y))
            return c.create_line(*coords, **kwargs)

        def oval(x1: float, y1: float, x2: float, y2: float, **kwargs: Any) -> int:
            a = p(x1, y1); b = p(x2, y2)
            return c.create_oval(*a, *b, **kwargs)

        def rect(x1: float, y1: float, x2: float, y2: float, **kwargs: Any) -> int:
            a = p(x1, y1); b = p(x2, y2)
            return c.create_rectangle(*a, *b, **kwargs)

        shoulder, hip = self.BODY_PRESETS.get(self.body_var.get(), self.BODY_PRESETS["Balanced"])
        cx = 50.0
        head_r = 12.0
        head_y = 24.0
        shoulder_y = 48.0
        waist_y = 84.0
        hip_y = 99.0
        knee_y = 137.0
        foot_y = 169.0
        waist = max(12.0, min(shoulder, hip) - 4.5)

        skin = self._hex_for("skin")
        hair = self._hex_for("hair")
        outline = self._hex_for("edge")
        stroke = max(1, int(round(scale * 1.1)))

        # Background card and body silhouette.
        rect(3, 3, 97, 177, fill="#282c32", outline="#454b54", width=1)
        oval(cx - head_r, head_y - head_r, cx + head_r, head_y + head_r, fill=skin, outline=outline, width=stroke)
        oval(cx - head_r - 1, head_y - head_r - 2, cx + head_r + 1, head_y + 2, fill=hair, outline="")
        rect(cx - 4, 35, cx + 4, shoulder_y + 2, fill=skin, outline="")
        torso = [
            (cx - shoulder, shoulder_y), (cx + shoulder, shoulder_y),
            (cx + waist, waist_y), (cx + hip, hip_y),
            (cx - hip, hip_y), (cx - waist, waist_y),
        ]
        poly(torso, fill=skin, outline=outline, width=stroke)
        line([(cx - shoulder + 1, shoulder_y + 2), (cx - shoulder - 8, 82), (cx - shoulder - 5, 111)], fill=skin, width=max(3, int(scale * 6)), capstyle="round")
        line([(cx + shoulder - 1, shoulder_y + 2), (cx + shoulder + 8, 82), (cx + shoulder + 5, 111)], fill=skin, width=max(3, int(scale * 6)), capstyle="round")
        line([(cx - 9, hip_y - 1), (cx - 10, knee_y), (cx - 11, foot_y)], fill=skin, width=max(4, int(scale * 8)), capstyle="round")
        line([(cx + 9, hip_y - 1), (cx + 10, knee_y), (cx + 11, foot_y)], fill=skin, width=max(4, int(scale * 8)), capstyle="round")

        # Layer order mirrors how a viewer thinks about dressing: basewear first,
        # then garments, outerwear/accessories, and armor as its own loadout.
        for slot in self.DISPLAY_ORDER:
            state = self.loadout.get(slot)
            if state:
                self._draw_slot(c, p, poly, line, oval, rect, slot, state, cx, shoulder, waist, hip, shoulder_y, waist_y, hip_y, knee_y, foot_y, scale)

        if self.show_labels_var.get():
            y = 8.0
            for slot in self.DISPLAY_ORDER:
                state = self.loadout.get(slot)
                if not state:
                    continue
                c.create_text(
                    p(6, y)[0], p(6, y)[1],
                    text=f"{self.SLOT_LABELS.get(slot, slot)}: {state.get('name')}",
                    fill="#d9dde3", anchor="nw", font=("TkDefaultFont", max(7, int(scale * 2.2))),
                )
                y += 6.0

        if not self.loadout:
            c.create_text(width / 2, height - 24, text="Double-click a wearable item to dress the doll", fill="#aeb5bf")

    def _draw_slot(
        self,
        c: tk.Canvas,
        p: Any,
        poly: Any,
        line: Any,
        oval: Any,
        rect: Any,
        slot: str,
        state: dict[str, Any],
        cx: float,
        shoulder: float,
        waist: float,
        hip: float,
        shoulder_y: float,
        waist_y: float,
        hip_y: float,
        knee_y: float,
        foot_y: float,
        scale: float,
    ) -> None:
        item_id = str(state.get("item_id") or "")
        color = self._hex_for(str(state.get("color") or self.DEFAULT_SLOT_COLORS.get(slot, "fill")))
        rgb = self._rgb_for(str(state.get("color") or self.DEFAULT_SLOT_COLORS.get(slot, "fill")))
        edge = rgb_to_hex(self._mix(rgb, 0.55))
        shade = rgb_to_hex(self._mix(rgb, 0.78))
        light = rgb_to_hex(self._mix(rgb, 1.30))
        stroke = max(1, int(scale * 0.85))

        if slot == "base_top":
            top_y = shoulder_y + 7
            if item_id in {"bra", "bralette"}:
                band_y = top_y + 14
                cup = max(4.5, shoulder / 3.4)
                for side in (-1, 1):
                    center = cx + side * cup
                    poly([(center - cup, band_y), (center, top_y + 3), (center + cup, band_y)], fill=color, outline=edge, width=stroke)
                line([(cx - shoulder * .55, band_y), (cx + shoulder * .55, band_y)], fill=shade, width=stroke)
                line([(cx - cup, top_y + 3), (cx - cup, shoulder_y + 1)], fill=edge, width=stroke)
                line([(cx + cup, top_y + 3), (cx + cup, shoulder_y + 1)], fill=edge, width=stroke)
            elif item_id == "bandeau":
                rect(cx - shoulder * .62, top_y + 4, cx + shoulder * .62, top_y + 15, fill=color, outline=edge, width=stroke)
            elif item_id == "camisole":
                half = shoulder * .62
                poly([(cx-half, top_y), (cx, top_y+4), (cx+half, top_y), (cx+waist*.85, waist_y+4), (cx-waist*.85, waist_y+4)], fill=color, outline=edge, width=stroke)
                line([(cx-half, top_y), (cx-half*.75, shoulder_y)], fill=edge, width=stroke)
                line([(cx+half, top_y), (cx+half*.75, shoulder_y)], fill=edge, width=stroke)
            else:
                half = shoulder * (.70 if "tank" in item_id else .85)
                poly([(cx-half, top_y), (cx+half, top_y), (cx+waist*.85, waist_y+3), (cx-waist*.85, waist_y+3)], fill=color, outline=edge, width=stroke)

        elif slot == "base_bottom":
            top = waist_y + 2
            if item_id in {"boxers", "boxer_briefs", "boyshorts"}:
                bottom = hip_y + (10 if item_id == "boxers" else 7)
                gap = 2.2
                poly([(cx-hip*.85, top), (cx-gap, top), (cx-gap, bottom), (cx-hip*.72, bottom)], fill=color, outline=edge, width=stroke)
                poly([(cx+gap, top), (cx+hip*.85, top), (cx+hip*.72, bottom), (cx+gap, bottom)], fill=color, outline=edge, width=stroke)
            elif item_id == "thong":
                line([(cx-hip*.75, top), (cx-2, hip_y+3)], fill=color, width=max(2, stroke+1))
                line([(cx+hip*.75, top), (cx+2, hip_y+3)], fill=color, width=max(2, stroke+1))
                poly([(cx-3, hip_y+2), (cx+3, hip_y+2), (cx, hip_y+10)], fill=color, outline=edge, width=stroke)
            else:
                high = waist_y - 5 if item_id == "high_waist_panties" else top
                panel = 6 if item_id in {"bikini_panties", "cheeky_panties"} else 9
                poly([(cx-hip*.78, high), (cx+hip*.78, high), (cx+panel, hip_y+8), (cx-panel, hip_y+8)], fill=color, outline=edge, width=stroke)

        elif slot == "top":
            top = shoulder_y - (1 if item_id == "turtleneck" else 0)
            bottom = waist_y + 6
            sleeve = 10 if item_id in {"sweater", "overshirt", "button_up"} else 6
            poly([(cx-shoulder, top), (cx+shoulder, top), (cx+waist, bottom), (cx-waist, bottom)], fill=color, outline=edge, width=stroke)
            line([(cx-shoulder+2, top+5), (cx-shoulder-sleeve, top+22)], fill=color, width=max(3, int(scale*5)), capstyle="round")
            line([(cx+shoulder-2, top+5), (cx+shoulder+sleeve, top+22)], fill=color, width=max(3, int(scale*5)), capstyle="round")
            if item_id in {"button_up", "blouse"}:
                line([(cx, top+4), (cx, bottom-2)], fill=light, width=stroke)
            if item_id == "turtleneck":
                rect(cx-6, shoulder_y-5, cx+6, shoulder_y+5, fill=color, outline=edge, width=stroke)

        elif slot == "bottom":
            top = waist_y + 2
            if item_id == "skirt":
                poly([(cx-waist, top), (cx+waist, top), (cx+hip+4, knee_y-3), (cx-hip-4, knee_y-3)], fill=color, outline=edge, width=stroke)
            elif item_id == "shorts":
                bottom = hip_y + 18
                gap = 2.5
                poly([(cx-hip, top), (cx-gap, top), (cx-gap, bottom), (cx-hip*.82, bottom)], fill=color, outline=edge, width=stroke)
                poly([(cx+gap, top), (cx+hip, top), (cx+hip*.82, bottom), (cx+gap, bottom)], fill=color, outline=edge, width=stroke)
            else:
                line([(cx-8, top+4), (cx-10, knee_y), (cx-11, foot_y-4)], fill=color, width=max(5, int(scale*8.5)), capstyle="round")
                line([(cx+8, top+4), (cx+10, knee_y), (cx+11, foot_y-4)], fill=color, width=max(5, int(scale*8.5)), capstyle="round")
                line([(cx-hip, top), (cx+hip, top)], fill=edge, width=max(2, stroke+1))

        elif slot == "full_body":
            top = shoulder_y
            if item_id == "dress":
                poly([(cx-shoulder, top), (cx+shoulder, top), (cx+waist, waist_y), (cx+hip+7, knee_y+6), (cx-hip-7, knee_y+6), (cx-waist, waist_y)], fill=color, outline=edge, width=stroke)
            else:
                poly([(cx-shoulder, top), (cx+shoulder, top), (cx+hip, hip_y+2), (cx-hip, hip_y+2)], fill=color, outline=edge, width=stroke)
                line([(cx-8, hip_y), (cx-10, foot_y-4)], fill=color, width=max(5, int(scale*8.5)), capstyle="round")
                line([(cx+8, hip_y), (cx+10, foot_y-4)], fill=color, width=max(5, int(scale*8.5)), capstyle="round")
                line([(cx, top+5), (cx, hip_y-2)], fill=light, width=stroke)

        elif slot == "outer":
            top = shoulder_y - 1
            bottom = knee_y + 3 if item_id == "coat" else waist_y + 13
            if item_id == "vest":
                poly([(cx-shoulder-2, top), (cx-4, top+5), (cx-5, bottom), (cx-waist-2, bottom)], fill=color, outline=edge, width=stroke)
                poly([(cx+4, top+5), (cx+shoulder+2, top), (cx+waist+2, bottom), (cx+5, bottom)], fill=color, outline=edge, width=stroke)
            else:
                left = [(cx-shoulder-3, top), (cx-3, top+6), (cx-4, bottom), (cx-waist-4, bottom)]
                right = [(cx+3, top+6), (cx+shoulder+3, top), (cx+waist+4, bottom), (cx+4, bottom)]
                poly(left, fill=color, outline=edge, width=stroke)
                poly(right, fill=color, outline=edge, width=stroke)
                line([(cx-shoulder-1, top+6), (cx-shoulder-10, waist_y)], fill=color, width=max(4, int(scale*6)), capstyle="round")
                line([(cx+shoulder+1, top+6), (cx+shoulder+10, waist_y)], fill=color, width=max(4, int(scale*6)), capstyle="round")

        elif slot == "shoes":
            for side in (-1, 1):
                x = cx + side * 11
                if item_id == "boots":
                    rect(x-5, foot_y-15, x+5, foot_y+3, fill=color, outline=edge, width=stroke)
                elif item_id == "sandals":
                    line([(x-5, foot_y-1), (x+6, foot_y-1)], fill=color, width=max(2, stroke+1))
                    line([(x-2, foot_y-5), (x+2, foot_y)], fill=edge, width=stroke)
                else:
                    oval(x-6, foot_y-5, x+7, foot_y+4, fill=color, outline=edge, width=stroke)

        elif slot == "hat":
            if "bandana" in item_id:
                rect(cx-12, 12, cx+12, 19, fill=color, outline=edge, width=stroke)
                poly([(cx+10, 18), (cx+18, 23), (cx+11, 25)], fill=color, outline=edge, width=stroke)
            else:
                oval(cx-13, 9, cx+13, 25, fill=color, outline=edge, width=stroke)
                rect(cx+6, 19, cx+18, 22, fill=color, outline=edge, width=stroke)

        elif slot == "earrings":
            oval(cx-13.5, 24, cx-10.5, 28, fill=color, outline=edge, width=stroke)
            oval(cx+10.5, 24, cx+13.5, 28, fill=color, outline=edge, width=stroke)

        elif slot == "necklace":
            line([(cx-9, 39), (cx, 47), (cx+9, 39)], fill=color, width=max(1, stroke+1))
            oval(cx-2, 45, cx+2, 49, fill=color, outline=edge, width=stroke)

        elif slot == "bracelet":
            oval(cx+shoulder+3, 104, cx+shoulder+9, 109, fill="", outline=color, width=max(2, stroke+1))

        elif slot in {"ring_left", "ring_right"}:
            side = -1 if slot == "ring_left" else 1
            x = cx + side * (shoulder + 6)
            oval(x-2, 108, x+2, 112, fill="", outline=color, width=max(1, stroke))

        elif slot == "armor_body":
            poly([(cx-shoulder*.85, shoulder_y+3), (cx+shoulder*.85, shoulder_y+3), (cx+waist*.9, waist_y+7), (cx-waist*.9, waist_y+7)], fill=color, outline=edge, width=max(2, stroke+1))
            line([(cx-8, shoulder_y+8), (cx-8, waist_y+2)], fill=shade, width=stroke)
            line([(cx+8, shoulder_y+8), (cx+8, waist_y+2)], fill=shade, width=stroke)

        elif slot == "armor_head":
            oval(cx-13, 9, cx+13, 28, fill=color, outline=edge, width=max(2, stroke+1))
            rect(cx-12, 21, cx+12, 27, fill=color, outline=edge, width=stroke)

    # --------------------------------------------------------------
    # Shell actions
    # --------------------------------------------------------------

    def handle_action(self, action: str, event: tk.Event | None = None) -> bool:
        if action == "open" or action == "import":
            self.reload_catalog()
            return True
        if action == "copy" or action == "export":
            self.copy_loadout()
            return True
        if action == "delete":
            self.clear_selected_slot()
            return True
        if action == "palette":
            path = filedialog.askopenfilename(parent=self, title="Load palette JSON", filetypes=[("JSON", "*.json"), ("All files", "*")])
            if not path:
                return True
            try:
                count = self.services.palette.load(Path(path))
            except Exception as exc:
                messagebox.showerror("Palette", str(exc), parent=self)
                return True
            self._refresh_palette_tokens()
            self._draw_doll()
            self.set_shell_status(f"Paper Doll: loaded {count} palette colors")
            return True
        if action == "help":
            messagebox.showinfo(
                "Paper Doll",
                "Reads wearable definitions directly from game/items.json.\n\n"
                "Double-click an item to equip it. The preview stores a color token per equipped slot. "
                "Full-body items replace top/bottom for authoring convenience, while armor remains a separate loadout layer.",
                parent=self,
            )
            return True
        return False


@register_mode
class ViewerMode(EditorMode):
    """Read-only browser for Bakerrrr Python/JSON content."""

    mode_id = "viewer"
    mode_title = "Viewer"
    mode_description = "Browse, inspect, preview, and hand game content to editors"

    def __init__(self, app: "WorkbenchApp", parent: tk.Misc) -> None:
        super().__init__(app, parent)
        self._root_seen: Path | None = None
        self._all_files: list[Path] = []
        self._visible_files: list[Path] = []
        self._current_path: Path | None = None
        self._current_source = ""
        self._objects: list[tuple[str, Any]] = []
        self._preview_shapes: list[Shape] = []

        self.filter_var = tk.StringVar()
        self.path_var = tk.StringVar(value="No file selected")
        self.summary_var = tk.StringVar(value="Set a Bakerrrr root, then choose a file.")
        self.preview_var = tk.StringVar(value="")

        self._build_ui()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=7)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Content Viewer", font=("TkDefaultFont", 13, "bold")).pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_files).pack(side="right")
        ttk.Button(top, text="Set Root…", command=self.app.choose_game_root).pack(side="right", padx=(0, 5))

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 6, 0))
        panes.add(left, weight=2)
        filter_row = ttk.Frame(left)
        filter_row.pack(fill="x", pady=(0, 5))
        ttk.Label(filter_row, text="Filter").pack(side="left")
        ttk.Entry(filter_row, textvariable=self.filter_var).pack(side="left", fill="x", expand=True, padx=(5, 0))

        file_holder = ttk.Frame(left)
        file_holder.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(file_holder, exportselection=False, activestyle="none", width=36)
        self.file_list.pack(side="left", fill="both", expand=True)
        file_scroll = ttk.Scrollbar(file_holder, orient="vertical", command=self.file_list.yview)
        file_scroll.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=file_scroll.set)
        self.file_list.bind("<<ListboxSelect>>", self._on_file_select)

        middle = ttk.Frame(panes, padding=(0, 0, 6, 0))
        panes.add(middle, weight=3)
        ttk.Label(middle, textvariable=self.path_var, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(middle, textvariable=self.summary_var, wraplength=420, justify="left").pack(anchor="w", pady=(2, 6))

        object_holder = ttk.Frame(middle)
        object_holder.pack(fill="both", expand=True)
        self.object_list = tk.Listbox(object_holder, exportselection=False, activestyle="none", width=52)
        self.object_list.pack(side="left", fill="both", expand=True)
        object_scroll = ttk.Scrollbar(object_holder, orient="vertical", command=self.object_list.yview)
        object_scroll.pack(side="right", fill="y")
        self.object_list.configure(yscrollcommand=object_scroll.set)
        self.object_list.bind("<<ListboxSelect>>", self._on_object_select)
        self.object_list.bind("<Double-Button-1>", lambda e: self.open_in_gfx(replace=True))

        right = ttk.Frame(panes)
        panes.add(right, weight=4)
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(0, 5))
        ttk.Label(actions, text="Preview", font=("TkDefaultFont", 10, "bold")).pack(side="left")
        ttk.Button(actions, text="Open in GFX", command=lambda: self.open_in_gfx(replace=True)).pack(side="right")
        ttk.Button(actions, text="Append to GFX", command=lambda: self.open_in_gfx(replace=False)).pack(side="right", padx=(0, 5))

        self.preview_canvas = tk.Canvas(
            right,
            height=345,
            background="#202329",
            highlightthickness=1,
            highlightbackground="#555a62",
        )
        self.preview_canvas.pack(fill="both", expand=False)
        self.preview_canvas.bind("<Configure>", lambda e: self._draw_preview())
        ttk.Label(right, textvariable=self.preview_var).pack(anchor="w", pady=(3, 5))

        source_frame = ttk.LabelFrame(right, text="Source / value", padding=4)
        source_frame.pack(fill="both", expand=True)
        self.source_text = tk.Text(
            source_frame,
            wrap="none",
            font=("TkFixedFont", 9),
            background="#17191d",
            foreground="#e8e8e8",
            insertbackground="#e8e8e8",
        )
        self.source_text.pack(side="left", fill="both", expand=True)
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_text.yview)
        source_scroll.pack(side="right", fill="y")
        self.source_text.configure(yscrollcommand=source_scroll.set)

    def activate(self) -> None:
        root = self.services.game.root
        if root != self._root_seen:
            self.refresh_files()

    def project_label(self) -> str:
        return "Viewer"

    def refresh_files(self) -> None:
        root = self.services.game.root
        self._root_seen = root
        self._all_files.clear()
        self._visible_files.clear()
        self.file_list.delete(0, "end")
        self.object_list.delete(0, "end")
        self._objects.clear()
        self._preview_shapes.clear()
        self._draw_preview()

        if root is None:
            self.path_var.set("No Bakerrrr root")
            self.summary_var.set("Choose the game checkout with Set Root…")
            self.set_shell_status("Viewer: Bakerrrr root not set")
            return

        try:
            self._all_files = self.services.game.content_files()
        except Exception as exc:
            messagebox.showerror("Viewer scan failed", str(exc), parent=self)
            return

        self._apply_filter()
        self.summary_var.set(f"{len(self._all_files)} Python/JSON files under {root}")
        self.set_shell_status(f"Viewer indexed {len(self._all_files)} source/content files")

    def _apply_filter(self) -> None:
        if not hasattr(self, "file_list"):
            return
        query = self.filter_var.get().strip().lower()
        selected = self._current_path
        self.file_list.delete(0, "end")
        self._visible_files = []
        for path in self._all_files:
            label = self.services.game.display_path(path)
            if query and query not in label.lower():
                continue
            self._visible_files.append(path)
            prefix = "PY " if path.suffix.lower() == ".py" else "JS "
            self.file_list.insert("end", prefix + label)
        if selected in self._visible_files:
            index = self._visible_files.index(selected)
            self.file_list.selection_set(index)
            self.file_list.see(index)

    def _on_file_select(self, event: tk.Event | None = None) -> None:
        selection = self.file_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self._visible_files):
            self.inspect_file(self._visible_files[index])

    def inspect_file(self, path: Path) -> None:
        self._current_path = path
        self._preview_shapes = []
        self._objects.clear()
        self.object_list.delete(0, "end")
        self._set_source("")
        self.preview_var.set("")
        self.path_var.set(self.services.game.display_path(path))

        try:
            if path.suffix.lower() == ".py":
                self._inspect_python(path)
            elif path.suffix.lower() == ".json":
                self._inspect_json(path)
            else:
                self.summary_var.set("Unsupported content type")
        except Exception as exc:
            self.summary_var.set(f"Could not inspect: {exc}")
            self._set_source(str(exc))
        self._draw_preview()

    def _add_object(self, label: str, kind: str, payload: Any) -> None:
        self._objects.append((kind, payload))
        self.object_list.insert("end", label)

    def _inspect_python(self, path: Path) -> None:
        resolved, source, tree = self.services.game.parse_python(path)
        self._current_source = source

        collector = DrawCallCollector()
        collector.visit(tree)
        candidates = collector.candidates()
        for candidate in candidates:
            self._add_object(f"DRAW  {candidate.label}", "draw", candidate)

        symbol_count = 0
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol_count += 1
                self._add_object(f"FUNC  {node.name}  [line {node.lineno}]", "ast", node)
            elif isinstance(node, ast.ClassDef):
                symbol_count += 1
                self._add_object(f"CLASS {node.name}  [line {node.lineno}]", "ast", node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                names = self._assignment_names(node)
                if names:
                    symbol_count += 1
                    self._add_object(
                        f"DATA  {', '.join(names)}  [line {getattr(node, 'lineno', 0)}]",
                        "ast",
                        node,
                    )

        self.summary_var.set(
            f"Python AST: {symbol_count} top-level symbols; {len(candidates)} drawable scopes. "
            "No game code executed."
        )
        self._set_source(source)

        if candidates:
            self.object_list.selection_set(0)
            self._on_object_select()

    @staticmethod
    def _assignment_names(node: ast.AST) -> list[str]:
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        names: list[str] = []
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                names.extend(elt.id for elt in target.elts if isinstance(elt, ast.Name))
        return names

    def _inspect_json(self, path: Path) -> None:
        data = self.services.game.load_json(path)
        self._current_source = json.dumps(data, indent=2, ensure_ascii=False)
        self._add_object(f"ROOT  {self._json_summary(data)}", "json", data)

        if isinstance(data, dict):
            for key, value in list(data.items())[:500]:
                self._add_object(f"KEY   {key}   {self._json_summary(value)}", "json", value)
        elif isinstance(data, list):
            for index, value in enumerate(data[:500]):
                label = f"[{index}]"
                if isinstance(value, dict):
                    for key in ("name", "id", "key", "slug", "title"):
                        if isinstance(value.get(key), (str, int, float)):
                            label += f" {value[key]}"
                            break
                self._add_object(f"ITEM  {label}   {self._json_summary(value)}", "json", value)

        self.summary_var.set(f"JSON: {self._json_summary(data)}")
        self._set_source(self._current_source)
        if self._objects:
            self.object_list.selection_set(0)

    @staticmethod
    def _json_summary(value: Any) -> str:
        if isinstance(value, dict):
            return f"{len(value)} keys"
        if isinstance(value, list):
            return f"{len(value)} items"
        if isinstance(value, str):
            compact = value.replace("\n", " ")
            return compact[:48] + ("…" if len(compact) > 48 else "")
        return repr(value)[:56]

    def _on_object_select(self, event: tk.Event | None = None) -> None:
        selection = self.object_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if not (0 <= index < len(self._objects)):
            return

        kind, payload = self._objects[index]
        self._preview_shapes = []

        if kind == "draw" and isinstance(payload, ImportCandidate):
            shapes: list[Shape] = []
            skipped = 0
            resolver = StaticDrawResolver(self._current_tree) if self._current_tree is not None else None
            for i, call in enumerate(payload.calls, 1):
                primitive = DrawCallCollector.draw_primitive(call) or "shape"
                contexts = resolver.contexts_for_call(call) if resolver is not None else [{}]
                imported_this_call = False
                for context_index, context in enumerate(contexts, 1):
                    suffix = f"_{context_index}" if len(contexts) > 1 else ""
                    shape = DrawcodeASTAdapter.shape_from_call(
                        call,
                        f"{primitive}_{getattr(call, 'lineno', i)}{suffix}",
                        resolver=resolver,
                        overrides=context,
                    )
                    if shape is not None:
                        shapes.append(shape)
                        imported_this_call = True
                if not imported_this_call:
                    skipped += 1
            self._preview_shapes = DrawcodeASTAdapter.merge_fill_outline_pairs(shapes)
            self.preview_var.set(
                f"{len(self._preview_shapes)} editable shape"
                f"{'s' if len(self._preview_shapes) != 1 else ''}"
                + (f"; {skipped} unsupported" if skipped else "")
            )
            lines: list[str] = []
            for call in payload.calls:
                try:
                    lines.append(ast.unparse(call))
                except Exception:
                    lines.append(f"# draw call at line {getattr(call, 'lineno', '?')}")
            self._set_source("\n".join(lines) + ("\n" if lines else ""))

        elif kind == "ast" and isinstance(payload, ast.AST):
            self.preview_var.set("")
            segment = ast.get_source_segment(self._current_source, payload)
            if segment is None:
                start = max(1, int(getattr(payload, "lineno", 1)))
                end = max(start, int(getattr(payload, "end_lineno", start)))
                lines = self._current_source.splitlines()
                segment = "\n".join(lines[start - 1:end])
            self._set_source(segment)

        elif kind == "json":
            self.preview_var.set("")
            self._set_source(json.dumps(payload, indent=2, ensure_ascii=False, default=repr))

        self._draw_preview()

    def _set_source(self, text: str) -> None:
        self.source_text.configure(state="normal")
        self.source_text.delete("1.0", "end")
        self.source_text.insert("1.0", text)
        self.source_text.configure(state="disabled")

    def _preview_color(self, token: str) -> str:
        text = (token or "").strip()
        if text in self.services.palette.colors:
            return rgb_to_hex(self.services.palette.colors[text])
        parsed = parse_hex_color(text)
        if parsed is not None:
            return rgb_to_hex(parsed)
        h = sum((i + 1) * ord(ch) for i, ch in enumerate(text))
        return rgb_to_hex((70 + h % 150, 70 + (h // 7) % 150, 70 + (h // 17) % 150))

    def _draw_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        c = self.preview_canvas
        c.delete("all")
        width = max(200, c.winfo_width())
        height = max(200, c.winfo_height())
        side = max(120, min(width - 28, height - 28))
        scale = side / LOGICAL_SIZE
        ox = (width - side) / 2
        oy = (height - side) / 2

        c.create_rectangle(ox, oy, ox + side, oy + side, fill="#2b2f35", outline="#8b929d")
        for i in range(17):
            x = ox + i * scale
            y = oy + i * scale
            grid = "#5b4b54" if i == 8 else "#41464e"
            lw = 2 if i == 8 else 1
            c.create_line(x, oy, x, oy + side, fill=grid, width=lw)
            c.create_line(ox, y, ox + side, y, fill=grid, width=lw)

        def pt(x: float, y: float) -> tuple[float, float]:
            return ox + x * scale, oy + y * scale

        for shape in self._preview_shapes:
            if not shape.visible:
                continue
            fill = self._preview_color(shape.color)
            outline = self._preview_color(shape.outline) if shape.outline else ""
            stroke = max(1, int(round(max(shape.width, 0.25) * scale / 4)))

            if shape.kind in {"rect", "ellipse"}:
                x, y, w, h = shape.bbox
                x1, y1 = pt(x, y)
                x2, y2 = pt(x + w, y + h)
                create = c.create_rectangle if shape.kind == "rect" else c.create_oval
                if shape.filled:
                    create(x1, y1, x2, y2, fill=fill, outline=outline, width=stroke)
                else:
                    create(x1, y1, x2, y2, fill="", outline=outline or fill, width=stroke)

            elif shape.kind == "circle":
                cx, cy = shape.bbox[0], shape.bbox[1]
                r = shape.radius
                x1, y1 = pt(cx - r, cy - r)
                x2, y2 = pt(cx + r, cy + r)
                if shape.filled:
                    c.create_oval(x1, y1, x2, y2, fill=fill, outline=outline, width=stroke)
                else:
                    c.create_oval(x1, y1, x2, y2, fill="", outline=outline or fill, width=stroke)

            elif shape.kind == "line":
                coords: list[float] = []
                for x, y in shape.points:
                    coords.extend(pt(x, y))
                if len(coords) >= 4:
                    c.create_line(*coords, fill=fill, width=stroke, capstyle="round", joinstyle="round")
                    if shape.closed and len(shape.points) > 2:
                        x1, y1 = pt(*shape.points[-1])
                        x2, y2 = pt(*shape.points[0])
                        c.create_line(x1, y1, x2, y2, fill=fill, width=stroke)

            elif shape.kind == "polygon":
                coords = []
                for x, y in shape.points:
                    coords.extend(pt(x, y))
                if len(coords) >= 6:
                    if shape.filled:
                        c.create_polygon(*coords, fill=fill, outline=outline, width=stroke)
                    else:
                        c.create_polygon(*coords, fill="", outline=outline or fill, width=stroke)

        if not self._preview_shapes:
            c.create_text(
                width / 2,
                height / 2,
                text="Select a drawable scope",
                fill="#aeb5bf",
                font=("TkDefaultFont", 11),
            )

    def open_in_gfx(self, *, replace: bool) -> None:
        if not self._preview_shapes:
            self.bell()
            self.set_shell_status("Viewer: select an importable drawable scope first")
            return
        mode = self.app.get_mode("gfx")
        if not isinstance(mode, GfxMode):
            return
        label = self.services.game.display_path(self._current_path) if self._current_path else "Viewer"
        if mode.accept_external_shapes(self._preview_shapes, label, replace=replace):
            self.app.show_mode("gfx")

    def choose_file(self) -> None:
        initial = str(self.services.game.root) if self.services.game.root else str(Path.cwd())
        path = filedialog.askopenfilename(
            parent=self,
            title="Inspect Bakerrrr content",
            initialdir=initial,
            filetypes=[
                ("Bakerrrr source/content", "*.py *.json"),
                ("Python", "*.py"),
                ("JSON", "*.json"),
                ("All files", "*"),
            ],
        )
        if path:
            self.inspect_file(Path(path).resolve())

    def copy_selected_source(self) -> None:
        text = self.source_text.get("1.0", "end-1c")
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self.set_shell_status("Viewer: source/value copied")

    def handle_action(self, action: str, event: tk.Event | None = None) -> bool:
        actions = {
            "open": self.choose_file,
            "import": self.choose_file,
            "copy": self.copy_selected_source,
        }
        func = actions.get(action)
        if func is None:
            return False
        func()
        return True


register_packaged_modes()


class WorkbenchApp(tk.Tk):
    """Thin application shell. Content behavior belongs to registered modes."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1360x860")
        self.minsize(1040, 680)

        self.services = WorkbenchServices()
        self.services.reload_root_content()
        self.mode_instances: dict[str, EditorMode] = {}
        self.active_mode_id: str | None = None
        self.active_mode: EditorMode | None = None
        self.mode_buttons: dict[str, ttk.Button] = {}
        self.status_var = tk.StringVar(value="Ready")
        self.root_var = tk.StringVar()

        self._configure_style()
        self._build_menu()
        self._build_shell()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        first = "gfx" if "gfx" in MODE_REGISTRY else next(iter(MODE_REGISTRY))
        self.show_mode(first)
        self._refresh_root_label()
        self.refresh_title()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Mode.TButton", padding=(10, 6))
        style.configure("ActiveMode.TButton", padding=(10, 6), relief="sunken")

    def _build_shell(self) -> None:
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, padding=(8, 7))
        header.pack(fill="x")
        ttk.Label(header, text="Bakerrrr", font=("TkDefaultFont", 12, "bold")).pack(side="left", padx=(0, 10))

        for mode_id, cls in MODE_REGISTRY.items():
            button = ttk.Button(
                header,
                text=cls.mode_title,
                style="Mode.TButton",
                command=lambda mid=mode_id: self.show_mode(mid),
            )
            button.pack(side="left", padx=(0, 4))
            self.mode_buttons[mode_id] = button

        ttk.Button(header, text="Set Game Root…", command=self.choose_game_root).pack(side="right")
        ttk.Label(header, textvariable=self.root_var).pack(side="right", padx=(8, 10))

        ttk.Separator(outer, orient="horizontal").pack(fill="x")
        self.mode_host = ttk.Frame(outer)
        self.mode_host.pack(fill="both", expand=True)

        footer = ttk.Frame(outer, padding=(7, 3))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")
        self.mode_desc_var = tk.StringVar()
        ttk.Label(footer, textvariable=self.mode_desc_var).pack(side="right")

    def _build_menu(self) -> None:
        menu = tk.Menu(self)

        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Set Bakerrrr Root…", command=self.choose_game_root)
        file_menu.add_separator()
        file_menu.add_command(label="New", accelerator="Ctrl+N", command=lambda: self.dispatch("new"))
        file_menu.add_command(label="Open…", accelerator="Ctrl+O", command=lambda: self.dispatch("open"))
        file_menu.add_command(label="Import from Game…", accelerator="Ctrl+I", command=lambda: self.dispatch("import"))
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=lambda: self.dispatch("save"))
        file_menu.add_command(label="Save As…", accelerator="Ctrl+Shift+S", command=lambda: self.dispatch("save_as"))
        file_menu.add_separator()
        file_menu.add_command(label="Load Palette…", command=lambda: self.dispatch("palette"))
        file_menu.add_command(label="Export…", accelerator="Ctrl+E", command=lambda: self.dispatch("export"))
        file_menu.add_command(label="Copy", accelerator="Ctrl+Shift+C", command=lambda: self.dispatch("copy"))
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=lambda: self.dispatch("undo"))
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=lambda: self.dispatch("redo"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Duplicate", accelerator="Ctrl+D", command=lambda: self.dispatch("duplicate"))
        edit_menu.add_command(label="Delete", accelerator="Delete", command=lambda: self.dispatch("delete"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Bring Forward", accelerator="]", command=lambda: self.dispatch("layer_forward"))
        edit_menu.add_command(label="Send Backward", accelerator="[", command=lambda: self.dispatch("layer_backward"))
        menu.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Zoom In", accelerator="Ctrl++", command=lambda: self.dispatch("zoom_in"))
        view_menu.add_command(label="Zoom Out", accelerator="Ctrl+-", command=lambda: self.dispatch("zoom_out"))
        view_menu.add_command(label="Reset Zoom", command=lambda: self.dispatch("zoom_reset"))
        view_menu.add_command(label="Toggle Grid", command=lambda: self.dispatch("toggle_grid"))
        menu.add_cascade(label="View", menu=view_menu)

        mode_menu = tk.Menu(menu, tearoff=False)
        for mode_id, cls in MODE_REGISTRY.items():
            mode_menu.add_command(label=cls.mode_title, command=lambda mid=mode_id: self.show_mode(mid))
        menu.add_cascade(label="Mode", menu=mode_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Mode Help", command=lambda: self.dispatch("help"))
        help_menu.add_command(label="About Workbench", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu)

    def _bind_shortcuts(self) -> None:
        bindings = {
            "<Control-n>": "new",
            "<Control-o>": "open",
            "<Control-i>": "import",
            "<Control-s>": "save",
            "<Control-Shift-S>": "save_as",
            "<Control-e>": "export",
            "<Control-z>": "undo",
            "<Control-y>": "redo",
            "<Control-d>": "duplicate",
            "<Control-Shift-C>": "copy",
        }
        for sequence, action in bindings.items():
            self.bind_all(sequence, lambda event, a=action: self._shortcut(a, event))
        self.bind_all("<KeyPress>", self._dispatch_keypress, add="+")

    def _shortcut(self, action: str, event: tk.Event) -> str:
        self.dispatch(action, event)
        return "break"

    def _dispatch_keypress(self, event: tk.Event) -> str | None:
        # Let dedicated Ctrl bindings win and ordinary text widgets type normally.
        if event.state & 0x0004:
            return None
        if self.active_mode and self.active_mode.handle_keypress(event):
            return "break"
        return None

    def dispatch(self, action: str, event: tk.Event | None = None) -> bool:
        if self.active_mode is None:
            return False
        handled = self.active_mode.handle_action(action, event)
        if not handled:
            self.set_status(f"{self.active_mode.mode_title} does not use '{action}' yet")
        self.refresh_title()
        return handled

    def get_mode(self, mode_id: str) -> EditorMode:
        cls = MODE_REGISTRY.get(mode_id)
        if cls is None:
            raise KeyError(mode_id)
        mode = self.mode_instances.get(mode_id)
        if mode is None:
            mode = cls(self, self.mode_host)
            self.mode_instances[mode_id] = mode
        return mode

    def show_mode(self, mode_id: str) -> None:
        if mode_id == self.active_mode_id:
            return
        cls = MODE_REGISTRY.get(mode_id)
        if cls is None:
            raise KeyError(mode_id)

        if self.active_mode is not None:
            self.active_mode.deactivate()
            self.active_mode.pack_forget()

        mode = self.get_mode(mode_id)

        self.active_mode_id = mode_id
        self.active_mode = mode
        mode.pack(fill="both", expand=True)
        mode.activate()

        for mid, button in self.mode_buttons.items():
            button.configure(style="ActiveMode.TButton" if mid == mode_id else "Mode.TButton")
        self.mode_desc_var.set(cls.mode_description)
        self.set_status(f"Mode: {cls.mode_title}")
        self.refresh_title()

    def choose_game_root(self) -> None:
        initial = str(self.services.game.root) if self.services.game.root else str(Path.cwd())
        chosen = filedialog.askdirectory(parent=self, title="Choose Bakerrrr checkout", initialdir=initial)
        if not chosen:
            return
        try:
            self.services.game.set_root(Path(chosen))
        except Exception as exc:
            messagebox.showerror("Game root", str(exc), parent=self)
            return
        content_ok = self.services.reload_root_content()
        self._refresh_root_label()
        for mode in tuple(self.mode_instances.values()):
            try:
                mode.game_root_changed()
            except Exception as exc:
                self.set_status(f"{mode.mode_title} root refresh failed: {exc}")
        if content_ok:
            drawable_count = len(self.services.drawables.catalog.definitions)
            stamp_count = len(self.services.building_stamps.catalog.definitions)
            self.set_status(
                f"Bakerrrr root: {self.services.game.root} · "
                f"{drawable_count} drawable(s) · {stamp_count} building stamp(s)"
            )
        elif self.services.building_stamps.error:
            self.set_status(f"Building stamp catalog: {self.services.building_stamps.error}")
        elif self.services.items.error:
            self.set_status(f"Item catalog: {self.services.items.error}")
        else:
            self.set_status(f"Drawable catalog: {self.services.drawables.error}")

    def _refresh_root_label(self) -> None:
        root = self.services.game.root
        self.root_var.set(f"root: {root.name}" if root else "root: not set")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def refresh_title(self) -> None:
        if self.active_mode is None:
            self.title(APP_NAME)
            return
        dirty = " *" if getattr(self.active_mode, "dirty", False) else ""
        self.title(f"{APP_NAME} — {self.active_mode.project_label()}{dirty}")

    def show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Bakerrrr Content Workbench\n\n"
            "A standard-library content editor with registered, independently maintained modes.\n"
            "Shared content contracts keep authoring, validation, preview, and game consumption aligned.",
            parent=self,
        )

    def on_close(self) -> None:
        for mode in self.mode_instances.values():
            if not mode.maybe_save_changes():
                return
        self.destroy()


def main() -> int:
    app = WorkbenchApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
