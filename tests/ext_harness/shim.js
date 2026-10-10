// Stand-in for the chrome.runtime API so content.js can run on a normal page.
window.chrome = {
  runtime: { onMessage: { addListener(fn) { window.__airscrollListener = fn; } } },
};
// run("next") -> Promise of the content script's {ok, detail} reply
window.run = (action) =>
  new Promise((resolve) => window.__airscrollListener({ type: "airscroll", action }, {}, resolve));

// Give every <video> a real playable stream (an animated canvas).
window.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("video").forEach((v, i) => {
    const c = document.createElement("canvas");
    c.width = 64; c.height = 64;
    const ctx = c.getContext("2d");
    setInterval(() => { ctx.fillStyle = `hsl(${(Date.now() / 10 + i * 70) % 360},70%,50%)`; ctx.fillRect(0, 0, 64, 64); }, 50);
    v.srcObject = c.captureStream(20);
    v.muted = true;
    v.play().catch(() => {});
  });
  // Mock Instagram heart behaviour: clicking Like flips the label to Unlike.
  document.addEventListener("click", (e) => {
    const btn = e.target.closest('[role="button"]');
    const svg = btn && btn.querySelector("svg[aria-label]");
    if (svg) svg.setAttribute("aria-label", svg.getAttribute("aria-label") === "Like" ? "Unlike" : "Like");
  });
});
