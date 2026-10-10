"""Smoke test: the real MediaPipe model loads and processes frames (no camera needed)."""
import numpy as np

from airscroll.tracker import HandTracker, draw_hand
from tests.handgen import make_hand


def test_model_runs_on_frames_without_a_hand():
    tracker = HandTracker()
    try:
        frame = np.full((480, 640, 3), 40, np.uint8)
        for i in range(5):
            assert tracker.process(frame, i * 33) is None
        # timestamps that go backwards must not crash VIDEO mode
        assert tracker.process(frame, 0) is None
    finally:
        tracker.close()


def test_draw_hand_on_frame():
    frame = np.zeros((480, 640, 3), np.uint8)
    pts = [(x / (640 / 480), y) for x, y in make_hand(cx=0.6, cy=0.5)]
    draw_hand(frame, pts)
    assert frame.any()
