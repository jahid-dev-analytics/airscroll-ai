"""Application core: wires camera -> gesture engine -> safety gate -> browser extension."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Optional

from .bridge import ExtensionBridge
from .camera import CameraError, CameraWorker
from .config import Settings
from .engine import ACTION_LABELS, Action, GestureEngine, GestureEvent
from .gestures import POSE_LABELS, Pose

log = logging.getLogger(__name__)

RECOGNIZED_DISPLAY_S = 1.5


class AirScrollApp:
    def __init__(self, settings: Settings, bridge: Optional[ExtensionBridge] = None):
        self.settings = settings
        self._engine_lock = threading.Lock()
        self.engine = GestureEngine(settings.engine_config())
        self.control_enabled = False
        self.events: deque[dict] = deque(maxlen=80)
        self._event_seq = 0
        self._last_recognized: tuple[float, str] = (0.0, "")
        self.camera_starting = False
        self.camera_error: Optional[str] = None
        self.bridge = bridge or ExtensionBridge(on_log=self.log_event, on_emergency=self._emergency_from_browser)
        self.camera = CameraWorker(self._on_landmarks)
        self.camera.mirror = settings.mirror_preview

    # ----------------------------------------------------------------- log
    def log_event(self, text: str, level: str = "info") -> None:
        self._event_seq += 1
        self.events.append({"id": self._event_seq, "t": time.time(), "text": text, "level": level})
        getattr(log, {"ok": "info", "warn": "warning"}.get(level, level), log.info)(text)

    # -------------------------------------------------------------- camera
    def start_camera(self) -> bool:
        """Blocking; call from a worker thread. Only ever triggered by the user."""
        if self.camera.running or self.camera_starting:
            return True
        self.camera_starting = True
        self.camera_error = None
        try:
            self.camera.start(self.settings.camera_index, self.settings.min_confidence)
            self.log_event(f"Camera {self.settings.camera_index} on — processing locally, nothing recorded", "ok")
            return True
        except CameraError as e:
            self.camera_error = str(e)
            self.log_event(str(e), "error")
            return False
        finally:
            self.camera_starting = False

    def stop_camera(self) -> None:
        was_running = self.camera.running
        self.camera.stop()
        with self._engine_lock:
            self.engine = GestureEngine(self.settings.engine_config())
        if was_running:
            self.log_event("Camera off")

    # ------------------------------------------------------------- control
    def set_control(self, enabled: bool, source: str = "dashboard") -> None:
        if self.control_enabled == enabled:
            return
        self.control_enabled = enabled
        self.log_event(f"Gesture control {'ENABLED' if enabled else 'DISABLED'} ({source})",
                       "ok" if enabled else "warn")

    def emergency_stop(self, source: str = "dashboard") -> None:
        self.control_enabled = False
        self.stop_camera()
        self.log_event(f"EMERGENCY STOP ({source}): control disabled, camera off", "error")

    def _emergency_from_browser(self) -> None:
        loop = self.bridge.loop
        if loop is not None:
            loop.run_in_executor(None, self.emergency_stop, "browser shortcut")
        else:
            self.emergency_stop("browser shortcut")

    def update_settings(self, values: dict) -> dict:
        changed = self.settings.update(values)
        if changed:
            with self._engine_lock:
                self.engine.config = self.settings.engine_config()
            self.camera.mirror = self.settings.mirror_preview
            self.settings.save()
            log.info("Settings changed: %s", changed)
        return changed

    # --------------------------------------------------- gesture pipeline
    def _on_landmarks(self, t: float, points) -> Optional[str]:
        """Called from the camera thread for every frame."""
        with self._engine_lock:
            events = self.engine.update(t, points)
            notes, self.engine.diagnostics = self.engine.diagnostics, []
        for note in notes:
            self.log_event(note)
        for ev in events:
            self.handle_event(ev)
        return None

    def handle_event(self, ev: GestureEvent) -> str:
        """The safety gate. Returns a short outcome string (used by tests)."""
        label = ACTION_LABELS[ev.action]
        if not ev.fired:
            self.log_event(f"{label}: skipped ({ev.blocked})")
            return f"blocked:{ev.blocked}"
        self._last_recognized = (time.monotonic(), label)

        if ev.action == Action.TOGGLE_CONTROL:
            if self.control_enabled and not self.settings.hold_can_disable:
                self.log_event("Palm hold ignored: control is already ON "
                               "(turn it off from the dashboard or with Alt+Shift+S)")
                return "ignored:hold"
            self.set_control(not self.control_enabled, "open-palm hold")
            return "toggled"
        if not self.control_enabled:
            self.log_event(f"{label} recognized, ignored (control disabled)")
            return "ignored:disabled"
        sent, reason = self.bridge.send_action(ev.action.value)
        if not sent:
            self.log_event(f"{label} recognized, not sent: {reason}", "warn")
            return f"ignored:{reason}"
        self.log_event(f"Gesture recognized: {label}")
        return "sent"

    # ------------------------------------------------------------- status
    def state(self) -> dict:
        now = time.monotonic()
        cam_on = self.camera.running
        if not cam_on and self.camera.error and not self.camera_error:
            self.camera_error = self.camera.error
            self.log_event(self.camera.error, "error")
        with self._engine_lock:
            eng = self.engine.snapshot(now)
        bridge = self.bridge.state()
        recent = now - self._last_recognized[0] < RECOGNIZED_DISPLAY_S

        if self.camera_starting:
            status, tone = "Starting camera…", "info"
        elif not cam_on:
            status, tone = ("Camera error" if self.camera_error else "Camera off"), (
                "error" if self.camera_error else "idle")
        elif not eng["hand"]:
            status, tone = "No hand detected", "idle"
        elif recent:
            status, tone = f"Gesture recognized: {self._last_recognized[1]}", "ok"
        elif not self.control_enabled:
            status, tone = "Hand detected · control disabled", "warn"
        elif not bridge["active"]:
            status, tone = "Hand detected · no supported site in front", "warn"
        else:
            status, tone = "Hand detected · ready", "ok"

        return {
            "status": status,
            "tone": tone,
            "camera": {
                "on": cam_on,
                "starting": self.camera_starting,
                "fps": round(self.camera.fps, 1),
                "error": self.camera_error,
            },
            "control_enabled": self.control_enabled,
            "engine": {**eng, "pose_label": POSE_LABELS[Pose(eng["pose"])]},
            "extension": bridge,
            "settings": self.settings.to_dict(),
            "swipe_distance": self.engine.config.swipe_distance,
        }

    def shutdown(self) -> None:
        self.control_enabled = False
        self.camera.stop()
