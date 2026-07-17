"""MCP Server for ComfyUI — tools, resources, and prompts."""

import base64
import json
import logging
from pathlib import Path

import httpx
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

# Disable DNS rebinding protection so LAN clients can connect.
# Security is handled by ComfyUI's own --listen flag instead.
_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
)


def _format_template_result(result: dict) -> str:
    """Format template execution result for MCP response."""
    return json.dumps(
        template_manager.build_public_execution_result(result),
        indent=2,
        ensure_ascii=False,
    )


def _queue_prompt_ids(queue: dict, key: str) -> set[str]:
    """Extract prompt IDs from a ComfyUI queue response."""
    prompt_ids = set()
    for item in queue.get(key, []):
        prompt_id = None
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            prompt_id = item[1]
        elif isinstance(item, dict):
            prompt_id = item.get("prompt_id") or item.get("id")
        if prompt_id is not None:
            prompt_ids.add(str(prompt_id))
    return prompt_ids


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
            "Execute ComfyUI templates for image generation, processing, and more. "
            "Use list_templates to discover templates, get_template for parameters, "
            "then run_template for one task or run_templates for multiple tasks in one call. "
            "run_templates steps may be independent or connected through bindings. "
            "Use interrupt_task with a run_id to stop a running or queued task. "
            "Template outputs include `ref` values. "
            "When chaining templates, pass the ref string into the next call's bindings parameter. "
            "NEVER use upload_image for template outputs - use bindings instead."
        ),
        stateless_http=True,
        transport_security=_TRANSPORT_SECURITY,
    )

    # ── Template Tools ──────────────────────────────────────

    @mcp.tool()
    async def list_templates() -> str:
        """List all available templates. Templates are workflows with typed inputs/outputs."""
        logger.info("[MCP] list_templates()")
        try:
            templates = template_manager.list_public_templates()
            result = json.dumps({"templates": templates}, ensure_ascii=False)
            logger.info(f"[MCP] list_templates → {len(templates)} templates")
            return result
        except Exception as e:
            logger.error(f"[MCP] list_templates error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def get_template(name: str) -> str:
        """Get template details: description, inputs, outputs, and readable docs.

        Args:
            name: Template name.
        """
        logger.info(f"[MCP] get_template(name={name!r})")
        try:
            template = template_manager.get_template(name)
            if not template:
                logger.warning(f"[MCP] get_template → not found: {name}")
                return json.dumps({"error": f"Template '{name}' not found"})
            if template_manager.is_template_disabled(template):
                logger.warning(f"[MCP] get_template → disabled: {name}")
                return json.dumps({"error": f"Template '{name}' is disabled"})
            return json.dumps(template_manager.build_public_template_schema(template), ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MCP] get_template error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def read_template_doc(name: str, title: str) -> str:
        """Read a named documentation section from a template.

        Use this for progressive disclosure: keep get_template concise, then fetch
        extra sections such as "usage", "examples", "tips", or "negative_prompt"
        only when needed.

        Args:
            name: Template name.
            title: Documentation section title to read.
        """
        logger.info(f"[MCP] read_template_doc(name={name!r}, title={title!r})")
        try:
            result = template_manager.read_template_doc(name, title)
            if result.get("error"):
                logger.warning(f"[MCP] read_template_doc → {result['error']}")
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MCP] read_template_doc error: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def update_template_doc(name: str, title: str, content: str, mode: str = "replace") -> str:
        """Update a documentation section in a template.

        Updates the MarkdownNote node in the original workflow and syncs the
        top-level template fields (title/description) when applicable.

        Args:
            name: Template name.
            title: Documentation section title (e.g. "description", "usage", "tips").
            content: Markdown content to write.
            mode: "replace" to overwrite entirely, "append" to add to the end.
        """
        logger.info(f"[MCP] update_template_doc(name={name!r}, title={title!r}, mode={mode!r})")
        if not config.get_update_doc_enabled():
            return json.dumps({"error": "update_template_doc is disabled. Enable it in MCP Server settings."})
        try:
            result = await template_manager.update_template_doc(name, title, content, mode)
            if result.get("error"):
                logger.warning(f"[MCP] update_template_doc → {result['error']}")
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MCP] update_template_doc error: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def upload_image(source: str) -> str:
        """Upload an image to ComfyUI. Supports local file path, HTTP URL, or base64 data.

        IMPORTANT: Do NOT use this for images generated by templates!
        When chaining templates (e.g., generate → upscale), use bindings instead.
        The previous result's output contains a ready-to-use `ref` string.
        Only use this tool when the user provides a NEW image that was NOT generated by a template.

        Args:
            source: Image source. Can be:
                - Local file path (e.g. 'E:/photos/input.png')
                - HTTP/HTTPS URL (e.g. 'https://example.com/image.png')
                - Base64 data URL (e.g. 'data:image/png;base64,iVBOR...')
        """
        logger.info(f"[MCP] upload_image(source={source[:80]}...)")
        try:
            filename, image_bytes = await _read_image(source)
            result = await _upload_to_comfyui(filename, image_bytes)
            logger.info(f"[MCP] upload_image → {result}")
            return json.dumps(result)
        except Exception as e:
            logger.error(f"[MCP] upload_image error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def list_models(folder: str = "", keywords: str = "") -> str:
        """List ComfyUI model folders or models in a specific folder.

        Args:
            folder: Optional ComfyUI model folder name, e.g. "checkpoints", "loras",
                    "vae", "controlnet". If omitted, returns available model folders.
            keywords: Optional search keywords to filter models (case-insensitive).
                      Multiple keywords separated by spaces are treated as AND conditions.
        """
        folder = folder.strip().strip("/")
        logger.info(f"[MCP] list_models(folder={folder!r}, keywords={keywords!r})")
        try:
            if not folder:
                folders = await client.list_model_folders()
                logger.info(f"[MCP] list_models → {len(folders)} folders")
                return json.dumps({"folders": folders}, ensure_ascii=False)
            models = await client.list_models(folder)
            if keywords:
                terms = keywords.lower().split()
                models = [m for m in models if all(t in m.lower() for t in terms)]
                logger.info(f"[MCP] list_models → {len(models)} models in {folder} (filtered by {keywords!r})")
            else:
                logger.info(f"[MCP] list_models → {len(models)} models in {folder}")
            return json.dumps({"folder": folder, "models": models}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MCP] list_models error: {e}")
            return json.dumps({"error": str(e), "folder": folder}, ensure_ascii=False)

    async def _read_image(source: str) -> tuple[str, bytes]:
        """Read image from various sources, return (filename, bytes)."""
        if source.startswith("data:"):
            # Base64 data URL: data:image/png;base64,xxxxx
            header, data = source.split(",", 1)
            ext = "png"
            if "jpeg" in header or "jpg" in header:
                ext = "jpg"
            elif "webp" in header:
                ext = "webp"
            elif "gif" in header:
                ext = "gif"
            filename = f"upload.{ext}"
            return filename, base64.b64decode(data)

        if source.startswith("http://") or source.startswith("https://"):
            # HTTP URL — download
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(source, timeout=30)
                resp.raise_for_status()
            # Extract filename from URL
            from urllib.parse import urlparse
            path = urlparse(source).path
            filename = Path(path).name or "image.png"
            if "." not in filename:
                filename += ".png"
            return filename, resp.content

        # Local file path
        filepath = Path(source)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {source}")
        return filepath.name, filepath.read_bytes()

    async def _upload_to_comfyui(filename: str, image_bytes: bytes) -> dict:
        """Upload image bytes to ComfyUI /upload/image endpoint."""
        return await client.upload_image_bytes(filename, image_bytes)

    @mcp.tool()
    async def run_template(
        name: str,
        params: str,
        wait: bool = True,
        bindings: str = "{}",
    ) -> str:
        """Execute a template with the given parameters.

        Args:
            name: Template name.
            params: JSON string of parameter values, e.g. '{"输入文本": "hello"}'.
            wait: If true (default), wait for execution to complete and return results directly.
                  If false, return immediately with run_id for later polling via get_template_result.
            bindings: Optional JSON object string mapping input names to `result://` refs.
                Example: '{"输入图片": "result://abc-123/输出图片/0"}'
        """
        effective_timeout = config.get_run_template_timeout()
        logger.info(
            f"[MCP] run_template(name={name!r}, params={params}, wait={wait}, timeout={effective_timeout})"
        )
        try:
            parameters = json.loads(params)
        except json.JSONDecodeError as e:
            logger.error(f"[MCP] run_template → invalid JSON: {e}")
            return json.dumps({"error": f"Invalid params JSON: {e}"})
        try:
            binding_data = json.loads(bindings)
        except json.JSONDecodeError as e:
            logger.error(f"[MCP] run_template → invalid bindings JSON: {e}")
            return json.dumps({"error": f"Invalid bindings JSON: {e}"})
        try:
            result = await template_manager.execute_template(
                name,
                parameters,
                wait=wait,
                timeout=effective_timeout,
                bindings=binding_data,
            )
            logger.info(f"[MCP] run_template → {result.get('status', 'unknown')}")
            return _format_template_result(result)
        except Exception as e:
            logger.error(f"[MCP] run_template error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def run_templates(pipeline: str, timeout_per_step: float = 300) -> str:
        """Run multiple tasks sequentially in one call, with optional bindings.

        Returns every step with the same full execution result shape as run_template,
        plus the step id and template name. Steps may be independent, or later steps
        may consume earlier outputs through bindings.

        Args:
            pipeline: JSON string describing the ordered tasks.
                Bindings map input names to `step://<step-id>/<output>/<index>` refs. Example:
                {
                  "steps": [
                    {
                      "id": "generate",
                      "template": "txt2img",
                      "params": {"prompt": "a cat"}
                    },
                    {
                      "id": "upscale",
                      "template": "upscale",
                      "params": {"scale": 2},
                      "bindings": {
                        "image": "step://generate/图片/0"
                      }
                    }
                  ]
                }
            timeout_per_step: Max seconds to wait for each step.
        """
        logger.info(f"[MCP] run_templates(timeout_per_step={timeout_per_step})")
        try:
            pipeline_data = json.loads(pipeline)
        except json.JSONDecodeError as e:
            logger.error(f"[MCP] run_templates → invalid JSON: {e}")
            return json.dumps({"error": f"Invalid pipeline JSON: {e}"}, ensure_ascii=False)

        try:
            result = await template_manager.run_templates(pipeline_data, timeout_per_step=timeout_per_step)
            logger.info(f"[MCP] run_templates → {result.get('status', 'unknown')}")
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MCP] run_templates error: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def get_template_result(name: str, run_id: str, wait: bool = False, timeout: float | None = None) -> str:
        """Fetch template execution result.

        Args:
            name: Template name.
            run_id: The run_id returned by run_template when wait=false.
            wait: If true, poll until the execution completes or times out.
            timeout: Max seconds to wait when wait=true. Defaults to the Run Template Timeout setting.
        """
        effective_timeout = timeout if timeout is not None else config.get_run_template_timeout()
        logger.info(f"[MCP] get_template_result(name={name!r}, run_id={run_id!r}, wait={wait}, timeout={effective_timeout})")
        try:
            template = template_manager.get_template(name)
            if not template:
                return json.dumps({"error": f"Template '{name}' not found"})
            if template_manager.is_template_disabled(template):
                return json.dumps({"error": f"Template '{name}' is disabled"})
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
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def interrupt_task(run_id: str) -> str:
        """Interrupt a running task or remove a queued task.

        Use the run_id returned by run_template(wait=false) or by a timed-out run.
        A running task is interrupted through ComfyUI's interrupt endpoint. A task
        that has not started is removed from the pending queue instead.

        Args:
            run_id: The run_id of the task to interrupt.
        """
        run_id = run_id.strip()
        logger.info(f"[MCP] interrupt_task(run_id={run_id!r})")
        if not run_id:
            return json.dumps({"error": "run_id must not be empty"})

        try:
            queue = await client.get_queue()
            running_ids = _queue_prompt_ids(queue, "queue_running")
            pending_ids = _queue_prompt_ids(queue, "queue_pending")

            # Newer ComfyUI versions provide an atomic ID-based cancellation
            # endpoint. Prefer it to avoid the race inherent in the legacy
            # get-queue-then-interrupt sequence.
            cancelled = await client.cancel_job(run_id)
            if cancelled is not None:
                if cancelled:
                    status = "interrupted" if run_id in running_ids else "cancelled"
                    logger.info(f"[MCP] interrupt_task → {status} task {run_id}")
                    return json.dumps({"status": status, "run_id": run_id})

                history = await client.get_history(run_id)
                if run_id in history:
                    logger.info(f"[MCP] interrupt_task → task already finished {run_id}")
                    return json.dumps({"status": "already_finished", "run_id": run_id})

                logger.warning(f"[MCP] interrupt_task → task not found: {run_id}")
                return json.dumps({"error": f"Task '{run_id}' not found", "run_id": run_id})

            # Compatibility path for ComfyUI versions without /api/jobs.
            if run_id in running_ids:
                await client.interrupt()
                logger.info(f"[MCP] interrupt_task → interrupted running task {run_id}")
                return json.dumps({"status": "interrupted", "run_id": run_id})

            if run_id in pending_ids:
                await client.delete_queue_items([run_id])
                logger.info(f"[MCP] interrupt_task → cancelled queued task {run_id}")
                return json.dumps({"status": "cancelled", "run_id": run_id})

            history = await client.get_history(run_id)
            if run_id in history:
                logger.info(f"[MCP] interrupt_task → task already finished {run_id}")
                return json.dumps({"status": "already_finished", "run_id": run_id})

            logger.warning(f"[MCP] interrupt_task → task not found: {run_id}")
            return json.dumps({"error": f"Task '{run_id}' not found", "run_id": run_id})
        except Exception as e:
            logger.error(f"[MCP] interrupt_task error: {e}")
            return json.dumps({"error": str(e), "run_id": run_id})

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
        """Guide the AI to use a ComfyUI template."""
        return (
            "## ComfyUI Templates\n\n"
            "A **template** is a reusable ComfyUI workflow with typed inputs and auto-detected outputs. "
            "Templates are created from ComfyUI workflows in the UI settings panel (Settings > MCP Server > Templates). "
            "Each template wraps a workflow and exposes its configurable parameters as named inputs.\n\n"
            "### How to Use\n"
            "1. Call `list_templates()` to see all available templates with their names and titles.\n"
            "2. Call `get_template('<name>')` to see the template's inputs, outputs, and readable doc titles.\n"
            "3. If you need extra docs, call `read_template_doc('<name>', '<title>')` for a specific documentation section.\n"
            "4. Call `run_template('<name>', '{\"param\": \"value\"}')` to execute with your parameters.\n"
            "   - Parameters are passed as a JSON string, e.g. '{\"提示词\": \"a beautiful sunset\"}'.\n"
            "   - By default, the call waits for completion and returns results directly.\n"
            "   - Set `wait=false` to return immediately with a `run_id` for later polling.\n"
            "   - Call `interrupt_task('<run-id>')` to stop a running or queued task.\n"
            "   - Each output includes a ready-to-use `ref` for chaining.\n"
            "5. Call `run_templates('{\"steps\": [...]}')` to run multiple tasks in one call. "
            "Steps can be independent, or connected through bindings when one depends on another.\n\n"
            "### CRITICAL: Always Use Bindings for Image Chaining\n\n"
            "When processing an image generated by a previous template (e.g., upscale, encrypt, img2img, style transfer), "
            "you **MUST** use bindings to pass the image automatically. **NEVER** download and re-upload images manually.\n\n"
            "Each execution output includes a ready-to-use `ref`:\n"
            "```json\n"
            "{\n"
            "  \"outputs\": {\n"
            "    \"输出图片\": {\n"
            "      \"type\": \"image\",\n"
            "      \"url\": \"...\",\n"
            "      \"ref\": \"result://<run-id>/输出图片/0\"\n"
            "    }\n"
            "  }\n"
            "}\n"
            "```\n\n"
            "To chain templates, copy the output `ref` into the next call:\n"
            "```json\n"
            "{\"输入图片\": \"result://<run-id>/输出图片/0\"}\n"
            "```\n\n"
            "Inside `run_templates`, use `step://<step-id>/<output>/0` refs.\n\n"
            "**Only use `upload_image()` when the user provides a NEW image file/URL that was NOT generated by a template.**\n\n"
            "### Tips\n"
            "- If a template's inputs have changed, ask the user to click 'Refresh' in the settings panel to re-extract from the workflow.\n"
            "- Generation may take 10-120 seconds depending on the workflow and hardware.\n"
            "- Use `run_templates` for batch tasks or multi-step workflows (multiple generations, generate → upscale, etc.).\n"
            "- **Displaying images**: Use the output's `url` directly."
        )

    return mcp


def main():
    """Entry point for standalone usage (stdio transport)."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
