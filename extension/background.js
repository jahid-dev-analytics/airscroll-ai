// AirScroll AI Bridge: background service worker.
// Keeps a WebSocket to the local app, reports whether Instagram is the active tab
// of the focused browser window, and forwards actions to the Instagram tab.
"use strict";

const SERVER_URL = "ws://127.0.0.1:8765/ext"; // change the port here if you run the app with --port
const VERSION = chrome.runtime.getManifest().version;

let ws = null;
let retryMs = 1000;
let retryTimer = null;
let keepAlive = null;

// ------------------------------------------------------------- connection
function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  clearTimeout(retryTimer);
  try {
    ws = new WebSocket(SERVER_URL);
  } catch (e) {
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    retryMs = 1000;
    send({ type: "hello", version: VERSION });
    reportFocus();
    setBadge(true);
    // Chrome 116+: WebSocket traffic keeps the service worker alive.
    keepAlive = setInterval(reportFocus, 2000);
  };
  ws.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === "action") runAction(msg);
  };
  ws.onclose = () => {
    ws = null;
    clearInterval(keepAlive);
    setBadge(false);
    scheduleReconnect();
  };
  ws.onerror = () => {}; // onclose follows; the app simply isn't running yet
}

function scheduleReconnect() {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(connect, retryMs);
  retryMs = Math.min(retryMs * 2, 10000);
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function setBadge(connected) {
  chrome.action.setBadgeText({ text: connected ? "ON" : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#b46bff" });
  chrome.action.setTitle({ title: connected ? "AirScroll AI: connected" : "AirScroll AI: app not running" });
}

// ---------------------------------------------------------------- focus
function isInstagram(url) {
  try { return new URL(url).hostname === "www.instagram.com"; } catch { return false; }
}

function pageKind(url) {
  try {
    const p = new URL(url).pathname;
    if (/^\/reels?\//.test(p)) return "reels";
    if (p === "/") return "feed";
    return "other";
  } catch { return "other"; }
}

// The Instagram tab only counts when it is the active tab of the window that
// currently has OS focus. tab.url is only visible to us for instagram.com
// (host permission), so other sites always read as "not Instagram".
async function activeInstagramTab() {
  const win = await chrome.windows.getLastFocused().catch(() => null);
  if (!win || !win.focused) return null;
  const [tab] = await chrome.tabs.query({ active: true, windowId: win.id });
  if (!tab || !isInstagram(tab.url)) return null;
  return tab;
}

async function reportFocus() {
  const tab = await activeInstagramTab();
  send({ type: "focus", instagram: !!tab, page: tab ? pageKind(tab.url) : null });
}

chrome.tabs.onActivated.addListener(reportFocus);
chrome.tabs.onUpdated.addListener((_id, info) => { if (info.url || info.status) reportFocus(); });
chrome.windows.onFocusChanged.addListener(reportFocus);

// --------------------------------------------------------------- actions
async function runAction(msg) {
  const reply = (ok, detail) => send({ type: "result", id: msg.id, ok, detail });
  const tab = await activeInstagramTab(); // re-check the real state right now
  if (!tab) return reply(false, "Instagram is not the active tab in the focused window");
  const payload = { type: "airscroll", action: msg.action };
  try {
    const res = await chrome.tabs.sendMessage(tab.id, payload);
    return reply(!!res?.ok, res?.detail || "");
  } catch (e) {
    // Tab was open before the extension loaded: inject the content script and retry once.
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      const res = await chrome.tabs.sendMessage(tab.id, payload);
      return reply(!!res?.ok, res?.detail || "");
    } catch (e2) {
      return reply(false, `page not ready (${e2.message || e2}); reload the Instagram tab`);
    }
  }
}

// ------------------------------------------------------- emergency stop
chrome.commands.onCommand.addListener((command) => {
  if (command === "emergency-stop") send({ type: "emergency" });
});

// ------------------------------------------------------------- lifecycle
// If the worker was put to sleep while the app was closed, this alarm wakes it to retry.
chrome.alarms.create("airscroll-reconnect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "airscroll-reconnect") connect(); });
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
