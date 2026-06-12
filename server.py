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
    if result.get("error"):
        return json.dumps(result, ensure_ascii=False)

    outputs = result.get("outputs", {})
    prompt_id = result.get("prompt_id", "")

    # Generate binding_hint for each output that has media or text
    binding_hint = {}
    for output_name, output_data in outputs.items():
        media = output_data.get("media", [])
        text = output_data.get("text", [])
        if media:
            media_item = media[0]
            binding_hint[output_name] = {
                "from": prompt_id,
                "output": output_name,
                "type": "image" if media_item.get("type") in ("image", "gif") else media_item.get("type", "image"),
                "index": 0,
            }
        elif text:
            binding_hint[output_name] = {
                "from": prompt_id,
                "output": output_name,
                "type": "text",
                "index": 0,
            }

    payload = {
        "status": result.get("status", "completed"),
        "prompt_id": prompt_id,
        "outputs": outputs,
    }

    if binding_hint:
        payload["binding_hint"] = binding_hint

    return json.dumps(payload, indent=2, ensure_ascii=False)


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
            "then run_template to execute. "
            "IMPORTANT: Each run_template result includes a `binding_hint` field. "
            "When chaining templates, copy the binding_hint value directly into the next call's bindings parameter. "
            "NEVER use upload_image for template outputs - use bindings instead."
        ),
        transport_security=_TRANSPORT_SECURITY,
    )

    # ── Template Tools ──────────────────────────────────────

    @mcp.tool()
    async def list_templates() -> str:
        """List all available templates. Templates are workflows with typed inputs/outputs."""
        logger.info("[MCP] list_templates()")
        try:
            templates = template_manager.list_templates()
            result = json.dumps({"templates": templates})
            logger.info(f"[MCP] list_templates → {len(templates)} templates")
            return result
        except Exception as e:
            logger.error(f"[MCP] list_templates error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def get_template(name: str) -> str:
        """Get template details: description, inputs (parameters you can set), and outputs.

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
            return json.dumps({
                "name": template["name"],
                "description": template.get("description", ""),
                "inputs": template.get("inputs", {}),
                "outputs": template.get("outputs", {}),
            })
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
    async def upload_image(source: str, overwrite: bool = True) -> str:
        """Upload an image to ComfyUI. Supports local file path, HTTP URL, or base64 data.

        IMPORTANT: Do NOT use this for images generated by templates!
        When chaining templates (e.g., generate → upscale), use bindings instead.
        The previous result's `binding_hint` field contains ready-to-use binding config.
        Only use this tool when the user provides a NEW image that was NOT generated by a template.

        Args:
            source: Image source. Can be:
                - Local file path (e.g. 'E:/photos/input.png')
                - HTTP/HTTPS URL (e.g. 'https://example.com/image.png')
                - Base64 data URL (e.g. 'data:image/png;base64,iVBOR...')
            overwrite: If true (default), overwrite existing file with same name.
        """
        logger.info(f"[MCP] upload_image(source={source[:80]}..., overwrite={overwrite})")
        try:
            filename, image_bytes = await _read_image(source)
            result = await _upload_to_comfyui(filename, image_bytes, overwrite)
            logger.info(f"[MCP] upload_image → {result}")
            return json.dumps(result)
        except Exception as e:
            logger.error(f"[MCP] upload_image error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def list_models(folder: str = "") -> str:
        """List ComfyUI model folders or models in a specific folder.

        Args:
            folder: Optional ComfyUI model folder name, e.g. "checkpoints", "loras",
                    "vae", "controlnet". If omitted, returns available model folders.
        """
        folder = folder.strip().strip("/")
        logger.info(f"[MCP] list_models(folder={folder!r})")
        try:
            if not folder:
                folders = await client.list_model_folders()
                logger.info(f"[MCP] list_models → {len(folders)} folders")
                return json.dumps({"folders": folders}, ensure_ascii=False)
            models = await client.list_models(folder)
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

    async def _upload_to_comfyui(filename: str, image_bytes: bytes, overwrite: bool) -> dict:
        """Upload image bytes to ComfyUI /upload/image endpoint."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{config.get_comfyui_api_url()}/upload/image",
                headers=config.get_comfyui_headers(),
                files={"image": (filename, image_bytes)},
                data={"overwrite": str(overwrite).lower()},
                timeout=30,
            )
            if resp.status_code != 200:
                try:
                    error_body = resp.json()
                except Exception:
                    error_body = resp.text
                return {"error": f"Upload failed ({resp.status_code})", "details": error_body}
            return resp.json()

    @mcp.tool()
    async def run_template(name: str, params: str, wait: bool = True, bindings: str = "{}") -> str:
        """Execute a template with the given parameters.

        Args:
            name: Template name.
            params: JSON string of parameter values, e.g. '{"输入文本": "hello"}'.
            wait: If true (default), wait for execution to complete and return results directly.
                  If false, return immediately with prompt_id for later polling via get_template_result.
            bindings: Optional JSON string of bindings that pull values from a previous result.

                HOW TO USE: The result of each run_template call includes a `binding_hint` field.
                When you need to process a template's output with another template,
                copy the value from `binding_hint` directly into the `bindings` parameter.

                Example workflow:
                1. run_template returns: {"binding_hint": {"输出图片": {"from": "abc-123", "output": "输出图片_122_output", "type": "image", "index": 0}}}
                2. Next call: bindings = '{"输入图片": {"from": "abc-123", "output": "输出图片_122_output", "type": "image", "index": 0}}'

                Supported binding types:
                - text: read text[index] from the source output
                - image: re-upload a source image output and pass the returned input filename
                - media_filename: pass the source media filename directly
                - media_url: pass the source media URL directly
        """
        logger.info(f"[MCP] run_template(name={name!r}, params={params}, wait={wait})")
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
            result = await template_manager.execute_template(name, parameters, wait=wait, bindings=binding_data)
            logger.info(f"[MCP] run_template → {result.get('status', 'unknown')}")
            return _format_template_result(result)
        except Exception as e:
            logger.error(f"[MCP] run_template error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def run_templates(pipeline: str, timeout_per_step: float = 300) -> str:
        """Run multiple templates sequentially with explicit output-to-input bindings.

        Args:
            pipeline: JSON string describing the template pipeline.
                In run_templates, bindings[from] refers to a previous pipeline step id,
                not a prompt_id. Example:
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
                        "image": {
                          "from": "generate",
                          "output": "SaveImage_12_output",
                          "type": "image",
                          "index": 0
                        }
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
    async def get_template_result(name: str, prompt_id: str, wait: bool = False, timeout: float = 300) -> str:
        """Fetch template execution result.

        Args:
            name: Template name.
            prompt_id: The prompt_id returned by run_template.
            wait: If true, poll until the execution completes or times out.
            timeout: Max seconds to wait when wait=true.
        """
        logger.info(f"[MCP] get_template_result(name={name!r}, prompt_id={prompt_id!r}, wait={wait})")
        try:
            template = template_manager.get_template(name)
            if not template:
                return json.dumps({"error": f"Template '{name}' not found"})
            if template_manager.is_template_disabled(template):
                return json.dumps({"error": f"Template '{name}' is disabled"})
            outputs = template.get("outputs", {})
            result = await template_manager.get_template_outputs(prompt_id, outputs, wait=wait, timeout=timeout)
            logger.info(f"[MCP] get_template_result → {result.get('status', 'unknown')}")
            return _format_template_result(result)
        except Exception as e:
            logger.error(f"[MCP] get_template_result error: {e}")
            return json.dumps({"error": str(e)})

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
            "1. Call `list_templates()` to see all available templates with their names and descriptions.\n"
            "2. Call `get_template('<name>')` to see the template's inputs (parameters you can set) and outputs.\n"
            "3. If you need extra docs, call `read_template_doc('<name>', '<title>')` for a specific documentation section.\n"
            "4. Call `run_template('<name>', '{\"param\": \"value\"}')` to execute with your parameters.\n"
            "   - Parameters are passed as a JSON string, e.g. '{\"提示词\": \"a beautiful sunset\"}'.\n"
            "   - By default, the call waits for completion and returns results directly.\n"
            "   - Set `wait=false` to return immediately with a `prompt_id` for later polling.\n"
            "   - The result includes `outputs` (generated media) and `binding_hint` (ready-to-use binding config).\n"
            "5. Call `run_templates('{\"steps\": [...]}')` to chain multiple templates in one call.\n\n"
            "### CRITICAL: Always Use Bindings for Image Chaining\n\n"
            "When processing an image generated by a previous template (e.g., upscale, encrypt, img2img, style transfer), "
            "you **MUST** use bindings to pass the image automatically. **NEVER** download and re-upload images manually.\n\n"
            "Each execution result includes a `binding_hint` field with ready-to-use binding configs:\n"
            "```json\n"
            "{\n"
            "  \"binding_hint\": {\n"
            "    \"输出图片_122_output\": {\n"
            "      \"from\": \"<prompt_id>\",\n"
            "      \"output\": \"输出图片_122_output\",\n"
            "      \"type\": \"image\",\n"
            "      \"index\": 0\n"
            "    }\n"
            "  }\n"
            "}\n"
            "```\n\n"
            "To chain templates, copy the binding from `binding_hint` into the next call:\n"
            "```json\n"
            "{\"输入图片\": {\"from\": \"...\", \"output\": \"...\", \"type\": \"image\", \"index\": 0}}\n"
            "```\n\n"
            "For `run_templates` pipeline, replace `from` value with the step `id` instead of `prompt_id`.\n\n"
            "**Only use `upload_image()` when the user provides a NEW image file/URL that was NOT generated by a template.**\n\n"
            "### Tips\n"
            "- If a template's inputs have changed, ask the user to click 'Refresh' in the settings panel to re-extract from the workflow.\n"
            "- Generation may take 10-120 seconds depending on the workflow and hardware.\n"
            "- Use `run_templates` for multi-step workflows (generate → upscale, generate → encrypt, etc.) to avoid timeout issues.\n"
            "- **Displaying images**: Each output includes a `markdown` field. Use it directly to show images to the user, e.g. `![输出图片](http://...)`."
        )

    return mcp


def main():
    """Entry point for standalone usage (stdio transport)."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
