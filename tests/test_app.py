"""Safety gate between recognized gestures and Instagram, plus settings handling."""
import pytest

from airscroll.app import AirScrollApp
from airscroll.config import Settings
from airscroll.engine import Action, GestureEvent


class FakeBridge:
    def __init__(self, connected=True, focused=True):
        self.connected = connected
        self.focused = focused
        self.sent = []
        self.loop = None

    def send_action(self, action):
        if not self.connected:
            return False, "browser extension not connected"
        if not self.focused:
            return False, "Instagram is not the active tab"
        self.sent.append(action)
        return True, "sent"

    def state(self):
        return {"connected": self.connected, "instagram": self.focused, "page": "reels", "version": "t"}


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    monkeypatch.setattr("airscroll.config.SETTINGS_FILE", tmp_path / "settings.json")

    def _make(**bridge_kw):
        bridge = FakeBridge(**bridge_kw)
        return AirScrollApp(Settings(), bridge=bridge), bridge
    return _make


def ev(action, blocked=None):
    return GestureEvent(action, 0.0, blocked)


def test_nothing_is_sent_while_control_disabled(make_app):
    app, bridge = make_app()
    for a in (Action.NEXT, Action.PREVIOUS, Action.LIKE, Action.TOGGLE_PLAY):
        assert app.handle_event(ev(a)) == "ignored:disabled"
    assert bridge.sent == []


def test_sent_only_when_enabled_and_instagram_in_front(make_app):
    app, bridge = make_app(focused=False)
    app.set_control(True)
    assert app.handle_event(ev(Action.NEXT)).startswith("ignored:")
    bridge.focused = True
    assert app.handle_event(ev(Action.NEXT)) == "sent"
    assert bridge.sent == ["next"]


def test_missing_extension_is_reported_not_crashing(make_app):
    app, bridge = make_app(connected=False)
    app.set_control(True)
    assert app.handle_event(ev(Action.LIKE)) == "ignored:browser extension not connected"


def test_blocked_engine_events_never_reach_instagram(make_app):
    app, bridge = make_app()
    app.set_control(True)
    assert app.handle_event(ev(Action.LIKE, blocked="like cooldown")) == "blocked:like cooldown"
    assert bridge.sent == []


def test_palm_hold_toggles_control_without_touching_instagram(make_app):
    app, bridge = make_app()
    app.handle_event(ev(Action.TOGGLE_CONTROL))
    assert app.control_enabled
    assert app.handle_event(ev(Action.TOGGLE_CONTROL)) == "ignored:hold"   # default: hold only turns ON
    assert app.control_enabled
    app.update_settings({"hold_can_disable": True})
    app.handle_event(ev(Action.TOGGLE_CONTROL))
    assert not app.control_enabled
    assert bridge.sent == []


def test_emergency_stop_disables_everything(make_app):
    app, bridge = make_app()
    app.set_control(True)
    app.emergency_stop("test")
    assert not app.control_enabled and not app.camera.running
    assert app.handle_event(ev(Action.NEXT)) == "ignored:disabled"


def test_settings_are_clamped_and_applied_to_engine(make_app):
    app, _ = make_app()
    changed = app.update_settings({"sensitivity": 99, "action_cooldown_s": "0.01",
                                   "mirror_preview": "false", "bogus": 1})
    assert changed == {"sensitivity": 10, "action_cooldown_s": 0.2, "mirror_preview": False}
    assert app.engine.config.sensitivity == 10
    assert app.camera.mirror is False


def test_state_has_status_for_dashboard(make_app):
    app, _ = make_app()
    s = app.state()
    assert s["status"] == "Camera off"
    assert s["camera"]["on"] is False and s["control_enabled"] is False


def test_bad_camera_index_fails_gracefully(make_app):
    app, _ = make_app()
    app.update_settings({"camera_index": 9})
    assert app.start_camera() is False
    assert "camera" in app.camera_error.lower()
    assert app.state()["status"] == "Camera error"
