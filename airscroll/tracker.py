"""MediaPipe Tasks hand-landmark wrapper (runs fully on this computer)."""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from .config import MODEL_FILE, MODEL_URL

log = logging.getLogger(__name__)

# Pairs of landmark indices to draw the hand skeleton
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


def ensure_model(path: Path = MODEL_FILE) -> Path:
    """Download Google's official hand model once (about 7.8 MB) if it is missing."""
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading MediaPipe hand model to %s ...", path)
    tmp = path.with_suffix(".part")
    try:
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(path)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not download the hand model ({e}). Download it manually from\n  {MODEL_URL}\n"
            f"and save it as {path}"
        ) from e
    return path


class HandTracker:
    """Detects one hand per frame. Frames are processed in memory and never stored."""

    def __init__(self, min_confidence: float = 0.6, model_path: Path = MODEL_FILE):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model(model_path))),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = -1

    def process(self, frame_bgr, timestamp_ms: int) -> Optional[list[tuple[float, float]]]:
        """Returns 21 (x, y) points normalised to 0..1, or None when no hand is visible."""
        ts = max(int(timestamp_ms), self._last_ts + 1)   # VIDEO mode needs increasing timestamps
        self._last_ts = ts
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, ts)
        if not result.hand_landmarks:
            return None
        return [(p.x, p.y) for p in result.hand_landmarks[0]]

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:  # already closed
            pass


def draw_hand(frame, points, color=(255, 200, 80)) -> None:
    """Draw the skeleton on a BGR frame from normalised points."""
    h, w = frame.shape[:2]
    px = [(int(x * w), int(y * h)) for x, y in points]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, px[a], px[b], (235, 235, 235), 2, cv2.LINE_AA)
    for p in px:
        cv2.circle(frame, p, 4, color, -1, cv2.LINE_AA)
