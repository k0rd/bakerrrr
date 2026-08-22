"""Pygame rasterization for renderer-neutral Bakerrrr drawable geometry.

This module deliberately knows about Pygame surfaces but not actors, items, or
the simulation.  The caller resolves those concerns into a ``ResolvedDrawable``
and a semantic paint palette before asking for pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from game.drawable_dsl import ResolvedDrawable, ResolvedShape


LOGICAL_DRAWABLE_SIZE = 16.0


@dataclass(frozen=True)
class RasterizedDrawable:
    overlay: Any
    garment_mask: Any
    garment_bounds: Any | None


def _rgba(value) -> tuple[int, int, int, int]:
    channels = tuple(int(channel) for channel in tuple(value or ()))
    if len(channels) >= 4:
        return channels[:4]
    if len(channels) == 3:
        return channels + (255,)
    raise ValueError("drawable paint colors must contain RGB or RGBA channels")


def _scaled_point(point, scale: float) -> tuple[int, int]:
    return (int(round(float(point[0]) * scale)), int(round(float(point[1]) * scale)))


def _scaled_width(value: float | None, scale: float) -> int:
    if value is None:
        return 1
    return max(1, int(round(float(value) * scale)))


def _scaled_rect(pygame, box, scale: float):
    x, y, width, height = (float(value) for value in box)
    left = int(round(x * scale))
    top = int(round(y * scale))
    right = int(round((x + width) * scale))
    bottom = int(round((y + height) * scale))
    return pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))


def _paint_for(shape: ResolvedShape, paints: Mapping[str, tuple], *, outline: bool = False):
    role = shape.outline_role if outline else shape.paint_role
    return _rgba(paints.get(str(role or "fill"), paints["fill"]))


def _draw_shape(pygame, target, shape: ResolvedShape, paints: Mapping[str, tuple], scale: float) -> None:
    fill = _paint_for(shape, paints)
    outline = _paint_for(shape, paints, outline=True) if shape.outline_role else None
    outline_width = _scaled_width(shape.outline_width, scale)

    if shape.kind == "polygon":
        points = tuple(_scaled_point(point, scale) for point in shape.points)
        if len(points) < 3:
            return
        pygame.draw.polygon(target, fill, points)
        if outline is not None:
            pygame.draw.lines(target, outline, True, points, outline_width)
        return

    if shape.kind == "line":
        points = tuple(_scaled_point(point, scale) for point in shape.points)
        if len(points) >= 2:
            pygame.draw.lines(
                target,
                fill,
                bool(shape.closed),
                points,
                _scaled_width(shape.stroke_width, scale),
            )
        return

    if shape.kind in {"rect", "ellipse"} and shape.box is not None:
        rect = _scaled_rect(pygame, shape.box, scale)
        draw = pygame.draw.rect if shape.kind == "rect" else pygame.draw.ellipse
        draw(target, fill, rect)
        if outline is not None:
            draw(target, outline, rect, outline_width)
        return

    if shape.kind == "circle" and shape.points and shape.radius is not None:
        center = _scaled_point(shape.points[0], scale)
        radius = max(1, int(round(float(shape.radius) * scale)))
        pygame.draw.circle(target, fill, center, radius)
        if outline is not None:
            pygame.draw.circle(target, outline, center, radius, outline_width)


def _draw_mask_shape(pygame, target, shape: ResolvedShape, scale: float) -> None:
    white = (255, 255, 255, 255)
    mask_paints = {
        "fill": white,
        "edge": white,
        "shade": white,
        "outline": white,
    }
    _draw_shape(pygame, target, shape, mask_paints, scale)


def _mask_bounds(pygame, mask_surface):
    rects = pygame.mask.from_surface(mask_surface, threshold=1).get_bounding_rects()
    if not rects:
        return None
    bounds = rects[0].copy()
    for rect in rects[1:]:
        bounds.union_ip(rect)
    return bounds


def rasterize_drawable(
    pygame,
    resolved: ResolvedDrawable,
    *,
    target_px: int,
    paints: Mapping[str, tuple],
) -> RasterizedDrawable:
    """Rasterize resolved geometry and its declared garment finish surface."""

    target_px = max(1, int(target_px))
    if "fill" not in paints:
        raise ValueError("drawable raster palette requires a fill role")
    scale = target_px / LOGICAL_DRAWABLE_SIZE
    overlay = pygame.Surface((target_px, target_px), pygame.SRCALPHA)
    for shape in resolved.shapes:
        _draw_shape(pygame, overlay, shape, paints, scale)

    garment_mask = pygame.Surface((target_px, target_px), pygame.SRCALPHA)
    surface_ids = frozenset(resolved.surfaces.get("garment", ()))
    for shape in resolved.shapes:
        if shape.shape_id in surface_ids:
            _draw_mask_shape(pygame, garment_mask, shape, scale)
    return RasterizedDrawable(
        overlay=overlay,
        garment_mask=garment_mask,
        garment_bounds=_mask_bounds(pygame, garment_mask),
    )
