"""
============================================================
 HIREX v2.0.0— main.py (Windows App Version)
 ------------------------------------------------------------
 Launches FastAPI backend + HTML/JS UI inside a native
 Windows window via PyWebview.

 Features:
   • Graceful startup with backend health polling
   • Built-in close (✖) button that exits cleanly
   • Auto router discovery (with import fallbacks) + logging
   • Developer-friendly CORS + tracing middleware
   • Cross-platform fallback (CLI-only mode)

 Author: Sri Akash Kadali
============================================================
"""

# ============================================================
# 🧭 Path Setup
# ============================================================
import os
import sys
import time
import signal
import threading
import importlib
from typing import Optional, Dict

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

for p in (ROOT_DIR, CURRENT_DIR, os.path.join(ROOT_DIR, "backend")):
    if p not in sys.path:
        sys.path.append(p)


# ============================================================
# 🪵 Logging Helper
# ============================================================
def _fallback_log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

try:
    from backend.core.utils import log_event  # type: ignore
except Exception:
    log_event = _fallback_log


# ============================================================
# 🌐 FastAPI Backend
# ============================================================
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

APP_VERSION = "2.0.0"

app = FastAPI(
    title="HIREX API",
    description="High Resume eXpert — AI-powered Resume, Cover Letter, and Assistant",
    version=APP_VERSION,
)

# ------------------------------------------------------------
# 🔄 Router Auto-Import (tries backend.api.<name> then api.<name>)
# ------------------------------------------------------------
def _safe_import(module: str):
    for mod_path in (f"backend.api.{module}", f"api.{module}"):
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "router"):
                log_event(f"🧩 Router loaded: {mod_path}")
                return mod
        except Exception:
            continue
    log_event(f"⚠️ Router load failed: {module}")
    return None


ROUTER_NAMES = [
    # core flows
    "optimize",
    "coverletter",
    "talk",
    "superhuman",
    "humanize",       # AIHumanize or related endpoints
    "mastermind",
    # system & UI data
    "dashboard",
    "models_router",  # models + pricing catalog
    "context_store",  # JD+Resume memory
    # misc
    "utils_router",
    "debug",
]
ROUTERS: Dict[str, object] = {name: _safe_import(name) for name in ROUTER_NAMES}

# ============================================================
# 🛰 Middleware — Request/Response Logger
# ============================================================
@app.middleware("http")
async def trace_requests(request: Request, call_next):
    start = time.time()
    path = request.url.path
    method = request.method
    log_event(f"➡️ {method} {path}")
    try:
        response = await call_next(request)
        ms = (time.time() - start) * 1000
        log_event(f"⬅️ {method} {path} → {response.status_code} ({ms:.1f} ms)")
        # Add simple cache headers for static assets
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=604800"  # 7 days
        return response
    except Exception as e:
        log_event(f"💥 Middleware error on {path}: {e}")
        return JSONResponse({"error": "internal_middleware_error", "detail": str(e)}, status_code=500)


# ============================================================
# 🔓 CORS (Frontend Access)
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 🧩 Static + Frontend Mount
# ============================================================
FRONTEND_DIR = os.path.normpath(os.path.join(ROOT_DIR, "frontend"))
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    log_event(f"📦 Static mounted → {STATIC_DIR}")
else:
    log_event(f"⚠️ Static folder missing: {STATIC_DIR}")

def _frontend_path(filename: str) -> Optional[str]:
    path = os.path.join(FRONTEND_DIR, filename)
    return path if os.path.exists(path) else None

@app.get("/", include_in_schema=False)
def serve_index():
    # Prefer master.html (single-file UI), fall back to index.html
    for fname in ("master.html", "index.html"):
        f = _frontend_path(fname)
        if f:
            return FileResponse(f)
    # Optional fallback to /mnt/data/master.html when developing
    alt = os.path.normpath("/mnt/data/master.html")
    if os.path.exists(alt):
        return FileResponse(alt)
    return JSONResponse({"error": "frontend_not_found"}, status_code=404)

@app.get("/{page_name}", include_in_schema=False)
def serve_page(page_name: str):
    # Allow /master -> master.html, also *.html direct hits
    if page_name == "master":
        f = _frontend_path("master.html")
        return FileResponse(f) if f else RedirectResponse("/")
    page = page_name if page_name.endswith(".html") else f"{page_name}.html"
    f = _frontend_path(page)
    return FileResponse(f) if f else RedirectResponse("/")


# ============================================================
# 🔗 Router Registration
# ============================================================
for name, mod in ROUTERS.items():
    if mod and hasattr(mod, "router"):
        app.include_router(mod.router)
    else:
        log_event(f"ℹ️ Skipping router: {name}")

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "version": APP_VERSION, "time": time.strftime("%H:%M:%S")}


# ============================================================
# 🪟 Windows GUI (PyWebview)
# ============================================================
def start_fastapi():
    import uvicorn
    host = os.getenv("HIREX_HOST", "127.0.0.1")
    port = int(os.getenv("HIREX_PORT", "8000"))
    # Disable uvicorn reload inside packaged app to avoid double-imports
    uvicorn.run(app, host=host, port=port, log_level="error", timeout_keep_alive=25, reload=False)

def _wait_for_backend(url: str, timeout_s: float = 15.0) -> bool:
    import urllib.request, json
    start = time.time()
    health_url = f"{url.rstrip('/')}/health"
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                ok = resp.status == 200
                if ok:
                    data = json.loads(resp.read() or b"{}")
                    if data.get("status") == "ok":
                        return True
        except Exception:
            time.sleep(0.35)
    return False

def start_window():
    # Allow disabling WebView via env (useful for servers/WSL)
    if os.getenv("HIREX_NO_GUI", "0") == "1":
        log_event("ℹ️ HIREX_NO_GUI set — running backend only (no webview).")
        return start_fastapi()

    try:
        import webview
    except Exception as e:
        log_event(f"⚠️ PyWebview unavailable ({e}) — starting backend only.")
        return start_fastapi()

    base_host = os.getenv("HIREX_HOST", "127.0.0.1")
    base_port = int(os.getenv("HIREX_PORT", "8000"))
    base_url = f"http://{base_host}:{base_port}"

    # Start backend first (in case user runs this entrypoint directly)
    if not _wait_for_backend(base_url, 2.0):
        threading.Thread(target=start_fastapi, daemon=True).start()

    # Give it a moment to come up
    _wait_for_backend(base_url, 20)

    class Bridge:
        def close_app(self):
            log_event("🛑 Close button pressed — shutting down HIREX.")
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except Exception:
                os._exit(0)

    window = webview.create_window(
        title=f"HIREX v{APP_VERSION} — Intelligent Career Suite",
        url=base_url,
        width=1280,
        height=820,
        resizable=True,
        background_color="#0a1020",
        js_api=Bridge(),
    )

    def inject_close_button():
        js = """
        (function(){
          if(window.__hirexClose)return;
          window.__hirexClose=true;
          const btn=document.createElement('button');
          btn.textContent='✖';
          Object.assign(btn.style,{
            position:'fixed',top:'12px',right:'16px',zIndex:'9999',
            padding:'6px 10px',border:'none',borderRadius:'6px',
            background:'#e74c3c',color:'#fff',fontSize:'15px',
            cursor:'pointer',transition:'transform .2s ease'
          });
          btn.onmouseenter=()=>btn.style.transform='scale(1.08)';
          btn.onmouseleave=()=>btn.style.transform='scale(1)';
          btn.onclick=()=>window.pywebview?.api?.close_app();
          document.body.appendChild(btn);
        })();
        """
        try:
            window.evaluate_js(js)
        except Exception as e:
            log_event(f"⚠️ JS injection failed: {e}")

    try:
        # Prefer Edge (Chromium) engine on Windows if available
        webview.start(func=inject_close_button, gui="edgechromium", debug=False)
    except Exception:
        webview.start(func=inject_close_button, debug=False)


# ============================================================
# 🚀 Entry Point
# ============================================================
if __name__ == "__main__":
    print(f"🚀 Launching HIREX v{APP_VERSION} — Windows App Mode")
    host = os.getenv("HIREX_HOST", "127.0.0.1")
    port = os.getenv("HIREX_PORT", "8000")
    print(f"🟢 Backend → http://{host}:{port}\n")

    def _graceful_exit(signum, _):
        print("\n🛑 Exiting HIREX…")
        os._exit(0)

    # Register signals if available (Windows supports SIGINT; SIGTERM may be present)
    for sig in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _graceful_exit)

    try:
        start_window()
    except Exception as e:
        log_event(f"⚠️ GUI fallback — {e}")
        print(f"Running backend only. Visit http://{host}:{port}")
        start_fastapi()
