"""ComfyUI API client — wraps localhost HTTP endpoints."""

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8188"


class ComfyUIClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}{path}", headers=self.headers, timeout=10)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}{path}", headers=self.headers, json=json, timeout=30)
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

    # ── System ──────────────────────────────────────────────

    async def get_system_info(self) -> dict:
        return await self._get("/system_stats")
