"""Local web server (127.0.0.1 only): dashboard, live preview, and WebSockets."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import WSMsgType, web

from .app import AirScrollApp

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
STATE_INTERVAL_S = 0.1
APP_KEY = web.AppKey("airscroll", AirScrollApp)
SOCKETS_KEY = web.AppKey("sockets", set)
TASK_KEY = web.AppKey("broadcaster", asyncio.Task)


def _same_origin(request: web.Request) -> bool:
    """Blocks other websites from talking to (or embedding) the local dashboard."""
    origin = request.headers.get("Origin")
    if origin is not None:
        host = request.host
        return origin in (f"http://{host}", f"http://127.0.0.1:{host.rsplit(':', 1)[-1]}",
                          f"http://localhost:{host.rsplit(':', 1)[-1]}")
    return request.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def video(request: web.Request) -> web.StreamResponse:
    """MJPEG preview stream. Ends as soon as the camera stops."""
    if not _same_origin(request):
        raise web.HTTPForbidden()
    app: AirScrollApp = request.app[APP_KEY]
    resp = web.StreamResponse(headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame",
        "Cache-Control": "no-store",
    })
    await resp.prepare(request)
    last_id = -1
    loop = asyncio.get_running_loop()
    try:
        while app.camera.running or app.camera_starting:
            last_id, jpeg = await loop.run_in_executor(None, app.camera.wait_frame, last_id, 1.0)
            if jpeg is None:
                continue
            await resp.write(
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
            )
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return resp


async def dashboard_ws(request: web.Request) -> web.WebSocketResponse:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="dashboard must be opened from this computer")
    app: AirScrollApp = request.app[APP_KEY]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    request.app[SOCKETS_KEY].add(ws)
    loop = asyncio.get_running_loop()
    try:
        await ws.send_json({"type": "state", "state": app.state(), "events": list(app.events)})
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except ValueError:
                continue
            cmd = data.get("cmd")
            if cmd == "start_camera":
                await loop.run_in_executor(None, app.start_camera)
            elif cmd == "stop_camera":
                await loop.run_in_executor(None, app.stop_camera)
            elif cmd == "enable":
                app.set_control(True)
            elif cmd == "disable":
                app.set_control(False)
            elif cmd == "emergency_stop":
                await loop.run_in_executor(None, app.emergency_stop, "dashboard")
            elif cmd == "settings" and isinstance(data.get("values"), dict):
                app.update_settings(data["values"])
            elif cmd == "quit":
                app.log_event("Shutting downâ€¦", "warn")
                loop.call_later(0.3, _request_exit)
    finally:
        request.app[SOCKETS_KEY].discard(ws)
    return ws


def _request_exit() -> None:
    raise web.GracefulExit()


async def _broadcast_state(webapp: web.Application) -> None:
    app: AirScrollApp = webapp[APP_KEY]
    last_event = 0
    while True:
        await asyncio.sleep(STATE_INTERVAL_S)
        sockets = webapp[SOCKETS_KEY]
        if not sockets:
            continue
        new_events = [e for e in app.events if e["id"] > last_event]
        if new_events:
            last_event = new_events[-1]["id"]
        payload = {"type": "state", "state": app.state(), "events": new_events}
        for ws in list(sockets):
            try:
                await ws.send_json(payload)
            except (ConnectionResetError, RuntimeError):
                sockets.discard(ws)


def _quiet_disconnects(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    # Windows logs a traceback whenever a browser tab closes a connection abruptly; it is harmless.
    if isinstance(context.get("exception"), ConnectionResetError):
        return
    loop.default_exception_handler(context)


async def _on_startup(webapp: web.Application) -> None:
    asyncio.get_running_loop().set_exception_handler(_quiet_disconnects)
    webapp[TASK_KEY] = asyncio.create_task(_broadcast_state(webapp))


async def _on_shutdown(webapp: web.Application) -> None:
    webapp[TASK_KEY].cancel()
    app: AirScrollApp = webapp[APP_KEY]
    await asyncio.get_running_loop().run_in_executor(None, app.shutdown)
    await app.bridge.close()
    for ws in list(webapp[SOCKETS_KEY]):
        await ws.close()
    log.info("Shut down cleanly: camera released")


async def _no_cache_static(request: web.Request, response: web.StreamResponse) -> None:
    # The dashboard is local and tiny; never let the browser show a stale version after an update.
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"


def create_web_app(app: AirScrollApp) -> web.Application:
    webapp = web.Application()
    webapp[APP_KEY] = app
    webapp[SOCKETS_KEY] = set()
    webapp.router.add_get("/", index)
    webapp.router.add_get("/health", health)
    webapp.router.add_get("/video.mjpg", video)
    webapp.router.add_get("/ws", dashboard_ws)
    webapp.router.add_get("/ext", app.bridge.handle)
    webapp.router.add_static("/static/", WEB_DIR)
    webapp.on_response_prepare.append(_no_cache_static)
    webapp.on_startup.append(_on_startup)
    webapp.on_shutdown.append(_on_shutdown)
    return webapp
