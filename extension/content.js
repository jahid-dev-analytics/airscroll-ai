// AirScroll AI Bridge: runs inside instagram.com and performs actions using the
// page's own scrolling and buttons. No private APIs, no network requests.
"use strict";

(() => {
  if (window.__airscrollLoaded) return; // guard against double injection
  window.__airscrollLoaded = true;

  // Instagram labels its heart icon with the UI language. Add your language's words here
  // if likes report "no Like button found" (e.g. Spanish: "Me gusta" / "Ya no me gusta").
  const LIKE_LABELS = ["Like"];
  const UNLIKE_LABELS = ["Unlike"];

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // --------------------------------------------------------------- helpers
  function visibleArea(el) {
    const r = el.getBoundingClientRect();
    const w = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
    const h = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
    return w > 0 && h > 0 ? w * h : 0;
  }

  function mostVisible(elements) {
    let best = null, bestArea = 0;
    for (const el of elements) {
      const a = visibleArea(el);
      if (a > bestArea) { best = el; bestArea = a; }
    }
    return best;
  }

  const currentVideo = () => mostVisible(document.querySelectorAll("video"));
  const isReelsPage = () => /^\/reels?\//.test(location.pathname);

  function scrollableAncestor(el) {
    for (let n = el && el.parentElement; n && n !== document.body; n = n.parentElement) {
      const oy = getComputedStyle(n).overflowY;
      if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 20) return n;
    }
    return null;
  }

  function hearts(root) {
    const sel = [...LIKE_LABELS, ...UNLIKE_LABELS].map((l) => `svg[aria-label="${l}"]`).join(",");
    return [...root.querySelectorAll(sel)].filter((s) => visibleArea(s) > 0);
  }

  // The post/reel the user is looking at: the most visible <article> on the feed,
  // or the nearest container around the current video that holds a heart button.
  function currentMediaRoot() {
    if (!isReelsPage()) {
      const art = mostVisible(document.querySelectorAll("article"));
      if (art) return art;
    }
    for (let n = currentVideo(); n && n !== document.body; n = n.parentElement) {
      if (hearts(n).length) return n;
    }
    return document.querySelector("main") || document.body;
  }

  function toast(text) {
    let el = document.getElementById("airscroll-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "airscroll-toast";
      Object.assign(el.style, {
        position: "fixed", top: "18px", right: "18px", zIndex: 2147483647,
        padding: "9px 14px", borderRadius: "12px", font: "600 14px system-ui, sans-serif",
        color: "#fff", background: "linear-gradient(135deg,#b46bff,#ff5fa2)",
        boxShadow: "0 8px 24px rgba(0,0,0,.35)", transition: "opacity .25s", pointerEvents: "none",
      });
      document.documentElement.appendChild(el);
    }
    el.textContent = `✋ ${text}`;
    el.style.opacity = "1";
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.opacity = "0"; }, 1100);
  }

  // Smooth scrolling finishes at different speeds per machine, so poll until the
  // position has moved and settled instead of guessing a fixed delay.
  async function waitForScroll(readPos, start, timeoutMs = 2000) {
    const t0 = performance.now();
    let last = readPos();
    while (performance.now() - t0 < timeoutMs) {
      await sleep(60);
      const now = readPos();
      if (Math.abs(now - start) > 20 && Math.abs(now - last) < 1) return true;
      last = now;
    }
    return Math.abs(readPos() - start) > 20;
  }

  // --------------------------------------------------------------- actions
  let navigating = false;

  async function navigate(direction) {
    const label = direction > 0 ? "Next" : "Previous";
    if (navigating) return { ok: false, detail: `${label}: still scrolling from the last gesture` };
    navigating = true;
    try {
      if (isReelsPage()) {
        const scroller = scrollableAncestor(currentVideo()) || document.scrollingElement;
        const start = scroller.scrollTop;
        const step = direction * scroller.clientHeight;
        scroller.scrollBy({ top: step, behavior: "smooth" });
        if (!(await waitForScroll(() => scroller.scrollTop, start, 900))) {
          scroller.scrollBy({ top: step, behavior: "instant" }); // smooth scroll didn't start
        }
        if (!(await waitForScroll(() => scroller.scrollTop, start, 800))) {
          return { ok: false, detail: `${label}: page did not scroll (end of list, or a single-reel page)` };
        }
        toast(`${label} reel`);
        return { ok: true, detail: `${label} reel` };
      }

      // Feed / profile / explore: jump to the next or previous post.
      const posts = [...document.querySelectorAll("article")];
      const start = scrollY;
      const target = direction > 0
        ? posts.find((a) => a.getBoundingClientRect().top > 60)
        : posts.filter((a) => a.getBoundingClientRect().top < -60).pop();
      const go = (behavior) => target
        ? target.scrollIntoView({ behavior, block: "start" })
        : scrollBy({ top: direction * innerHeight * 0.85, behavior });
      go("smooth");
      if (!(await waitForScroll(() => scrollY, start, 900))) go("instant");
      if (!(await waitForScroll(() => scrollY, start, 800))) {
        return { ok: false, detail: `${label}: page did not scroll (top or end of the page)` };
      }
      toast(`${label} post`);
      return { ok: true, detail: `${label} post` };
    } finally {
      navigating = false;
    }
  }

  async function like() {
    const root = currentMediaRoot();
    const list = hearts(root);
    if (!list.length) return { ok: false, detail: "no Like button found for the current reel/post" };
    // The main heart is the biggest one (comment hearts are much smaller).
    const heart = list.reduce((a, b) => (visibleArea(b) > visibleArea(a) ? b : a));
    if (UNLIKE_LABELS.includes(heart.getAttribute("aria-label"))) {
      toast("Already liked");
      return { ok: true, detail: "already liked (left unchanged)" };
    }
    const button = heart.closest('button,[role="button"]') || heart.parentElement;
    button.click();
    await sleep(600);
    const after = hearts(root).reduce((a, b) => (visibleArea(b) > visibleArea(a) ? b : a), heart);
    if (UNLIKE_LABELS.includes(after.getAttribute("aria-label"))) {
      toast("Liked ❤");
      return { ok: true, detail: "liked ❤" };
    }
    return { ok: false, detail: "clicked Like but Instagram did not confirm it" };
  }

  async function togglePlay() {
    const v = currentVideo();
    if (!v) return { ok: false, detail: "no video in view" };
    if (v.paused) {
      try { await v.play(); } catch (e) { return { ok: false, detail: `browser blocked play (${e.name}); click the video once` }; }
      toast("Playing ▶");
      return { ok: true, detail: "resumed ▶" };
    }
    v.pause();
    toast("Paused ⏸");
    return { ok: true, detail: "paused ⏸" };
  }

  const ACTIONS = {
    next: () => navigate(+1),
    previous: () => navigate(-1),
    like,
    toggle_play: togglePlay,
  };

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "airscroll") return;
    const fn = ACTIONS[msg.action];
    if (!fn) { sendResponse({ ok: false, detail: `unknown action ${msg.action}` }); return; }
    if (document.visibilityState !== "visible") {
      sendResponse({ ok: false, detail: "Instagram tab is hidden" });
      return;
    }
    fn().then(sendResponse, (e) => sendResponse({ ok: false, detail: String(e && e.message || e) }));
    return true; // async response
  });
})();
