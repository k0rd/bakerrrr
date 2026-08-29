"""Pure parser, resolver, serializer, and catalogue for Bakerrrr drawables.

This module is deliberately renderer-neutral and standard-library only.  Game
frontends and the internal content editor may share it without importing one
another or executing authored content.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping


DRAWABLE_FORMAT_VERSION = 1
DRAWABLE_FILE_SUFFIX = ".bkdraw"
DRAWABLE_CONTEXTS = frozenset({"garment", "ground"})
DRAWABLE_VARIANTS = ("compact", "detailed")
PAINT_ROLES = frozenset({"fill", "edge", "shade", "outline"})
CONDITION_SOURCES = frozenset({"detail", "material", "pattern"})
GARMENT_SYMBOLS = frozenset({
    "mid",
    "shoulder",
    "hip",
    "waist",
    "basewear_hip",
    "body_left",
    "body_right",
    "shoulder_y",
    "hip_y",
    "foot_y",
})
GROUND_SYMBOLS = frozenset({"mid", "left", "right", "top", "bottom"})
MAX_FILE_BYTES = 256 * 1024
MAX_DRAWABLES_PER_FILE = 256
MAX_SHAPES_PER_VARIANT = 256
MAX_POINTS_PER_SHAPE = 128
MAX_LETS_PER_SCOPE = 128
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_TOKEN_RE = re.compile(
    r"(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<identifier>[a-z][a-z0-9_]*)"
    r"|(?P<operator>[+-])"
)


@dataclass(frozen=True)
class SourceLocation:
    source: str
    line: int
    column: int = 1


class DrawableError(ValueError):
    """Friendly authored-content error carrying source coordinates."""

    def __init__(self, message: str, location: SourceLocation | None = None):
        self.message = str(message)
        self.location = location
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.location is None:
            return self.message
        return (
            f"{self.location.source}:{self.location.line}:"
            f"{self.location.column}: {self.message}"
        )


@dataclass(frozen=True)
class ExpressionTerm:
    sign: int
    value: float | str


@dataclass(frozen=True)
class Expression:
    terms: tuple[ExpressionTerm, ...]
    location: SourceLocation

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(
            term.value for term in self.terms if isinstance(term.value, str)
        )

    def evaluate(self, symbols: Mapping[str, float]) -> float:
        result = 0.0
        for term in self.terms:
            if isinstance(term.value, str):
                if term.value not in symbols:
                    raise DrawableError(
                        f"unknown symbol {term.value!r}", self.location
                    )
                value = float(symbols[term.value])
            else:
                value = float(term.value)
            result += term.sign * value
        if not math.isfinite(result):
            raise DrawableError("expression did not resolve to a finite number", self.location)
        return result


@dataclass(frozen=True)
class PointExpression:
    x: Expression
    y: Expression


@dataclass(frozen=True)
class ValueBinding:
    name: str
    expression: Expression
    location: SourceLocation


@dataclass(frozen=True)
class PaintAlias:
    name: str
    role: str
    location: SourceLocation


@dataclass(frozen=True)
class ShapeNode:
    kind: str
    shape_id: str
    paint: str
    location: SourceLocation
    points: tuple[PointExpression, ...] = ()
    x: Expression | None = None
    y: Expression | None = None
    width_value: Expression | None = None
    height_value: Expression | None = None
    radius: Expression | None = None
    stroke_width: Expression | None = None
    outline_paint: str | None = None
    outline_width: Expression | None = None
    closed: bool = False


@dataclass(frozen=True)
class MirrorNode:
    source_shape_id: str
    shape_id: str
    axis: Expression
    location: SourceLocation


@dataclass(frozen=True)
class ConditionalNode:
    source: str
    token: str
    nodes: tuple["DrawableNode", ...]
    location: SourceLocation


DrawableNode = ShapeNode | MirrorNode | ConditionalNode


@dataclass(frozen=True)
class DrawableLayer:
    name: str
    nodes: tuple[DrawableNode, ...]
    location: SourceLocation


@dataclass(frozen=True)
class DrawableGroup:
    name: str
    shape_ids: tuple[str, ...]
    location: SourceLocation


@dataclass(frozen=True)
class DrawableSurface:
    name: str
    shape_ids: tuple[str, ...]
    location: SourceLocation


@dataclass(frozen=True)
class DrawableVariant:
    name: str
    lets: tuple[ValueBinding, ...]
    layers: tuple[DrawableLayer, ...]
    groups: tuple[DrawableGroup, ...]
    surfaces: tuple[DrawableSurface, ...]
    location: SourceLocation


@dataclass(frozen=True)
class DrawablePresentation:
    context: str
    paints: tuple[PaintAlias, ...]
    lets: tuple[ValueBinding, ...]
    variants: tuple[DrawableVariant, ...]
    location: SourceLocation

    def variant(self, requested: str) -> DrawableVariant:
        return _variant_for_presentation(
            self.variants,
            requested,
            context=self.context,
            location=self.location,
        )


@dataclass(frozen=True)
class DrawableDefinition:
    drawable_id: str
    context: str
    version: int
    paints: tuple[PaintAlias, ...]
    lets: tuple[ValueBinding, ...]
    variants: tuple[DrawableVariant, ...]
    presentations: tuple[DrawablePresentation, ...]
    source: str
    location: SourceLocation

    def variant(self, requested: str) -> DrawableVariant:
        return _variant_for_presentation(
            self.variants,
            requested,
            context=self.context,
            location=self.location,
        )

    def presentation(self, context: str) -> DrawablePresentation | None:
        requested = normalize_identifier(context)
        if requested == self.context:
            return DrawablePresentation(
                context=self.context,
                paints=self.paints,
                lets=self.lets,
                variants=self.variants,
                location=self.location,
            )
        return next(
            (presentation for presentation in self.presentations if presentation.context == requested),
            None,
        )


def _variant_for_presentation(
    variants: tuple[DrawableVariant, ...],
    requested: str,
    *,
    context: str,
    location: SourceLocation,
) -> DrawableVariant:
    requested = normalize_identifier(requested)
    if requested not in DRAWABLE_VARIANTS:
        raise DrawableError(
            f"unknown requested variant {requested!r}; expected compact or detailed",
            location,
        )
    by_name = {variant.name: variant for variant in variants}
    variant = by_name.get(requested)
    if variant is not None:
        return variant
    compact = by_name.get("compact")
    if compact is None:
        raise DrawableError(
            f"drawable presentation {context!r} has no compact variant",
            location,
        )
    return compact


@dataclass(frozen=True)
class DrawableDocument:
    version: int
    drawables: tuple[DrawableDefinition, ...]
    source: str


@dataclass(frozen=True)
class DrawableRenderContext:
    context: str
    symbols: Mapping[str, float]
    conditions: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def garment(
        cls,
        *,
        shoulder: float,
        hip: float,
        waist: float,
        basewear_hip: float,
        shoulder_y: float,
        hip_y: float,
        foot_y: float,
        mid: float = 8.0,
        material: str = "",
        detail: str = "",
        pattern: str = "",
    ) -> "DrawableRenderContext":
        mid = float(mid)
        hip = float(hip)
        symbols = {
            "mid": mid,
            "shoulder": float(shoulder),
            "hip": hip,
            "waist": float(waist),
            "basewear_hip": float(basewear_hip),
            "body_left": mid - hip,
            "body_right": mid + hip,
            "shoulder_y": float(shoulder_y),
            "hip_y": float(hip_y),
            "foot_y": float(foot_y),
        }
        for name, value in symbols.items():
            if not math.isfinite(value):
                raise DrawableError(f"garment context symbol {name!r} must be finite")
        conditions = {
            "material": condition_tokens(material),
            "detail": condition_tokens(detail),
            "pattern": condition_tokens(pattern),
        }
        return cls(
            context="garment",
            symbols=MappingProxyType(symbols),
            conditions=MappingProxyType(conditions),
        )

    @classmethod
    def ground(
        cls,
        *,
        mid: float = 8.0,
        left: float = 0.0,
        right: float = 16.0,
        top: float = 0.0,
        bottom: float = 16.0,
        material: str = "",
        detail: str = "",
        pattern: str = "",
    ) -> "DrawableRenderContext":
        symbols = {
            "mid": float(mid),
            "left": float(left),
            "right": float(right),
            "top": float(top),
            "bottom": float(bottom),
        }
        for name, value in symbols.items():
            if not math.isfinite(value):
                raise DrawableError(f"ground context symbol {name!r} must be finite")
        if symbols["right"] < symbols["left"] or symbols["bottom"] < symbols["top"]:
            raise DrawableError("ground context bounds must not be inverted")
        conditions = {
            "material": condition_tokens(material),
            "detail": condition_tokens(detail),
            "pattern": condition_tokens(pattern),
        }
        return cls(
            context="ground",
            symbols=MappingProxyType(symbols),
            conditions=MappingProxyType(conditions),
        )


@dataclass(frozen=True)
class ResolvedShape:
    kind: str
    shape_id: str
    paint_role: str
    layer: str
    points: tuple[tuple[float, float], ...] = ()
    box: tuple[float, float, float, float] | None = None
    radius: float | None = None
    stroke_width: float | None = None
    outline_role: str | None = None
    outline_width: float | None = None
    closed: bool = False


@dataclass(frozen=True)
class ResolvedDrawable:
    drawable_id: str
    context: str
    requested_variant: str
    variant: str
    shapes: tuple[ResolvedShape, ...]
    groups: Mapping[str, tuple[str, ...]]
    surfaces: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class DrawableCatalog:
    definitions: Mapping[str, DrawableDefinition]
    sources: Mapping[str, str]
    revision: str
    files: tuple[str, ...]

    def get(self, drawable_id: str) -> DrawableDefinition | None:
        return self.definitions.get(normalize_identifier(drawable_id))

    def require(self, drawable_id: str) -> DrawableDefinition:
        definition = self.get(drawable_id)
        if definition is None:
            raise DrawableError(f"unknown drawable id {drawable_id!r}")
        return definition


@dataclass(frozen=True)
class _LogicalLine:
    indent: int
    text: str
    location: SourceLocation


def normalize_identifier(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_condition_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def condition_tokens(value: object) -> frozenset[str]:
    if isinstance(value, (tuple, list, set, frozenset)):
        values = value
    else:
        values = (value,)
    result = set()
    for raw in values:
        canonical = normalize_condition_token(raw)
        if canonical:
            result.add(canonical)
            result.update(part for part in canonical.split("_") if part)
    return frozenset(result)


def _validate_identifier(value: str, location: SourceLocation, label: str = "identifier") -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise DrawableError(
            f"invalid {label} {value!r}; expected [a-z][a-z0-9_]*",
            location,
        )
    return value


def parse_expression(text: str, location: SourceLocation) -> Expression:
    source = str(text or "")
    position = 0
    tokens: list[tuple[str, str, int]] = []
    while position < len(source):
        if source[position].isspace():
            position += 1
            continue
        match = _TOKEN_RE.match(source, position)
        if match is None:
            raise DrawableError(
                f"unexpected expression token {source[position]!r}",
                SourceLocation(location.source, location.line, location.column + position),
            )
        kind = str(match.lastgroup)
        tokens.append((kind, match.group(), match.start()))
        position = match.end()

    if not tokens:
        raise DrawableError("expected an expression", location)

    index = 0
    pending_sign = 1
    if tokens[index][0] == "operator":
        pending_sign = -1 if tokens[index][1] == "-" else 1
        index += 1
    terms = []
    expect_atom = True
    while index < len(tokens):
        kind, token, offset = tokens[index]
        if expect_atom:
            if kind == "number":
                value = float(token)
                if not math.isfinite(value):
                    raise DrawableError(
                        "numeric literal must be finite",
                        SourceLocation(location.source, location.line, location.column + offset),
                    )
            elif kind == "identifier":
                value = token
            else:
                raise DrawableError(
                    "expected a number or symbol",
                    SourceLocation(location.source, location.line, location.column + offset),
                )
            terms.append(ExpressionTerm(pending_sign, value))
            pending_sign = 1
            expect_atom = False
        else:
            if kind != "operator":
                raise DrawableError(
                    "expected '+' or '-'",
                    SourceLocation(location.source, location.line, location.column + offset),
                )
            pending_sign = -1 if token == "-" else 1
            expect_atom = True
        index += 1
    if expect_atom:
        raise DrawableError("expression cannot end with an operator", location)
    return Expression(tuple(terms), location)


class _DrawableParser:
    def __init__(self, text: str, source: str):
        self.source = str(source)
        self.lines = self._logical_lines(text)
        self.index = 0

    def _logical_lines(self, text: str) -> tuple[_LogicalLine, ...]:
        result = []
        for line_number, raw in enumerate(str(text).splitlines(), start=1):
            if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                raise DrawableError(
                    "tabs are not allowed for indentation",
                    SourceLocation(self.source, line_number, 1),
                )
            content = raw.split("#", 1)[0].rstrip()
            if not content.strip():
                continue
            spaces = len(content) - len(content.lstrip(" "))
            if spaces % 4:
                raise DrawableError(
                    "indentation must use multiples of four spaces",
                    SourceLocation(self.source, line_number, 1),
                )
            result.append(
                _LogicalLine(
                    spaces // 4,
                    content.strip(),
                    SourceLocation(self.source, line_number, spaces + 1),
                )
            )
        return tuple(result)

    def current(self) -> _LogicalLine | None:
        return self.lines[self.index] if self.index < len(self.lines) else None

    def take(self) -> _LogicalLine:
        line = self.current()
        if line is None:
            raise DrawableError("unexpected end of file")
        self.index += 1
        return line

    def require_child(self, parent: _LogicalLine) -> None:
        line = self.current()
        if line is None or line.indent != parent.indent + 1:
            raise DrawableError("expected an indented block", parent.location)

    def parse(self) -> DrawableDocument:
        if not self.lines:
            raise DrawableError("empty drawable document", SourceLocation(self.source, 1, 1))
        header = self.take()
        match = re.fullmatch(r"bakerrrr-drawable\s+(\d+)", header.text)
        if header.indent or match is None:
            raise DrawableError("expected 'bakerrrr-drawable 1' header", header.location)
        version = int(match.group(1))
        if version != DRAWABLE_FORMAT_VERSION:
            raise DrawableError(
                f"unsupported drawable format version {version}; expected {DRAWABLE_FORMAT_VERSION}",
                header.location,
            )

        drawables = []
        while self.current() is not None:
            drawables.append(self.parse_drawable(version))
            if len(drawables) > MAX_DRAWABLES_PER_FILE:
                raise DrawableError(
                    f"document exceeds {MAX_DRAWABLES_PER_FILE} drawables",
                    drawables[-1].location,
                )
        if not drawables:
            raise DrawableError("document must define at least one drawable", header.location)
        document = DrawableDocument(version, tuple(drawables), self.source)
        validate_document(document)
        return document

    def parse_drawable(self, version: int) -> DrawableDefinition:
        line = self.take()
        match = re.fullmatch(
            r"drawable\s+([a-z][a-z0-9_]*)\s+context\s+([a-z][a-z0-9_]*):",
            line.text,
        )
        if line.indent or match is None:
            raise DrawableError(
                "expected 'drawable <id> context <context>:'",
                line.location,
            )
        drawable_id = _validate_identifier(match.group(1), line.location, "drawable id")
        context = _validate_identifier(match.group(2), line.location, "context")
        if context not in DRAWABLE_CONTEXTS:
            raise DrawableError(f"unknown drawable context {context!r}", line.location)
        self.require_child(line)

        paints = []
        lets = []
        variants = []
        presentations = []
        while self.current() is not None and self.current().indent > line.indent:
            child = self.current()
            if child.indent != line.indent + 1:
                raise DrawableError("unexpected indentation", child.location)
            if child.text.startswith("paint "):
                paints.append(self.parse_paint())
            elif child.text.startswith("let "):
                lets.append(self.parse_let())
            elif child.text.startswith("variant "):
                variants.append(self.parse_variant())
            elif child.text.startswith("presentation "):
                presentations.append(self.parse_presentation())
            else:
                raise DrawableError(
                    "drawable blocks accept paint, let, variant, or presentation statements",
                    child.location,
                )
        return DrawableDefinition(
            drawable_id=drawable_id,
            context=context,
            version=version,
            paints=tuple(paints),
            lets=tuple(lets),
            variants=tuple(variants),
            presentations=tuple(presentations),
            source=self.source,
            location=line.location,
        )

    def parse_presentation(self) -> DrawablePresentation:
        line = self.take()
        match = re.fullmatch(r"presentation\s+([a-z][a-z0-9_]*):", line.text)
        if match is None:
            raise DrawableError("expected 'presentation <context>:'", line.location)
        context = _validate_identifier(match.group(1), line.location, "presentation context")
        if context not in DRAWABLE_CONTEXTS:
            raise DrawableError(f"unknown drawable context {context!r}", line.location)
        self.require_child(line)

        paints = []
        lets = []
        variants = []
        while self.current() is not None and self.current().indent > line.indent:
            child = self.current()
            if child.indent != line.indent + 1:
                raise DrawableError("unexpected indentation", child.location)
            if child.text.startswith("paint "):
                paints.append(self.parse_paint())
            elif child.text.startswith("let "):
                lets.append(self.parse_let())
            elif child.text.startswith("variant "):
                variants.append(self.parse_variant())
            else:
                raise DrawableError(
                    "presentation blocks accept paint, let, or variant statements",
                    child.location,
                )
        return DrawablePresentation(
            context=context,
            paints=tuple(paints),
            lets=tuple(lets),
            variants=tuple(variants),
            location=line.location,
        )

    def parse_paint(self) -> PaintAlias:
        line = self.take()
        match = re.fullmatch(
            r"paint\s+([a-z][a-z0-9_]*)\s*=\s*([a-z][a-z0-9_]*)",
            line.text,
        )
        if match is None:
            raise DrawableError("expected 'paint <alias> = <role>'", line.location)
        name = _validate_identifier(match.group(1), line.location, "paint alias")
        role = match.group(2)
        if role not in PAINT_ROLES:
            raise DrawableError(f"unknown paint role {role!r}", line.location)
        return PaintAlias(name, role, line.location)

    def parse_let(self) -> ValueBinding:
        line = self.take()
        match = re.fullmatch(r"let\s+([a-z][a-z0-9_]*)\s*=\s*(.+)", line.text)
        if match is None:
            raise DrawableError("expected 'let <name> = <expression>'", line.location)
        name = _validate_identifier(match.group(1), line.location, "let name")
        expression_text = match.group(2)
        expression = parse_expression(
            expression_text,
            SourceLocation(
                line.location.source,
                line.location.line,
                line.location.column + line.text.index(expression_text),
            ),
        )
        return ValueBinding(name, expression, line.location)

    def parse_variant(self) -> DrawableVariant:
        line = self.take()
        match = re.fullmatch(r"variant\s+([a-z][a-z0-9_]*):", line.text)
        if match is None:
            raise DrawableError("expected 'variant <name>:'", line.location)
        name = _validate_identifier(match.group(1), line.location, "variant name")
        if name not in DRAWABLE_VARIANTS:
            raise DrawableError(
                f"unknown variant {name!r}; expected compact or detailed",
                line.location,
            )
        self.require_child(line)
        lets = []
        layers = []
        groups = []
        surfaces = []
        while self.current() is not None and self.current().indent > line.indent:
            child = self.current()
            if child.indent != line.indent + 1:
                raise DrawableError("unexpected indentation", child.location)
            if child.text.startswith("let "):
                lets.append(self.parse_let())
            elif child.text.startswith("layer "):
                layers.append(self.parse_layer())
            elif child.text.startswith("group "):
                groups.append(self.parse_named_shape_list("group"))
            elif child.text.startswith("surface "):
                surfaces.append(self.parse_named_shape_list("surface"))
            else:
                raise DrawableError(
                    "variant blocks accept let, layer, group, or surface statements",
                    child.location,
                )
        return DrawableVariant(
            name,
            tuple(lets),
            tuple(layers),
            tuple(groups),
            tuple(surfaces),
            line.location,
        )

    def parse_layer(self) -> DrawableLayer:
        line = self.take()
        match = re.fullmatch(r"layer\s+([a-z][a-z0-9_]*):", line.text)
        if match is None:
            raise DrawableError("expected 'layer <name>:'", line.location)
        name = _validate_identifier(match.group(1), line.location, "layer name")
        self.require_child(line)
        nodes = self.parse_nodes(line.indent + 1, conditional_depth=0)
        return DrawableLayer(name, tuple(nodes), line.location)

    def parse_nodes(self, indent: int, *, conditional_depth: int) -> list[DrawableNode]:
        nodes: list[DrawableNode] = []
        while self.current() is not None and self.current().indent >= indent:
            line = self.current()
            if line.indent > indent:
                raise DrawableError("unexpected indentation", line.location)
            if line.indent < indent:
                break
            if line.text.startswith("when "):
                nodes.append(self.parse_condition(conditional_depth))
            elif line.text.startswith("mirror "):
                nodes.append(self.parse_mirror())
            elif line.text.startswith("polygon "):
                nodes.append(self.parse_polygon())
            elif line.text.startswith("line "):
                nodes.append(self.parse_line())
            elif line.text.startswith("rect ") or line.text.startswith("ellipse "):
                nodes.append(self.parse_box_shape())
            elif line.text.startswith("circle "):
                nodes.append(self.parse_circle())
            else:
                raise DrawableError("unknown layer statement", line.location)
        return nodes

    def parse_condition(self, depth: int) -> ConditionalNode:
        line = self.take()
        if depth >= 2:
            raise DrawableError("conditional nesting exceeds the v1 limit of 2", line.location)
        match = re.fullmatch(
            r"when\s+([a-z][a-z0-9_]*)\s+has\s+([a-z][a-z0-9_]*):",
            line.text,
        )
        if match is None:
            raise DrawableError(
                "expected 'when <detail|material|pattern> has <token>:'",
                line.location,
            )
        source = match.group(1)
        if source not in CONDITION_SOURCES:
            raise DrawableError(f"unknown condition source {source!r}", line.location)
        token = normalize_condition_token(match.group(2))
        self.require_child(line)
        nodes = self.parse_nodes(line.indent + 1, conditional_depth=depth + 1)
        return ConditionalNode(source, token, tuple(nodes), line.location)

    def parse_mirror(self) -> MirrorNode:
        line = self.take()
        match = re.fullmatch(
            r"mirror\s+([a-z][a-z0-9_]*)(?:\s+across\s+(.+?))?\s+as\s+([a-z][a-z0-9_]*)",
            line.text,
        )
        if match is None:
            raise DrawableError(
                "expected 'mirror <shape> [across <expression>] as <shape>'",
                line.location,
            )
        source_id = match.group(1)
        axis_text = match.group(2) or "mid"
        shape_id = match.group(3)
        axis = parse_expression(axis_text, line.location)
        return MirrorNode(source_id, shape_id, axis, line.location)

    def _parse_shape_header(
        self,
        line: _LogicalLine,
        kind: str,
        *,
        allow_outline: bool,
    ) -> tuple[str, str, str | None, Expression | None]:
        body = line.text[:-1] if line.text.endswith(":") else ""
        if not body:
            raise DrawableError(f"{kind} declaration must end with ':'", line.location)
        prefix = f"{kind} "
        tokens = body[len(prefix):].split()
        if len(tokens) < 2:
            raise DrawableError(f"expected '{kind} <id> <paint>:'", line.location)
        shape_id = _validate_identifier(tokens[0], line.location, "shape id")
        paint = _validate_identifier(tokens[1], line.location, "paint")
        outline_paint = None
        outline_width = None
        if len(tokens) > 2:
            if not allow_outline or len(tokens) < 6 or tokens[2] != "outline" or "width" not in tokens[4:]:
                raise DrawableError("malformed outline clause", line.location)
            width_index = tokens.index("width", 4)
            if width_index != 4:
                raise DrawableError("expected 'outline <paint> width <expression>'", line.location)
            outline_paint = _validate_identifier(tokens[3], line.location, "outline paint")
            width_text = " ".join(tokens[5:])
            outline_width = parse_expression(width_text, line.location)
        return shape_id, paint, outline_paint, outline_width

    def parse_polygon(self) -> ShapeNode:
        line = self.take()
        shape_id, paint, outline_paint, outline_width = self._parse_shape_header(
            line, "polygon", allow_outline=True
        )
        self.require_child(line)
        points = self.parse_points(line.indent + 1)
        if len(points) < 3:
            raise DrawableError("polygon requires at least three points", line.location)
        return ShapeNode(
            "polygon",
            shape_id,
            paint,
            line.location,
            points=tuple(points),
            outline_paint=outline_paint,
            outline_width=outline_width,
        )

    def parse_line(self) -> ShapeNode:
        line = self.take()
        match = re.fullmatch(
            r"line\s+([a-z][a-z0-9_]*)\s+([a-z][a-z0-9_]*)\s+width\s+(.+?)(\s+closed)?:",
            line.text,
        )
        if match is None:
            raise DrawableError(
                "expected 'line <id> <paint> width <expression> [closed]:'",
                line.location,
            )
        shape_id = _validate_identifier(match.group(1), line.location, "shape id")
        paint = _validate_identifier(match.group(2), line.location, "paint")
        stroke_width = parse_expression(match.group(3), line.location)
        self.require_child(line)
        points = self.parse_points(line.indent + 1)
        if len(points) < 2:
            raise DrawableError("line requires at least two points", line.location)
        return ShapeNode(
            "line",
            shape_id,
            paint,
            line.location,
            points=tuple(points),
            stroke_width=stroke_width,
            closed=bool(match.group(4)),
        )

    def parse_points(self, indent: int) -> list[PointExpression]:
        points = []
        while self.current() is not None and self.current().indent >= indent:
            line = self.current()
            if line.indent != indent:
                if line.indent > indent:
                    raise DrawableError("unexpected indentation in point list", line.location)
                break
            self.take()
            if "," not in line.text:
                raise DrawableError("point must be '<x>, <y>'", line.location)
            x_text, y_text = line.text.split(",", 1)
            points.append(
                PointExpression(
                    parse_expression(x_text, line.location),
                    parse_expression(y_text, line.location),
                )
            )
        return points

    def parse_box_shape(self) -> ShapeNode:
        line = self.take()
        kind = "rect" if line.text.startswith("rect ") else "ellipse"
        shape_id, paint, _, _ = self._parse_shape_header(line, kind, allow_outline=False)
        self.require_child(line)
        fields = self.parse_fields(line.indent + 1, {"x", "y", "w", "h", "outline", "width"})
        for required in ("x", "y", "w", "h"):
            if required not in fields:
                raise DrawableError(f"{kind} requires field {required!r}", line.location)
        outline_paint = None
        if "outline" in fields:
            outline_paint = _validate_identifier(fields["outline"][0], fields["outline"][1], "outline paint")
        outline_width = parse_expression(*fields["width"]) if "width" in fields else None
        if outline_paint is None and outline_width is not None:
            raise DrawableError("outline width requires an outline paint", line.location)
        return ShapeNode(
            kind,
            shape_id,
            paint,
            line.location,
            x=parse_expression(*fields["x"]),
            y=parse_expression(*fields["y"]),
            width_value=parse_expression(*fields["w"]),
            height_value=parse_expression(*fields["h"]),
            outline_paint=outline_paint,
            outline_width=outline_width,
        )

    def parse_circle(self) -> ShapeNode:
        line = self.take()
        shape_id, paint, _, _ = self._parse_shape_header(line, "circle", allow_outline=False)
        self.require_child(line)
        fields = self.parse_fields(line.indent + 1, {"center", "radius", "outline", "width"})
        if "center" not in fields or "radius" not in fields:
            raise DrawableError("circle requires center and radius fields", line.location)
        center_text, center_location = fields["center"]
        if "," not in center_text:
            raise DrawableError("circle center must be '<x>, <y>'", center_location)
        center_x, center_y = center_text.split(",", 1)
        outline_paint = None
        if "outline" in fields:
            outline_paint = _validate_identifier(fields["outline"][0], fields["outline"][1], "outline paint")
        outline_width = parse_expression(*fields["width"]) if "width" in fields else None
        if outline_paint is None and outline_width is not None:
            raise DrawableError("outline width requires an outline paint", line.location)
        return ShapeNode(
            "circle",
            shape_id,
            paint,
            line.location,
            x=parse_expression(center_x, center_location),
            y=parse_expression(center_y, center_location),
            radius=parse_expression(*fields["radius"]),
            outline_paint=outline_paint,
            outline_width=outline_width,
        )

    def parse_fields(
        self,
        indent: int,
        allowed: set[str],
    ) -> dict[str, tuple[str, SourceLocation]]:
        fields = {}
        while self.current() is not None and self.current().indent >= indent:
            line = self.current()
            if line.indent != indent:
                if line.indent > indent:
                    raise DrawableError("unexpected field indentation", line.location)
                break
            self.take()
            key, separator, value = line.text.partition(" ")
            if not separator or not value.strip():
                raise DrawableError("expected '<field> <value>'", line.location)
            if key not in allowed:
                raise DrawableError(f"unknown field {key!r}", line.location)
            if key in fields:
                raise DrawableError(f"duplicate field {key!r}", line.location)
            fields[key] = (value.strip(), line.location)
        return fields

    def parse_named_shape_list(self, kind: str) -> DrawableGroup | DrawableSurface:
        line = self.take()
        match = re.fullmatch(rf"{kind}\s+([a-z][a-z0-9_]*):", line.text)
        if match is None:
            raise DrawableError(f"expected '{kind} <name>:'", line.location)
        name = _validate_identifier(match.group(1), line.location, f"{kind} name")
        self.require_child(line)
        shape_ids = []
        expected_indent = line.indent + 1
        while self.current() is not None and self.current().indent >= expected_indent:
            child = self.current()
            if child.indent != expected_indent:
                if child.indent > expected_indent:
                    raise DrawableError("unexpected indentation", child.location)
                break
            self.take()
            shape_ids.append(_validate_identifier(child.text, child.location, "shape id"))
        if not shape_ids:
            raise DrawableError(f"{kind} must contain at least one shape id", line.location)
        cls = DrawableGroup if kind == "group" else DrawableSurface
        return cls(name, tuple(shape_ids), line.location)


def parse_drawable_text(text: str, *, source: str = "<memory>") -> DrawableDocument:
    if len(str(text).encode("utf-8")) > MAX_FILE_BYTES:
        raise DrawableError(
            f"drawable file exceeds the {MAX_FILE_BYTES}-byte v1 limit",
            SourceLocation(str(source), 1, 1),
        )
    return _DrawableParser(text, source).parse()


def parse_drawable_file(path: str | Path) -> DrawableDocument:
    resolved = Path(path)
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DrawableError(f"could not read drawable file: {exc}") from exc
    return parse_drawable_text(text, source=str(resolved))


def _expressions_for_shape(shape: ShapeNode) -> tuple[Expression, ...]:
    expressions = []
    for point in shape.points:
        expressions.extend((point.x, point.y))
    for expression in (
        shape.x,
        shape.y,
        shape.width_value,
        shape.height_value,
        shape.radius,
        shape.stroke_width,
        shape.outline_width,
    ):
        if expression is not None:
            expressions.append(expression)
    return tuple(expressions)


def _validate_expression_symbols(expression: Expression, available: set[str]) -> None:
    unknown = sorted(expression.symbols - available)
    if unknown:
        raise DrawableError(f"unknown symbol {unknown[0]!r}", expression.location)


def _validate_bindings(bindings: Iterable[ValueBinding], available: set[str]) -> set[str]:
    result = set(available)
    for binding in bindings:
        if binding.name in result:
            raise DrawableError(f"duplicate or reserved let name {binding.name!r}", binding.location)
        _validate_expression_symbols(binding.expression, result)
        result.add(binding.name)
    return result


def _validate_nodes(
    nodes: Iterable[DrawableNode],
    *,
    symbols: set[str],
    paints: set[str],
    all_shape_ids: set[str],
    available_sources: set[str],
) -> None:
    for node in nodes:
        if isinstance(node, ShapeNode):
            if node.shape_id in all_shape_ids:
                raise DrawableError(f"duplicate shape id {node.shape_id!r}", node.location)
            if node.paint not in paints:
                raise DrawableError(f"unknown paint {node.paint!r}", node.location)
            if node.outline_paint is not None and node.outline_paint not in paints:
                raise DrawableError(f"unknown outline paint {node.outline_paint!r}", node.location)
            for expression in _expressions_for_shape(node):
                _validate_expression_symbols(expression, symbols)
            if len(node.points) > MAX_POINTS_PER_SHAPE:
                raise DrawableError(
                    f"shape exceeds {MAX_POINTS_PER_SHAPE} points",
                    node.location,
                )
            all_shape_ids.add(node.shape_id)
            available_sources.add(node.shape_id)
        elif isinstance(node, MirrorNode):
            if node.shape_id in all_shape_ids:
                raise DrawableError(f"duplicate shape id {node.shape_id!r}", node.location)
            if node.source_shape_id not in available_sources:
                raise DrawableError(
                    f"mirror source {node.source_shape_id!r} is not available here",
                    node.location,
                )
            _validate_expression_symbols(node.axis, symbols)
            all_shape_ids.add(node.shape_id)
            available_sources.add(node.shape_id)
        else:
            branch_sources = set(available_sources)
            _validate_nodes(
                node.nodes,
                symbols=symbols,
                paints=paints,
                all_shape_ids=all_shape_ids,
                available_sources=branch_sources,
            )


def _context_symbols(context: str, location: SourceLocation) -> set[str]:
    if context == "garment":
        return set(GARMENT_SYMBOLS)
    if context == "ground":
        return set(GROUND_SYMBOLS)
    raise DrawableError(f"unknown context {context!r}", location)


def _validate_presentation(
    *,
    context: str,
    paints_authored: tuple[PaintAlias, ...],
    lets: tuple[ValueBinding, ...],
    variants: tuple[DrawableVariant, ...],
    location: SourceLocation,
) -> None:
    base_symbols = _context_symbols(context, location)
    paints = set(PAINT_ROLES)
    aliases = set()
    for alias in paints_authored:
        if alias.name in paints or alias.name in aliases:
            raise DrawableError(f"duplicate or reserved paint {alias.name!r}", alias.location)
        aliases.add(alias.name)
        paints.add(alias.name)
    if len(lets) > MAX_LETS_PER_SCOPE:
        raise DrawableError(
            f"presentation exceeds {MAX_LETS_PER_SCOPE} let bindings",
            location,
        )
    shared_symbols = _validate_bindings(lets, base_symbols)

    variant_names = set()
    for variant in variants:
        if variant.name in variant_names:
            raise DrawableError(f"duplicate variant {variant.name!r}", variant.location)
        variant_names.add(variant.name)
        if not variant.layers:
            raise DrawableError(
                f"variant {variant.name!r} requires at least one layer",
                variant.location,
            )
        if len(variant.lets) > MAX_LETS_PER_SCOPE:
            raise DrawableError(
                f"variant exceeds {MAX_LETS_PER_SCOPE} let bindings",
                variant.location,
            )
        symbols = _validate_bindings(variant.lets, shared_symbols)
        layer_names = set()
        all_shape_ids: set[str] = set()
        available_sources: set[str] = set()
        for layer in variant.layers:
            if layer.name in layer_names:
                raise DrawableError(f"duplicate layer {layer.name!r}", layer.location)
            layer_names.add(layer.name)
            _validate_nodes(
                layer.nodes,
                symbols=symbols,
                paints=paints,
                all_shape_ids=all_shape_ids,
                available_sources=available_sources,
            )
        if len(all_shape_ids) > MAX_SHAPES_PER_VARIANT:
            raise DrawableError(
                f"variant exceeds {MAX_SHAPES_PER_VARIANT} shapes",
                variant.location,
            )
        for collection, label in ((variant.groups, "group"), (variant.surfaces, "surface")):
            names = set()
            for record in collection:
                if record.name in names:
                    raise DrawableError(f"duplicate {label} {record.name!r}", record.location)
                names.add(record.name)
                for shape_id in record.shape_ids:
                    if shape_id not in all_shape_ids:
                        raise DrawableError(
                            f"unknown shape id {shape_id!r} in {label} {record.name!r}",
                            record.location,
                        )
    if "compact" not in variant_names:
        raise DrawableError(
            f"presentation {context!r} requires a compact variant",
            location,
        )


def validate_document(document: DrawableDocument) -> None:
    drawable_ids = set()
    for drawable in document.drawables:
        if drawable.drawable_id in drawable_ids:
            raise DrawableError(
                f"duplicate drawable id {drawable.drawable_id!r}", drawable.location
            )
        drawable_ids.add(drawable.drawable_id)
        _validate_presentation(
            context=drawable.context,
            paints_authored=drawable.paints,
            lets=drawable.lets,
            variants=drawable.variants,
            location=drawable.location,
        )
        contexts = {drawable.context}
        for presentation in drawable.presentations:
            if presentation.context in contexts:
                raise DrawableError(
                    f"duplicate presentation context {presentation.context!r}",
                    presentation.location,
                )
            contexts.add(presentation.context)
            _validate_presentation(
                context=presentation.context,
                paints_authored=presentation.paints,
                lets=presentation.lets,
                variants=presentation.variants,
                location=presentation.location,
            )


def _evaluate_bindings(
    bindings: Iterable[ValueBinding],
    symbols: dict[str, float],
) -> None:
    for binding in bindings:
        symbols[binding.name] = binding.expression.evaluate(symbols)


def _resolve_paint(paint: str | None, aliases: Mapping[str, str]) -> str | None:
    if paint is None:
        return None
    return aliases.get(paint, paint)


def _resolve_shape(
    node: ShapeNode,
    *,
    layer: str,
    symbols: Mapping[str, float],
    aliases: Mapping[str, str],
) -> ResolvedShape:
    points = tuple((point.x.evaluate(symbols), point.y.evaluate(symbols)) for point in node.points)
    box = None
    radius = node.radius.evaluate(symbols) if node.radius is not None else None
    if node.kind in {"rect", "ellipse"}:
        x = node.x.evaluate(symbols) if node.x is not None else 0.0
        y = node.y.evaluate(symbols) if node.y is not None else 0.0
        width = node.width_value.evaluate(symbols) if node.width_value is not None else 0.0
        height = node.height_value.evaluate(symbols) if node.height_value is not None else 0.0
        if width < 0 or height < 0:
            raise DrawableError("rect/ellipse width and height must be non-negative", node.location)
        box = (x, y, width, height)
    elif node.kind == "circle":
        x = node.x.evaluate(symbols) if node.x is not None else 0.0
        y = node.y.evaluate(symbols) if node.y is not None else 0.0
        if radius is None or radius < 0:
            raise DrawableError("circle radius must be non-negative", node.location)
        points = ((x, y),)
    stroke_width = node.stroke_width.evaluate(symbols) if node.stroke_width is not None else None
    outline_width = node.outline_width.evaluate(symbols) if node.outline_width is not None else None
    if stroke_width is not None and stroke_width < 0:
        raise DrawableError("line width must be non-negative", node.location)
    if outline_width is not None and outline_width < 0:
        raise DrawableError("outline width must be non-negative", node.location)
    return ResolvedShape(
        kind=node.kind,
        shape_id=node.shape_id,
        paint_role=str(_resolve_paint(node.paint, aliases)),
        layer=layer,
        points=points,
        box=box,
        radius=radius,
        stroke_width=stroke_width,
        outline_role=_resolve_paint(node.outline_paint, aliases),
        outline_width=outline_width,
        closed=node.closed,
    )


def _mirror_shape(shape: ResolvedShape, *, shape_id: str, axis: float) -> ResolvedShape:
    points = tuple((2.0 * axis - x, y) for x, y in shape.points)
    if shape.kind == "polygon":
        points = tuple(reversed(points))
    box = shape.box
    if box is not None:
        x, y, width, height = box
        box = (2.0 * axis - (x + width), y, width, height)
    return ResolvedShape(
        kind=shape.kind,
        shape_id=shape_id,
        paint_role=shape.paint_role,
        layer=shape.layer,
        points=points,
        box=box,
        radius=shape.radius,
        stroke_width=shape.stroke_width,
        outline_role=shape.outline_role,
        outline_width=shape.outline_width,
        closed=shape.closed,
    )


def _resolve_nodes(
    nodes: Iterable[DrawableNode],
    *,
    layer: str,
    symbols: Mapping[str, float],
    aliases: Mapping[str, str],
    conditions: Mapping[str, frozenset[str]],
    resolved: list[ResolvedShape],
    by_id: dict[str, ResolvedShape],
) -> None:
    for node in nodes:
        if isinstance(node, ShapeNode):
            shape = _resolve_shape(node, layer=layer, symbols=symbols, aliases=aliases)
            resolved.append(shape)
            by_id[shape.shape_id] = shape
        elif isinstance(node, MirrorNode):
            source_shape = by_id.get(node.source_shape_id)
            if source_shape is None:
                raise DrawableError(
                    f"active mirror source {node.source_shape_id!r} was not resolved",
                    node.location,
                )
            shape = _mirror_shape(
                source_shape,
                shape_id=node.shape_id,
                axis=node.axis.evaluate(symbols),
            )
            resolved.append(shape)
            by_id[shape.shape_id] = shape
        elif node.token in conditions.get(node.source, frozenset()):
            _resolve_nodes(
                node.nodes,
                layer=layer,
                symbols=symbols,
                aliases=aliases,
                conditions=conditions,
                resolved=resolved,
                by_id=by_id,
            )


def resolve_drawable(
    drawable: DrawableDefinition,
    context: DrawableRenderContext,
    *,
    variant: str = "compact",
) -> ResolvedDrawable:
    presentation = drawable.presentation(context.context)
    if presentation is None:
        raise DrawableError(
            f"drawable {drawable.drawable_id!r} has no {context.context!r} presentation",
            drawable.location,
        )
    requested = normalize_identifier(variant) or "compact"
    selected = presentation.variant(requested)
    symbols = {str(name): float(value) for name, value in context.symbols.items()}
    _evaluate_bindings(presentation.lets, symbols)
    _evaluate_bindings(selected.lets, symbols)
    aliases = {alias.name: alias.role for alias in presentation.paints}
    resolved: list[ResolvedShape] = []
    by_id: dict[str, ResolvedShape] = {}
    for layer in selected.layers:
        _resolve_nodes(
            layer.nodes,
            layer=layer.name,
            symbols=symbols,
            aliases=aliases,
            conditions=context.conditions,
            resolved=resolved,
            by_id=by_id,
        )
    present = set(by_id)
    groups = {
        group.name: tuple(shape_id for shape_id in group.shape_ids if shape_id in present)
        for group in selected.groups
    }
    surfaces = {
        surface.name: tuple(shape_id for shape_id in surface.shape_ids if shape_id in present)
        for surface in selected.surfaces
    }
    default_surface = "garment" if presentation.context == "garment" else "item"
    if default_surface not in surfaces:
        surfaces[default_surface] = tuple(
            shape.shape_id
            for shape in resolved
            if shape.kind in {"polygon", "rect", "ellipse", "circle"}
            and shape.paint_role == "fill"
        )
    return ResolvedDrawable(
        drawable_id=drawable.drawable_id,
        context=presentation.context,
        requested_variant=requested,
        variant=selected.name,
        shapes=tuple(resolved),
        groups=MappingProxyType(groups),
        surfaces=MappingProxyType(surfaces),
    )


def _format_number(value: float) -> str:
    value = float(value)
    if value == 0:
        return "0"
    if value.is_integer():
        return str(int(value))
    return f"{value:.8f}".rstrip("0").rstrip(".")


def serialize_expression(expression: Expression) -> str:
    parts = []
    for index, term in enumerate(expression.terms):
        value = term.value if isinstance(term.value, str) else _format_number(term.value)
        if index == 0:
            parts.append(f"-{value}" if term.sign < 0 else str(value))
        else:
            parts.append(("- " if term.sign < 0 else "+ ") + str(value))
    return " ".join(parts)


def _serialize_nodes(nodes: Iterable[DrawableNode], indent: int) -> list[str]:
    prefix = "    " * indent
    lines = []
    for node in nodes:
        if isinstance(node, ConditionalNode):
            lines.append(f"{prefix}when {node.source} has {node.token}:")
            lines.extend(_serialize_nodes(node.nodes, indent + 1))
            continue
        if isinstance(node, MirrorNode):
            axis = serialize_expression(node.axis)
            across = "" if axis == "mid" else f" across {axis}"
            lines.append(f"{prefix}mirror {node.source_shape_id}{across} as {node.shape_id}")
            continue
        if node.kind == "polygon":
            outline = ""
            if node.outline_paint is not None and node.outline_width is not None:
                outline = f" outline {node.outline_paint} width {serialize_expression(node.outline_width)}"
            lines.append(f"{prefix}polygon {node.shape_id} {node.paint}{outline}:")
            for point in node.points:
                lines.append(
                    f"{prefix}    {serialize_expression(point.x)}, {serialize_expression(point.y)}"
                )
        elif node.kind == "line":
            closed = " closed" if node.closed else ""
            lines.append(
                f"{prefix}line {node.shape_id} {node.paint} width "
                f"{serialize_expression(node.stroke_width)}{closed}:"
            )
            for point in node.points:
                lines.append(
                    f"{prefix}    {serialize_expression(point.x)}, {serialize_expression(point.y)}"
                )
        elif node.kind in {"rect", "ellipse"}:
            lines.append(f"{prefix}{node.kind} {node.shape_id} {node.paint}:")
            lines.append(f"{prefix}    x {serialize_expression(node.x)}")
            lines.append(f"{prefix}    y {serialize_expression(node.y)}")
            lines.append(f"{prefix}    w {serialize_expression(node.width_value)}")
            lines.append(f"{prefix}    h {serialize_expression(node.height_value)}")
            if node.outline_paint is not None:
                lines.append(f"{prefix}    outline {node.outline_paint}")
            if node.outline_width is not None:
                lines.append(f"{prefix}    width {serialize_expression(node.outline_width)}")
        elif node.kind == "circle":
            lines.append(f"{prefix}circle {node.shape_id} {node.paint}:")
            lines.append(
                f"{prefix}    center {serialize_expression(node.x)}, {serialize_expression(node.y)}"
            )
            lines.append(f"{prefix}    radius {serialize_expression(node.radius)}")
            if node.outline_paint is not None:
                lines.append(f"{prefix}    outline {node.outline_paint}")
            if node.outline_width is not None:
                lines.append(f"{prefix}    width {serialize_expression(node.outline_width)}")
    return lines


def _serialize_presentation_body(
    lines: list[str],
    *,
    paints: tuple[PaintAlias, ...],
    lets: tuple[ValueBinding, ...],
    variants: tuple[DrawableVariant, ...],
    indent: int,
) -> None:
    prefix = "    " * indent
    for alias in paints:
        lines.append(f"{prefix}paint {alias.name} = {alias.role}")
    for binding in lets:
        lines.append(f"{prefix}let {binding.name} = {serialize_expression(binding.expression)}")
    for variant in variants:
        lines.extend(("", f"{prefix}variant {variant.name}:"))
        variant_prefix = "    " * (indent + 1)
        for binding in variant.lets:
            lines.append(
                f"{variant_prefix}let {binding.name} = {serialize_expression(binding.expression)}"
            )
        for layer in variant.layers:
            lines.append(f"{variant_prefix}layer {layer.name}:")
            lines.extend(_serialize_nodes(layer.nodes, indent + 2))
        for group in variant.groups:
            lines.append(f"{variant_prefix}group {group.name}:")
            lines.extend(f"{'    ' * (indent + 2)}{shape_id}" for shape_id in group.shape_ids)
        for surface in variant.surfaces:
            lines.append(f"{variant_prefix}surface {surface.name}:")
            lines.extend(f"{'    ' * (indent + 2)}{shape_id}" for shape_id in surface.shape_ids)


def serialize_document(document: DrawableDocument) -> str:
    lines = [f"bakerrrr-drawable {document.version}"]
    for drawable in document.drawables:
        lines.extend(("", f"drawable {drawable.drawable_id} context {drawable.context}:"))
        _serialize_presentation_body(
            lines,
            paints=drawable.paints,
            lets=drawable.lets,
            variants=drawable.variants,
            indent=1,
        )
        for presentation in drawable.presentations:
            lines.extend(("", f"    presentation {presentation.context}:"))
            _serialize_presentation_body(
                lines,
                paints=presentation.paints,
                lets=presentation.lets,
                variants=presentation.variants,
                indent=2,
            )
    return "\n".join(lines).rstrip() + "\n"


def _drawable_files(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(path.rglob(f"*{DRAWABLE_FILE_SUFFIX}"))
        elif path.is_file() and path.suffix == DRAWABLE_FILE_SUFFIX:
            files.append(path)
    return tuple(sorted({path.resolve() for path in files}, key=lambda path: str(path)))


def load_drawable_catalog(paths: Iterable[str | Path]) -> DrawableCatalog:
    definitions: dict[str, DrawableDefinition] = {}
    sources: dict[str, str] = {}
    digest = hashlib.sha256()
    files = _drawable_files(paths)
    for path in files:
        try:
            source_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DrawableError(f"could not read drawable file {path}: {exc}") from exc
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_text.encode("utf-8"))
        digest.update(b"\0")
        document = parse_drawable_text(source_text, source=str(path))
        for definition in document.drawables:
            previous = sources.get(definition.drawable_id)
            if previous is not None:
                raise DrawableError(
                    f"duplicate drawable id {definition.drawable_id!r}; first defined in {previous}",
                    definition.location,
                )
            definitions[definition.drawable_id] = definition
            sources[definition.drawable_id] = str(path)
    return DrawableCatalog(
        definitions=MappingProxyType(definitions),
        sources=MappingProxyType(sources),
        revision=digest.hexdigest(),
        files=tuple(str(path) for path in files),
    )


BUILTIN_DRAWABLE_ROOT = Path(__file__).resolve().parent / "drawables"


def load_builtin_drawable_catalog() -> DrawableCatalog:
    return load_drawable_catalog((BUILTIN_DRAWABLE_ROOT,))
