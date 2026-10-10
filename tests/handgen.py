"""Synthetic 21-point hands for tests.

Hands are drawn in a local frame where the palm size (wrist -> middle knuckle)
is 1 and 'up' is -y, then rotated, scaled and placed in image units.
"""
from __future__ import annotations

import math
import random

WRIST = (0.0, 0.0)
MCP = {
    "index": (-0.30, -0.95),
    "middle": (0.00, -1.00),
    "ring": (0.25, -0.95),
    "pinky": (0.45, -0.85),
}
ORDER = ["index", "middle", "ring", "pinky"]


def _finger(mcp, extended):
    x, y = mcp
    if extended:
        return [(x, y), (x, y - 0.45), (x, y - 0.75), (x, y - 1.0)]
    # folded: PIP pokes forward, tip comes back below the knuckle
    return [(x, y), (x, y - 0.35), (x, y - 0.15), (x, y + 0.25)]


def _thumb(kind):
    cmc, mcp = (-0.35, -0.20), (-0.60, -0.40)
    if kind == "out":       # spread sideways, as in an open palm
        return [cmc, mcp, (-0.85, -0.60), (-1.05, -0.80)]
    if kind == "up":        # pointing straight up past the knuckles
        return [cmc, mcp, (-0.68, -1.00), (-0.75, -1.60)]
    return [cmc, mcp, (-0.45, -0.60), (-0.20, -0.70)]   # tucked across the fingers


SHAPES = {
    "open_palm": ({"index": 1, "middle": 1, "ring": 1, "pinky": 1}, "out"),
    "fist": ({"index": 0, "middle": 0, "ring": 0, "pinky": 0}, "tucked"),
    "thumb_up": ({"index": 0, "middle": 0, "ring": 0, "pinky": 0}, "up"),
    "peace": ({"index": 1, "middle": 1, "ring": 0, "pinky": 0}, "tucked"),
    "pointing": ({"index": 1, "middle": 0, "ring": 0, "pinky": 0}, "tucked"),
    "three": ({"index": 1, "middle": 1, "ring": 1, "pinky": 0}, "tucked"),   # no gesture
}


def make_hand(shape="open_palm", cx=0.65, cy=0.5, scale=0.15, angle_deg=0.0,
              noise=0.0, seed=None):
    fingers, thumb = SHAPES[shape]
    pts = [WRIST] + _thumb(thumb)
    for name in ORDER:
        pts += _finger(MCP[name], bool(fingers[name]))
    assert len(pts) == 21

    rng = random.Random(seed)
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    # palm centre in local frame ~ (0.08, -0.75); place it at (cx, cy)
    out = []
    for x, y in pts:
        rx, ry = x * ca - y * sa, x * sa + y * ca
        px = cx + (rx - 0.08) * scale + rng.gauss(0, noise)
        py = cy + (ry + 0.75) * scale + rng.gauss(0, noise)
        out.append((px, py))
    return out
