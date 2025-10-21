/* ============================================================
   HIREX • ui.js (v2.0.0 — Unified Global UI Layer, Stable Edition)
   ------------------------------------------------------------
   Global UI behavior for all pages:
   • Smooth sidebar (desktop + mobile adaptive)
   • Theme persistence with system fallback
   • Humanize switch enhancer + global event sync
   • Active nav highlight + scroll-in animations
   • Robust multi-tab + accessibility compatibility
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const APP_VERSION   = "v2.0.0";
  const THEME_KEY     = "hirex-theme";
  const HUMANIZE_KEY  = "hirex-use-humanize";
  const currentPage   = (window.location.pathname.split("/").pop() || "index.html");
  const toastEl       = document.getElementById("toast");
  const html          = document.documentElement;
  const body          = document.body;

  /* ============================================================
     🧠 GLOBAL NAMESPACE
     ============================================================ */
  window.HIREX = window.HIREX || {};
  Object.assign(window.HIREX, {
    version: APP_VERSION,

    toast: (msg, t = 2600) => {
      if (!toastEl) { console.log("[HIREX]", msg); return; }
      // Accessibility + robust timing
      toastEl.setAttribute("role", "status");
      toastEl.setAttribute("aria-live", "polite");
      toastEl.textContent = msg;
      toastEl.classList.add("visible");
      clearTimeout(toastEl._timeout);
      toastEl._timeout = setTimeout(() => toastEl.classList.remove("visible"), t);
    },

    debugLog: (msg, data = {}) => {
      console.log("%c🟦 [HIREX]", "color:#5bd0ff;font-weight:bold;", msg, data);
      // Fire-and-forget; ensure errors are handled
      try {
        const base = (["127.0.0.1", "localhost"].includes(location.hostname)
          ? "http://127.0.0.1:8000"
          : location.origin);
        void fetch(`${base}/api/debug/log`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            msg,
            ...data,
            version: APP_VERSION,
            timestamp: new Date().toISOString(),
            page: currentPage,
          }),
        }).catch(() => {/* swallow */});
      } catch (err) {
        console.warn("[HIREX] Debug log failed:", err?.message || err);
      }
    },

    getApiBase: () =>
      (["127.0.0.1", "localhost"].includes(location.hostname)
        ? "http://127.0.0.1:8000"
        : location.origin),

    getHumanizeState: () => localStorage.getItem(HUMANIZE_KEY) === "on",

    // Utility used by CTA buttons in markup
    scrollTo: (selector, offset = 0) => {
      const el = document.querySelector(selector);
      if (!el) return false;
      const top = Math.max(0, el.getBoundingClientRect().top + window.scrollY - offset);
      window.scrollTo({ top, behavior: "smooth" });
      return true;
    },
  });

  /* ============================================================
     🌗 THEME PERSISTENCE + SYNC
     ============================================================ */
  const themeMeta = document.querySelector('meta[name="theme-color"]');

  const setThemeMetaColor = (theme) => {
    if (!themeMeta) return;
    // Keep your brand dark color; use a neutral light for light mode
    themeMeta.setAttribute("content", theme === "dark" ? "#0a1020" : "#ffffff");
  };

  const getSystemTheme = () =>
    (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches)
      ? "light" : "dark";

  const applyTheme = (theme, { persist = true, silent = false } = {}) => {
    const val = theme === "light" ? "light" : "dark";
    html.setAttribute("data-theme", val);
    setThemeMetaColor(val);
    if (persist) localStorage.setItem(THEME_KEY, val);
    window.dispatchEvent(new CustomEvent("hirex:theme-change", { detail: { theme: val } }));
    if (!silent) HIREX.toast(`🌗 ${val === "dark" ? "Dark" : "Light"} Mode`);
  };

  // Init theme (use saved if present, else system)
  const savedTheme = localStorage.getItem(THEME_KEY);
  applyTheme(savedTheme || getSystemTheme(), { persist: !!savedTheme, silent: true });

  // Toggle button (optional)
  document.getElementById("themeToggle")?.addEventListener("click", () => {
    const cur = html.getAttribute("data-theme") || "dark";
    applyTheme(cur === "dark" ? "light" : "dark");
  });

  // React to system changes if user hasn't explicitly chosen a theme
  const mqlDark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (mqlDark) {
    const onSysChange = (e) => {
      if (!localStorage.getItem(THEME_KEY)) applyTheme(e.matches ? "dark" : "light", { persist: false });
    };
    // Old + new API compatibility
    if (typeof mqlDark.addEventListener === "function") mqlDark.addEventListener("change", onSysChange);
    else if (typeof mqlDark.addListener === "function") mqlDark.addListener(onSysChange);
  }

  // Cross-tab theme sync
  window.addEventListener("storage", (e) => {
    if (e.key === THEME_KEY && e.newValue) applyTheme(e.newValue, { persist: false, silent: true });
  });

  /* ============================================================
     🧩 HUMANIZE TOGGLE (Single Source of Truth)
     ============================================================ */
  (function initHumanizeToggle() {
    const toggle = document.getElementById("humanize-toggle");
    const hidden = document.getElementById("use_humanize_state");
    if (!toggle) return;

    const persist = (on) => localStorage.setItem(HUMANIZE_KEY, on ? "on" : "off");

    const setState = (on, { silent = false } = {}) => {
      toggle.classList.toggle("on", on);
      toggle.querySelector(".opt-off")?.classList.toggle("active", !on);
      toggle.querySelector(".opt-on")?.classList.toggle("active", on);
      if (hidden) hidden.value = on ? "on" : "off";
      persist(on);
      window.dispatchEvent(new CustomEvent("hirex:humanize-change", { detail: { on } }));
      if (!silent) HIREX.toast(on ? "🧑‍💼 Humanize Enabled" : "⚙️ Optimize Enabled");
    };

    // Default ON if unset
    const startOn = (localStorage.getItem(HUMANIZE_KEY) ?? "on") === "on";
    setState(startOn, { silent: true });

    toggle.addEventListener("click", () => setState(!toggle.classList.contains("on")));

    // Cross-tab sync
    window.addEventListener("storage", (e) => {
      if (e.key === HUMANIZE_KEY) setState(e.newValue === "on", { silent: true });
    });
  })();

  /* ============================================================
     🧭 ACTIVE NAV LINK
     ============================================================ */
  document.querySelectorAll(".vnav a").forEach((a) => {
    const href = a.getAttribute("href");
    if (href && href.endsWith(currentPage)) {
      a.classList.add("active-link");
      a.setAttribute("aria-current", "page");
    } else {
      a.classList.remove("active-link");
      a.removeAttribute("aria-current");
    }
  });

  /* ============================================================
     ✨ SCROLL-IN ANIMATIONS
     ============================================================ */
  const animatedEls = document.querySelectorAll("[data-anim], .anim");
  if (animatedEls.length && "IntersectionObserver" in window) {
    const obs = new IntersectionObserver((entries, o) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-animated");
          o.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    animatedEls.forEach((el) => obs.observe(el));
  } else {
    // Fallback: show immediately
    animatedEls.forEach((el) => el.classList.add("is-animated"));
  }

  /* ============================================================
     📱 RESPONSIVE SIDEBAR
     ============================================================ */
  const sidebar    = document.getElementById("sidebar");
  const menuToggle = document.getElementById("menuToggle");

  if (sidebar && menuToggle) {
    menuToggle.setAttribute("aria-controls", "sidebar");
    menuToggle.setAttribute("aria-expanded", "false");

    const closeNav = () => {
      body.classList.remove("nav-open");
      menuToggle.setAttribute("aria-expanded", "false");
      sidebar.style.boxShadow = "none";
    };

    menuToggle.addEventListener("click", () => {
      const open = body.classList.toggle("nav-open");
      menuToggle.setAttribute("aria-expanded", String(open));
      sidebar.style.boxShadow = open ? "0 0 30px rgba(91,208,255,0.25)" : "none";
    });

    // Click outside to close
    document.addEventListener("click", (e) => {
      if (body.classList.contains("nav-open") && !sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
        closeNav();
      }
    });

    // ESC to close
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && body.classList.contains("nav-open")) closeNav();
    });
  }

  /* ============================================================
     ♿ ACCESSIBILITY ENHANCEMENTS
     ============================================================ */
  window.addEventListener("keydown", (e) => {
    if (e.key === "Tab") body.classList.add("user-is-tabbing");
  });
  window.addEventListener("mousedown", () => body.classList.remove("user-is-tabbing"));

  /* ============================================================
     🌐 ONLINE / OFFLINE FEEDBACK
     ============================================================ */
  window.addEventListener("online",  () => HIREX.toast("✅ Back Online"));
  window.addEventListener("offline", () => HIREX.toast("⚠️ Offline Mode Active"));

  /* ============================================================
     🧩 LEGACY CLEANUP
     ============================================================ */
  (() => {
    const fileInput = document.getElementById("resume");
    if (fileInput) {
      fileInput.disabled = true;
      fileInput.style.display = "none";
      fileInput.setAttribute("aria-hidden", "true");
    }
  })();

  /* ============================================================
     ✨ CARD HOVER EFFECTS
     ============================================================ */
  document.querySelectorAll(".card").forEach((card) => {
    card.style.transition = "transform .25s ease, box-shadow .25s ease";
    card.addEventListener("mouseenter", () => {
      card.style.transform = "translateY(-4px)";
      card.style.boxShadow = "0 0 25px rgba(91,208,255,0.2)";
    });
    card.addEventListener("mouseleave", () => {
      card.style.transform = "translateY(0)";
      card.style.boxShadow = "none";
    });
  });

  /* ============================================================
     ✅ INIT LOG
     ============================================================ */
  console.log(
    "%c⚙️ HIREX ui.js initialized — v2.0.0",
    "background:#5bd0ff;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  HIREX.debugLog("UI LOADED", {
    version: APP_VERSION,
    page: currentPage,
    origin: window.location.origin,
    theme: html.getAttribute("data-theme"),
    humanize: localStorage.getItem(HUMANIZE_KEY),
  });
});
