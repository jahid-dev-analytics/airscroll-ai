"""WebSocket link to the AirScroll browser extension.

The extension reports whether Instagram is the active tab of the focused browser
window, and executes actions inside the Instagram page. This side only *sends*
actions when that report says Instagram is in front; the extension re-checks the
real tab state again before acting, so a stale report can never misfire.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Callable, Optional

from aiohttp import WSMsgType, web

log = logging.getLogger(__name__)

EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://")


class ExtensionBridge:
    def __init__(self, on_log: Callable[[str, str], None], on_emergency: Callable[[], None]):
        self._on_log = on_log
        self._on_emergency = on_emergency
        self._ws: Optional[web.WebSocketResponse] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.instagram_focused = False
        self.page: Optional[str] = None
        self.version: Optional[str] = None
        self._ids = itertools.count(1)
        self._pending: dict[int, str] = {}

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    def state(self) -> dict:
        return {
            "connected": self.connected,
            "instagram": self.connected and self.instagram_focused,
            "page": self.page if self.connected else None,
            "version": self.version,
        }

    # ------------------------------------------------------------ websocket
    async def handle(self, request: web.Request) -> web.StreamResponse:
        origin = request.headers.get("Origin", "")
        if not origin.startswith(EXTENSION_ORIGINS):
            log.warning("Rejected extension socket from origin %r", origin)
            raise web.HTTPForbidden(text="extension origin required")
        self.loop = asyncio.get_running_loop()
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        if self.connected:
            await self._ws.close()
        self._ws = ws
        self._on_log("Browser extension connected", "ok")
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        self._on_message(json.loads(msg.data))
                    except (ValueError, TypeError, AttributeError):
                        log.warning("Bad message from extension: %.200s", msg.data)
        finally:
            if self._ws is ws:
                self._ws = None
                self.instagram_focused = False
                self.page = None
                self._pending.clear()
                self._on_log("Browser extension disconnected", "warn")
        return ws

    def _on_message(self, data: dict) -> None:
        kind = data.get("type")
        if kind == "hello":
            self.version = str(data.get("version", "?"))
        elif kind == "focus":
            was = self.instagram_focused
            self.instagram_focused = bool(data.get("instagram"))
            self.page = data.get("page")
            if was != self.instagram_focused:
                log.info("Instagram focused: %s (%s)", self.instagram_focused, self.page)
        elif kind == "result":
            action = self._pending.pop(int(data.get("id", 0)), "action")
            detail = str(data.get("detail", ""))[:160]
            if data.get("ok"):
                self._on_log(f"Instagram: {detail or action}", "ok")
            else:
                self._on_log(f"Instagram could not {action}: {detail}", "warn")
        elif kind == "emergency":
            self._on_log("Emergency stop pressed in browser (Alt+Shift+S)", "error")
            self._on_emergency()

    # -------------------------------------------------------------- actions
    def send_action(self, action: str) -> tuple[bool, str]:
        """Thread-safe. Returns (sent, reason)."""
        ws, loop = self._ws, self.loop
        if ws is None or ws.closed or loop is None:
            return False, "browser extension not connected"
        if not self.instagram_focused:
            return False, "Instagram is not the active tab"
        msg_id = next(self._ids)
        self._pending[msg_id] = action
        if len(self._pending) > 50:                       # drop results that never came back
            self._pending.pop(next(iter(self._pending)))
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "action", "id": msg_id, "action": action}), loop
        )
        return True, "sent"

    async def close(self) -> None:
        if self.connected:
            await self._ws.close()
