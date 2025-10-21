
/* ============================================================
ASTRA • main.js (v2.0.0 — Unified Frontend Integration)
-------------------------------------------------------

Handles:
• JD submission → FastAPI /api/optimize/run (smart fallback)
• OpenAPI discovery (prefers /api/*, but can use /optimize)
• Auto-retry with placeholder base_resume_tex on 422
• Caches LaTeX / PDFs / JD-fit metrics in localStorage
• Saves JD + (optimized/humanized) resume to /api/context/save
• Safe Abort + Cancel UI with smooth toast feedback
• Keyboard + reset shortcuts
• Offline-aware (graceful error handling + no hard deps)
• History record includes type: "optimization"
Author: Sri Akash Kadali
============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const APP_NAME = "ASTRA";
  const APP_VERSION = "v2.0.0";

  /* ------------------------------------------------------------
     🔧 Elements
  ------------------------------------------------------------ */
  const form = document.getElementById("optimize-form");
  const jdInput = document.getElementById("jd");
  const hiddenHumanize = document.getElementById("use_humanize_state");

  /* ------------------------------------------------------------
     🧠 Utilities
  ------------------------------------------------------------ */
  const RT = (window.ASTRA ?? window.HIREX) || {};

  const getApiBase = () => {
    try { if (typeof RT.getApiBase === "function") return RT.getApiBase(); } catch {}
    if (["127.0.0.1", "localhost"].includes(location.hostname)) return "http://127.0.0.1:8000";
    return location.origin;
  };

  const toast  = (msg, t = 3000) => (RT.toast ? RT.toast(msg, t) : alert(msg));
  const debug  = (msg, data) => RT.debugLog?.(msg, data);
  const apiBase = getApiBase();

  const sanitize = (name) =>
    String(name || "file").replace(/[\\/:*?"<>|]+/g, "_").trim() || "file";

  const truthy = (v) => ["on", "true", "1", "yes"].includes(String(v ?? "").toLowerCase());

  const getHumanize = () => {
    if (hiddenHumanize) return truthy(hiddenHumanize.value);
    const a = localStorage.getItem("hirex-use-humanize");
    const b = localStorage.getItem("hirex_use_humanize");
    return truthy(a ?? b);
  };

  const getActiveModel = () =>
    localStorage.getItem("hirex_model") ||
    (typeof RT.getCurrentModel === "function" ? RT.getCurrentModel() : "") ||
    "gpt-4o-mini";

  const disableForm = (state) => {
    if (!form) return;
    Array.from(form.elements).forEach((el) => (el.disabled = state));
    form.style.opacity = state ? 0.6 : 1;
  };

  const progressFinish = () => document.dispatchEvent(new Event("hirex-finish"));

  /* ------------------------------------------------------------
     💾 Cache Utilities (Unified schema; backward-compatible)
  ------------------------------------------------------------ */
  const persistResults = (data, useHumanize, jdText) => {
    try {
      const score =
        typeof data.rating_score === "number"
          ? data.rating_score
          : typeof data.coverage_ratio === "number"
          ? Math.round((data.coverage_ratio || 0) * 100)
          : null;

      const record = {
        id: Date.now(),
        company: data.company || data.company_name || "UnknownCompany",
        role: data.role || "UnknownRole",
        fit_score: score ?? null,
        timestamp: new Date().toISOString(),
        pdf_path: data.pdf_path || null,
        type: "optimization",
      };

      const history = JSON.parse(localStorage.getItem("hirex_history") || "[]");
      history.push(record);
      localStorage.setItem("hirex_history", JSON.stringify(history));

      const kv = {
        hirex_tex: data.tex_string || "",
        hirex_pdf: data.pdf_base64 || "",
        hirex_pdf_humanized: data.pdf_base64_humanized || "",
        hirex_company: record.company,
        hirex_role: record.role,
        hirex_fit_score: score ?? "n/a",
        hirex_use_humanize: useHumanize ? "true" : "false",
        hirex_timestamp: record.timestamp,
        hirex_version: APP_VERSION,
        hirex_jd_text: jdText || "",
      };
      Object.entries(kv).forEach(([k, v]) => localStorage.setItem(k, String(v)));
      localStorage.setItem("hirex-use-humanize", useHumanize ? "on" : "off");

      debug("✅ Cached optimization results", record);
    } catch (err) {
      console.error("[ASTRA] Cache error:", err);
    }
  };

  /* ------------------------------------------------------------
     🧠 Persist context on backend (best-effort)
  ------------------------------------------------------------ */
  const saveContextOnBackend = async (data, jdText) => {
    try {
      const fd = new FormData();
      const company = data.company || data.company_name || "";
      const role = data.role || "";
      const fit =
        typeof data.rating_score === "number"
          ? String(data.rating_score)
          : typeof data.coverage_ratio === "number"
          ? String(Math.round((data.coverage_ratio || 0) * 100))
          : "";

      fd.append("company", company);
      fd.append("role", role);
      fd.append("jd_text", jdText || "");
      fd.append("resume_tex", data.tex_string || "");
      fd.append("humanized_tex", data.tex_string || "");
      fd.append("pdf_base64", data.pdf_base64 || "");
      fd.append("pdf_base64_humanized", data.pdf_base64_humanized || "");
      fd.append("model", getActiveModel());
      fd.append("fit_score", fit);

      const res = await fetch(`${apiBase}/api/context/save`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const resp = await res.json().catch(() => ({}));
      debug("🧷 Context saved", resp);
    } catch (e) {
      console.warn("[ASTRA] Context save skipped:", e);
    }
  };

  /* ------------------------------------------------------------
     📄 Placeholder base (only to satisfy 422 validation)
     — We DO NOT upload user base files; backend should use its default.
  ------------------------------------------------------------ */
  const addPlaceholderBase = (fd) => {
    const blob = new Blob(["% USE_SERVER_DEFAULT base_resume.tex\n"], { type: "text/plain" });
    fd.append("base_resume_tex", blob, "USE_SERVER_DEFAULT.tex");
    return fd;
  };

  /* ------------------------------------------------------------
     🧩 FormData Builders
  ------------------------------------------------------------ */
  const buildFormData = (jdText, useHumanize) => {
    const fd = new FormData();
    // v2 primary keys
    fd.append("jd_text", jdText || "");
    fd.append("use_humanize", useHumanize ? "true" : "false");
    fd.append("latex_safe", "true");
    // Compatibility aliases
    fd.append("jd", jdText || "");
    fd.append("job_description", jdText || "");
    fd.append("humanize", useHumanize ? "true" : "false");
    fd.append("model", getActiveModel());
    return fd;
  };

  /* ------------------------------------------------------------
     🌐 Optimize API helpers (smart discovery + fallback)
  ------------------------------------------------------------ */
  const CANDIDATE_PATHS = [
    "/api/optimize/run",     // preferred v2
    "/api/optimize",         // legacy
    "/api/optimize/submit",  // alt
    "/api/optimize/jd",      // occasional
    "/optimize"              // non-/api legacy (LAST resort)
  ];

  const postOptimize = async (url, fd, controller) => {
    const res = await fetch(url, { method: "POST", body: fd, signal: controller.signal });
    const text = await res.text().catch(() => "");
    if (!res.ok) {
      const err = new Error(text || `HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    try { return JSON.parse(text); }
    catch { throw new Error("Invalid JSON response from backend."); }
  };

  const discoverOptimizePath = async () => {
    try {
      const spec = await fetch(`${apiBase}/openapi.json`).then(r => r.json());
      const paths = Object.keys(spec.paths || {});
      const hitsApi   = paths.filter(p => /optimiz|resume/i.test(p) && p.startsWith("/api/"));
      const hitsOther = paths.filter(p => /optimiz|resume/i.test(p) && !p.startsWith("/api/"));
      return [...hitsApi, ...hitsOther][0] || null;
    } catch {
      return null;
    }
  };

  const tryOnePath = async (path, jd, useHumanize, controller) => {
    // First attempt: no base file → let server use its configured default
    let fd = buildFormData(jd, useHumanize);
    try {
      return await postOptimize(`${apiBase}${path}`, fd, controller);
    } catch (err) {
      const msg = String(err.message || "").toLowerCase();

      // 404 → bubble up so outer loop tries next path
      if (err.status === 404) throw err;

      // 422 complaining about base_resume_tex → retry once with placeholder marker
      if ((err.status === 422 || /422/.test(String(err.message || ""))) && /base_resume_tex/i.test(String(err.message || ""))) {
        debug("422 needs base_resume_tex — retrying with placeholder", { path });
        fd = buildFormData(jd, useHumanize);
        addPlaceholderBase(fd);
        return await postOptimize(`${apiBase}${path}`, fd, controller);
      }

      // 500 when backend default is actually missing → surface a clear, actionable error
      if (err.status === 500 && (msg.includes("default base resume not found") || msg.includes("no default base"))) {
        const e = new Error("Backend has no default base resume configured. Set the server's base_resume path.");
        e.status = 500;
        throw e;
      }

      // Other errors → rethrow
      throw err;
    }
  };

  const postOptimizeWithFallback = async (jd, useHumanize, controller) => {
    const cached     = localStorage.getItem("hirex_optimize_url");
    const discovered = await discoverOptimizePath();

    // Build final order (dedupe, preserve priority)
    const order = [cached, discovered, ...CANDIDATE_PATHS]
      .filter(Boolean)
      .filter((p, i, a) => a.indexOf(p) === i);

    for (const path of order) {
      try {
        const data = await tryOnePath(path, jd, useHumanize, controller);
        localStorage.setItem("hirex_optimize_url", path);
        debug("✅ Optimize path OK", { path });
        return data;
      } catch (err) {
        if (err.status === 404) {
          debug("Optimize path 404 — trying next", { path });
          continue;
        }
        // If it's the "no default base on server" case, surface immediately
        if (err.status === 500 && /base resume/i.test(String(err.message || ""))) throw err;

        // Otherwise log and try next candidate
        debug("Optimize path error — trying next", { path, error: String(err.message || err) });
        continue;
      }
    }
    const e = new Error("No optimize endpoint responded successfully. Open /docs to confirm the path.");
    e.status = 404;
    throw e;
  };

  /* ------------------------------------------------------------
     🚀 Form Submission Handler
  ------------------------------------------------------------ */
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const jd = jdInput?.value?.trim();
    const useHumanize = getHumanize();
    if (!jd) return toast("⚠️ Please paste the job description first.");

    disableForm(true);
    toast("⏳ Optimizing your resume…");
    debug("Submitting optimization", { useHumanize });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000); // 3 min

    // Cancel button
    let canceled = false;
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "❌ Cancel";
    cancelBtn.className = "cta-secondary";
    cancelBtn.style.marginTop = "1rem";
    form.appendChild(cancelBtn);
    cancelBtn.onclick = () => {
      canceled = true;
      controller.abort();
      toast("🛑 Optimization canceled by user.");
      cancelBtn.remove();
    };

    try {
      const data = await postOptimizeWithFallback(jd, useHumanize, controller);

      clearTimeout(timeout);
      cancelBtn.remove();

      if (!data?.tex_string && !data?.pdf_base64) throw new Error("Empty or malformed response from backend.");

      // Cache for other pages
      persistResults(data, useHumanize, jd);

      // Persist context to backend memory (ASTRA store)
      saveContextOnBackend(data, jd);

      const company = sanitize(data.company || data.company_name || "Company");
      const role    = sanitize(data.role || "Role");
      const score =
        typeof data.rating_score === "number"
          ? `${data.rating_score}/100`
          : typeof data.coverage_ratio === "number"
          ? `${Math.round((data.coverage_ratio || 0) * 100)}/100`
          : "n/a";

      toast(`✅ Optimized for ${company} (${role}) — JD Fit ${score}`);

      setTimeout(() => { if (!canceled) window.location.href = "/preview.html"; }, 1200);

      progressFinish();
    } catch (err) {
      console.error("[ASTRA] Optimization error:", err);
      const msg = String(err.message || "");
      if (err.name === "AbortError") {
        toast("⚠️ Optimization canceled or timed out (3 min limit).");
      } else if (/Failed to fetch|NetworkError/i.test(msg)) {
        toast("🌐 Network error — check FastAPI backend connection.");
      } else if (/no default base|default base resume not found/i.test(msg)) {
        toast("📄 Backend has no default base resume configured. Please set the server base_resume path and retry.");
      } else {
        toast("❌ " + msg);
      }
    } finally {
      clearTimeout(timeout);
      disableForm(false);
      if (cancelBtn.isConnected) cancelBtn.remove();
    }
  });

  /* ------------------------------------------------------------
     🧹 Reset Handler (clears cache)
  ------------------------------------------------------------ */
  form?.addEventListener("reset", () => {
    [
      "hirex_tex",
      "hirex_pdf",
      "hirex_pdf_humanized",
      "hirex_company",
      "hirex_role",
      "hirex_fit_score",
      "hirex_use_humanize",
      "hirex-use-humanize",
      "hirex_timestamp",
      "hirex_version",
      "hirex_jd_text",
    ].forEach((k) => localStorage.removeItem(k));
    toast("🧹 Cleared form and local cache.");
  });

  /* ------------------------------------------------------------
     💡 UX Enhancements
  ------------------------------------------------------------ */
  jdInput?.addEventListener("focus", () =>
    jdInput.scrollIntoView({ behavior: "smooth", block: "center" })
  );

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "enter") form?.requestSubmit();
  });

  /* ------------------------------------------------------------
     ✅ Init Log
  ------------------------------------------------------------ */
  console.log(
    `%c⚙️ ${APP_NAME} main.js initialized — ${APP_VERSION}`,
    "background:#5bd0ff;color:#00121e;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  debug("MAIN PAGE LOADED", {
    app: APP_NAME,
    version: APP_VERSION,
    apiBase,
    hasHumanize: getHumanize(),
    model: getActiveModel(),
    origin: location.origin,
  });
});
