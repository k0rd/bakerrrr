#!/usr/bin/env python3
"""Generate the BAKERRRR app icon from the pygame player-token shape."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = REPO_ROOT / "assets" / "icons"
PNG_PATH = ICON_DIR / "bakerrrr.png"
ICO_PATH = ICON_DIR / "bakerrrr.ico"

PLAYER = (100, 220, 255, 228)
PLAYER_STROKE = (132, 245, 255, 246)
PLAYER_ACCENT = (156, 250, 255, 190)
SHADOW = (15, 24, 30, 120)
TEXT = (20, 29, 35, 255)

AT_PATTERN = (
    "001111100",
    "011000110",
    "110000011",
    "110111011",
    "111001011",
    "111001011",
    "111011111",
    "110000000",
    "011000010",
    "001111100",
)


def _blank(size):
    return [(0, 0, 0, 0) for _ in range(size * size)]


def _blend(dst, src):
    sr, sg, sb, sa = src
    if sa <= 0:
        return dst
    dr, dg, db, da = dst
    src_a = sa / 255.0
    dst_a = da / 255.0
    out_a = src_a + dst_a * (1.0 - src_a)
    if out_a <= 0:
        return (0, 0, 0, 0)
    out_r = (sr * src_a + dr * dst_a * (1.0 - src_a)) / out_a
    out_g = (sg * src_a + dg * dst_a * (1.0 - src_a)) / out_a
    out_b = (sb * src_a + db * dst_a * (1.0 - src_a)) / out_a
    return (round(out_r), round(out_g), round(out_b), round(out_a * 255))


def _put(canvas, size, x, y, color):
    if 0 <= x < size and 0 <= y < size:
        idx = y * size + x
        canvas[idx] = _blend(canvas[idx], color)


def _circle(canvas, size, cx, cy, radius, color):
    left = max(0, math.floor(cx - radius))
    right = min(size - 1, math.ceil(cx + radius))
    top = max(0, math.floor(cy - radius))
    bottom = min(size - 1, math.ceil(cy + radius))
    r2 = radius * radius
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if ((x + 0.5 - cx) ** 2) + ((y + 0.5 - cy) ** 2) <= r2:
                _put(canvas, size, x, y, color)


def _ring(canvas, size, cx, cy, radius, width, color):
    outer = radius + (width / 2.0)
    inner = max(0.0, radius - (width / 2.0))
    left = max(0, math.floor(cx - outer))
    right = min(size - 1, math.ceil(cx + outer))
    top = max(0, math.floor(cy - outer))
    bottom = min(size - 1, math.ceil(cy + outer))
    outer2 = outer * outer
    inner2 = inner * inner
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            distance2 = ((x + 0.5 - cx) ** 2) + ((y + 0.5 - cy) ** 2)
            if inner2 <= distance2 <= outer2:
                _put(canvas, size, x, y, color)


def _line(canvas, size, x1, y1, x2, y2, width, color):
    dx = x2 - x1
    dy = y2 - y1
    length2 = (dx * dx) + (dy * dy)
    radius = width / 2.0
    left = max(0, math.floor(min(x1, x2) - radius))
    right = min(size - 1, math.ceil(max(x1, x2) + radius))
    top = max(0, math.floor(min(y1, y2) - radius))
    bottom = min(size - 1, math.ceil(max(y1, y2) + radius))
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if length2 <= 0:
                distance2 = ((x + 0.5 - x1) ** 2) + ((y + 0.5 - y1) ** 2)
            else:
                t = max(0.0, min(1.0, (((x + 0.5 - x1) * dx) + ((y + 0.5 - y1) * dy)) / length2))
                px = x1 + (t * dx)
                py = y1 + (t * dy)
                distance2 = ((x + 0.5 - px) ** 2) + ((y + 0.5 - py) ** 2)
            if distance2 <= radius * radius:
                _put(canvas, size, x, y, color)


def _arc(canvas, size, cx, cy, radius, start, end, width, color):
    steps = max(16, int(radius * 2.5))
    for idx in range(steps + 1):
        theta = start + ((end - start) * (idx / steps))
        x = cx + (math.cos(theta) * radius)
        y = cy + (math.sin(theta) * radius)
        _circle(canvas, size, x, y, width / 2.0, color)


def _glyph(canvas, size, pattern, color):
    rows = len(pattern)
    cols = max(len(row) for row in pattern)
    scale = max(1, int(size * 0.055))
    glyph_w = cols * scale
    glyph_h = rows * scale
    start_x = (size - glyph_w) // 2
    start_y = (size - glyph_h) // 2
    for row_idx, row in enumerate(pattern):
        for col_idx, value in enumerate(row):
            if value != "1":
                continue
            x0 = start_x + (col_idx * scale)
            y0 = start_y + (row_idx * scale)
            for y in range(y0, y0 + scale):
                for x in range(x0, x0 + scale):
                    _put(canvas, size, x, y, color)


def _downsample(canvas, size, factor):
    target = size // factor
    result = []
    area = factor * factor
    for y in range(target):
        for x in range(target):
            totals = [0, 0, 0, 0]
            for yy in range(factor):
                for xx in range(factor):
                    pixel = canvas[(y * factor + yy) * size + (x * factor + xx)]
                    for idx, value in enumerate(pixel):
                        totals[idx] += value
            result.append(tuple(round(value / area) for value in totals))
    return result


def _png_bytes(size, pixels):
    raw_rows = []
    for y in range(size):
        row = bytearray([0])
        for r, g, b, a in pixels[y * size : (y + 1) * size]:
            row.extend((r, g, b, a))
        raw_rows.append(bytes(row))
    payload = zlib.compress(b"".join(raw_rows), level=9)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", payload) + chunk(b"IEND", b"")


def render_icon(size):
    factor = 4
    hi = size * factor
    canvas = _blank(hi)
    cx = cy = hi / 2
    inset = hi / 8
    radius = (hi / 2) - inset
    stroke = max(2, hi / 18)

    _circle(canvas, hi, cx + factor, cy + factor, radius, SHADOW)
    _circle(canvas, hi, cx, cy, radius, PLAYER)
    _ring(canvas, hi, cx, cy, radius, stroke, PLAYER_STROKE)
    _arc(canvas, hi, cx, cy, radius * 0.78, 0.32, 2.35, max(2, stroke * 0.9), PLAYER_ACCENT)

    tick = max(3, hi // 7)
    tick_width = max(2, stroke * 0.95)
    for x1, y1, x2, y2 in (
        (cx, inset, cx, inset + tick),
        (cx, hi - inset - 1, cx, hi - inset - 1 - tick),
        (inset, cy, inset + tick, cy),
        (hi - inset - 1, cy, hi - inset - 1 - tick, cy),
    ):
        _line(canvas, hi, x1, y1, x2, y2, tick_width, PLAYER_ACCENT)

    _glyph(canvas, hi, AT_PATTERN, TEXT)
    return _downsample(canvas, hi, factor)


def write_png(path, size):
    path.write_bytes(_png_bytes(size, render_icon(size)))


def write_ico(path, sizes):
    images = [(size, _png_bytes(size, render_icon(size))) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + (16 * len(images))
    entries = []
    payloads = []
    for size, payload in images:
        entries.append(
            struct.pack(
                "<BBBBHHII",
                0 if size >= 256 else size,
                0 if size >= 256 else size,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        payloads.append(payload)
        offset += len(payload)
    path.write_bytes(header + b"".join(entries) + b"".join(payloads))


def main():
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    write_png(PNG_PATH, 256)
    write_ico(ICO_PATH, (16, 24, 32, 48, 64, 128, 256))
    print(f"wrote {PNG_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {ICO_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
