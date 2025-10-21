/* ============================================================
   HIREX • talk.js (v2.0.0 — Talk to HIREX)
   ------------------------------------------------------------
   Features:
   • Interactive Q&A chat for JD-based or interview questions
   • Sends {jd_text, question, resume_tex, tone, humanize} to /api/talk/answer
   • Typewriter animation for assistant replies
   • Local chat history (persisted, capped)
   • Resilient to network errors / timeouts
   • Works with both legacy and new HTML IDs
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const APP_VERSION = "v2.0.0";
  const LS_KEY = "hirex_talk_history";
  const MAX_HISTORY = 40;
  const TIMEOUT_MS = 120000; // 2 minutes

  /* ------------------------------------------------------------
     🔧 DOM References (support legacy/new IDs)
  ------------------------------------------------------------ */
  const form      = document.getElementById("talk-form") || null;
  const inputEl   = document.getElementById("talk-input") || document.getElementById("question");
  const chatEl    = document.getElementById("talk-chat")  || document.getElementById("chat_box");
  const sendBtn   = document.getElementById("talk-send")  || document.getElementById("send_btn");
  const clearBtn  = document.getElementById("talk-clear") || null;
  const statusEl  = document.getElementById("talk-status")|| document.getElementById("contextStatus");
  const toneEl    = document.getElementById("talk-tone")  || null; // optional <select>

  /* ------------------------------------------------------------
     🧠 Utilities
  ------------------------------------------------------------ */
  const H = window.HIREX || {};
  H.getApiBase = H.getApiBase || (() => (
    ["127.0.0.1", "localhost"].includes(location.hostname)
      ? "http://127.0.0.1:8000"
      : location.origin
  ));
  const apiBase = H.getApiBase();

  const toast = (msg, t = 3000) => (H.toast ? H.toast(msg, t) : alert(msg));
  const debug = (msg, data) => H.debugLog?.(msg, data);

  const getHumanize = () =>
    (typeof H.getHumanizeState === "function")
      ? !!H.getHumanizeState()
      : localStorage.getItem("hirex-use-humanize") === "on";

  const getTone = () => (toneEl?.value || "balanced").toLowerCase();

  const setStatus = (txt) => { if (statusEl) statusEl.textContent = txt; };

  const scrollBottom = () => chatEl?.scrollTo({ top: chatEl.scrollHeight, behavior: "smooth" });

  const chooseModel = () => {
    // If the frontend fetched models earlier, it may store preferred model here.
    // Otherwise default to the backend default ("gpt-4o-mini" in config).
    return localStorage.getItem("hirex_default_model") || "gpt-4o-mini";
  };

  /* ------------------------------------------------------------
     💾 Local History
  ------------------------------------------------------------ */
  const loadHistory = () => {
    try {
      const arr = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
      return Array.isArray(arr) ? arr : [];
    } catch { return []; }
  };
  const saveHistory = (hist) => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(hist.slice(-MAX_HISTORY))); }
    catch (e) { console.warn("[HIREX] Talk history save failed:", e); }
  };
  let history = loadHistory();

  /* ------------------------------------------------------------
     🧩 Context (selected JD+Resume or global cache)
  ------------------------------------------------------------ */
  const getSelectedContext = () => {
    // Preferred: a saved combo pushed by Optimize/Humanize
    try {
      const sel = JSON.parse(localStorage.getItem("hirex_selected_context") || "null");
      if (sel && (sel.jd_text || sel.resume_tex)) return sel;
    } catch {}
    // Fallback to global keys from main.js
    return {
      jd_text:   localStorage.getItem("hirex_jd_text") || "",
      resume_tex: localStorage.getItem("hirex_tex") || "",
      company:   localStorage.getItem("hirex_company") || "",
      role:      localStorage.getItem("hirex_role") || "",
    };
  };

  /* ------------------------------------------------------------
     💬 Rendering
  ------------------------------------------------------------ */
  const renderMessage = (role, text, { trusted = false } = {}) => {
    if (!chatEl) return;
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role}-bubble`;
    if (trusted) bubble.innerHTML = text; else bubble.textContent = text;
    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    scrollBottom();
  };

  const appendTyping = (txt = "Thinking…") => {
    if (!chatEl) return null;
    const wrap = document.createElement("div");
    wrap.className = "msg ai";
    const bubble = document.createElement("div");
    bubble.className = "bubble ai-bubble typing";
    bubble.textContent = txt;
    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    scrollBottom();
    return bubble;
  };

  const typeWriter = async (text, target, speed = 17) => {
    if (!target) return;
    target.textContent = "";
    for (const ch of text) {
      target.textContent += ch;
      // eslint-disable-next-line no-await-in-loop
      await new Promise((r) => setTimeout(r, speed));
    }
  };

  /* ------------------------------------------------------------
     🛰️ API: POST /api/talk/answer  (matches backend)
  ------------------------------------------------------------ */
  async function askBackend(question, controller) {
    const url = `${apiBase}/api/talk/answer`;
    const ctx = getSelectedContext();
    const payload = {
      jd_text: ctx?.jd_text || ctx?.jd || "",
      question,
      resume_tex: ctx?.resume_tex || "",
      resume_plain: ctx?.resume_plain || "",
      tone: getTone(),
      humanize: getHumanize(),
      model: chooseModel(),
    };

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const body = await res.text().catch(() => "");
      if (!res.ok) throw new Error(body || `HTTP ${res.status}`);
      const data = JSON.parse(body);
      // Backend fields: question, resume_summary, draft_answer, final_text, tone, humanized, model
      const reply = (data.final_text || data.draft_answer || "").trim();
      const usedModel = data.model || chooseModel();
      debug("Talk API OK", { model: usedModel, humanized: data.humanized, tone: data.tone });
      return { reply: reply || "⚠️ No response received.", model: usedModel };
    } catch (err) {
      console.error("[HIREX] Talk API error:", err);
      toast("⚠️ Backend unreachable — try again later.");
      return { reply: "⚠️ Unable to connect to backend.", model: "offline" };
    }
  }

  /* ------------------------------------------------------------
     🚀 Send Flow
  ------------------------------------------------------------ */
  const sendFlow = async () => {
    const text = inputEl?.value?.trim();
    if (!text) return toast("💬 Please enter a question first.");

    const ctx = getSelectedContext();
    if (!(ctx?.jd_text || ctx?.jd) || !(ctx?.resume_tex)) {
      console.warn("[HIREX] Missing JD or Resume in context — will still attempt but answers may be generic.");
    }

    // Render user, persist
    renderMessage("user", text);
    history.push({ role: "user", content: text });
    saveHistory(history);

    if (inputEl) { inputEl.value = ""; inputEl.disabled = true; }
    if (sendBtn) sendBtn.disabled = true;
    setStatus("Thinking…");

    const typing = appendTyping();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

    let result;
    try {
      result = await askBackend(text, controller);
    } catch (e) {
      console.error("[HIREX] Talk fetch error:", e);
      result = { reply: "⚠️ Request aborted or timed out.", model: "timeout" };
    } finally {
      clearTimeout(timeout);
    }

    const reply = result.reply || "⚠️ No response received.";
    if (typing) {
      typing.classList.remove("typing");
      await typeWriter(reply, typing, 17);
    } else {
      renderMessage("ai", reply);
    }

    history.push({ role: "assistant", content: reply, model: result.model });
    saveHistory(history);

    if (inputEl) { inputEl.disabled = false; inputEl.focus(); }
    if (sendBtn) sendBtn.disabled = false;
    setStatus("Ready");
  };

  /* ------------------------------------------------------------
     🔘 Wiring (form or button)
  ------------------------------------------------------------ */
  form?.addEventListener("submit", (e) => { e.preventDefault(); sendFlow(); });
  sendBtn?.addEventListener("click", () => sendFlow());

  /* Ctrl/Cmd + Enter */
  inputEl?.addEventListener("keydown", (e) => {
    const isMac = /Mac|iPhone|iPad/i.test(navigator.platform);
    const mod = isMac ? e.metaKey : e.ctrlKey;
    if (mod && e.key.toLowerCase() === "enter") {
      e.preventDefault();
      sendFlow();
    }
  });

  /* ------------------------------------------------------------
     🧹 Clear Chat
  ------------------------------------------------------------ */
  clearBtn?.addEventListener("click", () => {
    if (chatEl) chatEl.innerHTML = "";
    history = [];
    saveHistory(history);
    toast("🧹 Chat cleared.");
    setStatus("Ready");
  });

  /* ------------------------------------------------------------
     ♻️ Restore or Greet
  ------------------------------------------------------------ */
  if (chatEl && history.length) {
    history.forEach((m) => renderMessage(m.role === "assistant" ? "ai" : "user", m.content));
  } else if (chatEl) {
    renderMessage(
      "ai",
      "👋 Hi! I’m <b>HIREX</b> — ask any JD-specific or interview question. I’ll answer based on your latest optimized/humanized resume and job description.",
      { trusted: true }
    );
  }

  /* ------------------------------------------------------------
     🎨 Theme + Humanize Signals
  ------------------------------------------------------------ */
  window.addEventListener("hirex:theme-change", (e) =>
    debug("Talk theme changed", { theme: e.detail?.theme })
  );
  window.addEventListener("hirex:humanize-change", (e) =>
    debug("Talk humanize toggled", { on: e.detail?.on })
  );

  /* ------------------------------------------------------------
     ✅ Init Log
  ------------------------------------------------------------ */
  console.log(
    "%c💬 HIREX talk.js initialized — v2.0.0",
    "background:#5bd0ff;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  const hasCtx = (() => {
    const c = getSelectedContext();
    return !!(c && (c.jd_text || c.jd) && c.resume_tex);
  })();
  debug("TALK PAGE LOADED", {
    version: APP_VERSION,
    historyCount: history.length,
    humanize: getHumanize(),
    hasContext: hasCtx,
    apiBase,
    tone: getTone(),
    model: chooseModel(),
  });
});
