"""Versioned semantic building-shell stamps shared by genesis and the editor."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable, Mapping


BUILDING_STAMP_FORMAT = "bakerrrr-building-stamp"
BUILDING_STAMP_VERSION = 1
BUILDING_STAMP_ROOT = Path(__file__).resolve().parents[1] / "game" / "building_stamps"
BUILDING_STAMP_MAX_BYTES = 256 * 1024
BUILDING_STAMP_MAX_SIDE = 31
BUILDING_STAMP_GLYPHS = frozenset({" ", "#", ".", "D", "W", "S", "F"})
WALKABLE_STAMP_GLYPHS = frozenset({".", "D", "S", "F"})
STAMP_SIDES = ("north", "east", "south", "west")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class BuildingStampError(ValueError):
    def __init__(self, message: str, *, source: str = "<memory>", path: str = ""):
        location = str(source)
        if path:
            location += f":{path}"
        super().__init__(f"{location}: {message}")
        self.message = str(message)
        self.source = str(source)
        self.path = str(path)


@dataclass(frozen=True)
class BuildingStampFloor:
    z: int
    shell: tuple[str, ...]
    zones: tuple[str, ...]


@dataclass(frozen=True)
class BuildingStampAnchor:
    anchor_id: str
    kind: str
    x: int
    y: int
    z: int
    service: str = ""


@dataclass(frozen=True)
class BuildingStamp:
    stamp_id: str
    width: int
    height: int
    exterior_classes: tuple[str, ...]
    clearance: int
    rotations: tuple[int, ...]
    reflect: bool
    entry: Mapping[str, object]
    zone_legend: Mapping[str, str]
    floors: tuple[BuildingStampFloor, ...]
    anchors: tuple[BuildingStampAnchor, ...]
    source: str

    def floor(self, z: int) -> BuildingStampFloor | None:
        return next((floor for floor in self.floors if floor.z == int(z)), None)


@dataclass(frozen=True)
class ResolvedStampFloor:
    z: int
    cells: Mapping[tuple[int, int], str]
    excluded: frozenset[tuple[int, int]]
    walls: frozenset[tuple[int, int]]
    walkable: frozenset[tuple[int, int]]
    apertures: tuple[Mapping[str, object], ...]
    zones: Mapping[tuple[int, int], str]


@dataclass(frozen=True)
class ResolvedBuildingStamp:
    stamp_id: str
    left: int
    right: int
    top: int
    bottom: int
    width: int
    height: int
    rotation: int
    frontage_side: str
    entry: Mapping[str, object]
    floors: Mapping[int, ResolvedStampFloor]
    anchors: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class BuildingStampCatalog:
    definitions: Mapping[str, BuildingStamp]
    sources: Mapping[str, str]
    files: tuple[str, ...]
    revision: str

    def get(self, stamp_id: object) -> BuildingStamp | None:
        return self.definitions.get(_normalize_id(stamp_id))

    def require(self, stamp_id: object) -> BuildingStamp:
        stamp = self.get(stamp_id)
        if stamp is None:
            raise BuildingStampError(f"unknown building stamp {stamp_id!r}")
        return stamp


def _normalize_id(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _require_id(value: object, *, source: str, path: str) -> str:
    value = _normalize_id(value)
    if not _ID_RE.fullmatch(value):
        raise BuildingStampError("expected identifier matching [a-z][a-z0-9_]*", source=source, path=path)
    return value


def _require_int(value: object, *, source: str, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise BuildingStampError("expected integer", source=source, path=path)
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise BuildingStampError("expected integer", source=source, path=path) from None
    if result < minimum or result > maximum:
        raise BuildingStampError(f"expected integer from {minimum} to {maximum}", source=source, path=path)
    return result


def _rows(value: object, *, width: int, height: int, source: str, path: str, allowed=None) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != height:
        raise BuildingStampError(f"expected exactly {height} rows", source=source, path=path)
    result = []
    for index, row in enumerate(value):
        if not isinstance(row, str) or len(row) != width:
            raise BuildingStampError(f"expected row width {width}", source=source, path=f"{path}[{index}]")
        if allowed is not None:
            unexpected = sorted(set(row) - set(allowed))
            if unexpected:
                raise BuildingStampError(f"unsupported glyph(s): {unexpected!r}", source=source, path=f"{path}[{index}]")
        result.append(row)
    return tuple(result)


def _connected_walkable(shell: tuple[str, ...]) -> bool:
    walkable = {
        (x, y)
        for y, row in enumerate(shell)
        for x, glyph in enumerate(row)
        if glyph in WALKABLE_STAMP_GLYPHS
    }
    if not walkable:
        return False
    start = next(iter(walkable))
    reached = {start}
    pending = [start]
    while pending:
        x, y = pending.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in walkable and neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    return reached == walkable


def parse_building_stamp_data(data: object, *, source: str = "<memory>") -> BuildingStamp:
    if not isinstance(data, dict):
        raise BuildingStampError("document root must be an object", source=source)
    if data.get("format") != BUILDING_STAMP_FORMAT:
        raise BuildingStampError(f"format must be {BUILDING_STAMP_FORMAT!r}", source=source, path="format")
    version = _require_int(data.get("version"), source=source, path="version", minimum=1, maximum=BUILDING_STAMP_VERSION)
    if version != BUILDING_STAMP_VERSION:
        raise BuildingStampError(f"unsupported version {version}", source=source, path="version")
    stamp_id = _require_id(data.get("id"), source=source, path="id")
    size = data.get("size")
    if not isinstance(size, dict):
        raise BuildingStampError("size must be an object", source=source, path="size")
    width = _require_int(size.get("width"), source=source, path="size.width", minimum=3, maximum=BUILDING_STAMP_MAX_SIDE)
    height = _require_int(size.get("height"), source=source, path="size.height", minimum=3, maximum=BUILDING_STAMP_MAX_SIDE)

    placement = data.get("placement", {})
    if not isinstance(placement, dict):
        raise BuildingStampError("placement must be an object", source=source, path="placement")
    exterior_classes_value = placement.get("exterior_classes", ["building"])
    if not isinstance(exterior_classes_value, list) or not exterior_classes_value:
        raise BuildingStampError("exterior_classes must be a non-empty list", source=source, path="placement.exterior_classes")
    exterior_classes = tuple(dict.fromkeys(
        _require_id(value, source=source, path="placement.exterior_classes")
        for value in exterior_classes_value
    ))
    clearance = _require_int(placement.get("clearance", 0), source=source, path="placement.clearance", minimum=0, maximum=8)
    rotations_value = placement.get("rotations", [0])
    if not isinstance(rotations_value, list) or not rotations_value:
        raise BuildingStampError("rotations must be a non-empty list", source=source, path="placement.rotations")
    rotations = tuple(dict.fromkeys(
        _require_int(value, source=source, path="placement.rotations", minimum=0, maximum=270)
        for value in rotations_value
    ))
    if any(rotation not in {0, 90, 180, 270} for rotation in rotations):
        raise BuildingStampError("rotations may contain only 0, 90, 180, and 270", source=source, path="placement.rotations")
    if 0 not in rotations:
        raise BuildingStampError("canonical south-facing rotation 0 is required", source=source, path="placement.rotations")
    reflect = placement.get("reflect", False)
    if not isinstance(reflect, bool):
        raise BuildingStampError("reflect must be true or false", source=source, path="placement.reflect")
    if reflect:
        raise BuildingStampError("reflection is reserved and unsupported in version 1", source=source, path="placement.reflect")

    legend_data = data.get("zone_legend", {})
    if not isinstance(legend_data, dict):
        raise BuildingStampError("zone_legend must be an object", source=source, path="zone_legend")
    zone_legend = {}
    for glyph, label in legend_data.items():
        if not isinstance(glyph, str) or len(glyph) != 1 or glyph == " ":
            raise BuildingStampError("zone keys must be one non-space character", source=source, path="zone_legend")
        zone_legend[glyph] = _require_id(label, source=source, path=f"zone_legend.{glyph}")

    floors_value = data.get("floors")
    if not isinstance(floors_value, list) or not floors_value:
        raise BuildingStampError("floors must be a non-empty list", source=source, path="floors")
    floors = []
    seen_z = set()
    stair_cells = {}
    for index, value in enumerate(floors_value):
        path = f"floors[{index}]"
        if not isinstance(value, dict):
            raise BuildingStampError("floor must be an object", source=source, path=path)
        z = _require_int(value.get("z"), source=source, path=f"{path}.z", minimum=-8, maximum=8)
        if z in seen_z:
            raise BuildingStampError(f"duplicate floor z {z}", source=source, path=f"{path}.z")
        seen_z.add(z)
        shell = _rows(value.get("shell"), width=width, height=height, source=source, path=f"{path}.shell", allowed=BUILDING_STAMP_GLYPHS)
        if not _connected_walkable(shell):
            raise BuildingStampError("walkable shell cells must form one connected component", source=source, path=f"{path}.shell")
        zones = _rows(value.get("zones", [" " * width for _ in range(height)]), width=width, height=height, source=source, path=f"{path}.zones")
        for y, row in enumerate(zones):
            for x, zone_glyph in enumerate(row):
                if zone_glyph == " ":
                    continue
                if zone_glyph not in zone_legend:
                    raise BuildingStampError(f"unknown zone glyph {zone_glyph!r}", source=source, path=f"{path}.zones[{y}]")
                if shell[y][x] not in WALKABLE_STAMP_GLYPHS:
                    raise BuildingStampError("zones may label only walkable cells", source=source, path=f"{path}.zones[{y}]")
        stair_cells[z] = frozenset(
            (x, y) for y, row in enumerate(shell) for x, glyph in enumerate(row) if glyph == "S"
        )
        floors.append(BuildingStampFloor(z=z, shell=shell, zones=zones))
    if 0 not in seen_z:
        raise BuildingStampError("a ground floor at z 0 is required", source=source, path="floors")
    ordered_z = sorted(seen_z)
    if ordered_z != list(range(ordered_z[0], ordered_z[-1] + 1)):
        raise BuildingStampError("floor z values must be contiguous", source=source, path="floors")
    if len(floors) > 1:
        for lower_z, upper_z in zip(ordered_z, ordered_z[1:]):
            if not stair_cells[lower_z].intersection(stair_cells[upper_z]):
                raise BuildingStampError("adjacent floors require a shared S vertical anchor", source=source, path="floors")

    entry_data = data.get("entry")
    if not isinstance(entry_data, dict):
        raise BuildingStampError("entry must be an object", source=source, path="entry")
    entry_x = _require_int(entry_data.get("x"), source=source, path="entry.x", minimum=0, maximum=width - 1)
    entry_y = _require_int(entry_data.get("y"), source=source, path="entry.y", minimum=0, maximum=height - 1)
    entry_z = _require_int(entry_data.get("z", 0), source=source, path="entry.z", minimum=min(seen_z), maximum=max(seen_z))
    if entry_z != 0:
        raise BuildingStampError("the canonical exterior entry must be on ground floor z 0", source=source, path="entry.z")
    entry_side = str(entry_data.get("side", "south") or "south").strip().lower()
    if entry_side not in STAMP_SIDES:
        raise BuildingStampError("entry side must be north, east, south, or west", source=source, path="entry.side")
    entry_floor = next(floor for floor in floors if floor.z == entry_z)
    if entry_floor.shell[entry_y][entry_x] != "D":
        raise BuildingStampError("entry must point at a D shell cell", source=source, path="entry")
    boundary_for_side = {
        "north": entry_y == 0,
        "south": entry_y == height - 1,
        "west": entry_x == 0,
        "east": entry_x == width - 1,
    }
    if not boundary_for_side[entry_side]:
        raise BuildingStampError("entry coordinate must lie on its declared side", source=source, path="entry")

    anchors_value = data.get("anchors", [])
    if not isinstance(anchors_value, list):
        raise BuildingStampError("anchors must be a list", source=source, path="anchors")
    anchors = []
    seen_anchor_ids = set()
    for index, value in enumerate(anchors_value):
        path = f"anchors[{index}]"
        if not isinstance(value, dict):
            raise BuildingStampError("anchor must be an object", source=source, path=path)
        anchor_id = _require_id(value.get("id"), source=source, path=f"{path}.id")
        if anchor_id in seen_anchor_ids:
            raise BuildingStampError(f"duplicate anchor id {anchor_id!r}", source=source, path=f"{path}.id")
        seen_anchor_ids.add(anchor_id)
        kind = _require_id(value.get("kind"), source=source, path=f"{path}.kind")
        x = _require_int(value.get("x"), source=source, path=f"{path}.x", minimum=0, maximum=width - 1)
        y = _require_int(value.get("y"), source=source, path=f"{path}.y", minimum=0, maximum=height - 1)
        z = _require_int(value.get("z", 0), source=source, path=f"{path}.z", minimum=min(seen_z), maximum=max(seen_z))
        floor = next(floor for floor in floors if floor.z == z)
        if floor.shell[y][x] not in WALKABLE_STAMP_GLYPHS:
            raise BuildingStampError("anchors must occupy walkable cells", source=source, path=path)
        service_value = value.get("service")
        service = "" if service_value in (None, "") else _require_id(service_value, source=source, path=f"{path}.service")
        anchors.append(BuildingStampAnchor(anchor_id, kind, x, y, z, service))

    return BuildingStamp(
        stamp_id=stamp_id,
        width=width,
        height=height,
        exterior_classes=exterior_classes,
        clearance=clearance,
        rotations=rotations,
        reflect=reflect,
        entry=MappingProxyType({"x": entry_x, "y": entry_y, "z": entry_z, "side": entry_side}),
        zone_legend=MappingProxyType(dict(zone_legend)),
        floors=tuple(sorted(floors, key=lambda floor: floor.z)),
        anchors=tuple(anchors),
        source=str(source),
    )


def parse_building_stamp_text(text: str, *, source: str = "<memory>") -> BuildingStamp:
    if len(text.encode("utf-8")) > BUILDING_STAMP_MAX_BYTES:
        raise BuildingStampError(f"file exceeds {BUILDING_STAMP_MAX_BYTES} bytes", source=source)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildingStampError(exc.msg, source=f"{source}:{exc.lineno}:{exc.colno}") from None
    return parse_building_stamp_data(data, source=source)


def parse_building_stamp_file(path: str | Path) -> BuildingStamp:
    path = Path(path)
    return parse_building_stamp_text(path.read_text(encoding="utf-8"), source=str(path))


def building_stamp_data(stamp: BuildingStamp) -> dict:
    return {
        "format": BUILDING_STAMP_FORMAT,
        "version": BUILDING_STAMP_VERSION,
        "id": stamp.stamp_id,
        "size": {"width": stamp.width, "height": stamp.height},
        "placement": {
            "exterior_classes": list(stamp.exterior_classes),
            "clearance": stamp.clearance,
            "rotations": list(stamp.rotations),
            "reflect": stamp.reflect,
        },
        "entry": dict(stamp.entry),
        "zone_legend": dict(stamp.zone_legend),
        "floors": [
            {"z": floor.z, "shell": list(floor.shell), "zones": list(floor.zones)}
            for floor in stamp.floors
        ],
        "anchors": [
            {
                **{"id": anchor.anchor_id, "kind": anchor.kind, "x": anchor.x, "y": anchor.y, "z": anchor.z},
                **({"service": anchor.service} if anchor.service else {}),
            }
            for anchor in stamp.anchors
        ],
    }


def serialize_building_stamp(stamp: BuildingStamp) -> str:
    return json.dumps(building_stamp_data(stamp), indent=2, ensure_ascii=False) + "\n"


def load_building_stamp_catalog(paths: Iterable[str | Path]) -> BuildingStampCatalog:
    files = []
    for value in paths:
        path = Path(value)
        if path.is_dir():
            files.extend(path.rglob("*.json"))
        elif path.is_file() and path.suffix == ".json":
            files.append(path)
    files = sorted({path.resolve() for path in files}, key=lambda path: str(path))
    definitions = {}
    sources = {}
    digest = hashlib.sha256()
    for path in files:
        content = path.read_text(encoding="utf-8")
        stamp = parse_building_stamp_text(content, source=str(path))
        if stamp.stamp_id in definitions:
            raise BuildingStampError(
                f"duplicate building stamp {stamp.stamp_id!r}; first defined in {sources[stamp.stamp_id]}",
                source=str(path),
            )
        definitions[stamp.stamp_id] = stamp
        sources[stamp.stamp_id] = str(path)
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return BuildingStampCatalog(
        definitions=MappingProxyType(definitions),
        sources=MappingProxyType(sources),
        files=tuple(str(path) for path in files),
        revision=digest.hexdigest(),
    )


def load_builtin_building_stamp_catalog() -> BuildingStampCatalog:
    return load_building_stamp_catalog((BUILDING_STAMP_ROOT,))


def _rotation_for_side(canonical_side: str, frontage_side: str) -> int:
    canonical_index = STAMP_SIDES.index(canonical_side)
    frontage_index = STAMP_SIDES.index(frontage_side)
    return ((frontage_index - canonical_index) % 4) * 90


def _rotate_point(x: int, y: int, width: int, height: int, rotation: int) -> tuple[int, int]:
    if rotation == 0:
        return x, y
    if rotation == 90:
        return height - 1 - y, x
    if rotation == 180:
        return width - 1 - x, height - 1 - y
    return y, width - 1 - x


def _rotate_side(side: str, rotation: int) -> str:
    return STAMP_SIDES[(STAMP_SIDES.index(side) + (rotation // 90)) % 4]


def resolve_building_stamp(
    stamp: BuildingStamp,
    *,
    left: int,
    top: int,
    frontage_side: str,
) -> ResolvedBuildingStamp:
    frontage_side = str(frontage_side or "south").strip().lower()
    if frontage_side not in STAMP_SIDES:
        raise BuildingStampError(f"unknown frontage side {frontage_side!r}", source=stamp.source)
    rotation = _rotation_for_side(str(stamp.entry["side"]), frontage_side)
    if rotation not in stamp.rotations:
        raise BuildingStampError(f"stamp {stamp.stamp_id!r} does not allow rotation {rotation}", source=stamp.source)
    resolved_width = stamp.height if rotation in {90, 270} else stamp.width
    resolved_height = stamp.width if rotation in {90, 270} else stamp.height
    left = int(left)
    top = int(top)
    floors = {}
    for floor in stamp.floors:
        cells = {}
        excluded = set()
        walls = set()
        walkable = set()
        apertures = []
        zones = {}
        for y, row in enumerate(floor.shell):
            for x, glyph in enumerate(row):
                rx, ry = _rotate_point(x, y, stamp.width, stamp.height, rotation)
                absolute = (left + rx, top + ry)
                cells[absolute] = glyph
                if glyph == " ":
                    excluded.add(absolute)
                elif glyph in {"#", "W"}:
                    walls.add(absolute)
                elif glyph in WALKABLE_STAMP_GLYPHS:
                    walkable.add(absolute)
                if glyph in {"D", "W"}:
                    sides = []
                    if x == 0:
                        sides.append("west")
                    if x == stamp.width - 1:
                        sides.append("east")
                    if y == 0:
                        sides.append("north")
                    if y == stamp.height - 1:
                        sides.append("south")
                    side = _rotate_side(sides[0] if sides else str(stamp.entry["side"]), rotation)
                    apertures.append(MappingProxyType({
                        "x": absolute[0],
                        "y": absolute[1],
                        "z": floor.z,
                        "side": side,
                        "kind": "door" if glyph == "D" else "window",
                        "ordinary": glyph == "D",
                    }))
                zone_glyph = floor.zones[y][x]
                if zone_glyph != " ":
                    zones[absolute] = stamp.zone_legend[zone_glyph]
        floors[floor.z] = ResolvedStampFloor(
            z=floor.z,
            cells=MappingProxyType(cells),
            excluded=frozenset(excluded),
            walls=frozenset(walls),
            walkable=frozenset(walkable),
            apertures=tuple(apertures),
            zones=MappingProxyType(zones),
        )

    entry_x, entry_y = _rotate_point(
        int(stamp.entry["x"]),
        int(stamp.entry["y"]),
        stamp.width,
        stamp.height,
        rotation,
    )
    entry = MappingProxyType({
        "x": left + entry_x,
        "y": top + entry_y,
        "z": int(stamp.entry["z"]),
        "side": frontage_side,
        "kind": "door",
    })
    anchors = []
    for anchor in stamp.anchors:
        anchor_x, anchor_y = _rotate_point(anchor.x, anchor.y, stamp.width, stamp.height, rotation)
        anchors.append(MappingProxyType({
            "id": anchor.anchor_id,
            "kind": anchor.kind,
            "x": left + anchor_x,
            "y": top + anchor_y,
            "z": anchor.z,
            **({"service": anchor.service} if anchor.service else {}),
        }))
    return ResolvedBuildingStamp(
        stamp_id=stamp.stamp_id,
        left=left,
        right=left + resolved_width - 1,
        top=top,
        bottom=top + resolved_height - 1,
        width=resolved_width,
        height=resolved_height,
        rotation=rotation,
        frontage_side=frontage_side,
        entry=entry,
        floors=MappingProxyType(floors),
        anchors=tuple(anchors),
    )


BUILTIN_BUILDING_STAMPS = load_builtin_building_stamp_catalog()
