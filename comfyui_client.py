"""ComfyUI API client — wraps HTTP endpoints used by the MCP server."""

from pathlib import Path
from uuid import uuid4

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8188"


class ComfyUIClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    async def _get(self, path: str, *, params: dict | None = None, timeout: float = 10) -> dict:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self.headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict | None = None, *, timeout: float = 30) -> dict:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
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
        return await self._get(f"/models/{folder}")

    # ── Nodes ───────────────────────────────────────────────

    async def list_nodes(self) -> dict:
        return await self._get("/object_info")

    async def get_node_info(self, node_class: str) -> dict:
        return await self._get(f"/object_info/{node_class}")

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
            return await self._get(f"/history/{prompt_id}")
        return await self._get("/history")

    async def interrupt(self) -> None:
        async with httpx.AsyncClient(trust_env=False) as client:
            await client.post(f"{self.base_url}/interrupt", headers=self.headers, timeout=10)

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
            timeout=10,
        )

    async def get_workflow(self, name: str) -> dict:
        return await self._get(f"/api/userdata/workflows%2F{name}.json", timeout=10)

    async def save_workflow(self, name: str, workflow: dict) -> None:
        """Write a workflow back to ComfyUI's userdata storage."""
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{self.base_url}/api/userdata/workflows%2F{name}.json",
                headers=self.headers,
                json=workflow,
                timeout=10,
            )
            resp.raise_for_status()

    # ── Files ───────────────────────────────────────────────

    async def download_view(self, filename: str, subfolder: str = "", file_type: str = "output") -> bytes:
        async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
            resp = await client.get(
                f"{self.base_url}/view",
                params={"filename": filename, "subfolder": subfolder, "type": file_type},
                headers=self.headers,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.content

    async def upload_image_bytes(self, filename: str, image_bytes: bytes) -> dict:
        suffix = Path(filename).suffix.lower() or ".png"
        upload_name = f"mcp_{uuid4().hex}{suffix}"
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{self.base_url}/upload/image",
                headers=self.headers,
                files={"image": (upload_name, image_bytes)},
                data={"overwrite": "false"},
                timeout=60,
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
