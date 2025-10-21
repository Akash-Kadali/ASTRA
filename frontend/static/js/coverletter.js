/* ============================================================
   ASTRA • coverletter.js (v2.0.0 — JD-Specific Cover Letter)
   ------------------------------------------------------------
   What this does:
   • Reads the selected JD+Resume context from localStorage
   • Submits JD + (optional) latest resume .tex to /api/coverletter
     (maps EXACTLY to the new FastAPI backend contract)
   • Optional “Humanize BODY” via global toggle/state
   • Renders returned LaTeX and PDF into the current UI
     (works with coverletter.html: tabs + iframe)
   • Adds small PDF/LaTeX toolbar (copy / download)
   • Timeout (3m) + Cancel + graceful error handling
   • Progressive enhancement: no hard errors if DOM partial
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const APP_NAME = "ASTRA";
  const APP_VERSION = "v2.0.0";

  /* ------------------------------------------------------------
     🌐 Elements (optional-safe; code won’t explode if missing)
  ------------------------------------------------------------ */
  const selectEl    = document.getElementById("historySelect");
  const genBtn      = document.getElementById("generate_btn");
  const statusBadge = document.getElementById("meta_badge");

  const panePdf     = document.getElementById("pane_pdf");
  const pdfFrame    = document.getElementById("pdf_frame");

  const paneTex     = document.getElementById("pane_tex");
  const texOut      = document.getElementById("cl-tex-output");

  const paneBody    = document.getElementById("pane_body");
  const bodyOut     = document.getElementById("body_output");

  /* ------------------------------------------------------------
     🧠 Runtime helpers (integrates with master.js if present)
  ------------------------------------------------------------ */
  const RT = (window.ASTRA ?? window.HIREX) || {};
  const debug = (msg, data) => (typeof RT.debugLog === "function" ? RT.debugLog(msg, data) : void 0);

  const getApiBase = () => {
    try {
      if (typeof RT.getApiBase === "function") return RT.getApiBase();
    } catch {}
    if (["127.0.0.1", "localhost"].includes(location.hostname)) return "http://127.0.0.1:8000";
    return location.origin;
  };
  const apiBase = getApiBase();

  const toast = (msg, t = 3000) => (RT.toast ? RT.toast(msg, t) : alert(msg));
  const nowStamp = () => new Date().toISOString().replace(/[:.]/g, "-");
  const sanitize = (name) => String(name || "file").replace(/[\\/:*?"<>|]+/g, "_").trim() || "file";

  const b64ToBlob = (b64, mime = "application/pdf") =>
    new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: mime });

  const downloadText = (name, text) => {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };

  const downloadBlob = (name, blob) => {
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };

  const getHumanizeState = () => {
    try {
      if (typeof RT.getHumanizeState === "function") return !!RT.getHumanizeState();
    } catch {}
    return localStorage.getItem("hirex-use-humanize") === "on";
  };

  const getTone = () => {
    try {
      if (typeof RT.getTone === "function") return RT.getTone() || "balanced";
    } catch {}
    const el = document.getElementById("toneSelect");
    return (el && el.value) || "balanced";
  };

  const getLengthPref = () => {
    try {
      if (typeof RT.getCoverLetterLength === "function") return RT.getCoverLetterLength() || "standard";
    } catch {}
    const el = document.getElementById("lengthSelect");
    return (el && el.value) || "standard";
  };

  /* ------------------------------------------------------------
     📦 Context helpers
  ------------------------------------------------------------ */
  const pickFromHistory = (index) => {
    const history = JSON.parse(localStorage.getItem("hirex_history") || "[]");
    return history?.[index] || null;
  };

  const getFallbackCtx = () => ({
    jd:        localStorage.getItem("hirex_jd_text") || "",
    resumeTex: localStorage.getItem("hirex_tex") || "",
    company:   localStorage.getItem("hirex_company") || "Company",
    role:      localStorage.getItem("hirex_role") || "Role",
  });

  const getSelectedContext = () => {
    const idx = Number(selectEl?.value ?? 0);
    const item = pickFromHistory(idx);
    const fallback = getFallbackCtx();

    const selected = (() => {
      try { return JSON.parse(localStorage.getItem("hirex_selected_cl") || "null"); }
      catch { return null; }
    })();

    return {
      company:   selected?.company ?? item?.company ?? fallback.company,
      role:      selected?.role ?? item?.role ?? fallback.role,
      jd:        selected?.jd_text ?? item?.jd_text ?? fallback.jd,
      resumeTex: selected?.resume_tex ?? item?.resume_tex ?? fallback.resumeTex,
    };
  };

  /* ------------------------------------------------------------
     🧱 Build FormData for POST — matches backend contract
     Backend (/api/coverletter) expects:
       jd_text (Form, required)
       resume_tex (Form, default "")
       use_humanize (Form, default True)
       tone (Form, default "balanced")
       length (Form, default "standard")
  ------------------------------------------------------------ */
  const buildFormData = ({ jd, resumeTex, useHumanize, tone, length }) => {
    const fd = new FormData();
    fd.append("jd_text", jd || "");
    fd.append("resume_tex", (resumeTex || "").trim());
    fd.append("use_humanize", useHumanize ? "true" : "false");
    fd.append("tone", tone || "balanced");
    fd.append("length", length || "standard");
    return fd;
  };

  /* ------------------------------------------------------------
     🚀 POST /api/coverletter with cancel/timeout
  ------------------------------------------------------------ */
  const postCoverLetter = async (url, fd, controller) => {
    const res = await fetch(url, { method: "POST", body: fd, signal: controller.signal });
    const text = await res.text().catch(() => "");
    if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
    try {
      return JSON.parse(text);
    } catch {
      throw new Error("Invalid JSON from backend.");
    }
  };

  /* ------------------------------------------------------------
     🖼 Rendering helpers
  ------------------------------------------------------------ */
  const objectUrls = [];
  const urlFromPdfB64 = (b64) => {
    const blob = b64ToBlob(b64);
    const url = URL.createObjectURL(blob);
    objectUrls.push(url);
    return url;
  };

  const ensurePdfToolbar = (containerEl) => {
    if (!containerEl) return null;
    let bar = containerEl.querySelector(".cl-toolbar");
    if (bar) return bar;

    bar = document.createElement("div");
    bar.className = "cl-toolbar";
    bar.style.display = "flex";
    bar.style.gap = ".5rem";
    bar.style.justifyContent = "flex-end";
    bar.style.margin = ".5rem 0 0";

    const btnPdf = document.createElement("button");
    btnPdf.id = "cl_dl_pdf";
    btnPdf.className = "btn accent";
    btnPdf.textContent = "⬇️ Download PDF";

    const btnTex = document.createElement("button");
    btnTex.id = "cl_dl_tex";
    btnTex.className = "btn";
    btnTex.textContent = "⬇️ Download .tex";

    const btnCopy = document.createElement("button");
    btnCopy.id = "cl_copy_tex";
    btnCopy.className = "btn";
    btnCopy.textContent = "📋 Copy LaTeX";

    bar.append(btnPdf, btnTex, btnCopy);
    containerEl.prepend(bar);
    return bar;
  };

  const extractBodyFromLatex = (tex = "") => {
    const docMatch = tex.match(/\\begin\{document\}([\s\S]*?)\\end\{document\}/i);
    if (docMatch) return docMatch[1].trim();
    return tex
      .split("\n")
      .filter((l) => !/^\\documentclass|^\\usepackage|^%/.test(l.trim()))
      .join("\n")
      .trim();
  };

  const renderOutputs = (data = {}) => {
    // Backend returns: company, role, tone, use_humanize, tex_string, pdf_base64
    const {
      tex_string = "",
      pdf_base64 = "",
      company = "",
      role = "",
    } = data;

    // LaTeX
    if (texOut) {
      texOut.textContent = tex_string.trim() || "% ⚠️ No LaTeX returned.\n% Try again.";
    }

    // Body (plain)
    if (bodyOut) {
      const body = extractBodyFromLatex(tex_string || "");
      bodyOut.textContent = (body || "(no body extracted)").trim();
    }

    // PDF -> iframe
    if (pdfFrame) {
      if (pdf_base64) {
        const url = urlFromPdfB64(pdf_base64);
        pdfFrame.src = `${url}#view=FitH`;

        // Add toolbar (copy/download)
        const bar = ensurePdfToolbar(panePdf || pdfFrame.parentElement);
        if (bar) {
          const comp = sanitize(company || "Company").replace(/\s+/g, "_");
          const rl   = sanitize(role || "Role").replace(/\s+/g, "_");
          const pdfName = `ASTRA_CoverLetter_${comp}_${rl}_${nowStamp()}.pdf`;
          const texName = `ASTRA_CoverLetter_${comp}_${rl}_${nowStamp()}.tex`;

          bar.querySelector("#cl_dl_pdf")?.addEventListener("click", async () => {
            try {
              const blob = await fetch(url).then((r) => r.blob());
              downloadBlob(pdfName, blob);
            } catch (e) {
              console.error("[ASTRA] PDF download error:", e);
              toast("❌ Failed to download PDF.");
            }
          });

          bar.querySelector("#cl_dl_tex")?.addEventListener("click", () => {
            if (!(tex_string || "").trim()) return toast("⚠️ No LaTeX to download!");
            downloadText(texName, tex_string);
          });

          bar.querySelector("#cl_copy_tex")?.addEventListener("click", async () => {
            if (!(tex_string || "").trim()) return toast("⚠️ No LaTeX to copy!");
            try {
              await navigator.clipboard.writeText(tex_string);
              toast("✅ LaTeX copied!");
            } catch (e) {
              console.error("[ASTRA] Clipboard error:", e);
              toast("⚠️ Clipboard permission denied.");
            }
          });
        }
      } else {
        pdfFrame.removeAttribute("src");
      }
    }
  };

  /* ------------------------------------------------------------
     💾 Cache results (unified schema)
  ------------------------------------------------------------ */
  const cacheResult = (data = {}, fallbackCtx = {}) => {
    try {
      const record = {
        id: Date.now(),
        company: data.company || fallbackCtx.company || "Company",
        role: data.role || fallbackCtx.role || "Role",
        fit_score: data.fit_score ?? null,
        type: "coverletter",
        timestamp: new Date().toISOString(),
      };
      const history = JSON.parse(localStorage.getItem("hirex_history") || "[]");
      history.push(record);
      localStorage.setItem("hirex_history", JSON.stringify(history));

      if (data.tex_string) localStorage.setItem("hirex_cl_tex", data.tex_string);
      if (data.pdf_base64) localStorage.setItem("hirex_cl_pdf", data.pdf_base64);
      localStorage.setItem("hirex_cl_company", record.company);
      localStorage.setItem("hirex_cl_role", record.role);
      localStorage.setItem("hirex_cl_version", APP_VERSION);
    } catch (err) {
      console.warn("[ASTRA] Cache save failed:", err);
    }
  };

  /* ------------------------------------------------------------
     ✉️ Generate handler
  ------------------------------------------------------------ */
  const setStatus = (txt) => { if (statusBadge) statusBadge.textContent = txt; };

  const generateCoverLetter = async () => {
    const ctx = getSelectedContext();
    if (!ctx.jd?.trim()) {
      toast("⚠️ No Job Description found for the selected item.");
      setStatus("Idle");
      return;
    }

    const useHumanize = getHumanizeState();
    const tone = getTone();
    const length = getLengthPref();

    setStatus("Generating…");
    genBtn && (genBtn.disabled = true);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000); // 3 minutes
    let cancelBtn;

    if (statusBadge && !document.getElementById("cl_cancel_btn")) {
      cancelBtn = document.createElement("button");
      cancelBtn.id = "cl_cancel_btn";
      cancelBtn.type = "button";
      cancelBtn.textContent = "❌ Cancel";
      cancelBtn.className = "btn";
      cancelBtn.style.marginLeft = "0.5rem";
      statusBadge.insertAdjacentElement("afterend", cancelBtn);
      cancelBtn.onclick = () => controller.abort();
    }

    const fd = buildFormData({
      jd: ctx.jd,
      resumeTex: ctx.resumeTex || "",
      useHumanize,
      tone,
      length,
    });

    const endpoint = `${apiBase}/api/coverletter`;

    try {
      const data = await postCoverLetter(endpoint, fd, controller);

      clearTimeout(timeout);
      cancelBtn?.remove();

      if (!data?.tex_string && !data?.pdf_base64) {
        throw new Error("Empty cover letter response from backend.");
      }

      renderOutputs(data);
      cacheResult(data, ctx);
      toast(`✅ Cover Letter ready for ${data.company || ctx.company}`);
      setStatus("Ready");
    } catch (err) {
      console.error("[ASTRA] CoverLetter Error:", err);
      if (err.name === "AbortError") {
        toast("⚠️ Generation canceled or timed out (3 min).");
        setStatus("Canceled / Timed out");
      } else if (/Failed to fetch|NetworkError/i.test(err.message || "")) {
        toast("🌐 Network error — check FastAPI connection.");
        setStatus("Network error");
      } else {
        toast("❌ " + (err.message || "Unexpected error occurred."));
        setStatus("Error");
      }
    } finally {
      clearTimeout(timeout);
      cancelBtn?.remove();
      genBtn && (genBtn.disabled = false);
    }
  };

  /* ------------------------------------------------------------
     🔘 Wire up Generate button
  ------------------------------------------------------------ */
  genBtn?.addEventListener("click", generateCoverLetter);

  /* ------------------------------------------------------------
     🧹 Revoke object URLs on unload
  ------------------------------------------------------------ */
  window.addEventListener("beforeunload", () => {
    objectUrls.forEach((u) => URL.revokeObjectURL(u));
  });

  /* ------------------------------------------------------------
     ✅ Init log
  ------------------------------------------------------------ */
  console.log(
    `%c✉️ ${APP_NAME} coverletter.js initialized — ${APP_VERSION}`,
    "background:#5bd0ff;color:#00131c;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  debug("COVER LETTER JS LOADED", {
    app: APP_NAME,
    version: APP_VERSION,
    apiBase,
  });
});
