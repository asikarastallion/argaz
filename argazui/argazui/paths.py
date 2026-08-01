"""Configuration and paths for ArgazUI.

Nothing in this module assumes that ``env.sh`` lives beside the application.
Paths are resolved once, in this order: command-line overrides, environment,
``argaz.toml``, then the directory containing this checkout as a convenience
auto-detection fallback.  ``doctor`` reports any fallback that does not point
to a usable installation before a simulation is started.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Optional


# The application itself is deliberately fixed relative to this source file.
ARGAZUI_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ARGAZUI_DIR / "config"
STATIC_DIR = ARGAZUI_DIR / "static"
RUN_DIR = ARGAZUI_DIR / "run"
MODELS_JSON = CONFIG_DIR / "models.json"
BUTTONS_JSON = CONFIG_DIR / "buttons.json"
PROCEDURES_DIR = ARGAZUI_DIR / "procedures"

DEFAULT_HTTP_PORT = 8770
DEFAULT_MAVLINK_PORT = 14550
DEFAULT_SCRIPT_MAVLINK_PORT = 14551

_CLI: dict[str, Any] = {}
_TOML_PATH: Optional[Path] = None


def _toml_file() -> Optional[Path]:
    """Find the project configuration without making the caller's CWD special."""
    explicit = os.environ.get("ARGAZ_CONFIG")
    if explicit:
        return Path(explicit).expanduser().resolve()
    for candidate in (ARGAZUI_DIR.parent / "argaz.toml", ARGAZUI_DIR / "argaz.toml"):
        if candidate.is_file():
            return candidate
    return None


def _load_toml() -> tuple[dict[str, Any], Optional[Path]]:
    path = _toml_file()
    if path is None:
        return {}, None
    try:
        with path.open("rb") as fh:
            doc = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"Cannot read ArgazUI configuration {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise RuntimeError(f"ArgazUI configuration {path} must be a TOML table")
    return doc, path


def _as_path(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _value(key: str, env: str, toml: dict[str, Any], default: Any) -> Any:
    """Return one setting according to the public precedence contract."""
    if key in _CLI and _CLI[key] is not None:
        return _CLI[key]
    if os.environ.get(env):
        return os.environ[env]
    if key in toml and toml[key] not in (None, ""):
        return toml[key]
    return default


def configure(**overrides: Any) -> None:
    """Apply CLI overrides and refresh exported compatibility constants.

    Existing modules use constants such as ``paths.ARDUPILOT``.  Keeping those
    names makes v1.0 callers work while their values now originate from the
    configuration layer.
    """
    global _CLI, _TOML_PATH
    _CLI = {key: value for key, value in overrides.items() if value is not None}
    toml, _TOML_PATH = _load_toml()
    base = _TOML_PATH.parent if _TOML_PATH else ARGAZUI_DIR.parent

    root_raw = _value("argaz_root", "ARGAZ_ROOT", toml, ARGAZUI_DIR.parent)
    root = _as_path(root_raw, base)

    def configured_path(key: str, env: str, fallback: Path) -> Path:
        return _as_path(_value(key, env, toml, fallback), base)

    globals().update({
        "ARGAZ": root,
        "ARDUPILOT": configured_path("ardupilot_root", "ARGAZ_ARDUPILOT_ROOT", root / "ardupilot"),
        "SITL_MODELS": configured_path("sitl_models_root", "ARGAZ_SITL_MODELS_ROOT", root / "SITL_Models"),
        "ARDU_WS": configured_path("ardu_ws_root", "ARGAZ_ARDU_WS_ROOT", root / "ardu_ws"),
        "ENV_SH": configured_path("env_script", "ARGAZ_ENV_SCRIPT", root / "env.sh"),
        "QUADPLANE_ENV_SH": configured_path("quadplane_env_script", "ARGAZ_QUADPLANE_ENV_SCRIPT", root / "quadplane_env.sh"),
        "UI_MAVLINK_PORT": int(_value("mavlink_port", "ARGAZ_MAVLINK_PORT", toml, DEFAULT_MAVLINK_PORT)),
        "SCRIPT_MAVLINK_PORT": int(_value("script_mavlink_port", "ARGAZ_SCRIPT_MAVLINK_PORT", toml, DEFAULT_SCRIPT_MAVLINK_PORT)),
        "HTTP_PORT": int(_value("port", "ARGAZ_PORT", toml, DEFAULT_HTTP_PORT)),
        "SCRIPTS_DIR": configured_path("scripts_root", "ARGAZ_SCRIPTS_ROOT", root / "scripts"),
    })
    globals().update({
        "SITL_MODELS_DOCS": SITL_MODELS / "Gazebo" / "docs",
        "SITL_MODELS_CONFIG": SITL_MODELS / "Gazebo" / "config",
        "SITL_MODELS_WORLDS": SITL_MODELS / "Gazebo" / "worlds",
        "SITL_MODELS_SCRIPTS": SITL_MODELS / "Gazebo" / "scripts",
    })


def source_summary() -> dict[str, str]:
    """Configuration metadata for ``doctor --json`` and support reports."""
    return {
        "config_file": str(_TOML_PATH) if _TOML_PATH else "(auto-detected)",
        "argaz_root": str(ARGAZ),
        "ardupilot_root": str(ARDUPILOT),
        "sitl_models_root": str(SITL_MODELS),
        "ardu_ws_root": str(ARDU_WS),
        "env_script": str(ENV_SH),
        "port": str(HTTP_PORT),
        "mavlink_port": str(UI_MAVLINK_PORT),
        "script_mavlink_port": str(SCRIPT_MAVLINK_PORT),
    }


# Initial import is environment/TOML/auto-detection. __main__ calls configure()
# again after parsing CLI switches, before importing the FastAPI app.
configure()
