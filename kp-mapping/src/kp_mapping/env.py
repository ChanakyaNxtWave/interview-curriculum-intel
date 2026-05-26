from __future__ import annotations

import os
from pathlib import Path

_KP_MAPPING_ROOT = Path(__file__).resolve().parents[2]
_LOADED = False


def load_env() -> Path | None:
    """Load kp-mapping/.env into os.environ (does not override existing vars)."""
    global _LOADED
    if _LOADED:
        return _env_path_if_exists()

    try:
        from dotenv import load_dotenv
    except ImportError:
        _LOADED = True
        return None

    env_path = _KP_MAPPING_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    _LOADED = True
    return env_path if env_path.is_file() else None


def _env_path_if_exists() -> Path | None:
    p = _KP_MAPPING_ROOT / ".env"
    return p if p.is_file() else None


def require_openrouter_key() -> str:
    load_env()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        env_hint = _env_path_if_exists()
        hint = (
            f" Set OPENROUTER_API_KEY in {env_hint}"
            if env_hint
            else " Create kp-mapping/.env from .env.example"
        )
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set." + hint
            + " Or export it in your shell before running."
        )
    return key
