"""MCP Server for ComfyUI — tools, resources, and prompts."""

from __future__ import annotations

import json
import logging
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

try:
    from .comfyui_client import ComfyUIClient
    from . import config, template_manager
except ImportError:
    from comfyui_client import ComfyUIClient
    import config
    import template_manager

logger = logging.getLogger(__name__)

_UPLOAD_IMAGE_TIP = (
    "优先直接在模板 params 中使用图片 ref，不必先调用 upload_image。"
    "新本地图片：{\"image\": \"@{C:/images/input.png}\"}；"
    "file URI：{\"image\": \"@{file:///C:/images/input.png}\"}；"
    "远程图片：{\"image\": \"@{https://example.com/input.png}\"}；"
    "Base64：{\"image\": \"@{data:image/png;base64,...}\"}；"
    "模板结果：run_template 用 @{result://<run-id>/<output>/0}，"
    "run_templates 用 @{step://<step-id>/<output>/0}。"
    "直接图片 ref 会自动缓存到 input/mcp_cache。"
)


def _format_upload_result(result: dict) -> dict:
    """Expose only the path accepted by template image inputs plus guidance."""
    image = str(result.get("name", "") or "")
    if not image:
        raise ValueError("ComfyUI upload response did not include an image path")
    return {"image": image, "tip": _UPLOAD_IMAGE_TIP}


def _filter_models(models: list[str], keywords: str) -> list[str]:
    """Filter model names using case-insensitive AND/OR substring matching."""
    expression = (keywords or "").strip().lower()
    if not expression:
        return models
    branches = []
    for branch in expression.split("|"):
        terms = [term for term in branch.replace("&", " ").split() if term]
        if terms:
            branches.append(terms)
    if not branches:
        return models
    return [model for model in models if any(all(term in model.lower() for term in terms) for terms in branches)]

# Disable DNS rebinding protection so LAN clients can connect.
# Security is handled by ComfyUI's own --listen flag instead.
_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
)


def _json(obj) -> str:
    """Serialize a tool result without ASCII-escaping CJK text."""
    return json.dumps(obj, ensure_ascii=False)


def _format_template_result(result: dict) -> str:
    """Format template execution result for MCP response."""
    return json.dumps(
        template_manager.build_public_execution_result(result),
        indent=2,
        ensure_ascii=False,
    )


def create_mcp_server(client: ComfyUIClient | None = None) -> FastMCP:
    """Create and configure the MCP server instance."""
    if client is None:
        client = ComfyUIClient(
            base_url=config.get_comfyui_api_url(),
            headers=config.get_comfyui_headers(),
        )

    mcp = FastMCP(
        name="ComfyUI MCP Server",
        instructions=(
            "ComfyUI template workflow: first call list_templates, then get_template, then run_template "
            "or run_templates. Use run_templates for independent batch jobs as well as dependent pipelines. "
            "Use the exact input names and types returned by get_template. "
            "If template_token_required=true, pass the fresh template_token to execution. "
            "Every execution output includes a ref for reuse. For text, refs may be embedded in a larger "
            "string. For image inputs, prefer a direct image ref: @{local-path}, @{file://...}, @{https://...}, "
            "or @{data:image/...;base64,...} for a new image; use @{result://...} for a previous run and "
            "@{step://...} for an earlier run_templates step. Direct image refs are uploaded automatically "
            "to input/mcp_cache. Do not call upload_image before a template unless a standalone upload result "
            "is explicitly required."
        ),
        stateless_http=True,
        transport_security=_TRANSPORT_SECURITY,
    )

    # ── Template Tools ──────────────────────────────────────

    @mcp.tool()
    async def list_templates() -> str:
        """Discover enabled ComfyUI templates.

        Call this first to choose a capability. The result is a lightweight list of
        template names and titles; call get_template before execution.
        """
        logger.info("[MCP] list_templates()")
        try:
            templates = template_manager.list_public_templates()
            result = json.dumps({"templates": templates}, ensure_ascii=False)
            logger.info(f"[MCP] list_templates → {len(templates)} templates")
            return result
        except Exception as e:
            logger.error(f"[MCP] list_templates error: {e}")
            return _json({"error": str(e)})

    @mcp.tool()
    async def get_template(name: str) -> str:
        """Return one template's inputs, outputs, docs and optional execution token.

        Args:
            name: Template name.
        """
        logger.info(f"[MCP] get_template(name={name!r})")
        try:
            template = template_manager.get_template(name)
            if not template:
                logger.warning(f"[MCP] get_template → not found: {name}")
                return _json({"error": f"Template '{name}' not found"})
            if template_manager.is_template_disabled(template):
                logger.warning(f"[MCP] get_template → disabled: {name}")
                return _json({"error": f"Template '{name}' is disabled"})
            schema = template_manager.build_public_template_schema(template)
            schema.update(template_manager.build_template_token_fields(template))
            return _json(schema)
        except Exception as e:
            logger.error(f"[MCP] get_template error: {e}")
            return _json({"error": str(e)})

    @mcp.tool()
    async def read_template_doc(name: str, title: str) -> str:
        """Read one optional documentation section named by get_template.

        Args:
            name: Template name.
            title: Documentation section title to read.
        """
        logger.info(f"[MCP] read_template_doc(name={name!r}, title={title!r})")
        try:
            result = template_manager.read_template_doc(name, title)
            if result.get("error"):
                logger.warning(f"[MCP] read_template_doc → {result['error']}")
            return _json(result)
        except Exception as e:
            logger.error(f"[MCP] read_template_doc error: {e}")
            return _json({"error": str(e)})

    @mcp.tool()
    async def update_template_doc(name: str, title: str, content: str, mode: str = "replace") -> str:
        """Update stored template documentation; requires the settings toggle.

        Args:
            name: Template name.
            title: Documentation section title (e.g. "description", "usage", "tips").
            content: Markdown content to write.
            mode: "replace" to overwrite entirely, "append" to add to the end.
        """
        logger.info(f"[MCP] update_template_doc(name={name!r}, title={title!r}, mode={mode!r})")
        if not config.get_update_doc_enabled():
            return _json({"error": "update_template_doc is disabled. Enable it in MCP Server settings."})
        try:
            result = await template_manager.update_template_doc(name, title, content, mode)
            if result.get("error"):
                logger.warning(f"[MCP] update_template_doc → {result['error']}")
            return _json(result)
        except Exception as e:
            logger.error(f"[MCP] update_template_doc error: {e}")
            return _json({"error": str(e)})

    @mcp.tool()
    async def upload_image(source: str) -> str:
        """Upload a new image and return the path accepted by template image inputs.

        Prefer direct image refs in template params instead of calling this tool:
        ``@{C:/images/input.png}``, ``@{file:///C:/images/input.png}``,
        ``@{https://example.com/input.png}``, or ``@{data:image/png;base64,...}``.
        Images generated by templates must use their returned ``result://`` or
        ``step://`` ref and must not be downloaded and uploaded again.

        The compact success response is ``{"image": "mcp_cache/<filename>", "tip": "..."}``.

        Args:
            source: New image source. Can be:
                - Local file path (e.g. 'E:/photos/input.png')
                - HTTP/HTTPS URL (e.g. 'https://example.com/image.png')
                - Base64 data URL (e.g. 'data:image/png;base64,iVBOR...')
        """
        logger.info(f"[MCP] upload_image(source={source[:80]}...)")
        try:
            result = await template_manager.upload_image_source(source, client=client)
            formatted = _format_upload_result(result)
            logger.info(f"[MCP] upload_image → {formatted}")
            return _json(formatted)
        except Exception as e:
            logger.error(f"[MCP] upload_image error: {e}")
            return _json({"error": str(e), "tip": _UPLOAD_IMAGE_TIP})

    @mcp.tool()
    async def list_models(folder: str = "", keywords: str = "") -> str:
        """List model folders or search models in one folder.

        Without folder, returns available folders. With folder, returns model
        paths. Search is case-insensitive: spaces and ``&`` mean AND, ``|`` means
        OR, and AND binds first; e.g. ``foo&bar|baz`` means ``(foo AND bar) OR baz``.

        Args:
            folder: Optional ComfyUI model folder name, e.g. "checkpoints", "loras",
                    "vae", "controlnet". If omitted, returns available model folders.
            keywords: Optional case-insensitive search expression.
        """
        folder = folder.strip().strip("/")
        logger.info(f"[MCP] list_models(folder={folder!r}, keywords={keywords!r})")
        try:
            if not folder:
                folders = await client.list_model_folders()
                logger.info(f"[MCP] list_models → {len(folders)} folders")
                return _json({"folders": folders})
            models = await client.list_models(folder)
            if keywords:
                models = _filter_models(models, keywords)
                logger.info(f"[MCP] list_models → {len(models)} models in {folder} (filtered by {keywords!r})")
            else:
                logger.info(f"[MCP] list_models → {len(models)} models in {folder}")
            return _json({"folder": folder, "models": models})
        except Exception as e:
            logger.error(f"[MCP] list_models error: {e}")
            return _json({"error": str(e), "folder": folder})

    @mcp.tool()
    async def run_template(
        name: str,
        params: str,
        wait: bool = True,
        template_token: str | None = None,
    ) -> str:
        """Execute one template with a JSON params string.

        Use get_template for the parameter schema. Parameter strings may include
        refs written as ``@{...}`` (for example ``@{result://...}``); set wait=false
        to poll later.

        Args:
            name: Template name.
            params: JSON object string containing template inputs.
            wait: If true (default), wait for execution to complete and return results directly.
                  If false, return immediately with run_id for later polling via get_template_result.
            template_token: Token from get_template when token protection is enabled.
        """
        effective_timeout = config.get_run_template_timeout()
        logger.info(
            f"[MCP] run_template(name={name!r}, params={params}, wait={wait}, timeout={effective_timeout})"
        )
        try:
            parameters = json.loads(params)
        except json.JSONDecodeError as e:
            logger.error(f"[MCP] run_template → invalid JSON: {e}")
            return _json({"error": f"Invalid params JSON: {e}"})
        try:
            result = await template_manager.execute_template(
                name,
                parameters,
                wait=wait,
                timeout=effective_timeout,
                template_token=template_token,
                enforce_template_token=True,
            )
            logger.info(f"[MCP] run_template → {result.get('status', 'unknown')}")
            return _format_template_result(result)
        except Exception as e:
            logger.error(f"[MCP] run_template error: {e}")
            return _json({"error": str(e)})

    @mcp.tool()
    async def run_templates(pipeline: str, timeout_per_step: float | None = None) -> str:
        """Run multiple template calls sequentially in one request.

        Use this for either independent batch jobs (repeat one template with
        different params) or dependent pipelines (later steps use earlier refs).
        Each step's params may contain the same refs accepted by run_template.

        Args:
            pipeline: JSON string with a non-empty ``steps`` array. Each step has
                ``id``, ``template`` and ``params``; add ``template_token`` when
                required. Omit refs for independent batch steps; use ``step://``
                refs when a step depends on an earlier step.
                Example: ``{"steps":[{"id":"cat","template":"txt2img",
                "params":{"prompt":"a cat"}},{"id":"dog","template":"txt2img",
                "params":{"prompt":"a dog"}}]}`` runs one template twice independently.
                A dependent step can use ``{"image":"@{step://cat/output/0}"}``.
            timeout_per_step: Max seconds to wait for each step.
                Defaults to the Run Template Timeout setting.
        """
        effective_timeout = (
            timeout_per_step
            if timeout_per_step and timeout_per_step > 0
            else config.get_run_template_timeout()
        )
        logger.info(f"[MCP] run_templates(timeout_per_step={effective_timeout})")
        try:
            pipeline_data = json.loads(pipeline)
        except json.JSONDecodeError as e:
            logger.error(f"[MCP] run_templates → invalid JSON: {e}")
            return _json({"error": f"Invalid pipeline JSON: {e}"})

        try:
            result = await template_manager.run_templates(pipeline_data, timeout_per_step=effective_timeout)
            logger.info(f"[MCP] run_templates → {result.get('status', 'unknown')}")
            return _json(result)
        except Exception as e:
            logger.error(f"[MCP] run_templates error: {e}")
            return _json({"error": str(e)})

    @mcp.tool()
    async def get_template_result(name: str, run_id: str, wait: bool = False, timeout: float | None = None) -> str:
        """Poll or continue waiting for one template run.

        Use the run_id returned by run_template(wait=false) or a timed-out execution.
        wait=false returns current status; wait=true waits up to timeout.

        Args:
            name: Template name.
            run_id: The run_id returned by run_template when wait=false.
            wait: Whether to continue polling until completion or timeout.
            timeout: Maximum wait seconds when wait=true.
        """
        effective_timeout = timeout if timeout is not None else config.get_run_template_timeout()
        logger.info(f"[MCP] get_template_result(name={name!r}, run_id={run_id!r}, wait={wait}, timeout={effective_timeout})")
        try:
            template = template_manager.get_template(name)
            if not template:
                return _json({"error": f"Template '{name}' not found"})
            if template_manager.is_template_disabled(template):
                return _json({"error": f"Template '{name}' is disabled"})
            outputs = template.get("outputs", {})
            result = await template_manager.get_template_outputs(
                run_id,
                outputs,
                wait=wait,
                timeout=effective_timeout,
                template_name=name,
            )
            logger.info(f"[MCP] get_template_result → {result.get('status', 'unknown')}")
            return _format_template_result(result)
        except Exception as e:
            logger.error(f"[MCP] get_template_result error: {e}")
            return _json({"error": str(e)})

    # ── Resources ───────────────────────────────────────────

    @mcp.resource("comfyui://system")
    async def system_resource() -> str:
        """ComfyUI system status (GPU, memory, version)."""
        info = await client.get_system_info()
        return json.dumps(info, indent=2)

    @mcp.resource("comfyui://queue")
    async def queue_resource() -> str:
        """Current ComfyUI queue status."""
        queue = await client.get_queue()
        return json.dumps(queue, indent=2)

    @mcp.resource("comfyui://models/{folder}")
    async def models_resource(folder: str) -> str:
        """List models of a given type."""
        models = await client.list_models(folder)
        return json.dumps({"folder": folder, "models": models}, indent=2)

    # ── Prompts ─────────────────────────────────────────────

    @mcp.prompt()
    def use_template() -> str:
        """Provide a concise, end-to-end guide for the template tools."""
        return (
            "## ComfyUI MCP workflow\n\n"
            "1. Discover: call `list_templates()`.\n"
            "2. Inspect: call `get_template(name)` and use its exact input names/types. "
            "If a token is returned, pass the same `template_token` to execution.\n"
            "3. Execute one task with `run_template(name, params)`, where `params` is a JSON string. "
            "Use `wait=false` only when you want to poll later with `get_template_result`.\n"
            "4. Execute an ordered pipeline with `run_templates`; use `step://` refs only for earlier steps.\n\n"
            "### Reference rules\n\n"
            "- Text refs (`result://` or `step://`) can be embedded in prose.\n"
            "- Image inputs should normally be the complete value of the image parameter.\n"
            "- New image: `@{C:/images/input.png}`, `@{file:///C:/images/input.png}`, "
            "`@{https://example.com/input.png}`, or `@{data:image/png;base64,...}`.\n"
            "- Previous standalone run: `@{result://<run-id>/<output>/0}`.\n"
            "- Earlier pipeline step: `@{step://<step-id>/<output>/0}`.\n"
            "- New image refs are uploaded automatically to `input/mcp_cache`; do not call upload_image first.\n"
            "- `upload_image` is only for compatibility or when a standalone upload response is explicitly needed.\n\n"
            "A successful output includes a ready-to-use `ref`. Pass that exact ref in the next template call; "
            "never download a generated image and upload it again."
        )

    return mcp


def main():
    """Entry point for standalone usage (stdio transport)."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
