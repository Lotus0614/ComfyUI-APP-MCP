"""Standalone Streamable HTTP entry point for the ComfyUI MCP server."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the package directory is in sys.path for standalone execution
_pkg_dir = str(Path(__file__).resolve().parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

try:
    from . import config
    from .media_proxy import MediaProxyMiddleware, PublicURLMiddleware
    from .server import create_mcp_server
except ImportError:
    import config
    from media_proxy import MediaProxyMiddleware, PublicURLMiddleware
    from server import create_mcp_server


def _build_app():
    mcp = create_mcp_server()
    return MediaProxyMiddleware(PublicURLMiddleware(mcp.streamable_http_app()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ComfyUI MCP server standalone.")
    parser.add_argument("--config", help="Path to mcp.config.json")
    args = parser.parse_args()

    if args.config:
        config.configure(args.config)

    logging.basicConfig(level=logging.INFO)

    import uvicorn

    host = config.get_mcp_host()
    port = config.get_mcp_port()
    logging.getLogger(__name__).info("MCP Server starting at http://%s:%s/mcp", host, port)
    uvicorn.run(_build_app(), host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
