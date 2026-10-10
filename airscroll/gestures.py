"""Hand-pose geometry: turns 21 MediaPipe landmarks into a static pose.

This module is deliberately free of MediaPipe / OpenCV imports so it can be
unit-tested with synthetic landmark data.

Coordinates: a sequence of 21 (x, y) points in *aspect-corrected* image units
(x multiplied by width/height, y as given), y grows downward like the image.
All thresholds are ratios of the palm size, so they do not depend on how far the
hand is from the camera.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional, Sequence

Point = Sequence[float]
Landmarks = Sequence[Point]

# MediaPipe hand landmark indices
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

FINGERS = {
    "index": (INDEX_PIP, INDEX_TIP),
    "middle": (MIDDLE_PIP, MIDDLE_TIP),
    "ring": (RING_PIP, RING_TIP),
    "pinky": (PINKY_PIP, PINKY_TIP),
}

# A finger is extended when its tip is clearly further from the wrist than its
# middle (PIP) joint, and curled when the tip has folded back inside it.
EXTENDED_RATIO = 1.12
CURLED_RATIO = 1.0
# Thumb counts as extended when its tip is this many palm sizes from the index knuckle.
THUMB_OUT_RATIO = 0.6
# Thumb points up when its tip is this many palm sizes above its base and mostly vertical.
THUMB_UP_RISE = 0.5


class Pose(str, Enum):
    NONE = "none"          # no hand in view
    OPEN_PALM = "open_palm"
    FIST = "fist"
    THUMB_UP = "thumb_up"
    PEACE = "peace"           # two fingers (index + middle)
    ONE_FINGER = "one_finger"  # index only
    OTHER = "other"        # a hand, but not one of the gestures


POSE_LABELS = {
    Pose.NONE: "No hand",
    Pose.OPEN_PALM: "Open palm",
    Pose.FIST: "Fist",
    Pose.THUMB_UP: "Thumb up",
    Pose.PEACE: "Two fingers",
    Pose.ONE_FINGER: "One finger",
    Pose.OTHER: "Unrecognized",
}


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def palm_size(lm: Landmarks) -> float:
    """Wrist to middle-finger knuckle: a stable, rotation-independent scale."""
    return max(dist(lm[WRIST], lm[MIDDLE_MCP]), 1e-6)


def palm_center(lm: Landmarks) -> tuple[float, float]:
    idx = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)
    return (
        sum(lm[i][0] for i in idx) / len(idx),
        sum(lm[i][1] for i in idx) / len(idx),
    )


def motion_point(lm: Landmarks) -> tuple[float, float]:
    """Point used to measure flicks: the four knuckles, not the wrist.
    A flick from the wrist moves the knuckles while the wrist barely moves, and the
    knuckles (unlike fingertips) stay put when the fingers blur or bend mid-flick."""
    idx = (INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)
    return (
        sum(lm[i][0] for i in idx) / len(idx),
        sum(lm[i][1] for i in idx) / len(idx),
    )


def finger_state(lm: Landmarks, pip: int, tip: int) -> str:
    """'extended', 'curled' or 'unsure' for one of the four long fingers."""
    ratio = dist(lm[WRIST], lm[tip]) / max(dist(lm[WRIST], lm[pip]), 1e-6)
    if ratio >= EXTENDED_RATIO:
        return "extended"
    if ratio <= CURLED_RATIO:
        return "curled"
    return "unsure"


def finger_states(lm: Landmarks) -> dict[str, str]:
    return {name: finger_state(lm, pip, tip) for name, (pip, tip) in FINGERS.items()}


def thumb_extended(lm: Landmarks) -> bool:
    ps = palm_size(lm)
    away_from_hand = dist(lm[THUMB_TIP], lm[INDEX_MCP]) > THUMB_OUT_RATIO * ps
    straight = dist(lm[WRIST], lm[THUMB_TIP]) > dist(lm[WRIST], lm[THUMB_IP])
    return away_from_hand and straight


def thumb_points_up(lm: Landmarks) -> bool:
    ps = palm_size(lm)
    dx = lm[THUMB_TIP][0] - lm[THUMB_MCP][0]
    rise = lm[THUMB_MCP][1] - lm[THUMB_TIP][1]  # positive = tip above base
    return rise > THUMB_UP_RISE * ps and rise > 1.2 * abs(dx)


def classify_pose(lm: Optional[Landmarks]) -> Pose:
    if lm is None or len(lm) < 21:
        return Pose.NONE
    s = finger_states(lm)
    long_fingers = [s["index"], s["middle"], s["ring"], s["pinky"]]

    if all(f == "extended" for f in long_fingers):
        return Pose.OPEN_PALM
    if (
        s["index"] == "extended"
        and s["middle"] == "extended"
        and s["ring"] == "curled"
        and s["pinky"] == "curled"
    ):
        return Pose.PEACE
    if (
        s["index"] == "extended"
        and s["middle"] == "curled"
        and s["ring"] == "curled"
        and s["pinky"] == "curled"
    ):
        return Pose.ONE_FINGER
    if all(f == "curled" for f in long_fingers):
        if thumb_extended(lm) and thumb_points_up(lm):
            return Pose.THUMB_UP
        return Pose.FIST
    return Pose.OTHER
