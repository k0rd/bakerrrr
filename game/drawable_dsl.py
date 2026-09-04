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

# Shared body geometry is the sole source of worn-garment coordinates.
from .body_geometry import (
    DRAWABLE_UNITS,
    SEMANTIC_POINTS,
    BodyGeometry,
)

# Version 1 remains readable so the existing catalogue can be migrated garment
# by garment.  Version 2 is the relational garment format: body-space geometry
# must derive from semantic Points/body measurements; naked spatial offsets are
# rejected.  Ground/item presentations deliberately retain ordinary coordinates.
DRAWABLE_FORMAT_VERSION = 2
SUPPORTED_DRAWABLE_FORMAT_VERSIONS = frozenset({1, 2})
DRAWABLE_FILE_SUFFIX = ".bkdraw"
DRAWABLE_CONTEXTS = frozenset({"garment", "ground"})
DRAWABLE_VARIANTS = ("compact", "detailed")
PAINT_ROLES = frozenset({"fill", "edge", "shade", "outline"})
CONDITION_SOURCES = frozenset({"detail", "material", "pattern"})

# ---------- Public language vocabulary ----------
# These are the frozen, bare Point names visible to v2 authors.  Component
# values exist only behind evaluator keys that cannot be written as identifiers;
# v2 authors create scalar names explicitly by destructuring a Point.
GARMENT_POINT_NAMES = frozenset(SEMANTIC_POINTS)

# Measurements are cached shorthand only.  Every one is calculated from body
# points when a DrawableRenderContext is built; none is an independent body fact.
GARMENT_MEASURE_SYMBOLS = frozenset({
    "tile_width",
    "tile_height",
    "body_height",
    "head_width",
    "head_height",
    "neck_width",
    "shoulder_width",
    "armpit_width",
    "waist_width",
    "hip_width",
    "torso_height",
    "elbow_width_left",
    "elbow_width_right",
    "wrist_width_left",
    "wrist_width_right",
    "thigh_width_left",
    "thigh_width_right",
    "knee_width_left",
    "knee_width_right",
    "ankle_width_left",
    "ankle_width_right",
    "arm_length_left",
    "arm_length_right",
    "leg_length_left",
    "leg_length_right",
})

# v1 garments already use these names heavily.  Keep them as derived aliases so
# old catalogue content continues to resolve while v2 clothing moves to anchors.
GARMENT_LEGACY_SYMBOLS = frozenset({
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
    "left_foot_x",
    "right_foot_x",
    "left_hand_x",
    "right_hand_x",
    "hand_y",
    "head_y",
    "head_half",
    "head_top_y",
    "left_ear_x",
    "right_ear_x",
    "ear_y",
})

# ``GARMENT_SYMBOLS`` retains its historical meaning for v1 callers and tools.
# v2 validation uses GARMENT_POINT_NAMES and GARMENT_MEASURE_SYMBOLS separately.
GARMENT_SYMBOLS = GARMENT_LEGACY_SYMBOLS
GROUND_SYMBOLS = frozenset({"mid", "left", "right", "top", "bottom"})
SCALAR_HELPERS = frozenset({"distance", "x_distance", "y_distance"})
POINT_HELPERS = frozenset({"between"})


def _point_component_symbol(name: str, axis: str) -> str:
    """Return an evaluator-only key that cannot collide with DSL identifiers."""

    return f"@point:{name}:{axis}"

MAX_FILE_BYTES = 256 * 1024
MAX_DRAWABLES_PER_FILE = 256
MAX_SHAPES_PER_VARIANT = 256
MAX_POINTS_PER_SHAPE = 128
MAX_LETS_PER_SCOPE = 128
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TOKEN_RE = re.compile(
    r"(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<identifier>[a-z][a-z0-9_]*)"
    r"|(?P<operator>[+\-*/(),])"
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


# ---------- Expression AST ----------
class ExprNode:
    def evaluate(self, symbols: Mapping[str, float]) -> float:
        raise NotImplementedError

    def symbols(self) -> frozenset[str]:
        raise NotImplementedError

    def serialize(self) -> str:
        raise NotImplementedError

    def point_symbols(self) -> frozenset[str]:
        return frozenset()


class NumberNode(ExprNode):
    __slots__ = ("value",)

    def __init__(self, value: float):
        self.value = float(value)

    def evaluate(self, symbols: Mapping[str, float]) -> float:
        return self.value

    def symbols(self) -> frozenset[str]:
        return frozenset()

    def serialize(self) -> str:
        return _format_number(self.value)


class SymbolNode(ExprNode):
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = str(name)

    def evaluate(self, symbols: Mapping[str, float]) -> float:
        if self.name not in symbols:
            raise DrawableError(f"unknown symbol {self.name!r}")
        return symbols[self.name]

    def symbols(self) -> frozenset[str]:
        return frozenset({self.name})

    def serialize(self) -> str:
        return self.name


class BinOpNode(ExprNode):
    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: ExprNode, right: ExprNode):
        self.op = str(op)
        self.left = left
        self.right = right

    def evaluate(self, symbols: Mapping[str, float]) -> float:
        l = self.left.evaluate(symbols)
        r = self.right.evaluate(symbols)
        if self.op == "+":
            return l + r
        if self.op == "-":
            return l - r
        if self.op == "*":
            return l * r
        if self.op == "/":
            return l / r
        raise DrawableError(f"unknown operator {self.op!r}")

    def symbols(self) -> frozenset[str]:
        return self.left.symbols() | self.right.symbols()

    def serialize(self) -> str:
        left = self.left.serialize()
        right = self.right.serialize()
        return f"({left} {self.op} {right})"

    def point_symbols(self) -> frozenset[str]:
        return self.left.point_symbols() | self.right.point_symbols()


class PointExpression:
    """A v2 Point expression; resolution still produces an ordinary pair."""

    location: SourceLocation

    def evaluate(self, symbols: Mapping[str, float]) -> tuple[float, float]:
        raise NotImplementedError

    @property
    def symbols(self) -> frozenset[str]:
        raise NotImplementedError

    @property
    def point_symbols(self) -> frozenset[str]:
        raise NotImplementedError

    def serialize(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class PointReference(PointExpression):
    name: str
    location: SourceLocation

    def evaluate(self, symbols: Mapping[str, float]) -> tuple[float, float]:
        try:
            return (
                float(symbols[_point_component_symbol(self.name, "x")]),
                float(symbols[_point_component_symbol(self.name, "y")]),
            )
        except KeyError as exc:
            raise DrawableError(f"unknown Point {self.name!r}", self.location) from exc

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset({self.name})

    @property
    def point_symbols(self) -> frozenset[str]:
        return self.symbols

    def serialize(self) -> str:
        return self.name


@dataclass(frozen=True)
class CoordinatePoint(PointExpression):
    x: "Expression"
    y: "Expression"
    location: SourceLocation

    def evaluate(self, symbols: Mapping[str, float]) -> tuple[float, float]:
        return self.x.evaluate(symbols), self.y.evaluate(symbols)

    @property
    def symbols(self) -> frozenset[str]:
        return self.x.symbols | self.y.symbols

    @property
    def point_symbols(self) -> frozenset[str]:
        return self.x.point_symbols | self.y.point_symbols

    def serialize(self) -> str:
        return f"{self.x.root.serialize()}, {self.y.root.serialize()}"


@dataclass(frozen=True)
class BetweenPoint(PointExpression):
    start: PointExpression
    finish: PointExpression
    ratio: "Expression"
    location: SourceLocation

    def evaluate(self, symbols: Mapping[str, float]) -> tuple[float, float]:
        ax, ay = self.start.evaluate(symbols)
        bx, by = self.finish.evaluate(symbols)
        ratio = self.ratio.evaluate(symbols)
        return ax + (bx - ax) * ratio, ay + (by - ay) * ratio

    @property
    def symbols(self) -> frozenset[str]:
        return self.start.symbols | self.finish.symbols | self.ratio.symbols

    @property
    def point_symbols(self) -> frozenset[str]:
        return (
            self.start.point_symbols
            | self.finish.point_symbols
            | self.ratio.point_symbols
        )

    def serialize(self) -> str:
        return (
            f"between({self.start.serialize()}, {self.finish.serialize()}, "
            f"{self.ratio.root.serialize()})"
        )


class ScalarFunctionNode(ExprNode):
    __slots__ = ("name", "first", "second")

    def __init__(self, name: str, first: PointExpression, second: PointExpression):
        self.name = str(name)
        self.first = first
        self.second = second

    def evaluate(self, symbols: Mapping[str, float]) -> float:
        ax, ay = self.first.evaluate(symbols)
        bx, by = self.second.evaluate(symbols)
        if self.name == "distance":
            return math.hypot(bx - ax, by - ay)
        if self.name == "x_distance":
            return abs(bx - ax)
        if self.name == "y_distance":
            return abs(by - ay)
        raise DrawableError(f"unknown Scalar helper {self.name!r}")

    def symbols(self) -> frozenset[str]:
        return self.first.symbols | self.second.symbols

    def point_symbols(self) -> frozenset[str]:
        return self.first.point_symbols | self.second.point_symbols

    def serialize(self) -> str:
        return f"{self.name}({self.first.serialize()}, {self.second.serialize()})"


@dataclass(frozen=True)
class Expression:
    root: ExprNode
    location: SourceLocation

    @property
    def symbols(self) -> frozenset[str]:
        return self.root.symbols()

    @property
    def point_symbols(self) -> frozenset[str]:
        return self.root.point_symbols()

    @property
    def scalar_symbols(self) -> frozenset[str]:
        return self.symbols - self.point_symbols

    def evaluate(self, symbols: Mapping[str, float]) -> float:
        try:
            value = float(self.root.evaluate(symbols))
        except ZeroDivisionError as exc:
            raise DrawableError("division by zero in expression", self.location) from exc
        if not math.isfinite(value):
            raise DrawableError("expression did not resolve to a finite number", self.location)
        return value


# ---------- Parsing helpers ----------
def _format_number(value: float) -> str:
    value = float(value)
    if value == 0:
        return "0"
    if value.is_integer():
        return str(int(value))
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _tokenise(text: str, location: SourceLocation) -> list[tuple[str, str, int]]:
    source = str(text)
    tokens: list[tuple[str, str, int]] = []
    cursor = 0
    for match in _TOKEN_RE.finditer(source):
        skipped = source[cursor:match.start()]
        if skipped.strip():
            bad_at = cursor + next(
                (index for index, char in enumerate(skipped) if not char.isspace()),
                0,
            )
            raise DrawableError(
                f"invalid expression character {source[bad_at]!r}",
                SourceLocation(location.source, location.line, location.column + bad_at),
            )
        kind = match.lastgroup
        value = match.group()
        tokens.append((kind, value, match.start()))
        cursor = match.end()
    tail = source[cursor:]
    if tail.strip():
        bad_at = cursor + next(
            (index for index, char in enumerate(tail) if not char.isspace()),
            0,
        )
        raise DrawableError(
            f"invalid expression character {source[bad_at]!r}",
            SourceLocation(location.source, location.line, location.column + bad_at),
        )
    if not tokens:
        raise DrawableError("empty expression", location)
    return tokens


class _ExpressionParser:
    """Small typed-expression parser shared by Scalar and Point contexts."""

    def __init__(self, text: str, location: SourceLocation):
        self.location = location
        self.tokens = _tokenise(text, location)
        self.pos = 0

    def peek(self, offset: int = 0):
        index = self.pos + int(offset)
        return self.tokens[index] if 0 <= index < len(self.tokens) else None

    def token_location(self, token) -> SourceLocation:
        return SourceLocation(
            self.location.source,
            self.location.line,
            self.location.column + int(token[2]),
        )

    def consume(self, expected_type=None, expected_value=None):
        token = self.peek()
        if token is None:
            raise DrawableError("unexpected end of expression", self.location)
        if expected_type is not None and token[0] != expected_type:
            raise DrawableError(
                f"expected {expected_type}, got {token[0]}",
                self.token_location(token),
            )
        if expected_value is not None and token[1] != expected_value:
            raise DrawableError(
                f"expected {expected_value!r}, got {token[1]!r}",
                self.token_location(token),
            )
        self.pos += 1
        return token

    def scalar(self, *, complete: bool = True) -> Expression:
        root = self._addsub()
        if complete and self.peek() is not None:
            token = self.peek()
            raise DrawableError(
                f"extra token {token[1]!r} after Scalar expression",
                self.token_location(token),
            )
        return Expression(root, self.location)

    def point(self, *, complete: bool = True) -> PointExpression:
        if self._has_top_level_comma():
            x = self.scalar(complete=False)
            self.consume("operator", ",")
            y_location = self.token_location(self.peek()) if self.peek() else self.location
            y_root = self._addsub()
            y = Expression(y_root, y_location)
            result: PointExpression = CoordinatePoint(x, y, self.location)
        else:
            result = self._point_atom()
        if complete and self.peek() is not None:
            token = self.peek()
            raise DrawableError(
                f"extra token {token[1]!r} after Point expression",
                self.token_location(token),
            )
        return result

    def _has_top_level_comma(self) -> bool:
        depth = 0
        for kind, value, _offset in self.tokens[self.pos :]:
            if kind != "operator":
                continue
            if value == "(":
                depth += 1
            elif value == ")":
                depth -= 1
            elif value == "," and depth == 0:
                return True
        return False

    def _addsub(self) -> ExprNode:
        node = self._muldiv()
        while True:
            token = self.peek()
            if token and token[0] == "operator" and token[1] in ("+", "-"):
                self.consume()
                node = BinOpNode(token[1], node, self._muldiv())
                continue
            return node

    def _muldiv(self) -> ExprNode:
        node = self._factor()
        while True:
            token = self.peek()
            if token and token[0] == "operator" and token[1] in ("*", "/"):
                self.consume()
                node = BinOpNode(token[1], node, self._factor())
                continue
            return node

    def _factor(self) -> ExprNode:
        token = self.peek()
        if token is None:
            raise DrawableError("expected Scalar value", self.location)
        if token[0] == "number":
            self.consume()
            return NumberNode(token[1])
        if token[0] == "identifier":
            name = self.consume()[1]
            if self.peek() and self.peek()[0] == "operator" and self.peek()[1] == "(":
                if name not in SCALAR_HELPERS:
                    raise DrawableError(
                        f"unknown Scalar helper {name!r}",
                        self.token_location(token),
                    )
                self.consume("operator", "(")
                first = self._point_atom()
                self.consume("operator", ",")
                second = self._point_atom()
                self.consume("operator", ")")
                return ScalarFunctionNode(name, first, second)
            return SymbolNode(name)
        if token[0] == "operator" and token[1] == "-":
            self.consume()
            return BinOpNode("*", NumberNode(-1.0), self._factor())
        if token[0] == "operator" and token[1] == "(":
            self.consume()
            node = self._addsub()
            self.consume("operator", ")")
            return node
        raise DrawableError(
            f"unexpected token {token[1]!r} in Scalar expression",
            self.token_location(token),
        )

    def _point_atom(self) -> PointExpression:
        token = self.peek()
        if token is None or token[0] != "identifier":
            location = self.token_location(token) if token else self.location
            raise DrawableError("expected a Point name or between(...) expression", location)
        name = self.consume("identifier")[1]
        point_location = self.token_location(token)
        if not (self.peek() and self.peek()[0] == "operator" and self.peek()[1] == "("):
            return PointReference(name, point_location)
        if name not in POINT_HELPERS:
            raise DrawableError(f"unknown Point helper {name!r}", point_location)
        self.consume("operator", "(")
        start = self._point_atom()
        self.consume("operator", ",")
        finish = self._point_atom()
        self.consume("operator", ",")
        ratio_location = self.token_location(self.peek()) if self.peek() else point_location
        ratio = Expression(self._addsub(), ratio_location)
        self.consume("operator", ")")
        return BetweenPoint(start, finish, ratio, point_location)


def parse_expression(text: str, location: SourceLocation) -> Expression:
    return _ExpressionParser(text, location).scalar()


def parse_point_expression(text: str, location: SourceLocation) -> PointExpression:
    return _ExpressionParser(text, location).point()


# ---------- Validation ----------
_SCALAR_RATIO = "ratio"
_SCALAR_LENGTH = "length"
_SCALAR_COORD_X = "x-coordinate"
_SCALAR_COORD_Y = "y-coordinate"
_SCALAR_FREE = "number"


def _validate_expression_references(
    expression: Expression,
    scalar_symbols: set[str],
    point_symbols: set[str],
) -> None:
    unknown_scalars = sorted(expression.scalar_symbols - scalar_symbols)
    if unknown_scalars:
        name = unknown_scalars[0]
        if name in point_symbols:
            raise DrawableError(
                f"Point {name!r} cannot be used where a Scalar is required",
                expression.location,
            )
        raise DrawableError(f"unknown Scalar {name!r}", expression.location)
    unknown_points = sorted(expression.point_symbols - point_symbols)
    if unknown_points:
        name = unknown_points[0]
        if name in scalar_symbols:
            raise DrawableError(
                f"Scalar {name!r} cannot be used where a Point is required",
                expression.location,
            )
        raise DrawableError(f"unknown Point {name!r}", expression.location)


def _expression_kind(
    node: ExprNode,
    symbol_kinds: Mapping[str, str],
    location: SourceLocation,
) -> str:
    """Infer the physical kind of a v2 garment Scalar expression."""

    if isinstance(node, NumberNode):
        return _SCALAR_RATIO
    if isinstance(node, SymbolNode):
        try:
            return symbol_kinds[node.name]
        except KeyError as exc:
            raise DrawableError(f"unknown Scalar {node.name!r}", location) from exc
    if isinstance(node, ScalarFunctionNode):
        return _SCALAR_LENGTH
    if not isinstance(node, BinOpNode):
        raise DrawableError("unsupported expression node", location)

    left_kind = _expression_kind(node.left, symbol_kinds, location)
    right_kind = _expression_kind(node.right, symbol_kinds, location)

    if node.op == "+":
        if left_kind == right_kind and left_kind in {_SCALAR_RATIO, _SCALAR_LENGTH}:
            return left_kind
        if left_kind in {_SCALAR_COORD_X, _SCALAR_COORD_Y} and right_kind == _SCALAR_LENGTH:
            return left_kind
        if left_kind == _SCALAR_LENGTH and right_kind in {_SCALAR_COORD_X, _SCALAR_COORD_Y}:
            return right_kind
        raise DrawableError(
            f"cannot add {left_kind} and {right_kind}; a literal such as 1 is a ratio, not a length",
            location,
        )

    if node.op == "-":
        if left_kind == right_kind and left_kind in {_SCALAR_RATIO, _SCALAR_LENGTH}:
            return left_kind
        if left_kind == right_kind and left_kind in {_SCALAR_COORD_X, _SCALAR_COORD_Y}:
            return _SCALAR_LENGTH
        if left_kind in {_SCALAR_COORD_X, _SCALAR_COORD_Y} and right_kind == _SCALAR_LENGTH:
            return left_kind
        raise DrawableError(
            f"cannot subtract {right_kind} from {left_kind}; a literal such as 1 is a ratio, not a length",
            location,
        )

    if node.op == "*":
        if left_kind == right_kind == _SCALAR_RATIO:
            return _SCALAR_RATIO
        if left_kind == _SCALAR_LENGTH and right_kind == _SCALAR_RATIO:
            return _SCALAR_LENGTH
        if left_kind == _SCALAR_RATIO and right_kind == _SCALAR_LENGTH:
            return _SCALAR_LENGTH
        raise DrawableError(
            f"cannot multiply {left_kind} by {right_kind}; only ratios may scale lengths",
            location,
        )

    if node.op == "/":
        if left_kind == right_kind == _SCALAR_RATIO:
            return _SCALAR_RATIO
        if left_kind == _SCALAR_LENGTH and right_kind == _SCALAR_RATIO:
            return _SCALAR_LENGTH
        if left_kind == right_kind == _SCALAR_LENGTH:
            return _SCALAR_RATIO
        raise DrawableError(
            f"cannot divide {left_kind} by {right_kind}; coordinates cannot be scaled around the tile origin",
            location,
        )

    raise DrawableError(f"unknown operator {node.op!r}", location)


def _validate_scalar_expression(
    expression: Expression,
    scalar_symbols: set[str],
    symbol_kinds: Mapping[str, str],
    point_symbols: set[str],
    *,
    strict: bool,
    expected: str | None = None,
) -> str:
    _validate_expression_references(expression, scalar_symbols, point_symbols)
    if not strict:
        return _SCALAR_FREE
    kind = _expression_kind(expression.root, symbol_kinds, expression.location)
    if expected is not None and kind != expected:
        raise DrawableError(
            f"expected {expected}, got {kind}",
            expression.location,
        )
    return kind


def _validate_point_expression(
    point: PointExpression,
    scalar_symbols: set[str],
    symbol_kinds: Mapping[str, str],
    point_symbols: set[str],
    *,
    strict: bool,
) -> None:
    unknown_scalars = sorted((point.symbols - point.point_symbols) - scalar_symbols)
    if unknown_scalars:
        name = unknown_scalars[0]
        if name in point_symbols:
            raise DrawableError(
                f"Point {name!r} cannot be used where a Scalar is required",
                point.location,
            )
        raise DrawableError(f"unknown Scalar {name!r}", point.location)
    unknown_points = sorted(point.point_symbols - point_symbols)
    if unknown_points:
        name = unknown_points[0]
        if name in scalar_symbols:
            raise DrawableError(
                f"Scalar {name!r} cannot be used where a Point is required",
                point.location,
            )
        raise DrawableError(f"unknown Point {name!r}", point.location)

    if isinstance(point, CoordinatePoint):
        _validate_scalar_expression(
            point.x,
            scalar_symbols,
            symbol_kinds,
            point_symbols,
            strict=strict,
            expected=_SCALAR_COORD_X if strict else None,
        )
        _validate_scalar_expression(
            point.y,
            scalar_symbols,
            symbol_kinds,
            point_symbols,
            strict=strict,
            expected=_SCALAR_COORD_Y if strict else None,
        )
    elif isinstance(point, BetweenPoint):
        _validate_point_expression(
            point.start,
            scalar_symbols,
            symbol_kinds,
            point_symbols,
            strict=strict,
        )
        _validate_point_expression(
            point.finish,
            scalar_symbols,
            symbol_kinds,
            point_symbols,
            strict=strict,
        )
        _validate_scalar_expression(
            point.ratio,
            scalar_symbols,
            symbol_kinds,
            point_symbols,
            strict=strict,
            expected=_SCALAR_RATIO if strict else None,
        )


def _validate_style_expression(
    expression: Expression,
    scalar_symbols: set[str],
    symbol_kinds: Mapping[str, str],
    point_symbols: set[str],
    *,
    strict: bool,
) -> None:
    """Literal renderer thickness is legal; coordinates are never thickness."""

    _validate_expression_references(expression, scalar_symbols, point_symbols)
    if not strict:
        return
    kind = _expression_kind(expression.root, symbol_kinds, expression.location)
    if kind not in {_SCALAR_RATIO, _SCALAR_LENGTH}:
        raise DrawableError(
            f"renderer width requires a literal ratio or length, got {kind}",
            expression.location,
        )


def _validate_bindings(
    bindings: Iterable[ValueBinding],
    scalar_symbols: set[str],
    symbol_kinds: Mapping[str, str],
    point_symbols: set[str],
    *,
    strict: bool,
    typed: bool,
) -> tuple[set[str], dict[str, str], set[str]]:
    scalars = set(scalar_symbols)
    kinds = dict(symbol_kinds)
    points = set(point_symbols)

    def reserve(name: str, location: SourceLocation) -> None:
        if name in scalars or name in points or name in GARMENT_POINT_NAMES:
            raise DrawableError(f"duplicate or reserved name {name!r}", location)

    for binding in bindings:
        if isinstance(binding, PointBinding):
            if not typed:
                raise DrawableError("point bindings require bakerrrr-drawable 2", binding.location)
            reserve(binding.name, binding.location)
            _validate_point_expression(
                binding.expression,
                scalars,
                kinds,
                points,
                strict=strict,
            )
            points.add(binding.name)
            continue

        if isinstance(binding, DestructureBinding):
            if not typed:
                raise DrawableError("Point destructuring requires bakerrrr-drawable 2", binding.location)
            reserve(binding.x_name, binding.location)
            reserve(binding.y_name, binding.location)
            if binding.x_name == binding.y_name:
                raise DrawableError("Point destructuring requires two distinct names", binding.location)
            _validate_point_expression(
                binding.expression,
                scalars,
                kinds,
                points,
                strict=strict,
            )
            scalars.update((binding.x_name, binding.y_name))
            kinds[binding.x_name] = _SCALAR_COORD_X if strict else _SCALAR_FREE
            kinds[binding.y_name] = _SCALAR_COORD_Y if strict else _SCALAR_FREE
            continue

        reserve(binding.name, binding.location)
        kind = _validate_scalar_expression(
            binding.expression,
            scalars,
            kinds,
            points,
            strict=strict,
        )
        scalars.add(binding.name)
        kinds[binding.name] = kind
    return scalars, kinds, points


def _validate_nodes(
    nodes: Iterable[DrawableNode],
    *,
    scalar_symbols: set[str],
    symbol_kinds: Mapping[str, str],
    point_symbols: set[str],
    paints: set[str],
    all_shape_ids: set[str],
    available_sources: set[str],
    strict: bool,
) -> None:
    for node in nodes:
        if isinstance(node, ShapeNode):
            if node.shape_id in all_shape_ids:
                raise DrawableError(f"duplicate shape id {node.shape_id!r}", node.location)
            if node.paint not in paints:
                raise DrawableError(f"unknown paint {node.paint!r}", node.location)
            if node.outline_paint is not None and node.outline_paint not in paints:
                raise DrawableError(f"unknown outline paint {node.outline_paint!r}", node.location)

            for point in node.points:
                _validate_point_expression(
                    point,
                    scalar_symbols,
                    symbol_kinds,
                    point_symbols,
                    strict=strict,
                )

            scalar_fields = (
                (node.x, _SCALAR_COORD_X),
                (node.y, _SCALAR_COORD_Y),
                (node.width_value, _SCALAR_LENGTH),
                (node.height_value, _SCALAR_LENGTH),
                (node.end_width, _SCALAR_LENGTH),
                (node.radius, _SCALAR_LENGTH),
            )
            for expression, expected in scalar_fields:
                if expression is None:
                    continue
                _validate_scalar_expression(
                    expression,
                    scalar_symbols,
                    symbol_kinds,
                    point_symbols,
                    strict=strict,
                    expected=expected if strict else None,
                )
            for expression in (node.stroke_width, node.outline_width):
                if expression is None:
                    continue
                _validate_style_expression(
                    expression,
                    scalar_symbols,
                    symbol_kinds,
                    point_symbols,
                    strict=strict,
                )

            if len(node.points) > MAX_POINTS_PER_SHAPE:
                raise DrawableError(
                    f"shape exceeds {MAX_POINTS_PER_SHAPE} points",
                    node.location,
                )
            all_shape_ids.add(node.shape_id)
            available_sources.add(node.shape_id)
            continue

        if isinstance(node, MirrorNode):
            if node.shape_id in all_shape_ids:
                raise DrawableError(f"duplicate shape id {node.shape_id!r}", node.location)
            if node.source_shape_id not in available_sources:
                raise DrawableError(
                    f"mirror source {node.source_shape_id!r} is not available here",
                    node.location,
                )
            if node.axis is not None:
                _validate_scalar_expression(
                    node.axis,
                    scalar_symbols,
                    symbol_kinds,
                    point_symbols,
                    strict=strict,
                    expected=_SCALAR_COORD_X if strict else None,
                )
            all_shape_ids.add(node.shape_id)
            available_sources.add(node.shape_id)
            continue

        branch_sources = set(available_sources)
        _validate_nodes(
            node.nodes,
            scalar_symbols=scalar_symbols,
            symbol_kinds=symbol_kinds,
            point_symbols=point_symbols,
            paints=paints,
            all_shape_ids=all_shape_ids,
            available_sources=branch_sources,
            strict=strict,
        )


def _context_symbols(version: int, context: str, location: SourceLocation) -> set[str]:
    if context == "garment" and int(version) >= 2:
        return set(GARMENT_MEASURE_SYMBOLS)
    if context == "garment":
        return set(GARMENT_LEGACY_SYMBOLS)
    if context == "ground":
        return set(GROUND_SYMBOLS)
    raise DrawableError(f"unknown context {context!r}", location)


def _context_symbol_kinds(version: int, context: str, location: SourceLocation) -> dict[str, str]:
    if context == "garment" and int(version) >= 2:
        return {symbol: _SCALAR_LENGTH for symbol in GARMENT_MEASURE_SYMBOLS}
    if context == "garment":
        return {symbol: _SCALAR_FREE for symbol in GARMENT_LEGACY_SYMBOLS}
    if context == "ground":
        return {symbol: _SCALAR_FREE for symbol in GROUND_SYMBOLS}
    raise DrawableError(f"unknown context {context!r}", location)


def _context_points(version: int, context: str) -> set[str]:
    if int(version) >= 2 and context == "garment":
        return set(GARMENT_POINT_NAMES)
    return set()


def _validate_presentation(
    *,
    version: int,
    context: str,
    paints_authored: tuple[PaintAlias, ...],
    lets: tuple[ValueBinding, ...],
    variants: tuple[DrawableVariant, ...],
    location: SourceLocation,
) -> None:
    base_symbols = _context_symbols(version, context, location)
    base_kinds = _context_symbol_kinds(version, context, location)
    base_points = _context_points(version, context)
    strict = int(version) >= 2 and context == "garment"
    typed = int(version) >= 2
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
    shared_symbols, shared_kinds, shared_points = _validate_bindings(
        lets,
        base_symbols,
        base_kinds,
        base_points,
        strict=strict,
        typed=typed,
    )

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
        symbols, symbol_kinds, points = _validate_bindings(
            variant.lets,
            shared_symbols,
            shared_kinds,
            shared_points,
            strict=strict,
            typed=typed,
        )
        layer_names = set()
        all_shape_ids: set[str] = set()
        available_sources: set[str] = set()
        for layer in variant.layers:
            if layer.name in layer_names:
                raise DrawableError(f"duplicate layer {layer.name!r}", layer.location)
            layer_names.add(layer.name)
            _validate_nodes(
                layer.nodes,
                scalar_symbols=symbols,
                symbol_kinds=symbol_kinds,
                point_symbols=points,
                paints=paints,
                all_shape_ids=all_shape_ids,
                available_sources=available_sources,
                strict=strict,
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


@dataclass(frozen=True)
class ScalarBinding:
    name: str
    expression: Expression
    location: SourceLocation


@dataclass(frozen=True)
class PointBinding:
    name: str
    expression: PointExpression
    location: SourceLocation


@dataclass(frozen=True)
class DestructureBinding:
    x_name: str
    y_name: str
    expression: PointExpression
    location: SourceLocation


ValueBinding = ScalarBinding | PointBinding | DestructureBinding


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
    end_width: Expression | None = None
    radius: Expression | None = None
    stroke_width: Expression | None = None
    outline_paint: str | None = None
    outline_width: Expression | None = None
    closed: bool = False


@dataclass(frozen=True)
class MirrorNode:
    source_shape_id: str
    shape_id: str
    axis: Expression | None
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
            (
                presentation
                for presentation in self.presentations
                if presentation.context == requested
            ),
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
        geometry: BodyGeometry | None = None,
        *,
        shoulder: float | None = None,
        hip: float | None = None,
        waist: float | None = None,
        basewear_hip: float | None = None,
        shoulder_y: float | None = None,
        hip_y: float | None = None,
        foot_y: float | None = None,
        mid: float = 8.0,
        left_foot_x: float | None = None,
        right_foot_x: float | None = None,
        left_hand_x: float | None = None,
        right_hand_x: float | None = None,
        hand_y: float | None = None,
        head_y: float | None = None,
        head_half: float | None = None,
        head_top_y: float | None = None,
        left_ear_x: float | None = None,
        right_ear_x: float | None = None,
        ear_y: float | None = None,
        material: str = "",
        detail: str = "",
        pattern: str = "",
    ) -> "DrawableRenderContext":
        """Create a garment context from one authoritative BodyGeometry.

        Runtime and editor callers pass ``geometry``.  The historical keyword
        form remains intact for v1 tests, external content tools, and Python
        fallback clothing during migration.
        """

        conditions = {
            "material": condition_tokens(material),
            "detail": condition_tokens(detail),
            "pattern": condition_tokens(pattern),
        }

        if geometry is None:
            required = {
                "shoulder": shoulder,
                "hip": hip,
                "waist": waist,
                "basewear_hip": basewear_hip,
                "shoulder_y": shoulder_y,
                "hip_y": hip_y,
                "foot_y": foot_y,
            }
            missing = sorted(name for name, value in required.items() if value is None)
            if missing:
                raise TypeError(
                    "DrawableRenderContext.garment() requires a BodyGeometry or legacy "
                    f"keyword {missing[0]!r}"
                )
            resolved_mid = float(mid)
            resolved_hip = float(hip)
            resolved_head_half = float(head_half if head_half is not None else 2.0)
            resolved_head_y = float(
                head_y if head_y is not None else float(shoulder_y) - 3.0
            )
            symbols = {
                "mid": resolved_mid,
                "shoulder": float(shoulder),
                "hip": resolved_hip,
                "waist": float(waist),
                "basewear_hip": float(basewear_hip),
                "body_left": resolved_mid - resolved_hip,
                "body_right": resolved_mid + resolved_hip,
                "shoulder_y": float(shoulder_y),
                "hip_y": float(hip_y),
                "foot_y": float(foot_y),
                "left_foot_x": float(
                    left_foot_x if left_foot_x is not None else resolved_mid - 2.0
                ),
                "right_foot_x": float(
                    right_foot_x if right_foot_x is not None else resolved_mid + 2.0
                ),
                "left_hand_x": float(
                    left_hand_x
                    if left_hand_x is not None
                    else resolved_mid - resolved_hip - 2.0
                ),
                "right_hand_x": float(
                    right_hand_x
                    if right_hand_x is not None
                    else resolved_mid + resolved_hip + 2.0
                ),
                "hand_y": float(hand_y if hand_y is not None else float(hip_y) - 1.0),
                "head_y": resolved_head_y,
                "head_half": resolved_head_half,
                "head_top_y": float(
                    head_top_y
                    if head_top_y is not None
                    else resolved_head_y - resolved_head_half
                ),
                "left_ear_x": float(
                    left_ear_x
                    if left_ear_x is not None
                    else resolved_mid - resolved_head_half
                ),
                "right_ear_x": float(
                    right_ear_x
                    if right_ear_x is not None
                    else resolved_mid + resolved_head_half
                ),
                "ear_y": float(ear_y if ear_y is not None else resolved_head_y),
            }
            for name, value in symbols.items():
                if not math.isfinite(value):
                    raise DrawableError(f"garment context symbol {name!r} must be finite")
            return cls(
                context="garment",
                symbols=MappingProxyType(symbols),
                conditions=MappingProxyType(conditions),
            )

        if not isinstance(geometry, BodyGeometry):
            raise TypeError("geometry must be a BodyGeometry")

        symbols: dict[str, float] = {}

        def add_point(name: str, point) -> None:
            x, y = point
            symbols[_point_component_symbol(name, "x")] = float(x)
            symbols[_point_component_symbol(name, "y")] = float(y)

        for name, point in geometry.drawable_anchors.items():
            add_point(name, point)
        for name, point in geometry.internal_drawable_anchors.items():
            add_point(name, point)

        def point(name: str) -> tuple[float, float]:
            return (
                symbols[_point_component_symbol(name, "x")],
                symbols[_point_component_symbol(name, "y")],
            )

        def midpoint(name: str, first: str, second: str) -> None:
            ax, ay = point(first)
            bx, by = point(second)
            add_point(name, ((ax + bx) / 2.0, (ay + by) / 2.0))

        def distance(first: str, second: str) -> float:
            ax, ay = point(first)
            bx, by = point(second)
            return math.hypot(bx - ax, by - ay)

        midpoint("tile_center", "tile_left", "tile_right")
        midpoint("shoulder_center", "shoulder_left", "shoulder_right")
        midpoint("waist_center", "waist_left", "waist_right")
        midpoint("hip_center", "hip_left", "hip_right")
        midpoint("body_center", "crown", "ground")

        # Frame/body spans.
        symbols["tile_width"] = distance("tile_left", "tile_right")
        symbols["tile_height"] = distance("tile_top", "ground")
        symbols["body_height"] = distance("crown", "ground")
        symbols["head_width"] = distance("head_left", "head_right")
        symbols["head_height"] = distance("crown", "chin")
        symbols["neck_width"] = distance("neck_left", "neck_right")
        symbols["shoulder_width"] = distance("shoulder_left", "shoulder_right")
        symbols["armpit_width"] = distance("armpit_left", "armpit_right")
        symbols["waist_width"] = distance("waist_left", "waist_right")
        symbols["hip_width"] = distance("hip_left", "hip_right")
        symbols["torso_height"] = distance("shoulder_center", "hip_center")

        for joint in ("elbow", "wrist", "thigh", "knee", "ankle"):
            for side in ("left", "right"):
                symbols[f"{joint}_width_{side}"] = distance(
                    f"{joint}_inner_{side}",
                    f"{joint}_outer_{side}",
                )

        symbols["arm_length_left"] = (
            distance("shoulder_left", "elbow_center_left")
            + distance("elbow_center_left", "wrist_center_left")
        )
        symbols["arm_length_right"] = (
            distance("shoulder_right", "elbow_center_right")
            + distance("elbow_center_right", "wrist_center_right")
        )
        symbols["leg_length_left"] = (
            distance("thigh_center_left", "knee_center_left")
            + distance("knee_center_left", "ankle_center_left")
            + distance("ankle_center_left", "foot_center_left")
        )
        symbols["leg_length_right"] = (
            distance("thigh_center_right", "knee_center_right")
            + distance("knee_center_right", "ankle_center_right")
            + distance("ankle_center_right", "foot_center_right")
        )

        # Compatibility aliases for the existing v1 catalogue.  Even these are
        # derived from shared geometry.  One legacy logical unit is expressed as
        # 1/16 of the frame width rather than as an independent body constant.
        mid = point("tile_center")[0]
        shoulder = max(symbols["shoulder_width"], symbols["armpit_width"]) / 2.0
        hip = symbols["hip_width"] / 2.0
        waist = (
            min(shoulder, hip)
            if geometry.variant == "detailed" and geometry.presentation != "femme"
            else symbols["waist_width"] / 2.0
        )
        legacy_pixel = DRAWABLE_UNITS / float(geometry.px)
        legacy_basewear_inset = (
            max(1, int(round(float(geometry.px) / DRAWABLE_UNITS)))
            * legacy_pixel
        )
        symbols.update({
            "mid": mid,
            "shoulder": shoulder,
            "hip": hip,
            "waist": waist,
            "basewear_hip": max(legacy_pixel, hip - legacy_basewear_inset),
            "body_left": mid - hip,
            "body_right": mid + hip,
            "shoulder_y": point("shoulder_center")[1],
            "hip_y": point("crotch")[1],
            "foot_y": (point("foot_center_left")[1] + point("foot_center_right")[1]) / 2.0,
            "left_foot_x": point("foot_center_left")[0],
            "right_foot_x": point("foot_center_right")[0],
            "left_hand_x": point("wrist_center_left")[0],
            "right_hand_x": point("wrist_center_right")[0],
            "hand_y": (point("wrist_center_left")[1] + point("wrist_center_right")[1]) / 2.0,
            "head_y": point("head_center")[1],
            "head_half": symbols["head_width"] / 2.0,
            "head_top_y": point("crown")[1],
            "left_ear_x": point("head_left")[0],
            "right_ear_x": point("head_right")[0],
            "ear_y": (
                point("head_center")[1]
                if geometry.variant == "detailed"
                else float(
                    int(round(4.0 * float(geometry.px) / DRAWABLE_UNITS))
                )
                * legacy_pixel
            ),
        })

        missing = (GARMENT_LEGACY_SYMBOLS | GARMENT_MEASURE_SYMBOLS) - set(symbols)
        if missing:
            raise DrawableError(
                f"garment geometry did not provide symbol {sorted(missing)[0]!r}"
            )
        for name, value in symbols.items():
            if not math.isfinite(float(value)):
                raise DrawableError(f"garment context symbol {name!r} must be finite")

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
        """Create free-coordinate item/ground geometry.

        Ground art intentionally does *not* inherit the v2 garment provenance
        restrictions.  An item has legitimate reasons to say ``left + 3`` or
        simply ``w 6`` inside its own tile.
        """

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


# ---------- Parser ----------
class _DrawableParser:
    def __init__(self, text: str, source: str):
        self.source = str(source)
        self.lines = self._logical_lines(text)
        self.index = 0
        self.version = 1

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
            raise DrawableError("expected 'bakerrrr-drawable <1|2>' header", header.location)
        version = int(match.group(1))
        if version not in SUPPORTED_DRAWABLE_FORMAT_VERSIONS:
            supported = ", ".join(str(item) for item in sorted(SUPPORTED_DRAWABLE_FORMAT_VERSIONS))
            raise DrawableError(
                f"unsupported drawable format version {version}; expected one of {supported}",
                header.location,
            )
        self.version = version

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
            elif child.text.startswith("point "):
                lets.append(self.parse_point_binding())
            elif child.text.startswith("variant "):
                variants.append(self.parse_variant())
            elif child.text.startswith("presentation "):
                presentations.append(self.parse_presentation())
            else:
                raise DrawableError(
                    "drawable blocks accept paint, let, point, variant, or presentation statements",
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
            elif child.text.startswith("point "):
                lets.append(self.parse_point_binding())
            elif child.text.startswith("variant "):
                variants.append(self.parse_variant())
            else:
                raise DrawableError(
                    "presentation blocks accept paint, let, point, or variant statements",
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
        destructure = re.fullmatch(
            r"let\s+\(\s*([a-z][a-z0-9_]*)\s*,\s*([a-z][a-z0-9_]*)\s*\)\s*=\s*(.+)",
            line.text,
        )
        if destructure is not None:
            x_name = _validate_identifier(destructure.group(1), line.location, "let name")
            y_name = _validate_identifier(destructure.group(2), line.location, "let name")
            expression_text = destructure.group(3)
            expression = parse_point_expression(
                expression_text,
                SourceLocation(
                    line.location.source,
                    line.location.line,
                    line.location.column + line.text.index(expression_text),
                ),
            )
            return DestructureBinding(x_name, y_name, expression, line.location)

        match = re.fullmatch(r"let\s+([a-z][a-z0-9_]*)\s*=\s*(.+)", line.text)
        if match is None:
            raise DrawableError(
                "expected 'let <name> = <Scalar>' or 'let (<x>, <y>) = <Point>'",
                line.location,
            )
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
        return ScalarBinding(name, expression, line.location)

    def parse_point_binding(self) -> PointBinding:
        line = self.take()
        match = re.fullmatch(r"point\s+([a-z][a-z0-9_]*)\s*=\s*(.+)", line.text)
        if match is None:
            raise DrawableError("expected 'point <name> = <Point>'", line.location)
        name = _validate_identifier(match.group(1), line.location, "point name")
        expression_text = match.group(2)
        expression = parse_point_expression(
            expression_text,
            SourceLocation(
                line.location.source,
                line.location.line,
                line.location.column + line.text.index(expression_text),
            ),
        )
        return PointBinding(name, expression, line.location)

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
            elif child.text.startswith("point "):
                lets.append(self.parse_point_binding())
            elif child.text.startswith("layer "):
                layers.append(self.parse_layer())
            elif child.text.startswith("group "):
                groups.append(self.parse_named_shape_list("group"))
            elif child.text.startswith("surface "):
                surfaces.append(self.parse_named_shape_list("surface"))
            else:
                raise DrawableError(
                    "variant blocks accept let, point, layer, group, or surface statements",
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
            elif line.text.startswith("strip "):
                nodes.append(self.parse_strip())
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
        axis_text = match.group(2)
        shape_id = match.group(3)
        axis = parse_expression(axis_text, line.location) if axis_text else None
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
        tokens = body[len(prefix) :].split()
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

    def _parse_point_expression(
        self,
        text: str,
        location: SourceLocation,
        *,
        label: str = "point",
    ) -> PointExpression:
        """Parse ``x, y`` or a semantic point shorthand such as ``shoulder_left``.

        Bare point names are deliberately limited to the shared garment point
        vocabulary.  Ground/item art keeps its ordinary scalar-coordinate syntax.
        """

        try:
            return parse_point_expression(text, location)
        except DrawableError as exc:
            raise DrawableError(
                f"{label} must be '<x>, <y>', a Point name, or between(...): {exc.message}",
                exc.location or location,
            ) from exc

    def parse_strip(self) -> ShapeNode:
        """Parse a centered geometric strip with optional taper/flare.

        ``width`` is the full width at ``start``.  ``finish_width`` defaults to
        the same value; making it larger or smaller creates flare or taper.
        Unlike ``line``, this resolves to filled polygon geometry rather than a
        renderer stroke.
        """

        line = self.take()
        shape_id, paint, _, _ = self._parse_shape_header(
            line, "strip", allow_outline=False
        )
        self.require_child(line)
        fields = self.parse_fields(
            line.indent + 1,
            {"start", "finish", "width", "finish_width", "outline", "outline_width"},
        )
        for required in ("start", "finish", "width"):
            if required not in fields:
                raise DrawableError(f"strip requires field {required!r}", line.location)

        def parse_point_field(name: str) -> PointExpression:
            value, value_location = fields[name]
            return self._parse_point_expression(
                value,
                value_location,
                label=f"strip {name}",
            )

        outline_paint = None
        if "outline" in fields:
            outline_paint = _validate_identifier(
                fields["outline"][0], fields["outline"][1], "outline paint"
            )
        outline_width = (
            parse_expression(*fields["outline_width"])
            if "outline_width" in fields
            else None
        )
        if outline_paint is None and outline_width is not None:
            raise DrawableError("outline_width requires an outline paint", line.location)
        if outline_paint is not None and outline_width is None:
            raise DrawableError("strip outline requires outline_width", line.location)

        start_point = parse_point_field("start")
        finish_point = parse_point_field("finish")
        return ShapeNode(
            "strip",
            shape_id,
            paint,
            line.location,
            points=(start_point, finish_point),
            width_value=parse_expression(*fields["width"]),
            end_width=(
                parse_expression(*fields["finish_width"])
                if "finish_width" in fields
                else None
            ),
            outline_paint=outline_paint,
            outline_width=outline_width,
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
            points.append(self._parse_point_expression(line.text, line.location))
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
            outline_paint = _validate_identifier(
                fields["outline"][0], fields["outline"][1], "outline paint"
            )
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
        center_point = self._parse_point_expression(
            center_text,
            center_location,
            label="circle center",
        )
        outline_paint = None
        if "outline" in fields:
            outline_paint = _validate_identifier(
                fields["outline"][0], fields["outline"][1], "outline paint"
            )
        outline_width = parse_expression(*fields["width"]) if "width" in fields else None
        if outline_paint is None and outline_width is not None:
            raise DrawableError("outline width requires an outline paint", line.location)
        return ShapeNode(
            "circle",
            shape_id,
            paint,
            line.location,
            points=(center_point,),
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


# ---------- Public API ----------
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


def validate_document(document: DrawableDocument) -> None:
    drawable_ids = set()
    for drawable in document.drawables:
        if drawable.drawable_id in drawable_ids:
            raise DrawableError(
                f"duplicate drawable id {drawable.drawable_id!r}", drawable.location
            )
        drawable_ids.add(drawable.drawable_id)
        _validate_presentation(
            version=drawable.version,
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
                version=drawable.version,
                context=presentation.context,
                paints_authored=presentation.paints,
                lets=presentation.lets,
                variants=presentation.variants,
                location=presentation.location,
            )


# ---------- Resolution ----------
def _evaluate_bindings(bindings: Iterable[ValueBinding], symbols: dict[str, float]) -> None:
    for binding in bindings:
        if isinstance(binding, ScalarBinding):
            symbols[binding.name] = binding.expression.evaluate(symbols)
        elif isinstance(binding, PointBinding):
            x, y = binding.expression.evaluate(symbols)
            symbols[_point_component_symbol(binding.name, "x")] = x
            symbols[_point_component_symbol(binding.name, "y")] = y
        else:
            x, y = binding.expression.evaluate(symbols)
            symbols[binding.x_name] = x
            symbols[binding.y_name] = y


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
    points = tuple(point.evaluate(symbols) for point in node.points)
    box = None
    radius = node.radius.evaluate(symbols) if node.radius is not None else None
    resolved_kind = node.kind

    if node.kind in {"rect", "ellipse"}:
        x = node.x.evaluate(symbols) if node.x is not None else 0.0
        y = node.y.evaluate(symbols) if node.y is not None else 0.0
        width = node.width_value.evaluate(symbols) if node.width_value is not None else 0.0
        height = node.height_value.evaluate(symbols) if node.height_value is not None else 0.0
        if width < 0 or height < 0:
            raise DrawableError("rect/ellipse width and height must be non-negative", node.location)
        box = (x, y, width, height)
    elif node.kind == "circle":
        if len(points) != 1:
            raise DrawableError("circle requires one center Point", node.location)
        x, y = points[0]
        if radius is None or radius < 0:
            raise DrawableError("circle radius must be non-negative", node.location)
        points = ((x, y),)
    elif node.kind == "strip":
        if len(points) != 2 or node.width_value is None:
            raise DrawableError("strip requires start, finish, and width", node.location)
        start_point, finish_point = points
        start_width = node.width_value.evaluate(symbols)
        finish_width = (
            node.end_width.evaluate(symbols)
            if node.end_width is not None
            else start_width
        )
        if start_width < 0 or finish_width < 0:
            raise DrawableError("strip widths must be non-negative", node.location)
        dx = finish_point[0] - start_point[0]
        dy = finish_point[1] - start_point[1]
        magnitude = math.hypot(dx, dy)
        if magnitude <= 1.0e-9:
            raise DrawableError("strip start and finish must not be the same point", node.location)
        nx = -dy / magnitude
        ny = dx / magnitude
        start_half = start_width / 2.0
        finish_half = finish_width / 2.0
        points = (
            (start_point[0] + nx * start_half, start_point[1] + ny * start_half),
            (finish_point[0] + nx * finish_half, finish_point[1] + ny * finish_half),
            (finish_point[0] - nx * finish_half, finish_point[1] - ny * finish_half),
            (start_point[0] - nx * start_half, start_point[1] - ny * start_half),
        )
        resolved_kind = "polygon"

    stroke_width = node.stroke_width.evaluate(symbols) if node.stroke_width is not None else None
    outline_width = node.outline_width.evaluate(symbols) if node.outline_width is not None else None
    if stroke_width is not None and stroke_width < 0:
        raise DrawableError("line width must be non-negative", node.location)
    if outline_width is not None and outline_width < 0:
        raise DrawableError("outline width must be non-negative", node.location)
    return ResolvedShape(
        kind=resolved_kind,
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
                axis=(
                    node.axis.evaluate(symbols)
                    if node.axis is not None
                    else float(
                        symbols.get(
                            _point_component_symbol("tile_top", "x"),
                            symbols.get("mid", DRAWABLE_UNITS / 2.0),
                        )
                    )
                ),
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


# ---------- Serialization ----------
def serialize_expression(expression: Expression) -> str:
    return expression.root.serialize()


def _serialize_point(point: PointExpression) -> str:
    return point.serialize()


def _serialize_nodes(nodes: Iterable[DrawableNode], indent: int) -> list[str]:
    prefix = "    " * indent
    lines = []
    for node in nodes:
        if isinstance(node, ConditionalNode):
            lines.append(f"{prefix}when {node.source} has {node.token}:")
            lines.extend(_serialize_nodes(node.nodes, indent + 1))
            continue
        if isinstance(node, MirrorNode):
            across = (
                f" across {serialize_expression(node.axis)}"
                if node.axis is not None
                else ""
            )
            lines.append(f"{prefix}mirror {node.source_shape_id}{across} as {node.shape_id}")
            continue
        if node.kind == "polygon":
            outline = ""
            if node.outline_paint is not None and node.outline_width is not None:
                outline = f" outline {node.outline_paint} width {serialize_expression(node.outline_width)}"
            lines.append(f"{prefix}polygon {node.shape_id} {node.paint}{outline}:")
            for point in node.points:
                lines.append(f"{prefix}    {_serialize_point(point)}")
        elif node.kind == "line":
            closed = " closed" if node.closed else ""
            lines.append(
                f"{prefix}line {node.shape_id} {node.paint} width "
                f"{serialize_expression(node.stroke_width)}{closed}:"
            )
            for point in node.points:
                lines.append(f"{prefix}    {_serialize_point(point)}")
        elif node.kind == "strip":
            lines.append(f"{prefix}strip {node.shape_id} {node.paint}:")
            lines.append(f"{prefix}    start {_serialize_point(node.points[0])}")
            lines.append(f"{prefix}    finish {_serialize_point(node.points[1])}")
            lines.append(f"{prefix}    width {serialize_expression(node.width_value)}")
            if node.end_width is not None:
                lines.append(
                    f"{prefix}    finish_width {serialize_expression(node.end_width)}"
                )
            if node.outline_paint is not None:
                lines.append(f"{prefix}    outline {node.outline_paint}")
            if node.outline_width is not None:
                lines.append(
                    f"{prefix}    outline_width {serialize_expression(node.outline_width)}"
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
            lines.append(f"{prefix}    center {_serialize_point(node.points[0])}")
            lines.append(f"{prefix}    radius {serialize_expression(node.radius)}")
            if node.outline_paint is not None:
                lines.append(f"{prefix}    outline {node.outline_paint}")
            if node.outline_width is not None:
                lines.append(f"{prefix}    width {serialize_expression(node.outline_width)}")
    return lines


def _serialize_binding(binding: ValueBinding) -> str:
    if isinstance(binding, ScalarBinding):
        return f"let {binding.name} = {serialize_expression(binding.expression)}"
    if isinstance(binding, PointBinding):
        return f"point {binding.name} = {_serialize_point(binding.expression)}"
    return (
        f"let ({binding.x_name}, {binding.y_name}) = "
        f"{_serialize_point(binding.expression)}"
    )


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
        lines.append(f"{prefix}{_serialize_binding(binding)}")
    for variant in variants:
        lines.extend(("", f"{prefix}variant {variant.name}:"))
        variant_prefix = "    " * (indent + 1)
        for binding in variant.lets:
            lines.append(f"{variant_prefix}{_serialize_binding(binding)}")
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


# ---------- Catalog loading ----------
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
