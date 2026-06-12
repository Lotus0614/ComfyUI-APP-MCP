"""Runtime configuration for plugin and standalone modes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent
DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_TEMPLATE_DIR = BASE_DIR / "templates"
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = 8189

_config_path_override: Path | None = None
_loaded_config: dict[str, Any] | None = None
_loaded_config_dir: Path | None = None


def configure(config_path: str | os.PathLike[str] | None = None) -> None:
    """Set the JSON config file path and reload configuration."""
    global _config_path_override, _loaded_config, _loaded_config_dir
    _config_path_override = Path(config_path).expanduser() if config_path else None
    _loaded_config = None
    _loaded_config_dir = None


def _candidate_config_path() -> Path | None:
    if _config_path_override:
        return _config_path_override
    env_path = os.environ.get("MCP_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    cwd_config = Path.cwd() / "mcp.config.json"
    if cwd_config.exists():
        return cwd_config
    return None


def _load_config() -> dict[str, Any]:
    global _loaded_config, _loaded_config_dir
    if _loaded_config is not None:
        return _loaded_config

    path = _candidate_config_path()
    if path and path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _loaded_config = data if isinstance(data, dict) else {}
        _loaded_config_dir = path.resolve().parent
    else:
        _loaded_config = {}
        _loaded_config_dir = None
    return _loaded_config


def _section(name: str) -> dict[str, Any]:
    value = _load_config().get(name, {})
    return value if isinstance(value, dict) else {}


def _resolve_path(value: str | os.PathLike[str] | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    if _loaded_config_dir is not None:
        return (_loaded_config_dir / path).resolve()
    return (Path.cwd() / path).resolve()


def get_comfyui_api_url() -> str:
    """URL used by MCP to call ComfyUI HTTP APIs."""
    comfyui = _section("comfyui")
    url = os.environ.get("COMFYUI_URL") or comfyui.get("apiUrl") or comfyui.get("url")
    return str(url or DEFAULT_COMFYUI_URL).rstrip("/")


def get_comfyui_public_url() -> str:
    """URL returned to clients for media links."""
    comfyui = _section("comfyui")
    url = os.environ.get("COMFYUI_PUBLIC_URL") or comfyui.get("publicUrl")
    return str(url or get_comfyui_api_url()).rstrip("/")


def use_mcp_media_proxy() -> bool:
    """Whether media links returned by direct MCP access should point to MCP /view."""
    value = os.environ.get("MCP_MEDIA_PROXY")
    if value is None:
        value = _section("mcp").get("mediaProxy", True)
    if isinstance(value, bool):
        return value
    return str(value).lower() not in {"0", "false", "no", "off"}


def get_comfyui_headers() -> dict[str, str]:
    """Optional headers for ComfyUI API calls."""
    headers = _section("comfyui").get("headers", {})
    if not isinstance(headers, dict):
        return {}
    return {str(k): str(v) for k, v in headers.items()}


def get_template_dir() -> Path:
    templates = _section("templates")
    value = os.environ.get("MCP_TEMPLATE_DIR") or templates.get("dir")
    return _resolve_path(value, DEFAULT_TEMPLATE_DIR)


def get_mcp_host() -> str:
    mcp = _section("mcp")
    return str(os.environ.get("MCP_HOST") or mcp.get("host") or DEFAULT_MCP_HOST)


def get_mcp_port() -> int:
    mcp = _section("mcp")
    value = os.environ.get("MCP_PORT") or mcp.get("port") or DEFAULT_MCP_PORT
    return int(value)
