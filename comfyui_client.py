"""ComfyUI API client — wraps HTTP endpoints used by the MCP server."""

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8188"


class ComfyUIClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    async def _get(self, path: str, *, params: dict | None = None, timeout: float = 10) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self.headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict | None = None, *, timeout: float = 30) -> dict:
        async with httpx.AsyncClient() as client:
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

    async def queue_prompt(self, workflow: dict) -> dict:
        return await self._post("/prompt", json={"prompt": workflow})

    async def get_queue(self) -> dict:
        return await self._get("/queue")

    async def get_history(self, prompt_id: str | None = None) -> dict:
        if prompt_id:
            return await self._get(f"/history/{prompt_id}")
        return await self._get("/history")

    async def interrupt(self) -> None:
        async with httpx.AsyncClient() as client:
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

    # ── Files ───────────────────────────────────────────────

    async def download_view(self, filename: str, subfolder: str = "", file_type: str = "output") -> bytes:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                f"{self.base_url}/view",
                params={"filename": filename, "subfolder": subfolder, "type": file_type},
                headers=self.headers,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.content

    async def upload_image_bytes(self, filename: str, image_bytes: bytes, overwrite: bool = True) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/upload/image",
                headers=self.headers,
                files={"image": (filename, image_bytes)},
                data={"overwrite": str(overwrite).lower()},
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
