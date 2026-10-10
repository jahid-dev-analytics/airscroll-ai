"""HTTP/WebSocket layer: dashboard served, foreign websites and non-extensions rejected."""
import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from airscroll.app import AirScrollApp
from airscroll.config import Settings
from airscroll.server import create_web_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("airscroll.config.SETTINGS_FILE", tmp_path / "settings.json")
    loop = asyncio.new_event_loop()
    app = AirScrollApp(Settings())
    c = TestClient(TestServer(create_web_app(app)), loop=loop)
    loop.run_until_complete(c.start_server())
    yield c, loop, app
    loop.run_until_complete(c.close())
    loop.close()


def test_dashboard_is_served(client):
    c, loop, _ = client

    async def go():
        r = await c.get("/")
        assert r.status == 200 and "AirScroll AI" in await r.text()
        assert (await c.get("/static/app.js")).status == 200
    loop.run_until_complete(go())


def test_foreign_website_cannot_open_dashboard_socket(client):
    c, loop, _ = client

    async def go():
        r = await c.get("/ws", headers={"Origin": "https://evil.example", "Upgrade": "websocket",
                                        "Connection": "Upgrade", "Sec-WebSocket-Version": "13",
                                        "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
        assert r.status == 403
    loop.run_until_complete(go())


def test_foreign_website_cannot_embed_camera_preview(client):
    c, loop, _ = client

    async def go():
        r = await c.get("/video.mjpg", headers={"Sec-Fetch-Site": "cross-site"})
        assert r.status == 403
    loop.run_until_complete(go())


def test_only_extensions_may_use_extension_socket(client):
    c, loop, _ = client

    async def go():
        r = await c.get("/ext", headers={"Origin": "https://www.instagram.com", "Upgrade": "websocket",
                                         "Connection": "Upgrade", "Sec-WebSocket-Version": "13",
                                         "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
        assert r.status == 403
    loop.run_until_complete(go())


def test_extension_round_trip(client):
    """Fake extension: hello + focus, then the app sends an action and gets a result."""
    c, loop, app = client

    async def go():
        ws = await c.ws_connect("/ext", headers={"Origin": "chrome-extension://abc"})
        await ws.send_json({"type": "hello", "version": "1.0.0"})
        await ws.send_json({"type": "focus", "instagram": True, "page": "reels"})
        for _ in range(50):
            if app.bridge.instagram_focused:
                break
            await asyncio.sleep(0.02)
        assert app.bridge.state() == {"connected": True, "instagram": True, "page": "reels", "version": "1.0.0"}

        app.set_control(True)
        sent, _ = app.bridge.send_action("next")
        assert sent
        msg = await ws.receive_json(timeout=2)
        assert msg["type"] == "action" and msg["action"] == "next"
        await ws.send_json({"type": "result", "id": msg["id"], "ok": True, "detail": "Next reel"})

        await ws.send_json({"type": "emergency"})
        for _ in range(100):
            if not app.control_enabled:
                break
            await asyncio.sleep(0.02)
        assert not app.control_enabled
        texts = [e["text"] for e in app.events]
        assert "Instagram: Next reel" in texts
        await ws.close()
        for _ in range(50):
            if not app.bridge.connected:
                break
            await asyncio.sleep(0.02)
        assert not app.bridge.connected
    loop.run_until_complete(go())
