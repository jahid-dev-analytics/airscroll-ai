// AirScroll AI Bridge: runs inside supported social sites and performs actions using
// each page's own buttons and scrolling. No private APIs, no network requests.
//
// Supported: Instagram, Facebook, YouTube, TikTok, LinkedIn. Every site gets the same
// four actions (next, previous, like, pause/play). Each site adapter below only lists
// *where* things are on that site; the logic that uses them is shared. If a site
// changes its layout, its adapter is the one place to fix.
"use strict";

(() => {
  if (window.__airscrollLoaded) return; // guard against double injection
  window.__airscrollLoaded = true;

  // ------------------------------------------------------------ site adapters
  //  shorts: path of the full-screen short-video player (reels, shorts, ...)
  //  next/prev: the site's own "next / previous video" buttons, tried before scrolling
  //  posts: containers of one feed post, used to jump post-by-post on normal feeds
  const SITES = {
    instagram: {
      name: "Instagram",
      host: /(^|\.)instagram\.com$/,
      shorts: /^\/reels?\//,
      next: [], prev: [],
      posts: ["article"],
    },
    facebook: {
      name: "Facebook",
      host: /(^|\.)facebook\.com$/,
      shorts: /^\/(reel|watch|stories)\b/,
      next: ['[aria-label="Next card"]', '[aria-label="Next Card"]', '[aria-label="Next video"]'],
      prev: ['[aria-label="Previous card"]', '[aria-label="Previous Card"]', '[aria-label="Previous video"]'],
      posts: ["div[aria-posinset]", '[role="article"][aria-labelledby]'],
    },
    youtube: {
      name: "YouTube",
      host: /(^|\.)youtube\.com$/,
      shorts: /^\/shorts\//,
      next: ["#navigation-button-down button", 'button[aria-label="Next video"]'],
      prev: ["#navigation-button-up button", 'button[aria-label="Previous video"]'],
      posts: ["ytd-rich-item-renderer", "ytd-video-renderer", "ytd-reel-item-renderer"],
    },
    tiktok: {
      name: "TikTok",
      host: /(^|\.)tiktok\.com$/,
      shorts: /^\/(foryou|following|explore)?\/?$|\/video\//,
      next: ['button[data-e2e="arrow-right"]', 'button[aria-label="Go to next video"]'],
      prev: ['button[data-e2e="arrow-left"]', 'button[aria-label="Go to previous video"]'],
      posts: ['[data-e2e="recommend-list-item-container"]', "article"],
    },
    linkedin: {
      name: "LinkedIn",
      host: /(^|\.)linkedin\.com$/,
      shorts: null,
      next: [], prev: [],
      posts: ['[data-urn^="urn:li:activity"]', ".feed-shared-update-v2", "[data-id^='urn:li:activity']"],
    },
  };
  // window.__airscrollTestSite lets tests/ext_harness pretend to be a site on localhost.
  const SITE = SITES[window.__airscrollTestSite] || Object.values(SITES).find((s) => s.host.test(location.hostname)) || {
    name: "this site", host: /./, shorts: null, next: [], prev: [], posts: ["article"],
  };

  // Like buttons are found by their accessible label. Add your language's words here
  // if likes report "no Like button found" (e.g. Spanish "Me gusta").
  const LIKE_WORDS = /\b(like|react like)\b/i;
  // Like *counts* are links and are skipped separately; comment likes say "comment".
  const NOT_LIKE = /dislike|unlike|remove like|liked by|see who|comment/i;
  const ALREADY_LIKED = /^(unlike|remove like)\b/i;

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
  const onShortsPage = () => !!SITE.shorts && SITE.shorts.test(location.pathname);

  function scrollableAncestor(el) {
    for (let n = el && el.parentElement; n && n !== document.body; n = n.parentElement) {
      const oy = getComputedStyle(n).overflowY;
      if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 20) return n;
    }
    return null;
  }

  function findButton(selectors) {
    for (const sel of selectors) {
      const el = [...document.querySelectorAll(sel)].find((b) => visibleArea(b) > 0 && !b.disabled
        && b.getAttribute("aria-disabled") !== "true");
      if (el) return el;
    }
    return null;
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

  // Poll until something changed and settled, instead of guessing a fixed delay.
  async function waitFor(check, timeoutMs) {
    const t0 = performance.now();
    while (performance.now() - t0 < timeoutMs) {
      await sleep(60);
      if (check()) return true;
    }
    return check();
  }

  async function waitForScroll(readPos, start, timeoutMs) {
    let last = readPos();
    return waitFor(() => {
      const now = readPos();
      const settled = Math.abs(now - start) > 20 && Math.abs(now - last) < 1;
      last = now;
      return settled;
    }, timeoutMs);
  }

  // "What am I looking at": the page path plus the video in view. A different
  // video element, source, or path means the site really moved to another video.
  function viewState() {
    const v = currentVideo();
    return { path: location.pathname, video: v, src: v ? v.currentSrc || v.src : "" };
  }
  function viewChanged(before) {
    const now = viewState();
    return now.path !== before.path || now.video !== before.video || now.src !== before.src;
  }

  // --------------------------------------------------------------- actions
  let navigating = false;

  async function navigate(direction) {
    const label = direction > 0 ? "Next" : "Previous";
    if (navigating) return { ok: false, detail: `${label}: still scrolling from the last gesture` };
    navigating = true;
    try {
      // 1. The site's own next/previous button (YouTube Shorts, TikTok, Facebook reels)
      const button = findButton(direction > 0 ? SITE.next : SITE.prev);
      if (button) {
        const before = viewState();
        button.click();
        if (await waitFor(() => viewChanged(before), 2000)) {
          toast(`${label} video`);
          return { ok: true, detail: `${label} video (${SITE.name} button)` };
        }
      }

      // 2. Short-video player: scroll its container by one screen
      const video = currentVideo();
      const scroller = video && scrollableAncestor(video);
      if (onShortsPage() || (scroller && visibleArea(video) > innerWidth * innerHeight * 0.25)) {
        const box = scroller || document.scrollingElement;
        const start = box.scrollTop;
        const step = direction * box.clientHeight;
        box.scrollBy({ top: step, behavior: "smooth" });
        if (!(await waitForScroll(() => box.scrollTop, start, 900))) {
          box.scrollBy({ top: step, behavior: "instant" }); // smooth scroll didn't start
        }
        if (await waitForScroll(() => box.scrollTop, start, 800)) {
          toast(`${label} video`);
          return { ok: true, detail: `${label} video` };
        }
        if (onShortsPage()) {
          return { ok: false, detail: `${label}: page did not scroll (end of list, or a single-video page)` };
        }
      }

      // 3. Normal feed: jump to the next / previous post, or by most of a screen
      const posts = [...document.querySelectorAll(SITE.posts.join(","))].filter((p) => p.offsetHeight > 80);
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

  // ------------------------------------------------------------------- like
  function labelOf(el) {
    const own = el.getAttribute("aria-label") || el.getAttribute("title") || "";
    if (own) return own.trim();
    const icon = el.querySelector("svg[aria-label], [aria-label]");
    return icon ? (icon.getAttribute("aria-label") || "").trim() : "";
  }

  function isLiked(btn) {
    const label = labelOf(btn);
    return btn.getAttribute("aria-pressed") === "true" || ALREADY_LIKED.test(label);
  }

  function likeButtons(root) {
    const all = [...root.querySelectorAll('button, [role="button"]')].filter((b) => visibleArea(b) > 0);
    return all.filter((b) => {
      const label = labelOf(b);
      if (!label || b.closest("a[href]")) return false;
      return ALREADY_LIKED.test(label) || (LIKE_WORDS.test(label) && !NOT_LIKE.test(label));
    });
  }

  // The post/video the user is looking at.
  function currentMediaRoot() {
    if (!onShortsPage()) {
      const post = mostVisible(document.querySelectorAll(SITE.posts.join(",")));
      if (post && likeButtons(post).length) return post;
    }
    for (let n = currentVideo(); n && n !== document.body; n = n.parentElement) {
      if (likeButtons(n).length) return n;
    }
    return document.body;
  }

  // The main Like button is the biggest one; on ties, the one nearest the screen centre.
  function mainLikeButton(root) {
    const list = likeButtons(root);
    if (!list.length) return null;
    const cx = innerWidth / 2, cy = innerHeight / 2;
    const score = (b) => {
      const r = b.getBoundingClientRect();
      return visibleArea(b) * 1000 - Math.hypot(r.left + r.width / 2 - cx, r.top + r.height / 2 - cy);
    };
    return list.reduce((a, b) => (score(b) > score(a) ? b : a));
  }

  async function like() {
    const root = currentMediaRoot();
    const button = mainLikeButton(root);
    if (!button) return { ok: false, detail: `no Like button found on ${SITE.name}` };
    if (isLiked(button)) {
      toast("Already liked");
      return { ok: true, detail: "already liked (left unchanged)" };
    }
    button.click();
    const confirmed = await waitFor(() => {
      const now = mainLikeButton(root);
      return (now && isLiked(now)) || isLiked(button);
    }, 1200);
    if (confirmed) {
      toast("Liked ❤");
      return { ok: true, detail: "liked ❤" };
    }
    return { ok: false, detail: `clicked Like but ${SITE.name} did not confirm it (are you logged in?)` };
  }

  // ------------------------------------------------------------ pause / play
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
      sendResponse({ ok: false, detail: `${SITE.name} tab is hidden` });
      return;
    }
    fn().then(sendResponse, (e) => sendResponse({ ok: false, detail: String(e && e.message || e) }));
    return true; // async response
  });
})();
