"""User settings, persisted to settings.json next to the project (no biometric data)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .engine import EngineConfig

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "settings.json"
MODEL_FILE = ROOT / "models" / "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
LOG_DIR = ROOT / "logs"
DEFAULT_PORT = 8765

# name: (min, max) — values from the dashboard are clamped to these
LIMITS = {
    "sensitivity": (1, 10),
    "action_cooldown_s": (0.2, 3.0),
    "like_cooldown_s": (1.0, 15.0),
    "neutral_hold_s": (0.0, 1.5),
    "hold_toggle_s": (1.0, 5.0),
    "stable_frames": (1, 10),
    "return_lockout_s": (0.0, 2.5),
    "static_hold_s": (0.1, 1.5),
    "camera_index": (0, 9),
    "min_confidence": (0.3, 0.9),
}


@dataclass
class Settings:
    sensitivity: int = 5
    action_cooldown_s: float = 0.8
    like_cooldown_s: float = 3.0
    neutral_hold_s: float = 0.3
    hold_toggle_s: float = 2.0
    stable_frames: int = 4
    return_lockout_s: float = 1.0
    mirror_preview: bool = True
    static_hold_s: float = 0.4
    palm_swipes: bool = False        # open-palm flicks; off since one/two fingers do next/previous
    hold_can_disable: bool = False   # palm hold turns control ON; turning OFF by hold is opt-in
    camera_index: int = 0
    min_confidence: float = 0.6

    def engine_config(self) -> EngineConfig:
        return EngineConfig(
            sensitivity=self.sensitivity,
            action_cooldown_s=self.action_cooldown_s,
            like_cooldown_s=self.like_cooldown_s,
            neutral_hold_s=self.neutral_hold_s,
            hold_toggle_s=self.hold_toggle_s,
            stable_frames=self.stable_frames,
            return_lockout_s=self.return_lockout_s,
            static_hold_s=self.static_hold_s,
            palm_swipes=self.palm_swipes,
        )

    def update(self, values: dict) -> dict:
        """Apply known keys with type coercion and clamping; returns what changed."""
        changed = {}
        for f in fields(self):
            if f.name not in values:
                continue
            raw = values[f.name]
            try:
                if f.type in ("bool", bool):
                    val = raw if isinstance(raw, bool) else str(raw).lower() in ("1", "true", "yes", "on")
                elif f.type in ("int", int):
                    val = int(round(float(raw)))
                else:
                    val = float(raw)
            except (TypeError, ValueError):
                log.warning("Ignoring invalid value for %s: %r", f.name, raw)
                continue
            if f.name in LIMITS:
                lo, hi = LIMITS[f.name]
                val = type(val)(min(hi, max(lo, val)))
            if getattr(self, f.name) != val:
                setattr(self, f.name, val)
                changed[f.name] = val
        return changed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        if SETTINGS_FILE.exists():
            try:
                s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                log.warning("Could not read %s (%s); using defaults", SETTINGS_FILE.name, e)
        return s

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except OSError as e:
            log.warning("Could not save settings: %s", e)
