"""Behavioural tests for the gesture engine, driven at 30 fps with synthetic hands.

"three" (three fingers up) is a hand that is not any gesture, used as a neutral pose.
"""
from airscroll.engine import Action, EngineConfig, GestureEngine
from tests.handgen import make_hand

FPS = 30
DT = 1 / FPS


class Sim:
    def __init__(self, **cfg):
        self.engine = GestureEngine(EngineConfig(**cfg))
        self.t = 0.0
        self.y = 0.5
        self.fired = []
        self.blocked = []

    def frames(self, n, shape="open_palm", dy_per_frame=0.0, present=True):
        for _ in range(n):
            self.t += DT
            self.y += dy_per_frame
            lm = make_hand(shape, cy=self.y) if present else None
            for ev in self.engine.update(self.t, lm):
                (self.fired if ev.fired else self.blocked).append(ev)
        return self

    def hold(self, seconds, shape="open_palm"):
        return self.frames(round(seconds * FPS), shape)

    def move(self, distance, seconds, shape="open_palm"):
        n = max(1, round(seconds * FPS))
        return self.frames(n, shape, dy_per_frame=distance / n)

    def away(self, seconds=0.5):
        return self.frames(round(seconds * FPS), present=False)

    def actions(self):
        return [e.action for e in self.fired]


def Flicks(**cfg):
    """Engine with the optional open-palm flicks switched on."""
    return Sim(palm_swipes=True, **cfg)


# ------------------------------------------------- one / two fingers, fist
def test_one_finger_is_next_two_fingers_is_previous_fist_is_pause():
    assert Sim().hold(1.0, "pointing").actions() == [Action.NEXT]
    assert Sim().hold(1.0, "peace").actions() == [Action.PREVIOUS]
    assert Sim().hold(1.0, "fist").actions() == [Action.TOGGLE_PLAY]
    assert Sim().hold(1.0, "thumb_up").actions() == [Action.LIKE]


def test_gesture_must_be_held_for_static_hold_time():
    # 4 frames to stabilise + 0.4 s hold; a 0.3 s glimpse is not enough
    assert Sim(static_hold_s=0.4).hold(0.3, "pointing").hold(0.5, "three").actions() == []
    assert Sim(static_hold_s=0.4).hold(0.6, "pointing").actions() == [Action.NEXT]


def test_holding_a_gesture_fires_only_once():
    assert Sim().hold(5.0, "pointing").actions() == [Action.NEXT]


def test_showing_the_gesture_again_repeats_it():
    s = Sim().hold(0.8, "pointing").away().hold(0.8, "pointing").hold(0.6, "three").hold(0.8, "pointing")
    assert s.actions() == [Action.NEXT, Action.NEXT, Action.NEXT]


def test_switching_between_one_and_two_fingers():
    s = Sim().hold(0.8, "pointing").hold(0.8, "peace").hold(0.8, "pointing")
    assert s.actions() == [Action.NEXT, Action.PREVIOUS, Action.NEXT]


def test_fist_toggles_pause_each_time_it_is_shown():
    s = Sim().hold(0.8, "fist").hold(0.6, "three").hold(0.8, "fist")
    assert s.actions() == [Action.TOGGLE_PLAY, Action.TOGGLE_PLAY]


def test_open_palm_and_unknown_hands_do_nothing_by_default():
    s = Sim().hold(1.5).move(-0.3, 0.25).hold(1.0, "three")
    assert s.actions() == []


def test_progress_ring_fills_while_holding():
    s = Sim(static_hold_s=1.0).hold(0.6, "pointing")
    assert 0.2 < s.engine.pose_progress < 1.0


def test_like_needs_release_and_respects_like_cooldown():
    s = Sim(like_cooldown_s=3.0).hold(0.8, "thumb_up").hold(0.6, "three").hold(0.8, "thumb_up")
    assert s.actions() == [Action.LIKE]          # second like is within 3 s
    assert any(e.blocked == "like cooldown" for e in s.blocked)
    s.hold(2.5, "three").hold(0.8, "thumb_up")
    assert s.actions() == [Action.LIKE, Action.LIKE]


def test_global_cooldown_between_different_gestures():
    s = Sim(action_cooldown_s=3.0).hold(0.6, "pointing").hold(0.6, "peace")
    assert s.actions() == [Action.NEXT]
    assert any(e.blocked == "cooldown" for e in s.blocked)


def test_flicker_shorter_than_stable_frames_is_ignored():
    s = Sim(stable_frames=4).hold(0.8, "three").frames(2, "pointing").hold(0.8, "three")
    assert s.actions() == []


def test_hand_leaving_keeps_cooldowns():
    s = Sim(action_cooldown_s=5.0).hold(0.8, "pointing").away().hold(0.8, "pointing")
    assert s.actions() == [Action.NEXT]
    assert not Sim().away().engine.hand_present


def test_brief_tracking_dropout_does_not_retrigger():
    # hand lost for 3 frames while holding one finger: same showing, no second NEXT
    s = Sim().hold(0.8, "pointing").frames(3, present=False).hold(0.8, "pointing")
    assert s.actions() == [Action.NEXT]


# ------------------------------------------------------- hold to toggle
def test_still_open_palm_toggles_control_once():
    s = Sim(hold_toggle_s=2.0).hold(1.5)
    assert s.actions() == []
    s.hold(4.0)
    assert s.actions() == [Action.TOGGLE_CONTROL]


def test_hold_progress_resets_when_hand_moves():
    s = Sim().hold(1.5)
    assert s.engine.hold_progress > 0.5
    s.move(-0.25, 0.25)
    assert s.engine.hold_progress < 0.3


# ------------------------------------------- optional open-palm flicks
def test_palm_flick_up_is_next_and_down_is_previous():
    assert Flicks().hold(0.5).move(-0.25, 0.25).actions() == [Action.NEXT]
    assert Flicks().hold(0.5).move(+0.25, 0.25).actions() == [Action.PREVIOUS]


def test_raising_hand_into_view_does_not_scroll():
    assert Flicks().move(-0.4, 0.3).actions() == []


def test_one_long_movement_scrolls_only_once():
    assert Flicks().hold(0.5).move(-0.6, 0.6).actions() == [Action.NEXT]


def test_return_stroke_after_swipe_is_ignored():
    s = Flicks(return_lockout_s=1.0).hold(0.5).move(-0.25, 0.25).hold(0.5).move(+0.25, 0.2)
    assert s.actions() == [Action.NEXT]
    assert any(e.blocked == "return stroke ignored" for e in s.blocked)


def test_return_from_too_small_up_flick_is_not_previous():
    assert Flicks(sensitivity=5).hold(0.5).move(-0.08, 0.2).move(+0.2, 0.2).actions() == []


def test_second_swipe_after_neutral_pause_works():
    s = Flicks().hold(0.5).move(-0.25, 0.25).hold(1.2).move(-0.25, 0.25)
    assert s.actions() == [Action.NEXT, Action.NEXT]


def test_slow_drift_is_not_a_swipe():
    assert Action.NEXT not in Flicks().hold(0.5).move(-0.25, 2.5).actions()


def test_sensitivity_changes_required_distance():
    small = 0.12  # ~0.8 palm sizes at scale 0.15
    assert Flicks(sensitivity=10).hold(0.5).move(-small, 0.2).actions() == [Action.NEXT]
    assert Flicks(sensitivity=1).hold(0.5).move(-small, 0.2).actions() == []


def test_lowering_hand_after_toggle_does_not_scroll():
    s = Flicks().hold(2.5).move(+0.4, 0.3).away()
    assert s.actions() == [Action.TOGGLE_CONTROL]


def test_flick_up_right_after_toggle_works():
    assert Flicks().hold(2.5).move(-0.25, 0.25).actions() == [Action.TOGGLE_CONTROL, Action.NEXT]


def test_flick_survives_brief_tracking_dropout():
    s = Flicks().hold(0.5).move(-0.12, 0.12).frames(3, present=False)
    s.y -= 0.08
    s.move(-0.06, 0.06)
    assert s.actions() == [Action.NEXT]


def test_flick_survives_fingers_blurring_into_other_pose():
    s = Flicks().hold(0.5).move(-0.05, 0.05).move(-0.12, 0.2, "three")
    assert s.actions() == [Action.NEXT]


def test_wrist_flick_counts_even_though_wrist_stays_put():
    engine = GestureEngine(EngineConfig(sensitivity=9, palm_swipes=True))
    t, fired = 0.0, []
    for i in range(40):                      # still, then fingers swing up 0.08 over 6 frames
        t += DT
        lift = min(max(i - 30, 0), 6) * 0.08 / 6
        lm = make_hand("open_palm")
        lm = [lm[0]] + [(x, y - lift) for x, y in lm[1:]]
        fired += [e.action for e in engine.update(t, lm) if e.fired]
    assert fired == [Action.NEXT]


def test_diagnostics_report_short_flicks():
    s = Flicks().hold(0.5).move(-0.05, 0.2).away(0.5)
    notes = s.engine.diagnostics
    assert len(notes) == 1 and "biggest flick up" in notes[0] and "hand left view" in notes[0]
