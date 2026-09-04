"""Authoritative semantic body geometry for Bakerrrr drawables.

This module turns the actor renderer's body profiles into a stable set of
semantic Points that clothing, the Drawables editor, and eventually the
paper doll can all share.

The public contract is deliberately anatomical.  Garments should consume
Points/spans and dimensionless proportions; they should not invent a second
body model with hard-coded spatial offsets.

Coordinate spaces
-----------------
``pixel_anchors`` are calibrated to the current pygame actor silhouettes for a
requested render size. ``drawable_anchors`` are those same points projected
into Bakerrrr's 16-unit drawable space.

The four frame Points (``tile_top``, ``tile_left``, ``tile_right``, ``ground``)
represent the midpoints of the drawable bounds and allow deliberately oversized
art to remain relative to the tile rather than to naked coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from types import MappingProxyType
from typing import Mapping

DRAWABLE_UNITS = 16.0

Point = tuple[float, float]
Vector = tuple[float, float]


@dataclass(frozen=True)
class BodyProfile:
    key: str
    presentation: str
    silhouette: str
    label: str


_PROFILE_ROWS = (
    ("femme_straight", "femme", "straight", "Femme · straight"),
    ("femme_soft", "femme", "soft", "Femme · soft"),
    ("femme_curvy", "femme", "curvy", "Femme · curvy"),
    ("masc_lean", "masc", "lean", "Masc · lean"),
    ("masc_standard", "masc", "", "Masc · standard"),
    ("masc_broad", "masc", "broad", "Masc · broad"),
    ("mixed_slight", "mixed", "slight", "Mixed · slight"),
    ("mixed_standard", "mixed", "", "Mixed · standard"),
    ("mixed_solid", "mixed", "solid", "Mixed · solid"),
)

BODY_PROFILES: Mapping[str, BodyProfile] = MappingProxyType(
    {
        key: BodyProfile(key, presentation, silhouette, label)
        for key, presentation, silhouette, label in _PROFILE_ROWS
    }
)

BODY_PROFILE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "default": "mixed_standard",
        "femme": "femme_soft",
        "masc": "masc_standard",
        "mixed": "mixed_standard",
    }
)

ACTOR_KINDS = ("civilian", "guard", "scout")

# Frozen public anatomical Point contract.  The order is intentional:
# head/neck, torso, left arm, right arm, pelvis/legs.  These plain names always
# identify exact geometry; fuzzy editor regions must use a different vocabulary.
BODY_POINTS = (
    "crown",
    "chin",
    "neck_left",
    "neck_right",
    "shoulder_left",
    "shoulder_right",
    "waist_left",
    "waist_right",
    "armpit_left",
    "elbow_inner_left",
    "elbow_outer_left",
    "wrist_inner_left",
    "wrist_outer_left",
    "armpit_right",
    "elbow_inner_right",
    "elbow_outer_right",
    "wrist_inner_right",
    "wrist_outer_right",
    "hip_left",
    "hip_right",
    "crotch",
    "thigh_inner_left",
    "thigh_outer_left",
    "knee_inner_left",
    "knee_outer_left",
    "ankle_inner_left",
    "ankle_outer_left",
    "toe_tip_left",
    "thigh_inner_right",
    "thigh_outer_right",
    "knee_inner_right",
    "knee_outer_right",
    "ankle_inner_right",
    "ankle_outer_right",
    "toe_tip_right",
)

FRAME_POINTS = ("tile_top", "tile_left", "tile_right", "ground")
SEMANTIC_POINTS = BODY_POINTS + FRAME_POINTS

# Compatibility names for the initial BodyGeometry checkpoint.  New DSL and
# editor code should call these Points.
ANATOMY_ANCHORS = BODY_POINTS
FRAME_ANCHORS = FRAME_POINTS
SEMANTIC_ANCHORS = SEMANTIC_POINTS

POINT_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({
    "crown": "Very top of the head; hat, hood, and helmet height reference.",
    "chin": "Bottom of the face; collar, neckline, and scarf reference.",
    "neck_left": "Wearer-left throat boundary for collars and neck openings.",
    "neck_right": "Wearer-right throat boundary for collars and neck openings.",
    "shoulder_left": "Wearer-left primary hang point for upper-body garments.",
    "shoulder_right": "Wearer-right primary hang point for upper-body garments.",
    "waist_left": "Wearer-left natural waist boundary for belts and tucking.",
    "waist_right": "Wearer-right natural waist boundary for belts and tucking.",
    "armpit_left": "Wearer-left lower sleeve-opening boundary.",
    "elbow_inner_left": "Wearer-left elbow boundary toward the torso.",
    "elbow_outer_left": "Wearer-left elbow boundary away from the torso.",
    "wrist_inner_left": "Wearer-left wrist boundary toward the torso.",
    "wrist_outer_left": "Wearer-left wrist boundary away from the torso.",
    "armpit_right": "Wearer-right lower sleeve-opening boundary.",
    "elbow_inner_right": "Wearer-right elbow boundary toward the torso.",
    "elbow_outer_right": "Wearer-right elbow boundary away from the torso.",
    "wrist_inner_right": "Wearer-right wrist boundary toward the torso.",
    "wrist_outer_right": "Wearer-right wrist boundary away from the torso.",
    "hip_left": "Wearer-left widest lower-torso point for pants and skirts.",
    "hip_right": "Wearer-right widest lower-torso point for pants and skirts.",
    "crotch": "Central leg-separation point for trouser geometry.",
    "thigh_inner_left": "Wearer-left upper-leg boundary toward the body centerline.",
    "thigh_outer_left": "Wearer-left outer upper-leg boundary.",
    "knee_inner_left": "Wearer-left knee boundary toward the body centerline.",
    "knee_outer_left": "Wearer-left outer knee boundary.",
    "ankle_inner_left": "Wearer-left ankle boundary toward the body centerline.",
    "ankle_outer_left": "Wearer-left outer ankle boundary.",
    "toe_tip_left": "Wearer-left maximum footwear/hem extent at the foot.",
    "thigh_inner_right": "Wearer-right upper-leg boundary toward the body centerline.",
    "thigh_outer_right": "Wearer-right outer upper-leg boundary.",
    "knee_inner_right": "Wearer-right knee boundary toward the body centerline.",
    "knee_outer_right": "Wearer-right outer knee boundary.",
    "ankle_inner_right": "Wearer-right ankle boundary toward the body centerline.",
    "ankle_outer_right": "Wearer-right outer ankle boundary.",
    "toe_tip_right": "Wearer-right maximum footwear/hem extent at the foot.",
    "tile_top": "Midpoint of the drawable's top edge.",
    "tile_left": "Midpoint of the drawable's left edge.",
    "tile_right": "Midpoint of the drawable's right edge.",
    "ground": "Midpoint of the drawable's maximum bottom edge.",
})

# Kept for the initial BodyGeometry checkpoint and any editor extensions built
# against it.  The v2 author-facing term is Point.
ANCHOR_DESCRIPTIONS = POINT_DESCRIPTIONS

# Centers are useful to the body builder and may later become public if the DSL
# needs them, but garments do not need them to describe ordinary clothing.
INTERNAL_ANCHORS = (
    # Rendering-derived helper points.  These are not additional anatomical
    # truths; they are conveniences used to derive measurements and preserve
    # the legacy v1 garment vocabulary from the same BodyGeometry.
    "head_center",
    "head_left",
    "head_right",
    "neck_center",
    "elbow_center_left",
    "wrist_center_left",
    "elbow_center_right",
    "wrist_center_right",
    "thigh_center_left",
    "knee_center_left",
    "ankle_center_left",
    "thigh_center_right",
    "knee_center_right",
    "ankle_center_right",
    "foot_center_left",
    "foot_center_right",
)


def _presentation(value: str) -> str:
    value = str(value or "mixed").strip().lower()
    return value if value in {"femme", "masc", "mixed"} else "mixed"


def _kind(value: str) -> str:
    value = str(value or "civilian").strip().lower()
    return value if value in ACTOR_KINDS else "civilian"


def resolve_body_profile(value: str | BodyProfile) -> BodyProfile:
    if isinstance(value, BodyProfile):
        return value
    key = str(value or "mixed_standard").strip().lower()
    key = BODY_PROFILE_ALIASES.get(key, key)
    try:
        return BODY_PROFILES[key]
    except KeyError as exc:
        choices = ", ".join(BODY_PROFILES)
        raise ValueError(f"unknown body profile {value!r}; expected one of {choices}") from exc


def _add(point: Point, vector: Vector) -> Point:
    return point[0] + vector[0], point[1] + vector[1]


def _sub(a: Point, b: Point) -> Vector:
    return a[0] - b[0], a[1] - b[1]


def _scale(vector: Vector, factor: float) -> Vector:
    return vector[0] * factor, vector[1] * factor


def _lerp(a: Point, b: Point, amount: float) -> Point:
    return _add(a, _scale(_sub(b, a), float(amount)))


def _length(vector: Vector) -> float:
    return hypot(vector[0], vector[1])


def _unit(vector: Vector) -> Vector:
    magnitude = _length(vector)
    if magnitude <= 1.0e-9:
        return 0.0, 1.0
    return vector[0] / magnitude, vector[1] / magnitude


def _perp(vector: Vector) -> Vector:
    return -vector[1], vector[0]


def _cross_section(
    center: Point,
    tangent: Vector,
    full_width: float,
    *,
    body_mid_x: float,
) -> tuple[Point, Point]:
    """Return (inner, outer) boundaries perpendicular to a limb centerline."""

    normal = _unit(_perp(tangent))
    half = max(0.0, float(full_width)) / 2.0
    first = _add(center, _scale(normal, half))
    second = _add(center, _scale(normal, -half))
    if abs(first[0] - body_mid_x) <= abs(second[0] - body_mid_x):
        return first, second
    return second, first


def actor_torso_half_widths(
    px: int,
    presentation: str = "mixed",
    silhouette: str = "",
    *,
    kind: str = "civilian",
) -> tuple[int, int]:
    """Mirror the current actor renderer's shoulder/hip half-widths."""

    px = max(1, int(px))
    presentation = _presentation(presentation)
    silhouette = str(silhouette or "").strip().lower()
    kind = _kind(kind)

    if presentation == "femme":
        shoulder_half = max(2, px // 7)
        hip_half = shoulder_half + {"straight": 0, "soft": 1, "curvy": 2}.get(
            silhouette, 1
        )
    elif presentation == "masc":
        shoulder_half = max(2, px // 6)
        hip_half = max(2, px // 7)
        if silhouette == "broad":
            shoulder_half += max(1, px // 24)
        elif silhouette == "lean":
            hip_half = max(1, hip_half - 1)
    else:
        shoulder_half = max(3, px // 6)
        hip_half = max(3, px // 6)
        if silhouette == "solid":
            shoulder_half += max(1, px // 28)
            hip_half += max(0, px // 32)
        elif silhouette == "slight":
            shoulder_half = max(3, shoulder_half - max(0, px // 28))
            hip_half = max(2, hip_half - max(0, px // 32))

    # Runtime role modifications currently happen only in the detailed actor.
    if px > 28:
        if kind == "guard":
            shoulder_half += max(0, px // 24)
        elif kind == "scout":
            shoulder_half = max(3, shoulder_half - max(0, px // 28))

    return shoulder_half, hip_half


@dataclass(frozen=True)
class BodyGeometry:
    px: int
    presentation: str
    silhouette: str
    kind: str
    variant: str
    pixel_anchors: Mapping[str, Point]
    drawable_anchors: Mapping[str, Point]
    internal_pixel_anchors: Mapping[str, Point]
    internal_drawable_anchors: Mapping[str, Point]
    pixel_torso_contour: tuple[Point, ...]
    drawable_torso_contour: tuple[Point, ...]
    pixel_limb_paths: Mapping[str, tuple[Point, ...]]
    drawable_limb_paths: Mapping[str, tuple[Point, ...]]

    @property
    def profile_key(self) -> str:
        for profile in BODY_PROFILES.values():
            if (
                profile.presentation == self.presentation
                and profile.silhouette == self.silhouette
            ):
                return profile.key
        return f"{self.presentation}_{self.silhouette or 'standard'}"

    def point(self, name: str, *, drawable: bool = True) -> Point:
        """Return one exact public semantic Point."""

        source = self.drawable_anchors if drawable else self.pixel_anchors
        try:
            return source[str(name)]
        except KeyError as exc:
            raise KeyError(f"unknown semantic body Point {name!r}") from exc

    def anchor(self, name: str, *, drawable: bool = True) -> Point:
        """Compatibility spelling for the initial BodyGeometry checkpoint."""

        return self.point(name, drawable=drawable)


def _project(points: Mapping[str, Point], px: int) -> Mapping[str, Point]:
    scale = DRAWABLE_UNITS / float(px)
    return MappingProxyType(
        {
            name: (float(point[0]) * scale, float(point[1]) * scale)
            for name, point in points.items()
        }
    )


def _project_sequence(points: tuple[Point, ...], px: int) -> tuple[Point, ...]:
    scale = DRAWABLE_UNITS / float(px)
    return tuple((float(x) * scale, float(y) * scale) for x, y in points)


def _project_paths(
    paths: Mapping[str, tuple[Point, ...]],
    px: int,
) -> Mapping[str, tuple[Point, ...]]:
    return MappingProxyType(
        {name: _project_sequence(tuple(points), px) for name, points in paths.items()}
    )


def actor_body_geometry(
    px: int,
    presentation: str = "mixed",
    silhouette: str = "",
    *,
    kind: str = "civilian",
) -> BodyGeometry:
    """Resolve one current Bakerrrr body into semantic garment anchors."""

    px = max(1, int(px))
    presentation = _presentation(presentation)
    silhouette = str(silhouette or "").strip().lower()
    kind = _kind(kind)
    variant = "compact" if px <= 28 else "detailed"
    mid_x = float(px // 2)

    shoulder_half, hip_half = actor_torso_half_widths(
        px,
        presentation,
        silhouette,
        kind=kind,
    )

    if variant == "compact":
        q = lambda value: float(int(round(float(value) * px / DRAWABLE_UNITS)))
        shoulder_y = q(7)
        waist_y = q(9)
        hip_y = q(11)
        foot_y = float(min(px - 1, int(q(15))))
        waist_half = float(max(1, min(shoulder_half, hip_half) - 1))

        crown = (mid_x, q(2))
        chin = (mid_x, q(5))
        head_left = (q(6), q(3.5))
        head_right = (q(10), q(3.5))

        shoulder_left = (mid_x - shoulder_half, shoulder_y)
        shoulder_right = (mid_x + shoulder_half, shoulder_y)
        waist_left = (mid_x - waist_half, waist_y)
        waist_right = (mid_x + waist_half, waist_y)
        hip_left = (mid_x - hip_half, hip_y)
        hip_right = (mid_x + hip_half, hip_y)

        # q(8) is exactly halfway between the compact shoulder and waist rows.
        armpit_left = _lerp(shoulder_left, waist_left, 0.5)
        armpit_right = _lerp(shoulder_right, waist_right, 0.5)

        left_arm_bend_a = (q(5), q(8))
        left_arm_bend_b = (q(5), q(10))
        right_arm_bend_a = (q(11), q(8))
        right_arm_bend_b = (q(11), q(10))
        elbow_center_left = _lerp(left_arm_bend_a, left_arm_bend_b, 0.5)
        elbow_center_right = _lerp(right_arm_bend_a, right_arm_bend_b, 0.5)
        wrist_center_left = (q(6), hip_y)
        wrist_center_right = (q(10), hip_y)

        leg_gap = float(max(1, int(q(1))))
        left_leg_top = (mid_x - leg_gap, hip_y)
        right_leg_top = (mid_x + leg_gap, hip_y)
        knee_center_left = (mid_x - leg_gap, q(13))
        knee_center_right = (mid_x + leg_gap, q(13))
        left_foot_center = (q(6), foot_y)
        right_foot_center = (q(10), foot_y)
        thigh_center_left = _lerp(left_leg_top, knee_center_left, 1.0 / 3.0)
        thigh_center_right = _lerp(right_leg_top, knee_center_right, 1.0 / 3.0)
        ankle_center_left = _lerp(knee_center_left, left_foot_center, 3.0 / 4.0)
        ankle_center_right = _lerp(knee_center_right, right_foot_center, 3.0 / 4.0)

        # Current compact limbs are one rendered pixel.  Deriving that width
        # from the visible torso span keeps authored garments independent of it.
        arm_width = max(1.0, abs(shoulder_right[0] - shoulder_left[0]) / 8.0)
        leg_width = max(1.0, abs(hip_right[0] - hip_left[0]) / 8.0)
        torso_contour = (
            shoulder_left,
            shoulder_right,
            waist_right,
            hip_right,
            hip_left,
            waist_left,
        )
        limb_paths = {
            "arm_left": (
                shoulder_left,
                left_arm_bend_a,
                left_arm_bend_b,
                wrist_center_left,
            ),
            "arm_right": (
                shoulder_right,
                right_arm_bend_a,
                right_arm_bend_b,
                wrist_center_right,
            ),
            "leg_left": (left_leg_top, knee_center_left, left_foot_center),
            "leg_right": (right_leg_top, knee_center_right, right_foot_center),
        }
    else:
        head_r = float(max(2, px // 8))
        head_y = float(max(int(head_r) + 1, px // 4))
        shoulder_y = head_y + head_r + float(max(1, px // 18))
        hip_y = float(px - max(5, px // 4))
        foot_y = float(px - max(2, px // 12))
        body_corner = float(max(1, px // 16))

        crown = (mid_x, head_y - head_r)
        chin = (mid_x, head_y + head_r)
        head_left = (mid_x - head_r, head_y)
        head_right = (mid_x + head_r, head_y)

        # The renderer's detailed torso has a rounded shoulder corner: the
        # top shoulder point is where garments hang, while the side point one
        # corner lower is the armpit/sleeve-opening boundary.
        shoulder_left = (mid_x - shoulder_half + body_corner, shoulder_y)
        shoulder_right = (mid_x + shoulder_half - body_corner, shoulder_y)
        waist_y = shoulder_y + float(max(2, int((hip_y - shoulder_y) // 2)))
        if presentation == "femme":
            waist_half = float(
                max(1, min(shoulder_half, hip_half) - max(1, px // 20))
            )
        else:
            # Non-femme detailed torsos have no authored waist vertex.  The
            # semantic waist lies on the actual straight shoulder→hip contour.
            progress = (waist_y - shoulder_y) / max(1.0, hip_y - shoulder_y)
            waist_half = float(shoulder_half) + (
                float(hip_half - shoulder_half) * progress
            )
        waist_left = (mid_x - waist_half, waist_y)
        waist_right = (mid_x + waist_half, waist_y)
        hip_left = (mid_x - hip_half, hip_y - body_corner)
        hip_right = (mid_x + hip_half, hip_y - body_corner)
        armpit_left = (mid_x - shoulder_half, shoulder_y + body_corner)
        armpit_right = (mid_x + shoulder_half, shoulder_y + body_corner)

        stroke_w = float(max(1, px // 20))
        arm_y = min(hip_y - 1.0, shoulder_y + float(max(3, px // 4)))
        arm_outset = float(max(2, px // 12))
        left_arm_x = mid_x - shoulder_half - arm_outset
        right_arm_x = mid_x + shoulder_half + arm_outset
        left_arm_start = (mid_x - shoulder_half + 1.0, shoulder_y + 1.0)
        right_arm_start = (mid_x + shoulder_half - 1.0, shoulder_y + 1.0)
        left_arm_bend = (left_arm_x, shoulder_y + 2.0)
        right_arm_bend = (right_arm_x, shoulder_y + 2.0)
        wrist_center_left = (left_arm_x, arm_y)
        wrist_center_right = (right_arm_x, arm_y)
        elbow_center_left = _lerp(left_arm_bend, wrist_center_left, 0.5)
        elbow_center_right = _lerp(right_arm_bend, wrist_center_right, 0.5)

        leg_gap = float(max(1, px // 18))
        stance_half = float(max(2, px // (6 if kind == "guard" else 7)))
        left_leg_top = (mid_x - leg_gap, hip_y)
        right_leg_top = (mid_x + leg_gap, hip_y)
        left_foot_center = (mid_x - stance_half, foot_y)
        right_foot_center = (mid_x + stance_half, foot_y)
        knee_center_left = _lerp(left_leg_top, left_foot_center, 0.55)
        knee_center_right = _lerp(right_leg_top, right_foot_center, 0.55)
        thigh_center_left = _lerp(left_leg_top, knee_center_left, 1.0 / 3.0)
        thigh_center_right = _lerp(right_leg_top, knee_center_right, 1.0 / 3.0)
        ankle_center_left = _lerp(knee_center_left, left_foot_center, 3.0 / 4.0)
        ankle_center_right = _lerp(knee_center_right, right_foot_center, 3.0 / 4.0)

        # These match the fill lines the detailed actor actually draws.
        arm_width = float(max(1, int(stroke_w) + 1))
        leg_width = float(max(1, int(stroke_w) + 1))
        right_hip_control = (mid_x + hip_half - body_corner, hip_y)
        left_hip_control = (mid_x - hip_half + body_corner, hip_y)
        if presentation == "femme":
            torso_contour = (
                shoulder_left,
                shoulder_right,
                armpit_right,
                waist_right,
                hip_right,
                right_hip_control,
                left_hip_control,
                hip_left,
                waist_left,
                armpit_left,
            )
        else:
            torso_contour = (
                shoulder_left,
                shoulder_right,
                armpit_right,
                hip_right,
                right_hip_control,
                left_hip_control,
                hip_left,
                armpit_left,
            )
        limb_paths = {
            "arm_left": (left_arm_start, left_arm_bend, wrist_center_left),
            "arm_right": (right_arm_start, right_arm_bend, wrist_center_right),
            "leg_left": (left_leg_top, left_foot_center),
            "leg_right": (right_leg_top, right_foot_center),
        }

    neck_center = _lerp(chin, _lerp(shoulder_left, shoulder_right, 0.5), 0.5)
    # Neck width is body-derived rather than garment-authored.  At compact
    # scale it approximates the one-pixel throat; at detailed scale it tracks
    # the renderer's visible neck stroke.
    head_width = _length(_sub(head_right, head_left))
    neck_width = max(1.0, head_width / 4.0)
    neck_left = (neck_center[0] - neck_width / 2.0, neck_center[1])
    neck_right = (neck_center[0] + neck_width / 2.0, neck_center[1])

    left_arm_tangent = _sub(wrist_center_left, shoulder_left)
    right_arm_tangent = _sub(wrist_center_right, shoulder_right)
    elbow_inner_left, elbow_outer_left = _cross_section(
        elbow_center_left,
        left_arm_tangent,
        arm_width,
        body_mid_x=mid_x,
    )
    wrist_inner_left, wrist_outer_left = _cross_section(
        wrist_center_left,
        _sub(wrist_center_left, elbow_center_left),
        arm_width,
        body_mid_x=mid_x,
    )
    elbow_inner_right, elbow_outer_right = _cross_section(
        elbow_center_right,
        right_arm_tangent,
        arm_width,
        body_mid_x=mid_x,
    )
    wrist_inner_right, wrist_outer_right = _cross_section(
        wrist_center_right,
        _sub(wrist_center_right, elbow_center_right),
        arm_width,
        body_mid_x=mid_x,
    )

    crotch = (mid_x, hip_y)

    thigh_inner_left, thigh_outer_left = _cross_section(
        thigh_center_left,
        _sub(knee_center_left, left_leg_top),
        leg_width,
        body_mid_x=mid_x,
    )
    knee_inner_left, knee_outer_left = _cross_section(
        knee_center_left,
        _sub(ankle_center_left, thigh_center_left),
        leg_width,
        body_mid_x=mid_x,
    )
    ankle_inner_left, ankle_outer_left = _cross_section(
        ankle_center_left,
        _sub(left_foot_center, knee_center_left),
        leg_width,
        body_mid_x=mid_x,
    )
    thigh_inner_right, thigh_outer_right = _cross_section(
        thigh_center_right,
        _sub(knee_center_right, right_leg_top),
        leg_width,
        body_mid_x=mid_x,
    )
    knee_inner_right, knee_outer_right = _cross_section(
        knee_center_right,
        _sub(ankle_center_right, thigh_center_right),
        leg_width,
        body_mid_x=mid_x,
    )
    ankle_inner_right, ankle_outer_right = _cross_section(
        ankle_center_right,
        _sub(right_foot_center, knee_center_right),
        leg_width,
        body_mid_x=mid_x,
    )

    # The front-facing actor has no depth axis, so toe tips are the outward
    # footwear extents on the ground row.  Their width is derived from ankle
    # thickness rather than from a garment constant.
    left_ankle_span = _length(_sub(ankle_outer_left, ankle_inner_left))
    right_ankle_span = _length(_sub(ankle_outer_right, ankle_inner_right))
    toe_tip_left = (left_foot_center[0] - left_ankle_span, left_foot_center[1])
    toe_tip_right = (right_foot_center[0] + right_ankle_span, right_foot_center[1])

    public = {
        "crown": crown,
        "chin": chin,
        "neck_left": neck_left,
        "neck_right": neck_right,
        "shoulder_left": shoulder_left,
        "shoulder_right": shoulder_right,
        "waist_left": waist_left,
        "waist_right": waist_right,
        "armpit_left": armpit_left,
        "elbow_inner_left": elbow_inner_left,
        "elbow_outer_left": elbow_outer_left,
        "wrist_inner_left": wrist_inner_left,
        "wrist_outer_left": wrist_outer_left,
        "armpit_right": armpit_right,
        "elbow_inner_right": elbow_inner_right,
        "elbow_outer_right": elbow_outer_right,
        "wrist_inner_right": wrist_inner_right,
        "wrist_outer_right": wrist_outer_right,
        "hip_left": hip_left,
        "hip_right": hip_right,
        "crotch": crotch,
        "thigh_inner_left": thigh_inner_left,
        "thigh_outer_left": thigh_outer_left,
        "knee_inner_left": knee_inner_left,
        "knee_outer_left": knee_outer_left,
        "ankle_inner_left": ankle_inner_left,
        "ankle_outer_left": ankle_outer_left,
        "toe_tip_left": toe_tip_left,
        "thigh_inner_right": thigh_inner_right,
        "thigh_outer_right": thigh_outer_right,
        "knee_inner_right": knee_inner_right,
        "knee_outer_right": knee_outer_right,
        "ankle_inner_right": ankle_inner_right,
        "ankle_outer_right": ankle_outer_right,
        "toe_tip_right": toe_tip_right,
        "tile_top": (mid_x, 0.0),
        "tile_left": (0.0, float(px) / 2.0),
        "tile_right": (float(px), float(px) / 2.0),
        "ground": (mid_x, float(px)),
    }

    internal = {
        "head_center": _lerp(head_left, head_right, 0.5),
        "head_left": head_left,
        "head_right": head_right,
        "neck_center": neck_center,
        "elbow_center_left": elbow_center_left,
        "wrist_center_left": wrist_center_left,
        "elbow_center_right": elbow_center_right,
        "wrist_center_right": wrist_center_right,
        "thigh_center_left": thigh_center_left,
        "knee_center_left": knee_center_left,
        "ankle_center_left": ankle_center_left,
        "thigh_center_right": thigh_center_right,
        "knee_center_right": knee_center_right,
        "ankle_center_right": ankle_center_right,
        "foot_center_left": left_foot_center,
        "foot_center_right": right_foot_center,
    }

    missing = set(SEMANTIC_POINTS) - set(public)
    extra = set(public) - set(SEMANTIC_POINTS)
    if missing or extra:
        raise AssertionError(
            f"body Point contract mismatch: missing={sorted(missing)} extra={sorted(extra)}"
        )
    missing_internal = set(INTERNAL_ANCHORS) - set(internal)
    extra_internal = set(internal) - set(INTERNAL_ANCHORS)
    if missing_internal or extra_internal:
        raise AssertionError(
            "body internal-anchor contract mismatch: "
            f"missing={sorted(missing_internal)} extra={sorted(extra_internal)}"
        )

    return BodyGeometry(
        px=px,
        presentation=presentation,
        silhouette=silhouette,
        kind=kind,
        variant=variant,
        pixel_anchors=MappingProxyType(public),
        drawable_anchors=_project(public, px),
        internal_pixel_anchors=MappingProxyType(internal),
        internal_drawable_anchors=_project(internal, px),
        pixel_torso_contour=tuple(torso_contour),
        drawable_torso_contour=_project_sequence(tuple(torso_contour), px),
        pixel_limb_paths=MappingProxyType(limb_paths),
        drawable_limb_paths=_project_paths(limb_paths, px),
    )


def geometry_for_profile(
    profile: str | BodyProfile,
    px: int,
    *,
    kind: str = "civilian",
) -> BodyGeometry:
    resolved = resolve_body_profile(profile)
    return actor_body_geometry(
        px,
        resolved.presentation,
        resolved.silhouette,
        kind=kind,
    )


def validate_point_contract() -> None:
    """Cheap invariant check suitable for regressions and editor startup tests."""

    for profile in BODY_PROFILES.values():
        for px in (16, 24, 32, 48):
            for kind in ACTOR_KINDS:
                geometry = geometry_for_profile(profile, px, kind=kind)
                if tuple(geometry.pixel_anchors) != SEMANTIC_POINTS:
                    raise AssertionError(
                        f"Point order drifted for {profile.key}/{px}/{kind}"
                    )
                if tuple(geometry.internal_pixel_anchors) != INTERNAL_ANCHORS:
                    raise AssertionError(
                        f"internal anchor order drifted for {profile.key}/{px}/{kind}"
                    )
                for name, point in geometry.pixel_anchors.items():
                    if not all(float(value) == float(value) for value in point):
                        raise AssertionError(
                            f"non-finite Point {name} for {profile.key}/{px}/{kind}"
                        )
                anchors = geometry.pixel_anchors
                for left, right in (
                    ("neck_left", "neck_right"),
                    ("shoulder_left", "shoulder_right"),
                    ("waist_left", "waist_right"),
                    ("hip_left", "hip_right"),
                ):
                    if not anchors[left][0] < anchors[right][0]:
                        raise AssertionError(
                            f"body Point ordering drifted for {profile.key}/{px}/{kind}: "
                            f"{left} must remain left of {right}"
                        )
                for joint in ("elbow", "wrist", "thigh", "knee", "ankle"):
                    if not (
                        anchors[f"{joint}_outer_left"][0]
                        <= anchors[f"{joint}_inner_left"][0]
                        <= anchors[f"{joint}_inner_right"][0]
                        <= anchors[f"{joint}_outer_right"][0]
                    ):
                        raise AssertionError(
                            f"{joint} Point ordering drifted for {profile.key}/{px}/{kind}"
                        )
                if not anchors["crown"][1] < anchors["chin"][1]:
                    raise AssertionError("crown must remain above chin")
                if not anchors["shoulder_left"][1] <= anchors["hip_left"][1]:
                    raise AssertionError("shoulders must remain above hips")
                if not anchors["toe_tip_left"][1] <= anchors["ground"][1]:
                    raise AssertionError("feet must not extend below ground")
                if geometry.drawable_anchors["tile_top"][1] != 0.0:
                    raise AssertionError("tile_top must remain on y=0")
                if geometry.drawable_anchors["tile_left"][0] != 0.0:
                    raise AssertionError("tile_left must remain on x=0")
                if geometry.drawable_anchors["tile_right"][0] != DRAWABLE_UNITS:
                    raise AssertionError("tile_right must remain on x=16")
                if geometry.drawable_anchors["ground"][1] != DRAWABLE_UNITS:
                    raise AssertionError("ground must remain on y=16")


def validate_anchor_contract() -> None:
    """Compatibility spelling for the initial BodyGeometry checkpoint."""

    validate_point_contract()


if __name__ == "__main__":
    validate_point_contract()
    print(
        f"body Point contract ok: {len(BODY_PROFILES)} profiles, "
        f"{len(SEMANTIC_POINTS)} public Points"
    )
