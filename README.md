# AirScroll AI: Hand Gesture Instagram Controller

Control Instagram Reels (and the home feed) in your desktop browser with hand gestures in
front of your laptop webcam. Hand tracking runs **entirely on your computer**, and webcam
frames are never recorded, stored or uploaded.

| Gesture | Action |
|---|---|
| ☝️ **One finger** up (index) | Scroll up: next reel / next post |
| ✌️ **Two fingers** up (index + middle) | Scroll down: previous reel / previous post |
| ✊ Closed **fist** | Pause the video (show a fist again to resume) |
| 👍 Thumb up | Like (only ever *likes*, never unlikes; 3 s like cooldown) |
| ✋ Open palm held **still** for 2 s | Turn gesture control on |

Hold a gesture until the ring on the dashboard fills (0.4 s by default). Each gesture fires
**once** per showing: to go two reels forward, show one finger, drop or change your hand,
then show one finger again. Open-palm flicks up/down are still available under
*Settings → Advanced* but are off by default.
---|---|
| ✋⬆ Open palm, quick flick **up** | Next reel / next post |
| ✋⬇ Open palm, quick flick **down** | Previous reel / previous post |
| 👍 Thumb up | Like (only ever *likes*, never unlikes; 3 s like cooldown) |
| ✌️ Peace sign | Pause / resume the video in view |
| ✊ Closed fist | Pauses all gestures while held (+0.6 s after); use it to reposition your hand |
| ✋⏱ Open palm held **still** for 2 s | Turn gesture control on / off |

---

## 1. How it works

```
 Webcam ─► OpenCV ─► MediaPipe HandLandmarker ─► Gesture engine ─► Safety gate ─► WebSocket ─► Browser extension ─► Instagram tab
           (capture)   (21 landmarks, local)      (poses, swipes,   (control on?   (127.0.0.1   (re-checks Instagram is
                                                   cooldowns)        Instagram       only)        the active tab, then uses
                                                                     in front?)                   the page's own scroll/buttons)
            └──────────── Python app (python run.py) ── serves the dashboard at http://127.0.0.1:8765 ───┘
```

**Why two parts?** A desktop program that fakes key presses (PyAutoGUI) sends them to
*whatever* window has focus and cannot tell which browser tab is open. A small browser
extension *can* check that Instagram is the active tab of the focused window, and it can
scroll and click inside the page reliably. So the Python app does the vision and the
extension does the Instagram part. Nothing else is involved: no cloud, no Instagram API,
no login automation. You log in to Instagram yourself, as usual.

### Project structure

```
airscroll-ai/
├── run.py                  launcher (python run.py)
├── run.bat / run.sh        start scripts (Windows / macOS-Linux)
├── setup.bat               one-time Windows setup
├── requirements.txt        runtime dependencies
├── requirements-dev.txt    + pytest
├── airscroll/
│   ├── __main__.py         entry point, logging, CLI flags
│   ├── gestures.py         pose classification from landmarks (pure Python)
│   ├── engine.py           stabilisation, swipes, cooldowns, neutral re-arm, hold-to-toggle
│   ├── tracker.py          MediaPipe Tasks HandLandmarker wrapper + model download
│   ├── camera.py           webcam thread, preview rendering, cleanup
│   ├── bridge.py           WebSocket link to the browser extension
│   ├── app.py              wiring + safety gate + dashboard status
│   ├── config.py           settings (settings.json), paths, limits
│   ├── server.py           local web server: dashboard, MJPEG preview, sockets
│   └── web/                dashboard (index.html, app.css, app.js)
├── extension/              Chrome / Edge extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js       connection, active-tab check, emergency shortcut
│   └── content.js          scroll / like / pause inside instagram.com
├── models/                 hand_landmarker.task (downloaded automatically)
├── logs/                   airscroll.log (no images, no landmarks)
└── tests/                  pytest suite + browser harness for content.js
```

---

## 2. Installation (Windows 10/11)

**Requirements:** Python **3.11, 3.12 or 3.13** ([python.org](https://www.python.org/downloads/), tick
*"Add python.exe to PATH"*), Google Chrome or Microsoft Edge (version 116+), and a webcam.

1. **Install the Python app:** double-click **`setup.bat`**. It creates `.venv`, installs the
   packages and downloads Google's MediaPipe hand model (about 8 MB). This takes a few minutes the first time.

   Or do it manually in a terminal inside the `airscroll-ai` folder:

   ```bash
   python -m venv .venv
   ```
   ```bash
   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

2. **Load the browser extension** (one time):
   1. Open `chrome://extensions` (Edge: `edge://extensions`).
   2. Turn on **Developer mode** (top-right in Chrome, left sidebar in Edge).
   3. Click **Load unpacked** and choose the **`airscroll-ai\extension`** folder.
   4. Optional: pin the extension. Its badge shows **ON** while it is connected to the app.

3. **Windows camera permission:** *Settings → Privacy & security → Camera*: turn on **Camera
   access** and **Let desktop apps access your camera**.

## 3. Launching

Double-click **`run.bat`** (or run `.venv\Scripts\python.exe run.py`). The dashboard opens at
**http://127.0.0.1:8765**. Keep the black console window open; closing it quits the app.

Options: `--no-browser` (don't open the dashboard), `--verbose` (debug logs),
`--port N` (if you change the port, also edit `SERVER_URL` at the top of `extension/background.js`
and reload the extension).

## 4. Step-by-step usage

1. Open **instagram.com** in Chrome/Edge and **log in normally**. Go to **Reels**
   (`instagram.com/reels/`) or stay on the home feed.
2. Put the AirScroll dashboard in a **separate window** (drag its tab out) beside Instagram.
   On a small screen you can minimise it once everything is green.
3. In the dashboard click **Start Camera**. The camera turns on only now, and the red **CAMERA LIVE**
   badge shows whenever it is on.
4. Check the status chips: **Camera**, **Hand** and **Extension** should be green.
5. Click **Enable Gesture Control**, or hold an open palm still for 2 s and watch the ring fill.
6. **Click once inside the Instagram window.** Actions only go through when Instagram is the
   active tab of the focused window (the *Instagram in front* chip turns green). This is a
   safety feature: gestures can never act on another site or app.
7. Gesture! A small pink toast in the Instagram page confirms each action, and the dashboard's
   **Activity** list shows what was recognized, sent, skipped and why.

**Stopping:** **Stop Camera** releases the webcam immediately. **EMERGENCY STOP** (or **Esc** in
the dashboard, or **Alt+Shift+S** anywhere in Chrome/Edge) disables control *and* turns the
camera off. **Quit app** (or closing the console) shuts everything down and releases the camera.

### Technique that works

* Sit 50–80 cm from the camera with your hand roughly at chest-to-face height, in good front light.
* **Swipe:** show an open palm, **hold still ~0.3 s** (the *Swipe armed* chip turns green), then
  make a **quick** flick up or down of about a hand's length. Slow movements never scroll.
* **Return** your hand **slowly**, or close it into a **fist** while moving it back. A return flick
  within 1 s is ignored anyway.
* Thumb up / peace: show the sign clearly for a moment. Each fires **once**; to repeat it,
  change pose (or drop your hand) and show it again.

## 5. Gesture calibration

Open the **Settings** card (changes apply instantly and are saved in `settings.json`):

| Problem | Adjust |
|---|---|
| Flicks are ignored | Raise **Swipe sensitivity** (the hint shows the flick distance in palm-heights), or lower **Neutral pause** |
| Scrolls happen by accident | Lower **Swipe sensitivity**, raise **Neutral pause** to 0.5 s, raise **Delay between actions** |
| Two scrolls from one movement | Raise **Delay between actions** (default 0.8 s) |
| Returning the hand goes back a reel | Raise **Ignore return stroke for** (Advanced), or return with a fist |
| Pose flickers / wrong pose shown | Raise **Frames to confirm a pose** (Advanced), improve lighting |
| Hand not detected | Lower **Hand detection confidence** (Advanced; applies on next camera start) |
| Wrong camera (e.g. IR camera) | Change **Camera number** to 1 or 2 (Advanced), then Stop/Start camera |

The pose under your hand is shown live in the preview and in the status card, so you can see
exactly what the app reads before it acts. Test with control **disabled** first: the Activity
list says *"recognized, ignored (control disabled)"* without touching Instagram.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| **"No camera available at index 0"** | Turn on camera access for desktop apps (step 3 above); close Teams/Zoom/Camera app; try Camera number 1 |
| Camera opens but image is black | Another app holds the camera, or a privacy shutter/F-key camera switch is on |
| **Extension** chip red | App not running, or extension not loaded/enabled. Open `chrome://extensions` and click the reload icon on *AirScroll AI Bridge*. It retries every few seconds. |
| **Instagram in front** chip stays amber | Click inside the Instagram tab. The dashboard's own window being focused counts as "not Instagram". |
| "page not ready… reload the Instagram tab" | The tab was open before the extension was installed: press F5 on Instagram |
| "no Like button found" | Your Instagram language isn't English. Add your language's label to `LIKE_LABELS` / `UNLIKE_LABELS` at the top of `extension/content.js`, then reload the extension |
| "page did not scroll" | You're at the end of the list, or on a single-reel page (`/reel/…` opened from a post). Open `instagram.com/reels/` |
| Port 8765 already in use | AirScroll is already running: open http://127.0.0.1:8765, or close the other copy |
| Low FPS / laggy | Close other heavy apps; plug in the laptop (power-saving throttles the CPU) |
| `pip install mediapipe` fails | Use Python 3.11–3.13 (64-bit). MediaPipe has no builds for 32-bit Python or brand-new Python versions. |

Logs: `logs/airscroll.log` (rotating, text only, with no images or hand data). Run with
`--verbose` for more detail. Extension errors: `chrome://extensions` → *AirScroll AI Bridge* →
*service worker* → Console.

## 7. Privacy and security

* Camera starts **only** when you click Start Camera and stops immediately on Stop / Emergency / Quit.
* Frames are processed in memory by MediaPipe on your CPU. The only image kept is the latest
  preview frame in RAM, which is discarded when the camera stops. Nothing is written to disk or sent anywhere.
* No biometric data is stored: `settings.json` holds only slider values, and the log holds only text events.
* The server listens on **127.0.0.1 only** (not reachable from your network). Other websites
  are refused access to the dashboard socket and the camera preview, and only a browser
  extension may connect to the extension socket.
* No Instagram actions happen while control is disabled, while your fist is closed, or when
  Instagram isn't the active tab of the focused window. The extension re-checks the last
  condition itself just before every action.
* The extension uses Instagram's normal page: no private APIs, no automation of login,
  no requests to Instagram's servers beyond what clicking the page would do.

## 8. macOS and Linux

The Python code is cross-platform. Use `./run.sh` (it creates `.venv` on first run).

* **macOS:** grant camera access to your terminal app (*System Settings → Privacy & Security →
  Camera*) and restart the terminal. The emergency shortcut is **Option+Shift+S**. On Apple Silicon,
  MediaPipe wheels exist for Python 3.11–3.13.
* **Linux:** your user needs access to `/dev/video0` (usually the `video` group). Chrome/Chromium
  or Edge work the same way.
* On Windows the app uses the DirectShow camera backend for fast startup. Other OSes use OpenCV's default.

## 9. Tests

```bash
.venv\Scripts\python.exe -m pytest -q
```

80 automated tests cover pose classification (tilt, distance, jitter), the gesture engine
(single scroll per movement, raise-into-view doesn't scroll, return-stroke lockout, cooldowns,
like cooldown, latching, fist pause, hold-to-toggle, hand leaving), the safety gate (disabled,
not focused, extension missing, emergency stop), settings clamping, the server's origin checks
and a full fake-extension round trip, plus a smoke test of the real MediaPipe model.

**Content-script harness:** `python tests/ext_harness/serve.py`, then open
`http://127.0.0.1:8799/reels/` and run `await run("next")`, `run("like")`, etc. in DevTools.
It loads the real `extension/content.js` against a mock page with the same structure.

## 10. Known limitations (read these)

* **Instagram can change its website at any time.** Scrolling uses generic page scrolling, which is
  fairly robust. Liking depends on Instagram's heart icon label (`aria-label="Like"`/`"Unlike"`)
  and **breaks if Instagram renames it or your UI isn't in English** (see Troubleshooting).
* **Not verified against live Instagram by the developer.** The extension logic was tested in
  Chrome against a mock page that mimics Instagram's structure, but not on a logged-in
  instagram.com. Your first session is the real test. Watch the Activity list, where each
  action reports success or the reason it failed.
* **Pause/resume** controls the HTML video directly. Instagram's own play/pause icon may not
  update to match, and if the browser blocks playback you may need to click the video once.
* **Like** only ever *likes*. Unliking by gesture is intentionally not supported.
* Works in **Chrome / Edge (Chromium 116+)**. Firefox and Safari are not supported (the extension uses Chrome APIs).
* The dashboard must not be the focused window when you gesture (by design). Click into Instagram after using the dashboard.
* One hand at a time. Very dim light, strong backlight, gloves or a hand partly out of frame reduce accuracy.
* Gesture thresholds were tuned with synthetic hand data and unit tests. Expect to adjust
  sensitivity once for your camera, distance and lighting.
* The Instagram mobile app and the Instagram desktop app from the Microsoft Store are not supported; use the website.
