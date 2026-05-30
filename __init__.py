"""ComfyUI MCP Server — plugin entry point.

Starts an MCP (Model Context Protocol) server alongside ComfyUI,
exposing workflow template management via Streamable HTTP transport.

Configure the MCP port via environment variable MCP_PORT (default: 8189).
Clients connect at: http://127.0.0.1:<MCP_PORT>/mcp
"""

import asyncio
import logging
import os

from comfy_api.latest import ComfyExtension, io

from .server import create_mcp_server
from . import routes  # noqa: F401 — register aiohttp routes on import

logger = logging.getLogger(__name__)

WEB_DIRECTORY = "./js"

MCP_PORT = int(os.environ.get("MCP_PORT", "8189"))
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")


async def _run_mcp_background():
    """Run the MCP server as a background uvicorn task."""
    import uvicorn

    mcp = create_mcp_server()
    app = mcp.streamable_http_app()

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
    asyncio.create_task(_run_mcp_background())
    logger.info(f"ComfyUI MCP Server plugin loaded (port {MCP_PORT})")
    return MCPExtension()
