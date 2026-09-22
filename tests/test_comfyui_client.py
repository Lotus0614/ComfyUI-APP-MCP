import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from comfyui_client import ComfyUIClient, MCP_UPLOAD_SUBFOLDER


class UploadImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_uses_mcp_cache_and_returns_combined_path(self) -> None:
        response = SimpleNamespace(status_code=200, json=lambda: {
            "name": "mcp_abc.png",
            "subfolder": "mcp_cache",
            "type": "input",
        })
        http_client = SimpleNamespace(post=AsyncMock(return_value=response))
        with patch("comfyui_client._shared_client", return_value=http_client):
            result = await ComfyUIClient("http://comfy").upload_image_bytes("input.png", b"data")

        self.assertEqual(result["name"], "mcp_cache/mcp_abc.png")
        self.assertEqual(result["subfolder"], MCP_UPLOAD_SUBFOLDER)
        call = http_client.post.await_args
        self.assertEqual(call.kwargs["data"]["subfolder"], MCP_UPLOAD_SUBFOLDER)

