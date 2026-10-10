# AirScroll AI: Hand Gesture Social Media Controller

Scroll, like and pause videos on **Instagram, Facebook, YouTube, TikTok and LinkedIn** in your
desktop browser with hand gestures in front of your laptop webcam. Hand tracking runs
**entirely on your computer**, and webcam frames are never recorded, stored or uploaded.

| Gesture | Action |
|---|---|
| ☝️ **One finger** up (index) | Scroll up: next video / next post |
| ✌️ **Two fingers** up (index + middle) | Scroll down: previous video / previous post |
| ✊ Closed **fist** | Pause the video (show a fist again to resume) |
| 👍 Thumb up | Like (only ever *likes*, never unlikes; 3 s like cooldown) |
| ✋ Open palm held **still** for 2 s | Turn gesture control on |

Hold a gesture until the ring on the dashboard fills (0.4 s by default). Each gesture fires
**once** per showing: to go two videos forward, show one finger, drop or change your hand,
then show one finger again. Open-palm flicks up/down are also available under
*Settings → Advanced* but are off by default.

### Supported sites

| Site | Short videos | Feed | How "next" works |
|---|---|---|---|
| Instagram | Reels (`/reels/`) | Home feed | Scrolls the reels list / jumps post to post |
| YouTube | Shorts (`/shorts/`) | Home, search | Shorts' own ▲▼ buttons when visible, otherwise scrolls |
| TikTok | For You, Following, videos | n/a | TikTok's own arrow buttons when present, otherwise scrolls |
| Facebook | Reels, Watch | News feed | Facebook's "Next card" buttons when present, otherwise scrolls |
| LinkedIn | n/a | Feed | Jumps post to post |

Pause works on any page with a video in view. Like looks for the site's own Like button
(a "Like" label, or a pressed/unpressed Like toggle) and never clicks a Dislike, comment
Like or like count. See [Known limitations](#10-known-limitations-read-these) for what has
been verified on each live site.

---

## 1. How it works

```
 Webcam ─► OpenCV ─► MediaPipe HandLandmarker ─► Gesture engine ─► Safety gate ─► WebSocket ─► Browser extension ─► Social site tab
           (capture)   (21 landmarks, local)      (poses, holds,    (control on?   (127.0.0.1   (re-checks a supported site
                                                   cooldowns)        supported       only)        is the active tab, then uses
                                                                     site in front?)              the page's own buttons/scroll)
            └──────────── Python app (python run.py) ── serves the dashboard at http://127.0.0.1:8765 ───┘
```

**Why two parts?** A desktop program that fakes key presses (PyAutoGUI) sends them to
*whatever* window has focus and cannot tell which browser tab is open. A small browser
extension *can* check that a supported site is the active tab of the focused window, and it
can scroll and click inside the page reliably. So the Python app does the vision and the
extension does the website part. Nothing else is involved: no cloud, no site APIs, no login
automation. You log in to each site yourself, as usual.

**Adding or fixing a site:** each site is a small adapter at the top of `extension/content.js`
(its next/previous buttons, short-video URL and post containers), plus its address in
`extension/manifest.json` and `extension/background.js`. The scrolling, liking and pausing
logic is shared.

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
│   ├── engine.py           stabilisation, hold-to-fire, cooldowns, optional flicks, hold-to-toggle
│   ├── tracker.py          MediaPipe Tasks HandLandmarker wrapper + model download
│   ├── camera.py           webcam thread, preview rendering, cleanup
│   ├── bridge.py           WebSocket link to the browser extension
│   ├── app.py              wiring + safety gate + dashboard status
│   ├── config.py           settings (settings.json), paths, limits
│   ├── server.py           local web server: dashboard, MJPEG preview, sockets
│   └── web/                dashboard (index.html, app.css, app.js)
├── extension/              Chrome / Edge extension (Manifest V3)
│   ├── manifest.json       supported sites
│   ├── background.js       connection, active-tab check, emergency shortcut
│   └── content.js          per-site adapters + scroll / like / pause
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

### Updating after a change

| What changed | What to do |
|---|---|
| Settings sliders | Nothing: applied instantly and saved |
| `airscroll/web/` (dashboard) | Press F5 on the dashboard |
| `airscroll/*.py` | Close the console window and run `run.bat` again |
| `extension/` | `chrome://extensions` → ↻ on *AirScroll AI Bridge*, then F5 on the site's tab |

## 4. Step-by-step usage

1. Open a supported site in Chrome/Edge and **log in normally**, e.g. `instagram.com/reels/`,
   `youtube.com/shorts`, `tiktok.com`, Facebook Reels or your LinkedIn feed.
2. Put the AirScroll dashboard in a **separate window** (or a split-view pane) beside it.
3. In the dashboard click **Start Camera**. The camera turns on only now, and the red **CAMERA LIVE**
   badge shows whenever it is on.
4. Check the status chips: **Camera**, **Hand** and **Extension** should be green.
5. Click **Enable Gesture Control**, or hold an open palm still for 2 s and watch the ring fill.
6. **Click once inside the site's page.** Actions only go through when a supported site is the
   active tab of the focused window (the chip then reads e.g. *YouTube in front*). This is a
   safety feature: gestures can never act on another site or app. In split view, the pane you
   clicked last is the active one.
7. Gesture! A small pink toast on the page confirms each action, and the dashboard's
   **Activity** list shows what was recognized, sent, skipped and why.

**Stopping:** **Disable** turns gestures off. **Stop Camera** releases the webcam immediately.
**EMERGENCY STOP** (or **Esc** in the dashboard, or **Alt+Shift+S** anywhere in Chrome/Edge)
disables control *and* turns the camera off. **Quit app** (or closing the console) shuts
everything down and releases the camera.

### Technique that works

* Sit 50–80 cm from the camera with your hand roughly at chest-to-face height, in good **front**
  light. A bright window behind you makes detection much worse.
* Show the gesture clearly, palm towards the camera, and hold it until the ring fills.
* To repeat a gesture, relax or drop your hand first, then show it again.

## 5. Gesture calibration

Open the **Settings** card (changes apply instantly and are saved in `settings.json`):

| Problem | Adjust |
|---|---|
| Gestures fire by accident | Raise **Hold a gesture for** (e.g. 0.6 s), raise **Delay between actions** |
| Gestures feel slow | Lower **Hold a gesture for** (e.g. 0.25 s) |
| Two actions from one gesture | Raise **Delay between actions** (default 0.8 s) |
| Pose flickers / wrong pose shown | Raise **Frames to confirm a pose** (Advanced), improve lighting |
| Hand not detected | Lower **Hand detection confidence** (Advanced; applies on next camera start) |
| Wrong camera (e.g. IR camera) | Change **Camera number** to 1 or 2 (Advanced), then Stop/Start camera |
| Want open-palm flicks too | Turn on **Also allow open-palm flicks** (Advanced) and tune **Flick sensitivity** |

The pose under your hand is shown live in the preview and in the status card, so you can see
exactly what the app reads before it acts. Test with control **disabled** first: the Activity
list says *"recognized, ignored (control disabled)"* without touching any site.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| **"No camera available at index 0"** | Turn on camera access for desktop apps (step 3 above); close Teams/Zoom/Camera app; try Camera number 1 |
| Camera opens but image is black | Another app holds the camera, or a privacy shutter/F-key camera switch is on |
| **Extension** chip red | App not running, or extension not loaded/enabled. Open `chrome://extensions` and click ↻ on *AirScroll AI Bridge*. It retries every few seconds. |
| **Site in front** chip stays amber | Click inside the site's tab. The dashboard's own window being focused counts as "no site". |
| "page not ready… reload the … tab" | The tab was open before the extension was installed or updated: press F5 on it |
| "no Like button found" | The site's language isn't English, or the site changed its layout. Add your language's word to `LIKE_WORDS` at the top of `extension/content.js`, then reload the extension |
| "clicked Like but … did not confirm it" | Not logged in to that site, or the site changed its Like button |
| "page did not scroll" | End of the list, or a single-video page. Open the site's short-video feed (e.g. `instagram.com/reels/`, `youtube.com/shorts`) |
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
* No site actions happen while control is disabled or when no supported site is the active tab
  of the focused window. The extension re-checks that itself just before every action.
* The extension only has access to the five supported sites, and uses their normal pages: no
  private APIs, no automation of login, no requests beyond what clicking the page would do.

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

100 automated tests cover pose classification (tilt, distance, jitter), the gesture engine
(hold-to-fire, once per showing, cooldowns, like cooldown, hold-to-toggle, hand drop-outs,
and the optional flicks), the safety gate (disabled, no site in front, extension missing,
emergency stop), settings clamping, the server's origin checks and a full fake-extension round
trip, plus a smoke test of the real MediaPipe model.

**Content-script harness:** `python tests/ext_harness/serve.py`, then open one of the mock
pages and run `await run("next")`, `run("like")`, etc. in DevTools. Each loads the real
`extension/content.js`:

* `http://127.0.0.1:8799/reels/` and `/`: Instagram-style reels and feed
* `http://127.0.0.1:8799/shorts/?site=youtube`: YouTube-style Shorts (▲▼ buttons, pressed-state Like, Dislike)
* `http://127.0.0.1:8799/feed/?site=linkedin`: LinkedIn-style feed (React Like, comment likes)

## 10. Known limitations (read these)

* **What has been verified on the real sites** (as of v1.2):

  | Site | Next / previous | Pause | Like |
  |---|---|---|---|
  | Instagram | ✅ live (Reels) | mock only | mock only |
  | YouTube | ✅ live (Shorts, scrolling path) | ✅ live | label checked live, click untested (needs login) |
  | TikTok, Facebook, LinkedIn | mock / not yet | not yet | not yet |

  Everything else was tested against mock pages that copy each site's structure. Your first
  session on each site is the real test. Watch the Activity list, where each action reports
  success or the reason it failed.
* **Sites change their websites often.** Scrolling is generic and fairly robust. Next/previous
  buttons and Like detection depend on each site's button labels and **can break when a site
  renames them or your UI isn't in English** (see Troubleshooting). Fixes go in the site's
  adapter in `extension/content.js`.
* **Pause/resume** controls the HTML video directly. The site's own play/pause icon may not
  update to match, and if the browser blocks playback you may need to click the video once.
* **Like** only ever *likes*. Unliking by gesture is intentionally not supported.
* Works in **Chrome / Edge (Chromium 116+)**. Firefox and Safari are not supported (the extension uses Chrome APIs).
* The dashboard must not be the focused window when you gesture (by design). Click into the site after using the dashboard.
* One hand at a time. Very dim light, strong backlight, gloves or a hand partly out of frame reduce accuracy.
* Mobile apps and desktop store apps (Instagram, TikTok, etc.) are not supported; use the websites.
