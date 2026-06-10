"""MCP Server for ComfyUI — tools, resources, and prompts."""

import base64
import json
import os
import logging
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from mcp.server.transport_security import TransportSecuritySettings

from .comfyui_client import ComfyUIClient
from . import template_manager

logger = logging.getLogger(__name__)

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")

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

    # Collect media and text outputs
    all_media = []  # [{"url": ..., "type": ..., "filename": ...}]
    text_outputs = {}
    for node_name, node_data in outputs.items():
        # New format: media list
        media = node_data.get("media", [])
        if media:
            all_media.extend(media)
        # Legacy format: view_urls (image-only)
        for url in node_data.get("view_urls", []):
            all_media.append({"url": url, "type": "image", "filename": ""})
        texts = node_data.get("text", [])
        if texts:
            text_outputs[node_name] = texts[0] if len(texts) == 1 else texts

    # Build response
    lines = []
    if text_outputs:
        lines.append("**Text outputs:**")
        for name, text in text_outputs.items():
            lines.append(f"- **{name}**: {text}")

    if all_media:
        lines.append("")
        for item in all_media:
            mtype = item.get("type", "image")
            url = item["url"]
            fname = item.get("filename", "")
            if mtype == "image" or mtype == "gif":
                lines.append(f"![{mtype}]({url})")
            elif mtype == "audio":
                lines.append(f"🔊 **Audio**: [{fname}]({url})")
            else:
                lines.append(f"📎 **{mtype}**: [{fname}]({url})")

    if lines:
        return "\n".join(lines)

    # Fallback: return raw JSON
    return json.dumps(result, indent=2, ensure_ascii=False)


def create_mcp_server(client: ComfyUIClient | None = None) -> FastMCP:
    """Create and configure the MCP server instance."""
    if client is None:
        client = ComfyUIClient(base_url=COMFYUI_URL)

    mcp = FastMCP(
        name="ComfyUI MCP Server",
        instructions=(
            "This server lets you execute ComfyUI templates. "
            "Templates are pre-built workflows with typed inputs/outputs. "
            "Use list_templates to see available templates, get_template to see parameters, "
            "then call run_template with the required parameters."
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
    async def upload_image(source: str, overwrite: bool = True) -> str:
        """Upload an image to ComfyUI. Supports local file path, HTTP URL, or base64 data.

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
                f"{COMFYUI_URL}/upload/image",
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
    async def run_template(name: str, params: str, wait: bool = True) -> str:
        """Execute a template with the given parameters.

        Args:
            name: Template name.
            params: JSON string of parameter values, e.g. '{"输入文本": "hello"}'.
            wait: If true (default), wait for execution to complete and return results directly.
                  If false, return immediately with prompt_id for later polling via get_template_result.
        """
        logger.info(f"[MCP] run_template(name={name!r}, params={params}, wait={wait})")
        try:
            parameters = json.loads(params)
        except json.JSONDecodeError as e:
            logger.error(f"[MCP] run_template → invalid JSON: {e}")
            return json.dumps({"error": f"Invalid params JSON: {e}"})
        try:
            result = await template_manager.execute_template(name, parameters, wait=wait)
            logger.info(f"[MCP] run_template → {result.get('status', 'unknown')}")
            return _format_template_result(result)
        except Exception as e:
            logger.error(f"[MCP] run_template error: {e}")
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def get_template_result(name: str, prompt_id: str) -> str:
        """Poll for template execution result. Call repeatedly until status is 'completed'.

        Args:
            name: Template name.
            prompt_id: The prompt_id returned by run_template.
        """
        logger.info(f"[MCP] get_template_result(name={name!r}, prompt_id={prompt_id!r})")
        try:
            template = template_manager.get_template(name)
            if not template:
                return json.dumps({"error": f"Template '{name}' not found"})
            if template_manager.is_template_disabled(template):
                return json.dumps({"error": f"Template '{name}' is disabled"})
            outputs = template.get("outputs", {})
            result = await template_manager.get_template_outputs(prompt_id, outputs)
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
            "### Relationship to Workflows\n"
            "- A ComfyUI **workflow** is a node graph (e.g., txt2img, img2img, ControlNet) saved in the ComfyUI editor.\n"
            "- A **template** is a workflow packaged with auto-detected inputs (labeled widget fields) and outputs (terminal nodes).\n"
            "- Templates are stored as JSON files in the `mcp-server/templates/` directory.\n\n"
            "### How to Use\n"
            "1. Call `list_templates()` to see all available templates with their names and descriptions.\n"
            "2. Call `get_template('<name>')` to see the template's inputs (parameters you can set) and outputs.\n"
            "   - Inputs have names (e.g., '提示词', '模型名称'), types, and which node/widget they control.\n"
            "   - Outputs are auto-detected from terminal nodes (nodes whose outputs are not connected to other nodes).\n"
            "3. Call `run_template('<name>', '{\"param\": \"value\"}')` to execute with your parameters.\n"
            "   - Parameters are passed as a JSON string, e.g. '{\"提示词\": \"a beautiful sunset\"}'.\n"
            "   - By default, the call waits for completion and returns results directly.\n"
            "   - Set `wait=false` to return immediately with a `prompt_id` for later polling.\n"
            "4. Results include:\n"
            "   - **Text outputs** from nodes like ShowText.\n"
            "   - **Image URLs** in markdown format `![image](url)` — click to view in browser.\n"
            "   - Image view URLs follow the format: `http://<comfyui>/view?filename=<name>&subfolder=<path>&type=output`.\n\n"
            "### Tips\n"
            "- If a template's inputs have changed, ask the user to click 'Refresh' in the settings panel to re-extract from the workflow.\n"
            "- For image inputs, call `upload_image(source)` first with a local path or HTTP URL, "
            "then pass the returned filename to the template's image parameter.\n"
            "- Generation may take 10-120 seconds depending on the workflow and hardware."
        )

    return mcp


def main():
    """Entry point for standalone usage (stdio transport)."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
