# ============================================================
#  HIREX v2.x — models_router.py
#  Exposes model catalogs + pricing for the frontend picker.
#  Reads from backend.core.config (AVAILABLE_MODELS, MODEL_PRICING, etc.)
# ============================================================

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from backend.core import config

router = APIRouter(prefix="/api/models", tags=["models"])


def _providers() -> List[str]:
    return list(getattr(config, "AVAILABLE_MODELS", {}).keys())


def _available() -> Dict[str, Any]:
    return getattr(config, "AVAILABLE_MODELS", {})


def _pricing() -> Dict[str, Any]:
    return getattr(config, "MODEL_PRICING", {})


def _aliases() -> Dict[str, str]:
    # Optional; present in some HIREX configs
    return getattr(config, "MODEL_ALIASES", {})


@router.get("")
async def list_models():
    """
    Aggregate endpoint consumed by master.js to render model pickers.
    """
    return {
        "default_model": getattr(config, "DEFAULT_MODEL", ""),
        "providers": _providers(),
        "available": _available(),
        "pricing": _pricing(),
        "aliases": _aliases(),            # safe even if empty
        "version": getattr(config, "APP_VERSION", "0.0.0"),
    }


@router.get("/openai")
async def list_openai():
    """
    Return only OpenAI models and their pricing.
    """
    available = _available().get("openai", [])
    pricing = _pricing().get("openai", {})
    return {
        "provider": "openai",
        "models": available,
        "pricing": pricing,
        "default": getattr(config, "DEFAULT_MODEL", ""),
        "aliases": _aliases(),
        "version": getattr(config, "APP_VERSION", "0.0.0"),
    }


@router.get("/aihumanize")
async def list_aihumanize():
    """
    Return AIHumanize modes (they are modes/styles, not tokenized models)
    and the display pricing/plans info if present.
    """
    available = _available().get("aihumanize", [])
    pricing = _pricing().get("aihumanize", {})
    return {
        "provider": "aihumanize",
        "modes": available,
        "pricing": pricing,  # typically {"modes": [...], "plans": {...}, "unit": "subscription"}
        "version": getattr(config, "APP_VERSION", "0.0.0"),
    }


@router.get("/provider/{name}")
async def list_by_provider(name: str):
    """
    Generic provider fetch. Helpful if you add more providers later.
    """
    name = name.lower().strip()
    available = _available()
    pricing = _pricing()

    if name not in available:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    return {
        "provider": name,
        "available": available.get(name, []),
        "pricing": pricing.get(name, {}),
        "version": getattr(config, "APP_VERSION", "0.0.0"),
    }


@router.get("/pricing")
async def pricing_only():
    """
    Raw pricing object for UI tables.
    """
    return {
        "pricing": _pricing(),
        "version": getattr(config, "APP_VERSION", "0.0.0"),
    }


@router.get("/aliases")
async def aliases_only():
    """
    Optional alias map (human label -> model id).
    """
    return {
        "aliases": _aliases(),
        "version": getattr(config, "APP_VERSION", "0.0.0"),
    }
