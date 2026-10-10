"""Webcam capture thread: read frame -> track hand -> run engine -> render preview.

Nothing is written to disk. The only frame kept is the latest JPEG preview in
memory, and it is dropped as soon as the camera stops.
"""
from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Callable, Optional

import cv2

from .tracker import HandTracker, draw_hand

log = logging.getLogger(__name__)

PREVIEW_WIDTH = 640


class CameraError(RuntimeError):
    pass


def _open_capture(index: int) -> cv2.VideoCapture:
    if platform.system() == "Windows":
        # DirectShow opens much faster than the default MSMF backend on most laptops.
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(index)
    else:
        cap = cv2.VideoCapture(index)
    return cap


def camera_help() -> str:
    system = platform.system()
    if system == "Windows":
        return ("Check Settings > Privacy & security > Camera: 'Camera access' and "
                "'Let desktop apps access your camera' must be On. Close other apps using "
                "the camera (Teams, Zoom, Camera app) or try another camera index.")
    if system == "Darwin":
        return ("Allow camera access for your terminal app in System Settings > "
                "Privacy & Security > Camera, then restart the terminal.")
    return "Check that /dev/video* exists and your user is in the 'video' group."


class CameraWorker:
    """Owns the webcam and the hand tracker. start()/stop() are thread-safe."""

    def __init__(self, on_landmarks: Callable[[float, Optional[list]], Optional[str]]):
        # on_landmarks(t, aspect_corrected_points) -> optional overlay text
        self._on_landmarks = on_landmarks
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._frame_cond = threading.Condition()
        self._jpeg: Optional[bytes] = None
        self._frame_id = 0
        self.mirror = True
        self.fps = 0.0
        self.error: Optional[str] = None
        self.resolution = (0, 0)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, index: int, min_confidence: float) -> None:
        """Opens the camera (blocking, ~1-3 s). Raises CameraError with a friendly message."""
        with self._lock:
            if self.running:
                return
            self.error = None
            cap = _open_capture(index)
            if not cap.isOpened():
                cap.release()
                raise CameraError(f"No camera available at index {index}. {camera_help()}")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            ok, frame = False, None
            for _ in range(20):                        # some cameras need a few frames to wake
                ok, frame = cap.read()
                if ok and frame is not None:
                    break
                time.sleep(0.05)
            if not ok or frame is None:
                cap.release()
                raise CameraError(
                    f"Camera {index} opened but returned no image (blocked or in use). {camera_help()}"
                )
            try:
                tracker = HandTracker(min_confidence=min_confidence)
            except Exception as e:
                cap.release()
                raise CameraError(f"Could not start hand tracking: {e}") from e
            self.resolution = (frame.shape[1], frame.shape[0])
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, args=(cap, tracker), name="camera", daemon=True
            )
            self._thread.start()
            log.info("Camera %s started at %sx%s", index, *self.resolution)

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
            if thread is not None:
                thread.join(timeout=3)
            self._thread = None
        with self._frame_cond:
            self._jpeg = None
            self._frame_id += 1
            self._frame_cond.notify_all()

    def wait_frame(self, last_id: int, timeout: float = 1.0) -> tuple[int, Optional[bytes]]:
        """Blocks until a newer preview frame exists (used by the MJPEG stream)."""
        with self._frame_cond:
            self._frame_cond.wait_for(lambda: self._frame_id != last_id, timeout=timeout)
            return self._frame_id, self._jpeg

    # ---------------------------------------------------------------- loop
    def _run(self, cap: cv2.VideoCapture, tracker: HandTracker) -> None:
        t0 = time.monotonic()
        failures = 0
        frames, fps_t = 0, t0
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    if failures > 30:
                        self.error = "Camera stopped sending frames (unplugged or taken by another app)."
                        log.error(self.error)
                        break
                    time.sleep(0.03)
                    continue
                failures = 0
                now = time.monotonic()
                pts = tracker.process(frame, int((now - t0) * 1000))
                h, w = frame.shape[:2]
                aspect = w / h
                corrected = [(x * aspect, y) for x, y in pts] if pts else None
                overlay = self._on_landmarks(now, corrected)

                if pts:
                    draw_hand(frame, pts)
                if self.mirror:
                    frame = cv2.flip(frame, 1)
                if w > PREVIEW_WIDTH:
                    frame = cv2.resize(frame, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)))
                if overlay:
                    cv2.putText(frame, overlay, (12, frame.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (255, 255, 255), 2, cv2.LINE_AA)
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
                if ok:
                    with self._frame_cond:
                        self._jpeg = buf.tobytes()
                        self._frame_id += 1
                        self._frame_cond.notify_all()

                frames += 1
                if now - fps_t >= 1.0:
                    self.fps = frames / (now - fps_t)
                    frames, fps_t = 0, now
        except Exception:
            log.exception("Camera loop crashed")
            self.error = "Camera loop crashed; see logs/airscroll.log"
        finally:
            cap.release()
            tracker.close()
            self.fps = 0.0
            with self._frame_cond:
                self._jpeg = None
                self._frame_id += 1
                self._frame_cond.notify_all()
            self._on_landmarks(time.monotonic(), None)
            log.info("Camera released")
