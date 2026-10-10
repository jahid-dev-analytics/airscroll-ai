"use strict";
const $ = (id) => document.getElementById(id);
const RING_LEN = 119.4;
const POSE_ICONS = { none: "·", open_palm: "✋", fist: "✊", thumb_up: "👍", peace: "✌️", one_finger: "☝️", other: "🤚" };
const SETTING_FORMAT = {
  sensitivity: (v) => `${v}/10`,
  action_cooldown_s: (v) => `${(+v).toFixed(1)} s`,
  like_cooldown_s: (v) => `${(+v).toFixed(1)} s`,
  neutral_hold_s: (v) => `${(+v).toFixed(2)} s`,
  static_hold_s: (v) => `${(+v).toFixed(2)} s`,
  hold_toggle_s: (v) => `${(+v).toFixed(1)} s`,
  return_lockout_s: (v) => `${(+v).toFixed(1)} s`,
  stable_frames: (v) => `${v}`,
  min_confidence: (v) => `${Math.round(v * 100)}%`,
  camera_index: (v) => `${v}`,
};

let ws = null;
let state = null;
let cameraWasOn = false;
const editing = new Set();

// ---------------------------------------------------------------- socket
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { $("connBadge").textContent = "Connected"; };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type !== "state") return;
    state = msg.state;
    render(state);
    (msg.events || []).forEach(addLog);
  };
  ws.onclose = () => {
    $("connBadge").textContent = "App not running — reconnecting…";
    setStatus("App not running", "error");
    ["btnStartCam", "btnStopCam", "btnEnable", "btnDisable"].forEach((id) => { $(id).disabled = true; });
    setTimeout(connect, 1500);
  };
}
function send(cmd, extra = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cmd, ...extra }));
}

// ---------------------------------------------------------------- render
function setStatus(text, tone) {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${tone}`;
}
function chip(id, tone) { $(id).className = `chip ${tone || ""}`; }

function render(s) {
  setStatus(s.status, s.tone);
  const cam = s.camera, eng = s.engine, ext = s.extension;

  // camera + preview
  $("liveBadge").hidden = !cam.on;
  $("btnStartCam").disabled = cam.on || cam.starting;
  $("btnStopCam").disabled = !cam.on && !cam.starting;
  if (cam.on && !cameraWasOn) $("video").src = `/video.mjpg?t=${Date.now()}`;
  if (!cam.on && cameraWasOn) $("video").removeAttribute("src");
  cameraWasOn = cam.on;
  $("placeholder").classList.toggle("hidden", cam.on);
  $("placeholderText").textContent = cam.starting ? "Starting camera… allow access if Windows asks."
    : cam.error ? cam.error : "Camera is off. Nothing is being captured.";
  $("hudFps").textContent = cam.on ? `${cam.fps} fps` : "";
  const hudHand = $("hudHand");
  hudHand.textContent = cam.on ? (eng.hand ? eng.pose_label : "No hand") : "";
  hudHand.className = `pill ${eng.hand ? "on" : ""}`;

  // pose + hold ring
  $("poseIcon").textContent = POSE_ICONS[eng.pose] || "·";
  $("poseLabel").textContent = cam.on ? `Pose: ${eng.pose_label}` +
    (eng.cooldown_left > 0 ? ` · cooldown ${eng.cooldown_left.toFixed(1)} s` : "") : "Pose: —";
  const progress = eng.pose === "open_palm" ? eng.hold_progress : eng.pose_progress;
  $("holdRing").style.strokeDashoffset = String(RING_LEN * (1 - progress));

  // chips
  chip("chipCam", cam.error ? "error" : cam.on ? "ok" : "");
  chip("chipHand", eng.hand ? "ok" : "");
  chip("chipCtrl", s.control_enabled ? "ok" : "warn");
  chip("chipExt", ext.connected ? "ok" : "error");
  chip("chipIg", ext.active ? "ok" : ext.connected ? "warn" : "");
  $("siteChipLabel").textContent = ext.active ? `${ext.site} in front` : "Site in front";

  const ctrl = $("ctrlState");
  ctrl.textContent = s.control_enabled ? "ENABLED" : "DISABLED";
  ctrl.className = `ctrl-state ${s.control_enabled ? "on" : "off"}`;
  $("btnEnable").disabled = s.control_enabled;
  $("btnDisable").disabled = !s.control_enabled;

  $("extHint").innerHTML = !ext.connected
    ? "<b>Browser extension not connected.</b> Load the <b>extension</b> folder in Chrome or Edge (see README), then keep this app running."
    : !ext.active
      ? "Extension connected. Click into an <b>Instagram, Facebook, YouTube, TikTok or LinkedIn</b> tab so it is the active tab of the focused window — actions are blocked otherwise."
      : `<b>${ext.site}</b> is in front (${ext.page || "page"}). Gestures will act on it when control is enabled.`;

  // highlight current gesture in the list
  document.querySelectorAll(".gestures li").forEach((li) =>
    li.classList.toggle("active", li.dataset.pose === eng.pose));

  // settings (don't fight the user while they drag)
  for (const [key, value] of Object.entries(s.settings)) {
    const el = $(key);
    if (!el || editing.has(key)) continue;
    if (el.type === "checkbox") el.checked = !!value; else el.value = value;
    const out = $(`${key}_out`);
    if (out) out.textContent = SETTING_FORMAT[key] ? SETTING_FORMAT[key](value) : value;
  }
  $("swipeHint").textContent = `Higher = shorter flick needed (now ${s.swipe_distance} palm-heights)`;
  for (const id of ["sensitivity", "neutral_hold_s"]) $(id).disabled = !s.settings.palm_swipes;
}

function addLog(ev) {
  const li = document.createElement("li");
  li.className = ev.level;
  const time = document.createElement("time");
  time.textContent = new Date(ev.t * 1000).toLocaleTimeString();
  li.append(time, document.createTextNode(ev.text));
  const log = $("log");
  log.prepend(li);
  while (log.children.length > 80) log.lastChild.remove();
}

// ---------------------------------------------------------------- inputs
$("btnStartCam").onclick = () => send("start_camera");
$("btnStopCam").onclick = () => send("stop_camera");
$("btnEnable").onclick = () => send("enable");
$("btnDisable").onclick = () => send("disable");
$("btnEmergency").onclick = () => send("emergency_stop");
$("btnQuit").onclick = () => { if (confirm("Quit AirScroll? The camera will be released.")) send("quit"); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") send("emergency_stop"); });

for (const key of Object.keys(SETTING_FORMAT)) {
  const el = $(key);
  el.addEventListener("input", () => {
    editing.add(key);
    $(`${key}_out`).textContent = SETTING_FORMAT[key](el.value);
  });
  el.addEventListener("change", () => {
    send("settings", { values: { [key]: el.value } });
    setTimeout(() => editing.delete(key), 400);
  });
}
for (const key of ["mirror_preview", "hold_can_disable", "palm_swipes"]) {
  $(key).addEventListener("change", (e) => send("settings", { values: { [key]: e.target.checked } }));
}

connect();
