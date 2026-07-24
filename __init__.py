"""ComfyUI MCP Server — plugin entry point.

Starts an MCP (Model Context Protocol) server alongside ComfyUI,
exposing workflow template management via Streamable HTTP transport.

The MCP endpoint is available at /app-mcp on ComfyUI's own port.
An internal MCP server runs on localhost and requests are proxied through.

Environment variables:
  MCP_PORT    — Internal MCP server port (default: 8189, proxied via /app-mcp)
  MCP_HOST    — Internal MCP server bind host (default: 127.0.0.1)
  COMFYUI_URL — Optional override for the auto-detected ComfyUI API URL
"""

import asyncio
import logging

from comfy_api.latest import ComfyExtension, io

from .server import create_mcp_server
from . import routes  # noqa: F401 — register aiohttp routes on import
from . import config
from .media_proxy import MediaProxyMiddleware, PublicURLMiddleware

logger = logging.getLogger(__name__)

WEB_DIRECTORY = "./js"

MCP_PORT = config.get_mcp_port()
MCP_HOST = config.get_mcp_host()


def _configure_comfyui_api_url() -> str:
    """Use ComfyUI's actual startup port for same-process API calls."""
    from comfy.cli_args import args as comfy_args

    use_tls = bool(
        getattr(comfy_args, "tls_keyfile", None)
        and getattr(comfy_args, "tls_certfile", None)
    )
    scheme = "https" if use_tls else "http"
    url = f"{scheme}://127.0.0.1:{comfy_args.port}"
    config.set_runtime_comfyui_api_url(url)
    return config.get_comfyui_api_url()


async def _run_mcp_background():
    """Run the MCP server as a background uvicorn task."""
    import uvicorn

    mcp = create_mcp_server()
    app = mcp.streamable_http_app()
    app = MediaProxyMiddleware(PublicURLMiddleware(app))

    config = uvicorn.Config(
        app=app,
        host=MCP_HOST,
        port=MCP_PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info(f"MCP Server starting at http://{MCP_HOST}:{MCP_PORT}/mcp")
    await server.serve()


class MCPExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return []


async def comfy_entrypoint() -> MCPExtension:
    """ComfyUI V3 entry point — starts the MCP background server."""
    comfyui_api_url = _configure_comfyui_api_url()
    asyncio.create_task(_run_mcp_background())
    logger.info(
        "ComfyUI MCP Server plugin loaded (MCP port %s, ComfyUI API %s)",
        MCP_PORT,
        comfyui_api_url,
    )
    return MCPExtension()
