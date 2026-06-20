"""ComfyUI HTTP routes for MCP template management (frontend API)."""

import json
import logging
import zipfile
from io import BytesIO
import httpx
from aiohttp import web
from server import PromptServer

from .comfyui_client import ComfyUIClient
from . import config, template_manager

logger = logging.getLogger(__name__)

API_PREFIX = "/mcp-server/api"


def _setting_getters() -> dict[str, callable]:
    return {
        "run_template_timeout": config.get_run_template_timeout,
    }


def _setting_setters() -> dict[str, callable]:
    return {
        "run_template_timeout": config.set_run_template_timeout,
    }


def _comfyui_client() -> ComfyUIClient:
    return ComfyUIClient(
        base_url=config.get_comfyui_api_url(),
        headers=config.get_comfyui_headers(),
    )


@PromptServer.instance.routes.get(f"{API_PREFIX}/status")
async def mcp_status(request):
    """Return MCP server status and endpoint URL."""
    getters = _setting_getters()
    return web.json_response({
        "mcp_url": "http://127.0.0.1:8188/app-mcp",
        **{key: getter() for key, getter in getters.items()},
    })


@PromptServer.instance.routes.get(f"{API_PREFIX}/settings/{{key}}")
async def get_runtime_setting(request):
    """Read a runtime setting value."""
    key = request.match_info["key"]
    getter = _setting_getters().get(key)
    if getter is None:
        return web.json_response({"error": f"Unknown setting: {key}"}, status=404)
    return web.json_response({"key": key, "value": getter()})


@PromptServer.instance.routes.post(f"{API_PREFIX}/settings/{{key}}")
async def set_runtime_setting(request):
    """Update a runtime setting from frontend settings."""
    key = request.match_info["key"]
    setter = _setting_setters().get(key)
    if setter is None:
        return web.json_response({"error": f"Unknown setting: {key}"}, status=404)

    try:
        data = await request.json()
    except Exception as e:
        return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)

    raw_value = data.get("value")
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return web.json_response({"error": "value must be a number"}, status=400)

    if value <= 0:
        return web.json_response({"error": "value must be greater than 0"}, status=400)

    updated = setter(value)
    return web.json_response({"key": key, "value": updated})


@PromptServer.instance.routes.get(f"{API_PREFIX}/workflows")
async def list_workflows(request):
    """List all ComfyUI workflows for template creation."""
    try:
        items = await _comfyui_client().list_user_data("workflows")
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
        return web.json_response(await _comfyui_client().get_workflow(name))
    except Exception as e:
        logger.error(f"[MCP] Failed to fetch workflow '{name}': {e}")
        return web.json_response({"error": str(e)}, status=404)


# ── Template management ───────────────────────────────────

@PromptServer.instance.routes.get(f"{API_PREFIX}/templates")
async def list_templates(request):
    """List all templates."""
    include_disabled = request.query.get("include_disabled") in {"1", "true", "yes"}
    return web.json_response({"templates": template_manager.list_templates(include_disabled=include_disabled)})


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
    if template_manager.is_template_disabled(template) and request.query.get("include_disabled") not in {"1", "true", "yes"}:
        return web.json_response({"error": "Template disabled"}, status=403)
    return web.json_response(template)


@PromptServer.instance.routes.post(f"{API_PREFIX}/templates")
async def create_template(request):
    """Create a template from a workflow."""
    data = await request.json()
    name = data.get("name")
    workflow = data.get("workflow")
    api_prompt = data.get("api_prompt")  # Pre-converted API format from frontend
    if not name or not workflow:
        return web.json_response({"error": "name and workflow required"}, status=400)
    if not isinstance(workflow, dict) or "nodes" not in workflow:
        return web.json_response({"error": "Invalid workflow content (missing nodes)"}, status=400)
    template = await template_manager.save_template(name, workflow, api_prompt=api_prompt)
    return web.json_response(template)


@PromptServer.instance.routes.post(f"{API_PREFIX}/templates/auto-create")
async def auto_create_templates(request):
    """Create templates for workflows that contain a title markdown node."""
    try:
        client = _comfyui_client()
        items = await client.list_user_data("workflows")
    except Exception as e:
        logger.error(f"[MCP] auto_create_templates: failed to list workflows: {e}")
        return web.json_response({"error": str(e)}, status=500)

    created = []
    skipped = []
    failed = []
    needs_api_prompt = []

    for item in items:
        path = item.get("path", "") if isinstance(item, dict) else str(item)
        if not path.endswith(".json"):
            continue
        name = path.removesuffix(".json")
        if template_manager.get_template(name):
            skipped.append({"name": name, "reason": "template exists"})
            continue
        try:
            workflow = await client.get_workflow(name)
            info = await template_manager.extract_template_info(workflow)
            if not info.get("title"):
                skipped.append({"name": name, "reason": "missing title markdown"})
                continue
            await template_manager.save_template(name, workflow)
            created.append({"name": name, "title": info.get("title", "")})
            needs_api_prompt.append(name)
        except Exception as e:
            logger.error(f"[MCP] auto_create_templates: failed for workflow '{name}': {e}")
            failed.append({"name": name, "error": str(e)})

    return web.json_response({
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "needs_api_prompt": needs_api_prompt,
    })


@PromptServer.instance.routes.put(f"{API_PREFIX}/templates/{{name}}")
async def update_template(request):
    """Update template metadata (outputs, description, inputs)."""
    name = request.match_info["name"]
    updates = await request.json()
    template = template_manager.update_template(name, updates)
    if not template:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(template)


@PromptServer.instance.routes.post(f"{API_PREFIX}/templates/batch-refresh")
async def batch_refresh_templates(request):
    """Refresh all existing templates from current workflows."""
    templates = template_manager.list_templates(include_disabled=True)
    refreshed = []
    skipped = []
    failed = []
    needs_api_prompt = []

    for template_info in templates:
        name = template_info.get("name", "")
        if not name:
            continue
        try:
            try:
                workflow = await _comfyui_client().get_workflow(name)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    skipped.append({"name": name, "reason": "workflow not found"})
                    continue
                raise
            info = await template_manager.extract_template_info(workflow)
            # Check if template needs api_prompt generation
            existing = template_manager.get_template(name)
            has_api_prompt = existing and existing.get("api_prompt")
            template = template_manager.update_template(name, {
                "workflow": workflow,
                "inputs": info.get("inputs", {}),
                "outputs": info.get("outputs", {}),
                "description": info.get("description", ""),
                "title": info.get("title", ""),
            })
            if not template:
                failed.append({"name": name, "error": "template not found"})
                continue
            refreshed.append({"name": name, "title": info.get("title", "")})
            if not has_api_prompt:
                needs_api_prompt.append(name)
        except Exception as e:
            logger.error(f"[MCP] batch_refresh_templates: failed for template '{name}': {e}")
            failed.append({"name": name, "error": str(e)})

    return web.json_response({
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "needs_api_prompt": needs_api_prompt,
    })


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
    if template_manager.is_template_disabled(template):
        return web.json_response({"error": "Template disabled"}, status=403)
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
        async with httpx.AsyncClient(trust_env=False) as client:
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
