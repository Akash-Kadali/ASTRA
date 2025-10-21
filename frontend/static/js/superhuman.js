/* ============================================================
   HIREX • superhuman.js (v2.0.0 — Humanizer Engine)
   ------------------------------------------------------------
   Features:
   • Sends text (resume, paragraph, or cover letter body)
     to /api/superhuman/rewrite for tone refinement
   • Supports tone modes (Formal, Balanced, Conversational, Academic, Confident)
   • Honors global Humanize toggle (skips API when off)
   • Displays rewritten text side-by-side
   • Cache: tone + input/output persisted across sessions
   • Clear control + graceful backend error handling
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const APP_VERSION = "v2.0.0";
  const LS_KEY = "hirex_superhuman_cache";
  const TIMEOUT_MS = 120000; // 2 minutes

  /* ------------------------------------------------------------
     🔧 DOM Elements (match superhuman.html)
  ------------------------------------------------------------ */
  const inputEl            = document.getElementById("input_text");
  const modeEl             = document.getElementById("mode");
  const toneEl             = document.getElementById("tone");
  const latexSafeEl        = document.getElementById("latex_safe");
  const rewriteBtn         = document.getElementById("rewrite_btn");
  const clearBtn           = document.getElementById("clear_btn");
  const statusBadge        = document.getElementById("status_badge");

  const originalOut        = document.getElementById("original_output");
  const humanOut           = document.getElementById("human_output");
  const humanOnlyOut       = document.getElementById("human_only_output");
  const originalOnlyOut    = document.getElementById("original_only_output");

  /* ------------------------------------------------------------
     🧩 Utilities
  ------------------------------------------------------------ */
  const H = window.HIREX || {};
  H.getApiBase = H.getApiBase || (() => {
    if (["127.0.0.1", "localhost"].includes(location.hostname)) return "http://127.0.0.1:8000";
    return location.origin;
  });

  const apiBase = H.getApiBase();
  const toast = (msg, t = 3000) => (H.toast ? H.toast(msg, t) : alert(msg));
  const debug = (msg, data) => H.debugLog?.(msg, data);

  const getHumanizeState = () =>
    (typeof H.getHumanizeState === "function")
      ? !!H.getHumanizeState()
      : localStorage.getItem("hirex-use-humanize") === "on";

  const setBusy = (busy, msg = "") => {
    [rewriteBtn, clearBtn, inputEl, modeEl, toneEl, latexSafeEl]
      .filter(Boolean)
      .forEach(el => el.disabled = !!busy);
    if (statusBadge) statusBadge.textContent = busy ? (msg || "Working…") : "🟢 Ready";
  };

  /* ------------------------------------------------------------
     💾 Cache (load/restore)
  ------------------------------------------------------------ */
  const loadCache = () => {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); }
    catch { return {}; }
  };
  const saveCache = (data) => {
    try { localStorage.setItem(LS_KEY, JSON.stringify({ ...data, _v: APP_VERSION, _t: Date.now() })); }
    catch (e) { console.warn("[HIREX] SuperHuman cache save failed:", e); }
  };

  const boot = loadCache();
  if (boot.lastInput && inputEl && !inputEl.value) inputEl.value = boot.lastInput;
  if (boot.lastTone  && toneEl) toneEl.value   = boot.lastTone;
  if (boot.lastMode  && modeEl) modeEl.value   = boot.lastMode;
  if (typeof boot.latexSafe === "boolean" && latexSafeEl) latexSafeEl.checked = boot.latexSafe;
  if (boot.lastOutput) {
    originalOut      && (originalOut.textContent       = boot.lastInput || "");
    originalOnlyOut  && (originalOnlyOut.textContent   = boot.lastInput || "");
    humanOut         && (humanOut.textContent          = boot.lastOutput || "");
    humanOnlyOut     && (humanOnlyOut.textContent      = boot.lastOutput || "");
  }

  /* ------------------------------------------------------------
     🛰️ API: POST /api/superhuman/rewrite   (matches backend v2.1.0)
  ------------------------------------------------------------ */
  const buildPayload = (text, tone, mode, latexSafe) => ({
    text,                              // string or array of strings
    tone: (tone || "balanced").toLowerCase(),
    mode: (mode || "paragraph").toLowerCase(),
    latex_safe: !!latexSafe,
    // model not required (backend uses DEFAULT_MODEL)
    // constraints/max_len also optional; backend has safe defaults
  });

  async function callRewrite(payload, controller) {
    const url = `${apiBase}/api/superhuman/rewrite`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const body = await res.text().catch(() => "");
    if (!res.ok) throw new Error(body || `HTTP ${res.status}`);
    try { return JSON.parse(body); }
    catch { throw new Error("Invalid JSON from backend."); }
  }

  const extractRewritten = (response, originalText) => {
    // Backend returns { rewritten: string | string[] }
    const r = response?.rewritten;
    if (Array.isArray(r)) return r.join("\n");
    if (typeof r === "string" && r.trim()) return r;
    // fallback keys from older builds
    return response?.text || response?.output || originalText || "";
  };

  /* ------------------------------------------------------------
     🧠 Render helpers
  ------------------------------------------------------------ */
  const setOutputs = (original, humanized) => {
    if (originalOut)       originalOut.textContent      = original;
    if (originalOnlyOut)   originalOnlyOut.textContent  = original;
    if (humanOut)          humanOut.textContent         = humanized;
    if (humanOnlyOut)      humanOnlyOut.textContent     = humanized;
  };

  /* ------------------------------------------------------------
     ⚡ Rewrite (Humanize)
  ------------------------------------------------------------ */
  const runHumanize = async () => {
    const text = inputEl?.value?.trim() || "";
    if (!text) return toast("⚠️ Please paste text to refine.");

    const tone       = toneEl?.value || "Balanced";
    const mode       = modeEl?.value || "paragraph";
    const latexSafe  = !!latexSafeEl?.checked;
    const humanizeOn = getHumanizeState();

    // If global toggle is off, just mirror original to both panes
    if (!humanizeOn) {
      setOutputs(text, text);
      saveCache({ lastInput: text, lastOutput: text, lastTone: tone, lastMode: mode, latexSafe });
      toast("ℹ️ Humanize toggle is off — showing original text.");
      return;
    }

    setBusy(true, "Refining…");
    toast(`⚡ Humanizing in ${tone} tone…`);
    debug("SuperHuman submit", { tone, mode, latexSafe, humanizeOn });

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
      const payload = buildPayload(text, tone, mode, latexSafe);
      let response;
      try {
        response = await callRewrite(payload, controller);
      } catch (err) {
        // graceful offline fallback
        console.error("[HIREX] SuperHuman fetch failed:", err);
        toast("⚠️ Backend unreachable — showing original text.");
        response = { rewritten: text };
      }

      const humanized = extractRewritten(response, text) || "⚠️ No response received.";
      setOutputs(text, humanized);

      saveCache({
        lastInput: text,
        lastOutput: humanized,
        lastTone: tone,
        lastMode: mode,
        latexSafe,
      });

      toast("✅ Text refined successfully!");
    } catch (err) {
      if (err.name === "AbortError") toast("⚠️ Request canceled or timed out (2 min).");
      else toast("❌ " + (err.message || "Unexpected error."));
      console.error("[HIREX] SuperHuman error:", err);
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  };

  rewriteBtn?.addEventListener("click", runHumanize);

  /* ------------------------------------------------------------
     🧹 Clear
  ------------------------------------------------------------ */
  clearBtn?.addEventListener("click", () => {
    if (inputEl) inputEl.value = "";
    setOutputs("", "");
    saveCache({});
    toast("🧹 Cleared input and output.");
    statusBadge && (statusBadge.textContent = "🟢 Ready");
  });

  /* ------------------------------------------------------------
     ⌨️ Keyboard shortcut (Ctrl/Cmd + Enter)
  ------------------------------------------------------------ */
  inputEl?.addEventListener("keydown", (e) => {
    const isMac = /Mac|iPhone|iPad/i.test(navigator.platform);
    const mod   = isMac ? e.metaKey : e.ctrlKey;
    if (mod && e.key.toLowerCase() === "enter") {
      e.preventDefault();
      runHumanize();
    }
  });

  /* ------------------------------------------------------------
     🔄 Persist user choices
  ------------------------------------------------------------ */
  toneEl?.addEventListener("change",   () => saveCache({ ...(loadCache()), lastTone: toneEl.value }));
  modeEl?.addEventListener("change",   () => saveCache({ ...(loadCache()), lastMode: modeEl.value }));
  latexSafeEl?.addEventListener("change", () =>
    saveCache({ ...(loadCache()), latexSafe: !!latexSafeEl.checked })
  );

  /* ------------------------------------------------------------
     🔔 React to global UI events
  ------------------------------------------------------------ */
  window.addEventListener("hirex:theme-change", (e) =>
    debug("SuperHuman theme changed", { theme: e.detail?.theme })
  );
  window.addEventListener("hirex:humanize-change", (e) =>
    debug("SuperHuman humanize toggled", { on: e.detail?.on })
  );

  /* ------------------------------------------------------------
     ✅ Init Log
  ------------------------------------------------------------ */
  console.log(
    "%c⚡ HIREX superhuman.js initialized — v2.0.0",
    "background:#5bd0ff;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  debug("SUPERHUMAN PAGE LOADED", {
    version: APP_VERSION,
    apiBase,
    restored: !!boot.lastInput,
    tone: toneEl?.value,
    mode: modeEl?.value,
    latexSafe: !!latexSafeEl?.checked,
    humanizeOn: getHumanizeState(),
  });
});
