"""ComfyUI HTTP routes for MCP template management (frontend API)."""

import json
import logging
import zipfile
from io import BytesIO
import httpx
from aiohttp import web
from server import PromptServer

from . import config, template_manager

logger = logging.getLogger(__name__)

API_PREFIX = "/mcp-server/api"


@PromptServer.instance.routes.get(f"{API_PREFIX}/status")
async def mcp_status(request):
    """Return MCP server status and endpoint URL."""
    return web.json_response({
        "mcp_url": "http://127.0.0.1:8188/app-mcp",
    })


@PromptServer.instance.routes.get(f"{API_PREFIX}/workflows")
async def list_workflows(request):
    """List all ComfyUI workflows for template creation."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{config.get_comfyui_api_url()}/api/userdata",
                params={"dir": "workflows", "recurse": "true", "split": "false", "full_info": "true"},
                headers=config.get_comfyui_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json()
            workflows = []
            for item in items:
                if isinstance(item, dict):
                    path = item.get("path", "")
                else:
                    path = str(item)
                workflows.append({"name": path.removesuffix(".json"), "path": path})
            return web.json_response({"workflows": workflows})
    except Exception as e:
        logger.error(f"Failed to fetch workflows from ComfyUI: {e}")
        return web.json_response({"workflows": [], "error": str(e)})


@PromptServer.instance.routes.get(f"{API_PREFIX}/workflows/{{name}}")
async def get_workflow_content(request):
    """Get a specific workflow's content from ComfyUI."""
    name = request.match_info["name"]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{config.get_comfyui_api_url()}/api/userdata/workflows%2F{name}.json",
                headers=config.get_comfyui_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return web.json_response(resp.json())
    except Exception as e:
        logger.error(f"[MCP] Failed to fetch workflow '{name}': {e}")
        return web.json_response({"error": str(e)}, status=404)


# ── Template management ───────────────────────────────────

@PromptServer.instance.routes.get(f"{API_PREFIX}/templates")
async def list_templates(request):
    """List all templates."""
    return web.json_response({"templates": template_manager.list_templates()})


@PromptServer.instance.routes.get(f"{API_PREFIX}/templates/export")
async def export_templates(request):
    """Export current template JSON files as a standalone templates zip."""
    template_dir = config.get_template_dir()
    buffer = BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(template_dir.glob("*.json")):
            zf.write(path, arcname=f"templates/{path.name}")
            count += 1

    if count == 0:
        return web.json_response({"error": "No templates to export"}, status=404)

    return web.Response(
        body=buffer.getvalue(),
        content_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="mcp-templates.zip"'},
    )


@PromptServer.instance.routes.get(f"{API_PREFIX}/templates/{{name}}")
async def get_template(request):
    """Get template details (including workflow)."""
    name = request.match_info["name"]
    template = template_manager.get_template(name)
    if not template:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(template)


@PromptServer.instance.routes.post(f"{API_PREFIX}/templates")
async def create_template(request):
    """Create a template from a workflow."""
    data = await request.json()
    name = data.get("name")
    workflow = data.get("workflow")
    if not name or not workflow:
        return web.json_response({"error": "name and workflow required"}, status=400)
    if not isinstance(workflow, dict) or "nodes" not in workflow:
        return web.json_response({"error": "Invalid workflow content (missing nodes)"}, status=400)
    template = await template_manager.save_template(name, workflow)
    return web.json_response(template)


@PromptServer.instance.routes.put(f"{API_PREFIX}/templates/{{name}}")
async def update_template(request):
    """Update template metadata (outputs, description, inputs)."""
    name = request.match_info["name"]
    updates = await request.json()
    template = template_manager.update_template(name, updates)
    if not template:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(template)


@PromptServer.instance.routes.delete(f"{API_PREFIX}/templates/{{name}}")
async def delete_template(request):
    """Delete a template."""
    name = request.match_info["name"]
    deleted = template_manager.delete_template(name)
    if not deleted:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response({"deleted": name})


@PromptServer.instance.routes.post(f"{API_PREFIX}/templates/{{name}}/execute")
async def execute_template(request):
    """Execute a template with parameters."""
    name = request.match_info["name"]
    data = await request.json()
    params = data.get("params", {})
    try:
        result = await template_manager.execute_template(name, params)
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Template execution failed: {e}")
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.get(f"{API_PREFIX}/templates/{{name}}/result/{{prompt_id}}")
async def template_result(request):
    """Get template execution result."""
    name = request.match_info["name"]
    prompt_id = request.match_info["prompt_id"]
    template = template_manager.get_template(name)
    if not template:
        return web.json_response({"error": "Template not found"}, status=404)
    outputs = template.get("outputs", {})
    try:
        result = await template_manager.get_template_outputs(prompt_id, outputs)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post(f"{API_PREFIX}/templates/extract")
async def extract_template(request):
    """Extract template info from a workflow (auto-detect inputs/README)."""
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"[MCP] extract_template: invalid JSON body: {e}")
        return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)
    workflow = data.get("workflow")
    if not workflow:
        return web.json_response({"error": "workflow required"}, status=400)
    if isinstance(workflow, str):
        try:
            workflow = json.loads(workflow)
        except Exception as e:
            logger.error(f"[MCP] extract_template: workflow is not valid JSON: {e}")
            return web.json_response({"error": f"Invalid workflow JSON: {e}"}, status=400)
    try:
        info = await template_manager.extract_template_info(workflow)
        return web.json_response(info)
    except Exception as e:
        logger.error(f"[MCP] extract_template error: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ── MCP proxy ────────────────────────────────────────────
# Forward /app-mcp requests to the local MCP server so remote
# clients can reach it through ComfyUI's port without opening
# a second port.

MCP_PATH = "/app-mcp"

_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})


def _forward_headers(request: web.Request) -> dict[str, str]:
    """Build upstream headers, injecting comfyui_url from the inbound Host."""
    headers: dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() not in _HOP_BY_HOP:
            headers[k] = v
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    headers["comfyui_url"] = f"{scheme}://{host}"
    return headers


async def _proxy_handler(request: web.Request) -> web.StreamResponse:
    target = f"http://127.0.0.1:{config.get_mcp_port()}/mcp"
    if request.query_string:
        target += f"?{request.query_string}"

    body = await request.read()
    logger.info(f"[MCP Proxy] {request.method} {request.path} -> {target}")
    try:
        async with httpx.AsyncClient() as client:
            upstream = await client.request(
                method=request.method,
                url=target,
                headers=_forward_headers(request),
                content=body or None,
                timeout=300,
            )
    except Exception as e:
        logger.error(f"[MCP Proxy] upstream error: {e}")
        return web.json_response({"error": f"MCP upstream error: {e}"}, status=502)

    # Build response — stream for SSE, buffered otherwise
    ct = upstream.headers.get("content-type", "")
    if "text/event-stream" in ct:
        resp = web.StreamResponse(
            status=upstream.status_code,
            headers={
                k: v for k, v in upstream.headers.items()
                if k.lower() not in _HOP_BY_HOP
            },
        )
        await resp.prepare(request)
        async for chunk in upstream.aiter_bytes():
            await resp.write(chunk)
        await resp.write_eof()
        return resp

    resp = web.Response(
        status=upstream.status_code,
        body=upstream.content,
    )
    for k, v in upstream.headers.items():
        if k.lower() not in _HOP_BY_HOP:
            resp.headers[k] = v
    return resp


@PromptServer.instance.routes.get(MCP_PATH)
async def _mcp_proxy_get(request):
    return await _proxy_handler(request)

@PromptServer.instance.routes.post(MCP_PATH)
async def _mcp_proxy_post(request):
    return await _proxy_handler(request)

@PromptServer.instance.routes.delete(MCP_PATH)
async def _mcp_proxy_delete(request):
    return await _proxy_handler(request)
