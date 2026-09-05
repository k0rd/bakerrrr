"""Small top-down vehicle silhouettes, projected into all eight headings.

Geometry is authored once in vehicle-local (forward, right) coordinates.
Project before rasterizing so diagonal vehicles keep crisp native-size pixels.
"""

from __future__ import annotations

import math


def rasterize_vehicle(pygame, *, cell_px, heading, frame, palette,
                      vehicle_class="sedan", medium="land", status="", headlights=True):
    surface = pygame.Surface((cell_px, cell_px), pygame.SRCALPHA)
    scale = cell_px / 16.0
    center = (cell_px - 1) / 2.0
    length = math.hypot(*heading) or 1.0
    fx, fy = heading[0] / length, heading[1] / length

    def point(along, across):
        return (round(center + scale * (fx * along - fy * across)),
                round(center + scale * (fy * along + fx * across)))

    def polygon(color, vertices, *, outline=None):
        pixels = [point(*p) for p in vertices]
        pygame.draw.polygon(surface, color, pixels)
        if outline is not None:
            pygame.draw.lines(surface, outline, True, pixels, max(1, round(scale * 0.4)))

    def line(color, vertices, width=0.4):
        pygame.draw.lines(surface, color, False, [point(*p) for p in vertices], max(1, round(scale * width)))

    def panel(color, front, rear, left, right, *, outline=None):
        polygon(color, ((front, left), (front, right), (rear, right), (rear, left)), outline=outline)

    def mix(a, b, amount):
        return tuple(round(a[i] * (1 - amount) + b[i] * amount) for i in range(3)) + (255,)

    paint = tuple(frame[:3]) + (255,)
    tire, trim = palette["tire"], palette["trim"]
    edge = mix(tire, trim, 0.18)
    roof = mix(paint, trim, 0.12)
    glass = mix(palette["glass"], tire, 0.24)
    glass_edge = mix(palette["glass"], trim, 0.4)
    lamp = palette["light"] if headlights else mix(palette["light"], tire, 0.78)
    tail = palette["tail_light"] if headlights else mix(palette["tail_light"], tire, 0.65)
    boat = medium == "water" or vehicle_class in {"skiff", "launch"}

    if boat:
        # A pointed bow, gunwale and open cockpit distinguish boats from cars.
        polygon(paint, ((6, 0), (3.8, 2.6), (-4.9, 2.35), (-5.5, 1.8),
                        (-5.5, -1.8), (-4.9, -2.35), (3.8, -2.6)), outline=edge)
        polygon(mix(paint, tire, 0.6), ((3.9, 0), (2.6, 1.6), (-4.4, 1.5),
                                     (-4.4, -1.5), (2.6, -1.6)))
        panel(tire, -5.1, -6.3, -0.6, 0.6)
        if vehicle_class == "launch":
            panel(glass, 2.6, 1.3, -1.6, 1.6)
            panel(roof, 1.1, -1.6, -1.5, 1.5)
            line(trim, ((1.1, -1.5), (1.1, 1.5)))
        else:
            for along in (1.4, -1.1, -3.5):
                line(roof, ((along, -1.6), (along, 1.6)), 0.65)
        line(lamp, ((4.4, -0.45), (4.4, 0.45)))
        line(tail, ((-4.9, -0.5), (-4.9, 0.5)))
        roof_front, roof_rear, roof_half = 1.0, -1.0, 1.4
    else:
        front, rear, half = 5.6, -5.6, 3.0
        windshield_front, windshield_rear, rear_glass_front, rear_glass_rear = 2.5, 1.1, -1.7, -3.1
        if vehicle_class == "micro":
            front, rear, half = 4.6, -4.6, 2.65
            windshield_front, windshield_rear, rear_glass_front, rear_glass_rear = 2.1, 0.8, -1.3, -2.7
        elif vehicle_class in {"compact", "hatchback"}:
            front, rear, half = 5.1, -5.2, 2.85
            rear_glass_front, rear_glass_rear = -2.1, -3.5
        elif vehicle_class == "coupe":
            windshield_front, windshield_rear = 1.8, 0.5
        elif vehicle_class in {"van", "wagon", "utility", "suv"}:
            front, rear, half = 5.7, -5.9, 3.3
            windshield_front, windshield_rear = 3.6, 2.3
            rear_glass_front, rear_glass_rear = -3.3, -4.5
        elif vehicle_class == "pickup":
            front, rear, half = 5.8, -5.8, 3.15
            windshield_front, windshield_rear = 2.9, 1.5
            rear_glass_front, rear_glass_rear = -0.3, -0.9

        # Tires sit partly behind the body: short, dark sidewalls, not round pods.
        for along in (front * 0.52, rear * 0.58):
            for side in (-1, 1):
                panel(tire, along + 1.0, along - 1.0,
                      side * half - 0.65, side * half + 0.65)
                line(edge, ((along + 0.75, side * (half + 0.6)),
                            (along - 0.75, side * (half + 0.6))))

        polygon(paint, ((front, -half * 0.72), (front, half * 0.72),
                        (front - 0.65, half), (rear + 0.6, half),
                        (rear, half * 0.8), (rear, -half * 0.8),
                        (rear + 0.6, -half), (front - 0.65, -half)), outline=edge)

        # Separate hood, windshield, painted roof, rear glass and trunk/bed.
        glass_half = half * 0.72
        polygon(glass, ((windshield_front, -glass_half), (windshield_front, glass_half),
                        (windshield_rear, glass_half * 0.85), (windshield_rear, -glass_half * 0.85)))
        roof_front, roof_rear, roof_half = windshield_rear - 0.3, rear_glass_front + 0.3, glass_half * 0.82
        panel(roof, roof_front, roof_rear, -roof_half, roof_half)
        polygon(glass, ((rear_glass_front, -glass_half * 0.85), (rear_glass_front, glass_half * 0.85),
                        (rear_glass_rear, glass_half), (rear_glass_rear, -glass_half)))
        if cell_px >= 24:
            line(glass_edge, ((windshield_front, -glass_half), (windshield_front, glass_half)))
            for side in (-1, 1):
                line(glass, ((roof_front, side * (half - 0.35)), (roof_rear, side * (half - 0.35))))
        if vehicle_class == "pickup":
            panel(mix(paint, tire, 0.7), -1.3, rear + 0.7, -half * 0.72, half * 0.72,
                  outline=mix(paint, trim, 0.25))
            if cell_px >= 24:
                for across in (-0.8, 0.8):
                    line(edge, ((-1.7, across), (rear + 1.0, across)))
        elif vehicle_class in {"van", "utility", "suv", "wagon"} and cell_px >= 24:
            for side in (-1, 1):
                line(edge, ((roof_front - 0.4, side * roof_half * 0.8),
                            (roof_rear + 0.4, side * roof_half * 0.8)))

        line(trim, ((front - 0.1, -half * 0.28), (front - 0.1, half * 0.28)), 0.3)
        for side in (-1, 1):
            line(lamp, ((front - 0.15, side * half * 0.48), (front - 0.15, side * half * 0.78)), 0.45)
            line(tail, ((rear + 0.1, side * half * 0.45), (rear + 0.1, side * half * 0.78)), 0.45)

    # Status accents stay on the roof, keeping the glass and facing cues clear.
    if status == "vehicle_player":
        polygon(mix(paint, trim, 0.25), ((roof_front, -roof_half), (roof_front, roof_half),
                                      (roof_rear, roof_half), (roof_rear, -roof_half)),
                outline=trim)
    elif status == "vehicle_police":
        bar_y = (roof_front + roof_rear) / 2
        line(palette["tail_light"], ((bar_y, -roof_half), (bar_y, -0.15)), 0.7)
        line(palette["glass"], ((bar_y, 0.15), (bar_y, roof_half)), 0.7)
        if not boat:
            for side in (-1, 1):
                line(trim, ((roof_front, side * (half - 0.2)), (roof_rear, side * (half - 0.2))), 0.6)
    elif status == "vehicle_new":
        line(trim, ((roof_front, -roof_half * 0.6), (roof_rear, -roof_half * 0.6)), 0.3)
    return surface
