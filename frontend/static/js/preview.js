/* ============================================================
   HIREX • preview.js (v2.0.0 — Memory-Enhanced Resume Viewer)
   ------------------------------------------------------------
   Features:
   • Displays Optimized + Humanized PDFs from cache or backend memory
   • Pulls recent contexts from /api/context/list when local cache is empty
   • Select previous jobs from sidebar history list (latest first)
   • Updates JD Fit Score gauge + rounds + tier
   • Copy/download LaTeX with safe filenames
   • Auto-highlight active (Humanized/Optimized) mode
   • Dark-theme consistent UI (no white flash)
   • Resilient to partial cache / offline states
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const APP_VERSION = "v2.0.0";

  /* ------------------------------------------------------------
     🔧 DOM Elements
  ------------------------------------------------------------ */
  const texOutput      = document.getElementById("tex-output");
  const pdfContainer   = document.getElementById("pdf-container");
  const btnDownloadTex = document.getElementById("download-tex");
  const btnCopyTex     = document.getElementById("copy-tex");
  const fitCircle      = document.getElementById("fitCircle");
  const fitTierEl      = document.getElementById("fit-tier");
  const fitRoundsEl    = document.getElementById("fit-rounds");
  const historyList    = document.getElementById("history-list");

  /* ------------------------------------------------------------
     🧠 Runtime helpers
  ------------------------------------------------------------ */
  const RT = (window.ASTRA ?? window.HIREX) || {};
  const toast = (msg, t = 3000) => (RT.toast ? RT.toast(msg, t) : alert(msg));
  const debug = (msg, data) => RT.debugLog?.(msg, data);

  const getApiBase = () => {
    try { if (typeof RT.getApiBase === "function") return RT.getApiBase(); } catch {}
    if (["127.0.0.1", "localhost"].includes(location.hostname)) return "http://127.0.0.1:8000";
    return location.origin;
  };
  const apiBase = getApiBase();

  const getTS = () => new Date().toISOString().replace(/[:.]/g, "-");

  const sanitize = (s) =>
    String(s || "file").replace(/[\\/:*?"<>|]+/g, "_").trim() || "file";

  const safeAtob = (b64) => {
    try {
      const base = String(b64 || "");
      const idx  = base.indexOf("base64,");
      return atob(idx >= 0 ? base.slice(idx + 7) : base);
    } catch {
      return "";
    }
  };

  const b64ToBlob = (b64, mime = "application/pdf") => {
    const bin = safeAtob(b64);
    if (!bin) return null;
    return new Blob([Uint8Array.from(bin, c => c.charCodeAt(0))], { type: mime });
  };

  const downloadFile = (name, blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a   = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 700);
  };

  const downloadText = (name, text) =>
    downloadFile(name, new Blob([text], { type: "text/plain" }));

  /* ------------------------------------------------------------
     💾 Local Cache Snapshot
  ------------------------------------------------------------ */
  let texString         = localStorage.getItem("hirex_tex") || "";
  let pdfB64            = localStorage.getItem("hirex_pdf") || "";
  let pdfB64Humanized   = localStorage.getItem("hirex_pdf_humanized") || "";
  let companyRaw        = localStorage.getItem("hirex_company") || "Company";
  let roleRaw           = localStorage.getItem("hirex_role") || "Role";
  const cacheVersion    = localStorage.getItem("hirex_version") || "v2.0.0";

  let company = sanitize(companyRaw).replace(/\s+/g, "_");
  let role    = sanitize(roleRaw).replace(/\s+/g, "_");

  /* ------------------------------------------------------------
     🧭 History Loader (local) + Backend Contexts (fallback)
  ------------------------------------------------------------ */
  const loadLocalHistory = () => {
    try { return JSON.parse(localStorage.getItem("hirex_history") || "[]"); }
    catch { return []; }
  };
  const history = loadLocalHistory();

  const renderHistoryListLocal = () => {
    if (!historyList) return;
    if (!Array.isArray(history) || !history.length) return false;

    const reversed = [...history].reverse(); // newest first
    historyList.innerHTML = reversed.map((h, i) => `
      <li data-source="local" data-index="${reversed.length - 1 - i}" class="history-item">
        <div class="history-entry">
          <strong>${h.company || "—"}</strong><br/>
          <small>${h.role || "—"}</small>
        </div>
      </li>
    `).join("");
    return true;
  };

  const loadLocalEntry = (index) => {
    const entry = history[index];
    if (!entry) return;
    localStorage.setItem("hirex_company", entry.company || "Company");
    localStorage.setItem("hirex_role", entry.role || "Role");
    toast(`📂 Loaded ${entry.company || "—"} — ${entry.role || "—"}`);
    window.location.reload();
  };

  // --- Backend context API (matches /api/context v2.1.0) ---
  const fetchContextList = async (limit = 50) => {
    try {
      const res = await fetch(`${apiBase}/api/context/list?limit=${limit}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return Array.isArray(data.items) ? data.items : [];
    } catch (e) {
      console.warn("[HIREX] /api/context/list failed:", e);
      return [];
    }
  };

  const fetchContextById = async (idOrTitle) => {
    try {
      const res = await fetch(`${apiBase}/api/context/get?id_or_title=${encodeURIComponent(idOrTitle)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      console.warn("[HIREX] /api/context/get failed:", e);
      return null;
    }
  };

  const renderHistoryListBackend = async () => {
    if (!historyList) return;
    const items = await fetchContextList(50);
    if (!items.length) return false;

    // Append or render if empty
    const frag = document.createDocumentFragment();
    items.forEach((it) => {
      const li = document.createElement("li");
      li.className = "history-item";
      li.dataset.source = "backend";
      li.dataset.id = it.id || it.title;
      li.innerHTML = `
        <div class="history-entry">
          <strong>${it.company || "—"}</strong><br/>
          <small>${it.role || "—"}</small>
        </div>`;
      frag.appendChild(li);
    });

    // If already had local entries, append a divider
    if (historyList.children.length) {
      const sep = document.createElement("li");
      sep.className = "history-sep";
      sep.innerHTML = `<div class="history-entry muted">— Server Memory —</div>`;
      historyList.appendChild(sep);
    }

    historyList.appendChild(frag);
    return true;
  };

  const loadBackendEntry = async (idOrTitle) => {
    const ctx = await fetchContextById(idOrTitle);
    if (!ctx) return toast("⚠️ Unable to load context from server.");

    // Normalize + store into localStorage keys used across app
    localStorage.setItem("hirex_company", ctx.company || "Company");
    localStorage.setItem("hirex_role", ctx.role || "Role");
    localStorage.setItem("hirex_tex", ctx.humanized_tex || ctx.resume_tex || "");
    if (ctx.pdf_base64) localStorage.setItem("hirex_pdf", ctx.pdf_base64);
    if (ctx.pdf_base64_humanized) localStorage.setItem("hirex_pdf_humanized", ctx.pdf_base64_humanized);
    if (ctx.jd_text) localStorage.setItem("hirex_jd_text", ctx.jd_text);
    if (ctx.fit_score) localStorage.setItem("hirex_fit_score", ctx.fit_score);

    toast(`☁️ Loaded ${ctx.company || "—"} — ${ctx.role || "—"} from server memory`);
    window.location.reload();
  };

  if (historyList) {
    // Try local first; then backend memory
    const hadLocal = renderHistoryListLocal();
    renderHistoryListBackend().then((hadBackend) => {
      if (!hadLocal && !hadBackend) {
        historyList.innerHTML =
          "<li style='color:#888;padding:.5rem;'>No saved resumes yet.</li>";
      }
    });

    historyList.addEventListener("click", (e) => {
      const li = e.target.closest("li.history-item");
      if (!li) return;
      if (li.dataset.source === "local") {
        loadLocalEntry(Number(li.dataset.index));
      } else if (li.dataset.source === "backend") {
        loadBackendEntry(li.dataset.id);
      }
    });
  }

  /* ------------------------------------------------------------
     ⚠️ Version Notice
  ------------------------------------------------------------ */
  if (cacheVersion !== APP_VERSION) {
    console.warn(`[HIREX] Cache version mismatch: ${cacheVersion} ≠ ${APP_VERSION}`);
    toast("⚠️ Cache from a different version detected — re-optimize recommended.");
  }

  /* ------------------------------------------------------------
     🎯 JD Fit Gauge (align with main.js keys)
  ------------------------------------------------------------ */
  let ratingScore = (() => {
    const raw = localStorage.getItem("hirex_fit_score");
    if (raw == null) return NaN;
    if (raw === "n/a") return NaN;
    const n = Number(raw);
    return Number.isFinite(n) ? Math.round(n) : NaN;
  })();

  // Attempt fallback from legacy rating history (if present)
  let ratingRounds = 0;
  try {
    const hist = JSON.parse(localStorage.getItem("hirex_rating_history") || "[]");
    if (Array.isArray(hist)) ratingRounds = hist.length;
    if (!Number.isFinite(ratingScore) && hist.length) {
      const last = hist.at(-1);
      if (typeof last?.coverage === "number")
        ratingScore = Math.round(last.coverage * 100);
    }
  } catch {}

  if (fitCircle) {
    const hasScore = Number.isFinite(ratingScore) && ratingScore >= 0;
    const tier = hasScore
      ? ratingScore >= 90 ? "Excellent"
      : ratingScore >= 75 ? "Strong"
      : ratingScore >= 60 ? "Moderate"
      : "Low"
      : "Awaiting Analysis…";

    fitCircle.dataset.score = hasScore ? ratingScore : "--";
    fitCircle.style.borderColor = hasScore
      ? (ratingScore >= 90 ? "#6effa0"
        : ratingScore >= 75 ? "#5bd0ff"
        : ratingScore >= 60 ? "#ffc35b"
        : "#ff6b6b")
      : "rgba(255,255,255,0.25)";

    if (fitTierEl)   fitTierEl.textContent   = tier;
    if (fitRoundsEl) fitRoundsEl.textContent = ratingRounds || "--";
  }

  /* ------------------------------------------------------------
     📜 Render LaTeX
  ------------------------------------------------------------ */
  if (texOutput) {
    texOutput.style.background  = "rgba(10,16,32,0.85)";
    texOutput.style.color       = "#dfe7ff";
    texOutput.style.whiteSpace  = "pre-wrap";
    texOutput.textContent = (texString || "").trim()
      ? texString
      : "% ⚠️ No optimized LaTeX found.\n% Please re-run optimization from Home.";
  }

  /* ------------------------------------------------------------
     📋 Copy / Download LaTeX
  ------------------------------------------------------------ */
  btnCopyTex?.addEventListener("click", async () => {
    if (!(texString || "").trim()) return toast("⚠️ No LaTeX to copy!");
    try {
      await navigator.clipboard.writeText(texString);
      toast("✅ LaTeX copied to clipboard!");
    } catch {
      toast("⚠️ Clipboard permission denied.");
    }
  });

  btnDownloadTex?.addEventListener("click", () => {
    if (!(texString || "").trim()) return toast("⚠️ No LaTeX to download!");
    const name = sanitize(`HIREX_Resume_${company}_${role}_${getTS()}.tex`);
    downloadText(name, texString);
    toast("⬇️ Downloading LaTeX file…");
  });

  /* ------------------------------------------------------------
     📄 PDF Renderer
  ------------------------------------------------------------ */
  const objectUrls = [];
  const makePdfUrl = (b64) => {
    const blob = b64ToBlob(b64);
    if (!blob) return "";
    const url = URL.createObjectURL(blob);
    objectUrls.push(url);
    return url;
  };

  const createPdfCard = (title, b64, suffix = "") => {
    const url = makePdfUrl(b64);
    if (!url) return "";
    const filename = sanitize(`HIREX_Resume_${company}_${role}${suffix}_${getTS()}.pdf`);
    return `
      <div class="pdf-card anim fade">
        <h3>${title}</h3>
        <div class="pdf-frame">
          <iframe src="${url}#view=FitH" loading="lazy" title="${title}"></iframe>
        </div>
        <div class="pdf-download">
          <button class="cta-primary" data-url="${url}" data-filename="${filename}">
            ⬇️ Download PDF
          </button>
        </div>
      </div>`;
  };

  const renderPdfs = () => {
    let html = "";
    if (pdfB64)           html += createPdfCard("Optimized Resume", pdfB64);
    if (pdfB64Humanized)  html += createPdfCard("Humanized Resume (Tone-Refined)", pdfB64Humanized, "_Humanized");

    if (!html) {
      html = `<p class="muted" style="text-align:center;margin-top:2rem;">
        ⚠️ No PDF cached — optimize your resume first or pick a saved item on the left.
      </p>`;
    }

    if (pdfContainer) pdfContainer.innerHTML = html;
  };

  renderPdfs();

  pdfContainer?.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-filename]");
    if (!btn) return;
    const { filename, url } = btn.dataset;
    try {
      const blob = await fetch(url).then((r) => r.blob());
      downloadFile(filename, blob);
    } catch {
      toast("❌ Failed to download PDF.");
    }
  });

  /* ------------------------------------------------------------
     ✨ Humanize Mode Highlight
  ------------------------------------------------------------ */
  const highlightActiveMode = (on) => {
    const cards = pdfContainer?.querySelectorAll(".pdf-card") || [];
    cards.forEach((c) => c.classList.remove("preferred"));
    cards.forEach((c) => {
      const isHuman = /Humanized/i.test(c.querySelector("h3")?.textContent || "");
      const prefer  = on ? isHuman : !isHuman;
      if (prefer) c.classList.add("preferred");
    });
  };

  const humanizeOn = (() => {
    if (typeof RT.getHumanizeState === "function") {
      try { return !!RT.getHumanizeState(); } catch {}
    }
    const storedBool = localStorage.getItem("hirex_use_humanize"); // "true"/"false"
    if (storedBool === "true" || storedBool === "false") return storedBool === "true";
    return localStorage.getItem("hirex-use-humanize") === "on";  // legacy "on"/"off"
  })();

  highlightActiveMode(humanizeOn);
  window.addEventListener("hirex:humanize-change", (e) =>
    highlightActiveMode(!!e.detail?.on)
  );

  /* ------------------------------------------------------------
     ☁️ Auto-load most recent server memory if nothing local
  ------------------------------------------------------------ */
  (async () => {
    const nothingLocal =
      !(texString || "").trim() &&
      !(pdfB64 || "").trim() &&
      !(pdfB64Humanized || "").trim();

    if (!nothingLocal) return;

    try {
      const res = await fetch(`${apiBase}/api/context/get?latest=true`);
      if (res.ok) {
        const ctx = await res.json();
        if (ctx && (ctx.pdf_base64 || ctx.pdf_base64_humanized || ctx.humanized_tex || ctx.resume_tex)) {
          // store and re-render
          companyRaw = ctx.company || companyRaw;
          roleRaw    = ctx.role || roleRaw;
          company    = sanitize(companyRaw).replace(/\s+/g, "_");
          role       = sanitize(roleRaw).replace(/\s+/g, "_");

          texString       = ctx.humanized_tex || ctx.resume_tex || texString;
          pdfB64          = ctx.pdf_base64 || pdfB64;
          pdfB64Humanized = ctx.pdf_base64_humanized || pdfB64Humanized;

          localStorage.setItem("hirex_company", companyRaw);
          localStorage.setItem("hirex_role", roleRaw);
          if (texString) localStorage.setItem("hirex_tex", texString);
          if (pdfB64) localStorage.setItem("hirex_pdf", pdfB64);
          if (pdfB64Humanized) localStorage.setItem("hirex_pdf_humanized", pdfB64Humanized);
          if (ctx.fit_score) localStorage.setItem("hirex_fit_score", ctx.fit_score);

          // refresh UI parts
          if (texOutput) texOutput.textContent = texString || texOutput.textContent;
          renderPdfs();
          highlightActiveMode(humanizeOn);
          toast("☁️ Loaded latest resume from server memory.");
        }
      }
    } catch (e) {
      console.warn("[HIREX] Could not fetch latest context:", e);
    }
  })();

  /* ------------------------------------------------------------
     🧹 Cleanup + Init Log
  ------------------------------------------------------------ */
  window.addEventListener("beforeunload", () =>
    objectUrls.forEach((u) => URL.revokeObjectURL(u))
  );

  console.log(
    "%c📄 HIREX preview.js initialized — v2.0.0",
    "background:#5bd0ff;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  debug("PREVIEW PAGE LOADED", {
    version: APP_VERSION,
    company: companyRaw,
    role: roleRaw,
    ratingScore,
    ratingRounds,
    historyCount: history.length,
    hasTex: !!(texString || "").trim(),
    hasPdf: !!(pdfB64 || "").trim(),
    hasPdfHumanized: !!(pdfB64Humanized || "").trim(),
  });
});
