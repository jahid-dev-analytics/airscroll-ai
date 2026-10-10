"""Gesture engine: turns a stream of per-frame landmarks into discrete actions.

Safety rules implemented here (all unit-tested in tests/test_engine.py):

* A pose must be seen for `stable_frames` consecutive frames before it counts.
* Static gestures (one finger = next, two fingers = previous, fist = pause/play,
  thumb up = like) fire after being held for `static_hold_s`, once per showing: the
  pose must change before it can fire again.
* Open-palm flicks are optional (`palm_swipes`). When enabled, swipes only arm after the open palm has been held still for `neutral_hold_s`
  (so raising your hand into view never scrolls), and must re-arm the same way
  after every swipe, so one movement can only ever produce one scroll.
* A swipe in the opposite direction within `return_lockout_s` is treated as
  the hand returning to its start position and ignored.
* `action_cooldown_s` is the minimum gap between any two actions, and likes have
  their own longer `like_cooldown_s`.
* Holding a still open palm for `hold_toggle_s` toggles control on/off. After that,
  downward swipes stay blocked until the palm is released, so lowering your hand is
  safe, while an upward flick (next reel) works straight away.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .gestures import Landmarks, Pose, classify_pose, motion_point, palm_size

# Palm speed (palm sizes per second) below which the hand counts as "still".
STILL_SPEED = 1.2
# How far (palm sizes) the palm may drift during the 2-second hold.
HOLD_TOLERANCE = 0.35
# Speed is measured over at least this much time to smooth landmark jitter.
SPEED_BASELINE_S = 0.12
# Fast flicks blur the hand and the tracker can lose it for a few frames; keep state that long.
LOST_GRACE_S = 0.35


# Static poses and what they do.
STATIC_ACTIONS = {
    Pose.ONE_FINGER: "next",
    Pose.PEACE: "previous",
    Pose.FIST: "toggle_play",
    Pose.THUMB_UP: "like",
}


class Action(str, Enum):
    NEXT = "next"
    PREVIOUS = "previous"
    LIKE = "like"
    TOGGLE_PLAY = "toggle_play"
    TOGGLE_CONTROL = "toggle_control"


ACTION_LABELS = {
    Action.NEXT: "Next",
    Action.PREVIOUS: "Previous",
    Action.LIKE: "Like",
    Action.TOGGLE_PLAY: "Pause / play",
    Action.TOGGLE_CONTROL: "Toggle gesture control",
}


@dataclass
class EngineConfig:
    sensitivity: int = 5            # 1 (needs big movement) .. 10 (small movement)
    action_cooldown_s: float = 0.8
    like_cooldown_s: float = 3.0
    neutral_hold_s: float = 0.3
    hold_toggle_s: float = 2.0
    stable_frames: int = 4
    return_lockout_s: float = 1.0
    swipe_window_s: float = 0.7
    static_hold_s: float = 0.4      # how long a static pose must be held to fire
    palm_swipes: bool = False       # also allow open-palm flicks up/down

    @property
    def swipe_distance(self) -> float:
        """Vertical travel (in palm sizes) needed within `swipe_window_s`."""
        s = min(10, max(1, int(self.sensitivity)))
        return round(1.2 - 0.095 * (s - 1), 3)  # 1 -> 1.2, 5 -> 0.82, 10 -> 0.35


@dataclass
class GestureEvent:
    action: Action
    t: float
    blocked: Optional[str] = None  # reason, when the engine refused to fire it

    @property
    def fired(self) -> bool:
        return self.blocked is None


@dataclass
class _Sample:
    t: float
    x: float
    y: float
    ps: float


class GestureEngine:
    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self._last_action_t = -math.inf
        self._last_like_t = -math.inf
        self._last_swipe_t = -math.inf
        self._last_swipe_dir = 0
        # last time a half-size movement in each direction was seen (-1 up, +1 down)
        self._partial_t = {-1: -math.inf, 1: -math.inf}
        self._lost_since: Optional[float] = None
        self.diagnostics: list[str] = []   # human-readable notes, drained by the app for the log
        self._palm_stats: Optional[dict] = None
        self._reset_hand_state()

    # ------------------------------------------------------------------ state
    def _reset_hand_state(self) -> None:
        self.hand_present = False
        self.raw_pose = Pose.NONE
        self.stable_pose = Pose.NONE
        self._candidate = Pose.NONE
        self._candidate_n = 0
        self._history: deque[_Sample] = deque()
        self._swipe_armed = False
        self._swipes_blocked = False   # set after a hold-toggle until the palm is released
        self._carry_until: Optional[float] = None  # armed flick continuing through motion blur
        self._still_since: Optional[float] = None
        self._latched: Optional[Pose] = None
        self._pose_since = 0.0
        self.pose_progress = 0.0
        self._hold_anchor: Optional[tuple[float, float]] = None
        self._hold_start = 0.0
        self._hold_fired = False
        self.hold_progress = 0.0
        self.speed = 0.0

    def snapshot(self, now: float) -> dict:
        c = self.config
        return {
            "hand": self.hand_present,
            "raw_pose": self.raw_pose.value,
            "pose": self.stable_pose.value,
            "hold_progress": round(self.hold_progress, 3),
            "pose_progress": round(self.pose_progress, 3),
            "swipe_armed": self._swipe_armed,
            "cooldown_left": round(max(0.0, c.action_cooldown_s - (now - self._last_action_t)), 2),
            "like_cooldown_left": round(max(0.0, c.like_cooldown_s - (now - self._last_like_t)), 2),
        }

    # ----------------------------------------------------------------- update
    def update(self, t: float, landmarks: Optional[Landmarks]) -> list[GestureEvent]:
        events: list[GestureEvent] = []
        if landmarks is None:
            if self.hand_present:
                if self._lost_since is None:
                    self._lost_since = t
                    if self._palm_stats is not None:
                        self._palm_stats["dropouts"] += 1
                elif t - self._lost_since > LOST_GRACE_S:
                    self._end_palm_session("hand left view")
                    self._reset_hand_state()
                    self._lost_since = None
            return events

        self._lost_since = None
        self.hand_present = True
        raw = classify_pose(landmarks)
        self.raw_pose = raw
        if raw == self._candidate:
            self._candidate_n += 1
        else:
            self._candidate, self._candidate_n = raw, 1
        if self._candidate_n >= max(1, self.config.stable_frames) and raw != self.stable_pose:
            self._on_pose_change(raw, t)

        ps = palm_size(landmarks)
        cx, cy = motion_point(landmarks)
        pose = self.stable_pose

        if self._carry_until is not None:
            if pose == Pose.OTHER and t < self._carry_until:
                self._track_palm(t, cx, cy, ps, events, hold=False)
                return events
            self._carry_until = None
            self._end_palm_session("pose changed to other")
            self._reset_motion()
        self.pose_progress = 0.0
        if pose == Pose.OPEN_PALM:
            self._track_palm(t, cx, cy, ps, events)
        elif pose in STATIC_ACTIONS and self._latched != pose:
            held = t - self._pose_since
            self.pose_progress = min(1.0, held / max(self.config.static_hold_s, 0.01))
            if held >= self.config.static_hold_s:
                self._latched = pose
                self._try_emit(Action(STATIC_ACTIONS[pose]), t, events)
        return events

    def _on_pose_change(self, new: Pose, t: float = 0.0) -> None:
        old, self.stable_pose = self.stable_pose, new
        self._pose_since = t
        if new != self._latched:
            self._latched = None
        # Fingers blur during a fast flick and the palm can read as "other" for a few
        # frames: keep tracking an armed flick through that instead of cancelling it.
        if old == Pose.OPEN_PALM and new == Pose.OTHER and self._swipe_armed and self.config.palm_swipes:
            self._carry_until = t + self.config.swipe_window_s
            return
        if new == Pose.OPEN_PALM and self._carry_until is not None:
            self._carry_until = None
            return
        if old == Pose.OPEN_PALM or self._carry_until is not None:
            self._end_palm_session(f"pose changed to {new.value}")
        self._carry_until = None
        self._reset_motion()

    def _reset_motion(self) -> None:
        self._history.clear()
        self._still_since = None
        self._hold_anchor = None
        self._hold_fired = False
        self.hold_progress = 0.0
        # A freshly shown palm must first be held still (neutral) before swiping.
        self._swipe_armed = False
        self._swipes_blocked = False

    # ---------------------------------------------------------- palm motion
    def _speed(self, t: float, cx: float, cy: float, ps: float) -> float:
        ref = None
        for s in reversed(self._history):
            if t - s.t >= SPEED_BASELINE_S:
                ref = s
                break
        if ref is None:
            return 0.0 if len(self._history) < 2 else self.speed
        return math.hypot(cx - ref.x, cy - ref.y) / ps / (t - ref.t)

    def _track_palm(self, t: float, cx: float, cy: float, ps: float, events: list,
                    hold: bool = True) -> None:
        c = self.config
        if self._palm_stats is None:
            self._palm_stats = {"t0": t, "t1": t, "armed": False, "up": 0.0, "down": 0.0, "dropouts": 0}
        self._palm_stats["t1"] = t
        self.speed = self._speed(t, cx, cy, ps)
        h = self._history
        h.append(_Sample(t, cx, cy, ps))
        while h and t - h[0].t > max(c.swipe_window_s, SPEED_BASELINE_S * 2):
            h.popleft()

        # Re-arm swipes only after the hand has been still for the neutral time.
        if not self._swipe_armed:
            if self.speed < STILL_SPEED:
                if self._still_since is None:
                    self._still_since = t
                if t - self._still_since >= c.neutral_hold_s:
                    self._swipe_armed = True
                    h.clear()
                    h.append(_Sample(t, cx, cy, ps))
            else:
                self._still_since = None

        if hold:
            self._update_hold(t, cx, cy, ps, events)

        if not c.palm_swipes or not self._swipe_armed or len(h) < 2:
            return
        start = next((s for s in h if t - s.t <= c.swipe_window_s), h[0])
        # Scale by the hand size at the start: a wrist flick stretches the measured palm mid-move.
        dy = (cy - start.y) / start.ps
        dx = (cx - start.x) / start.ps
        if self._palm_stats is not None:
            st = self._palm_stats
            st["armed"] = True
            st["up"] = max(st["up"], -dy)
            st["down"] = max(st["down"], dy)
        vertical = abs(dy) >= 1.5 * abs(dx)
        if vertical and abs(dy) >= 0.5 * c.swipe_distance:
            self._partial_t[-1 if dy < 0 else 1] = t
        if abs(dy) < c.swipe_distance or not vertical:
            return

        direction = -1 if dy < 0 else 1           # -1 = hand moved up
        action = Action.NEXT if direction < 0 else Action.PREVIOUS
        self._swipe_armed = False
        self._still_since = None
        h.clear()
        self._hold_anchor = None
        self.hold_progress = 0.0
        if direction > 0 and self._swipes_blocked:
            events.append(GestureEvent(action, t, blocked="hand lowering after control toggle"))
            return
        # The hand coming back from a (possibly too small) flick the other way is not a swipe.
        if t - self._partial_t[-direction] < c.return_lockout_s or (
            self._last_swipe_dir
            and direction != self._last_swipe_dir
            and t - self._last_swipe_t < c.return_lockout_s
        ):
            events.append(GestureEvent(action, t, blocked="return stroke ignored"))
            return
        self._last_swipe_t, self._last_swipe_dir = t, direction
        self._try_emit(action, t, events)

    def _end_palm_session(self, reason: str) -> None:
        st, self._palm_stats = self._palm_stats, None
        if st is None or not self.config.palm_swipes:
            return
        need = self.config.swipe_distance
        if not st["armed"]:
            note = "never held still long enough to arm a swipe"
        else:
            note = (f"biggest flick up {st['up']:.2f}, down {st['down']:.2f} palm-heights "
                    f"(needed {need:.2f})")
        self.diagnostics.append(
            f"Palm seen {st['t1'] - st['t0']:.1f} s: {note}; tracking drop-outs {st['dropouts']}; {reason}"
        )

    def _update_hold(self, t: float, cx: float, cy: float, ps: float, events: list) -> None:
        if self._hold_fired:
            self.hold_progress = 1.0
            return
        if self._hold_anchor is None or math.hypot(
            cx - self._hold_anchor[0], cy - self._hold_anchor[1]
        ) / ps > HOLD_TOLERANCE:
            self._hold_anchor = (cx, cy)
            self._hold_start = t
        self.hold_progress = min(1.0, (t - self._hold_start) / max(self.config.hold_toggle_s, 0.1))
        if self.hold_progress >= 1.0:
            self._hold_fired = True
            self._swipes_blocked = True   # lowering the hand afterwards must not go back a reel
            events.append(GestureEvent(Action.TOGGLE_CONTROL, t))

    # --------------------------------------------------------------- output
    def _try_emit(self, action: Action, t: float, events: list) -> None:
        c = self.config
        if action == Action.LIKE and t - self._last_like_t < c.like_cooldown_s:
            events.append(GestureEvent(action, t, blocked="like cooldown"))
        elif t - self._last_action_t < c.action_cooldown_s:
            events.append(GestureEvent(action, t, blocked="cooldown"))
        else:
            self._last_action_t = t
            if action == Action.LIKE:
                self._last_like_t = t
            events.append(GestureEvent(action, t))
