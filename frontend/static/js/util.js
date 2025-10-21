/* ============================================================ 
   HIREX • util.js (v2.0.0 — Unified Utility Layer)
   ------------------------------------------------------------
   Shared helper utilities across HIREX front-end modules.
   • Safe JSON/text fetch with retry, timeout & backoff
   • Base64 ↔ Blob conversions, download, clipboard, debounce
   • Theme & Humanize state helpers (persist + event emitters)
   • Storage wrappers, filename sanitizer, FormData builder
   • Integrated with HIREX logging + toast + cross-tab events
   Author: Sri Akash Kadali
   ============================================================ */

/* ============================================================
   🔧 Constants
   ============================================================ */
const UTIL_VERSION = "v2.0.0";
const DEFAULT_BASE_TEX_PATH = "data/samples/base_resume.tex";
const LS_KEYS = {
  THEME: "hirex-theme",
  HUMANIZE: "hirex-use-humanize",
};

/* ============================================================
   🧰 Safe localStorage
   ============================================================ */
function lsGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, val); return true; } catch { return false; }
}
function lsRemove(key) {
  try { localStorage.removeItem(key); } catch {}
}

/* ============================================================
   🌐 API Base Resolver (honor global if provided)
   ============================================================ */
function getApiBase() {
  try {
    if (window.HIREX && typeof window.HIREX.getApiBase === "function") {
      return window.HIREX.getApiBase();
    }
  } catch {}
  return ["127.0.0.1", "localhost"].includes(location.hostname)
    ? "http://127.0.0.1:8000"
    : location.origin;
}

/* ============================================================
   🌗 Theme Helpers
   ============================================================ */
function getSystemTheme() {
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  } catch { return "dark"; }
}
function getTheme() {
  return lsGet(LS_KEYS.THEME) || getSystemTheme();
}
function setTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  try {
    lsSet(LS_KEYS.THEME, t);
    document.documentElement.setAttribute("data-theme", t);
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    if (themeMeta) themeMeta.setAttribute("content", t === "dark" ? "#0a1020" : "#ffffff");
    window.dispatchEvent(new CustomEvent("hirex:theme-change", { detail: { theme: t } }));
    window.HIREX?.debugLog?.("Theme changed", { theme: t });
  } catch (err) {
    console.warn("[HIREX util] Failed to set theme:", err);
  }
  return t;
}
function onThemeChange(handler) {
  const fn = (e) => handler?.(e.detail?.theme ?? getTheme());
  window.addEventListener("hirex:theme-change", fn);
  return () => window.removeEventListener("hirex:theme-change", fn);
}

/* ============================================================
   🧑‍💼 Humanize Helpers (matches global toggle semantics)
   ============================================================ */
function getHumanizeState() {
  return (lsGet(LS_KEYS.HUMANIZE) || "off") === "on";
}
function setHumanizeState(on) {
  lsSet(LS_KEYS.HUMANIZE, on ? "on" : "off");
  window.dispatchEvent(new CustomEvent("hirex:humanize-change", { detail: { on } }));
  window.HIREX?.debugLog?.("Humanize state changed", { on });
  return on;
}
function onHumanizeChange(handler) {
  const fn = (e) => handler?.(!!e.detail?.on);
  window.addEventListener("hirex:humanize-change", fn);
  return () => window.removeEventListener("hirex:humanize-change", fn);
}

/* ============================================================
   🌍 Fetch Helpers (retry + timeout + exponential backoff)
   - Works with JSON bodies, FormData, Blobs, etc.
   - Respects caller-supplied AbortSignal (linked)
   ============================================================ */
async function _doFetch(url, options = {}, retries = 2) {
  const internalController = new AbortController();
  const timeoutMs = options.timeout ?? 20000;
  const timeout = setTimeout(() => internalController.abort(), timeoutMs);

  // Link external signal to internal controller if provided
  if (options.signal && typeof options.signal.addEventListener === "function") {
    options.signal.addEventListener("abort", () => internalController.abort(), { once: true });
  }

  const isJsonBody =
    options.body &&
    typeof options.body === "object" &&
    !(options.body instanceof FormData) &&
    !(options.body instanceof Blob) &&
    !(options.body instanceof ArrayBuffer);

  const headers = {
    Accept: "application/json",
    ...(isJsonBody ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(url, {
      // preserve caller flags like credentials/mode/cache
      ...options,
      headers,
      body: isJsonBody ? JSON.stringify(options.body) : options.body,
      signal: internalController.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      const err = `HTTP ${res.status}: ${msg || "Unknown error"}`;
      window.HIREX?.debugLog?.("fetch ERROR", { url, status: res.status, msg });
      throw new Error(err);
    }
    return res;
  } catch (err) {
    clearTimeout(timeout);
    if (retries > 0) {
      const attempt = 3 - retries + 1; // 1..3
      const delay = 500 * attempt + 600; // progressive backoff
      window.HIREX?.toast?.(`⚠️ Network hiccup — retrying in ${Math.ceil(delay / 1000)}s…`);
      await new Promise((r) => setTimeout(r, delay));
      return _doFetch(url, options, retries - 1);
    }
    window.HIREX?.toast?.(`❌ Network error: ${err.message || err}`);
    window.HIREX?.debugLog?.("fetch FAIL", { url, err: err.message });
    throw err;
  }
}

async function fetchJSON(url, options = {}, retries = 2) {
  const res = await _doFetch(url, options, retries);
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    // Attempt best-effort parse
    const text = await res.text().catch(() => "");
    try {
      const parsed = JSON.parse(text);
      window.HIREX?.debugLog?.("fetchJSON (text->json)", { url, keys: Object.keys(parsed || {}) });
      return parsed;
    } catch {
      window.HIREX?.debugLog?.("fetchJSON non-json", { url, length: text.length });
      return {};
    }
  }
  const json = await res.json().catch(() => ({}));
  window.HIREX?.debugLog?.("fetchJSON OK", { url, keys: Object.keys(json || {}) });
  return json;
}

async function fetchText(url, options = {}, retries = 2) {
  const res = await _doFetch(url, options, retries);
  const text = await res.text().catch(() => "");
  window.HIREX?.debugLog?.("fetchText OK", { url, len: text.length });
  return text;
}

function postJSON(url, data, options = {}, retries = 2) {
  return fetchJSON(url, { method: "POST", body: data, ...(options || {}) }, retries);
}

/* ============================================================
   🧪 Base64 / Blob Conversion
   ============================================================ */
function base64ToBlob(base64, mime = "application/octet-stream") {
  try {
    // Support data URLs (e.g., "data:application/pdf;base64,AAAA...")
    const idx = String(base64 || "").indexOf("base64,");
    const raw = idx !== -1 ? String(base64).slice(idx + 7) : String(base64);
    const bytes = Uint8Array.from(atob(raw), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: mime });
    window.HIREX?.debugLog?.("base64ToBlob OK", { size: blob.size, mime });
    return blob;
  } catch (e) {
    console.error("[HIREX] base64ToBlob error:", e);
    window.HIREX?.toast?.("⚠️ Failed to decode Base64 data.");
    return null;
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      try {
        const b64 = reader.result?.toString().split(",")[1] || "";
        window.HIREX?.debugLog?.("blobToBase64 OK", { size: b64.length });
        resolve(b64);
      } catch (err) {
        window.HIREX?.debugLog?.("blobToBase64 ERROR", { err: err.message });
        reject(err);
      }
    };
    reader.onerror = (e) => reject(e);
    reader.readAsDataURL(blob);
  });
}

/* ============================================================
   ⬇️ Download + Clipboard
   ============================================================ */
function downloadFile(filename, data, mime = "application/octet-stream") {
  try {
    const blob =
      data instanceof Blob
        ? data
        : typeof data === "string"
        ? new Blob([data], { type: mime })
        : new Blob([JSON.stringify(data)], { type: mime });

    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 600);
    window.HIREX?.toast?.(`⬇️ Downloading ${filename}`);
  } catch (e) {
    console.error("[HIREX] downloadFile error:", e);
    window.HIREX?.toast?.("❌ Download failed.");
  }
}

function downloadTextFile(filename, text) {
  downloadFile(filename, text, "text/plain");
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    window.HIREX?.toast?.("📋 Copied to clipboard!");
  } catch (e) {
    console.error("[HIREX] copy error:", e);
    window.HIREX?.toast?.("⚠️ Clipboard permission denied.");
  }
}

/* ============================================================
   🕒 Misc Helpers
   ============================================================ */
function getTimestamp() {
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  window.HIREX?.debugLog?.("getTimestamp", { ts });
  return ts;
}

function debounce(fn, delay = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
}

function sleep(ms = 500) {
  return new Promise((r) => setTimeout(r, ms));
}

function formatBytes(bytes, decimals = 2) {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function sanitizeFilename(name, fallback = "file") {
  try {
    return (
      String(name)
        .replace(/[\\/:*?"<>|]+/g, "_")
        .replace(/\s+/g, " ")
        .trim() || fallback
    );
  } catch {
    return fallback;
  }
}

/* ============================================================
   📝 FormData Builder (aligns with backend v2.0.0)
   ============================================================ */
function buildOptimizeFormData(jdText, useHumanize) {
  const fd = new FormData();
  fd.append("jd_text", jdText || "");
  fd.append("use_humanize", useHumanize ? "true" : "false");
  return fd;
}

/* ============================================================
   🔗 Export Namespace
   ============================================================ */
window.HIREX = window.HIREX || {};
Object.assign(window.HIREX, {
  UTIL_VERSION,
  DEFAULT_BASE_TEX_PATH,
  LS_KEYS,

  lsGet,
  lsSet,
  lsRemove,

  getApiBase,

  getSystemTheme,
  getTheme,
  setTheme,
  onThemeChange,

  getHumanizeState,
  setHumanizeState,
  onHumanizeChange,

  fetchJSON,
  fetchText,
  postJSON,

  base64ToBlob,
  blobToBase64,

  downloadFile,
  downloadTextFile,
  copyToClipboard,

  getTimestamp,
  debounce,
  sleep,
  formatBytes,
  sanitizeFilename,
  buildOptimizeFormData,
});

console.log(
  `%c⚙️ [HIREX] util.js initialized — ${UTIL_VERSION}`,
  "background:#5bd0ff;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
);
