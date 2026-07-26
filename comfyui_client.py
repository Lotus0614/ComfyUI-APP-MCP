"""ComfyUI API client — wraps HTTP endpoints used by the MCP server."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx

# Shared connection pools, one per running event loop. Reusing a pooled
# httpx.AsyncClient avoids re-establishing a TCP connection for every call
# (the result poller alone makes one request per second).
_pooled_clients: dict[int, httpx.AsyncClient] = {}
_POOL_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def _shared_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    key = id(loop)
    client = _pooled_clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=True,
            limits=_POOL_LIMITS,
        )
        _pooled_clients[key] = client
        # Drop references to clients whose loop is gone (e.g. test runs).
        for other_key in [k for k in _pooled_clients if k != key]:
            other = _pooled_clients[other_key]
            if other.is_closed:
                _pooled_clients.pop(other_key, None)
    return client


class ComfyUIClient:
    def __init__(self, base_url: str | None = None, headers: dict[str, str] | None = None):
        if base_url is None:
            try:
                from . import config
            except ImportError:
                import config
            base_url = config.get_comfyui_api_url()
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    async def _get(self, path: str, *, params: dict | None = None, timeout: float = 30):
        resp = await _shared_client().get(
            f"{self.base_url}{path}",
            params=params,
            headers=self.headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json: dict | None = None, *, timeout: float = 30) -> dict:
        resp = await _shared_client().post(
            f"{self.base_url}{path}",
            headers=self.headers,
            json=json,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Models ──────────────────────────────────────────────

    async def list_model_folders(self) -> list[str]:
        return await self._get("/models")

    async def list_models(self, folder: str) -> list[str]:
        return await self._get(f"/models/{quote(folder, safe='')}")

    # ── Nodes ───────────────────────────────────────────────

    async def list_nodes(self) -> dict:
        # /object_info can be very large and slow on installs with many
        # custom node packs — give it a generous timeout.
        return await self._get("/object_info", timeout=120)

    async def get_node_info(self, node_class: str) -> dict:
        return await self._get(f"/object_info/{quote(node_class, safe='')}")

    # ── Prompt / Queue ──────────────────────────────────────

    async def queue_prompt(self, prompt: dict, *, workflow: dict | None = None) -> dict:
        """Queue a prompt for execution.

        If ``workflow`` (the UI-graph JSON) is given, it is embedded as
        ``extra_data.extra_pnginfo`` so output images carry the workflow and the
        API prompt in their PNG metadata (standard SaveImage/PreviewImage, plus
        custom savers that go through ComfyUI's save path).
        """
        body: dict = {"prompt": prompt}
        if workflow is not None:
            body["extra_data"] = {"extra_pnginfo": {"workflow": workflow, "prompt": prompt}}
        return await self._post("/prompt", json=body)

    async def get_queue(self) -> dict:
        return await self._get("/queue")

    async def get_history(self, prompt_id: str | None = None) -> dict:
        if prompt_id:
            return await self._get(f"/history/{quote(prompt_id, safe='')}")
        return await self._get("/history")

    async def interrupt(self) -> None:
        resp = await _shared_client().post(
            f"{self.base_url}/interrupt", headers=self.headers, timeout=10
        )
        resp.raise_for_status()

    # ── User data / workflows ──────────────────────────────

    async def list_user_data(self, directory: str, recurse: bool = True, full_info: bool = True) -> list:
        return await self._get(
            "/api/userdata",
            params={
                "dir": directory,
                "recurse": str(recurse).lower(),
                "split": "false",
                "full_info": str(full_info).lower(),
            },
            timeout=15,
        )

    def _workflow_file_path(self, name: str) -> str:
        # The whole "workflows/<name>.json" file path must be a single
        # percent-encoded path segment for ComfyUI's userdata API. quote()
        # also handles names containing '/', '#', '?' or non-ASCII characters.
        return quote(f"workflows/{name}.json", safe="")

    async def get_workflow(self, name: str) -> dict:
        return await self._get(f"/api/userdata/{self._workflow_file_path(name)}", timeout=15)

    async def save_workflow(self, name: str, workflow: dict) -> None:
        """Write a workflow back to ComfyUI's userdata storage."""
        resp = await _shared_client().post(
            f"{self.base_url}/api/userdata/{self._workflow_file_path(name)}",
            headers=self.headers,
            json=workflow,
            timeout=15,
        )
        resp.raise_for_status()

    # ── Files ───────────────────────────────────────────────

    async def download_view(self, filename: str, subfolder: str = "", file_type: str = "output") -> bytes:
        resp = await _shared_client().get(
            f"{self.base_url}/view",
            params={"filename": filename, "subfolder": subfolder, "type": file_type},
            headers=self.headers,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.content

    async def upload_image_bytes(self, filename: str, image_bytes: bytes) -> dict:
        suffix = Path(filename).suffix.lower() or ".png"
        upload_name = f"mcp_{uuid4().hex}{suffix}"
        resp = await _shared_client().post(
            f"{self.base_url}/upload/image",
            headers=self.headers,
            files={"image": (upload_name, image_bytes)},
            data={"overwrite": "false"},
            timeout=120,
        )
        if resp.status_code != 200:
            try:
                details = resp.json()
            except Exception:
                details = resp.text
            raise RuntimeError(f"Upload failed ({resp.status_code}): {details}")
        return resp.json()

    # ── System ──────────────────────────────────────────────

    async def get_system_info(self) -> dict:
        return await self._get("/system_stats")
