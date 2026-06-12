"""Template manager — wraps ComfyUI workflows as reusable templates with typed inputs/outputs."""

import asyncio
import copy
import json
import logging
import random
import contextvars

import httpx

logger = logging.getLogger(__name__)

try:
    from . import config
except ImportError:
    import config

# Set by middleware from MCP request query param or comfyui_url header.
# Used for media links returned to remote MCP clients.
_comfyui_public_url: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_comfyui_public_url", default=None
)

# Module-level cache for mcp_outputs, keyed by prompt_id.
# Allows cross-call binding resolution without requiring source_outputs.
_mcp_outputs_cache: dict[str, dict] = {}

# UI-only node types that should not be submitted for execution
_UI_ONLY_TYPES = {
    "MarkdownNote", "Note", "Reroute", "PrimitiveNode",
}

# Cache for object_info node definitions
_node_defs_cache: dict | None = None


async def _get_node_definitions() -> dict:
    """Fetch and cache node definitions from ComfyUI /object_info."""
    global _node_defs_cache
    if _node_defs_cache is not None:
        return _node_defs_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{config.get_comfyui_api_url()}/object_info",
            headers=config.get_comfyui_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        _node_defs_cache = resp.json()
    return _node_defs_cache


def _ensure_dir():
    config.get_template_dir().mkdir(parents=True, exist_ok=True)


# ── Auto-extract from workflow ────────────────────────────

def _extract_markdown_note(workflow: dict, note_title: str) -> str | None:
    """Extract content from a MarkdownNote node with the given title."""
    for node in workflow.get("nodes", []):
        if node.get("type") == "MarkdownNote" and node.get("title") == note_title:
            values = node.get("widgets_values", [])
            if values:
                return str(values[0])
    return None


def _extract_readme(workflow: dict) -> str:
    """Extract description from MarkdownNote node with title 'README' (legacy)."""
    return _extract_markdown_note(workflow, "README") or ""


def _extract_title_and_description(workflow: dict) -> tuple[str, str]:
    """Extract title and description from MarkdownNote nodes.

    Looks for dedicated 'title' and 'description' nodes first.
    Falls back to README node for backward compatibility.
    """
    title = _extract_markdown_note(workflow, "title")
    description = _extract_markdown_note(workflow, "description")
    readme = _extract_markdown_note(workflow, "README")

    # Backward compat: README fills in missing title/description
    if title is None:
        title = readme or ""
    if description is None:
        description = readme or ""

    return title, description


def _extract_inputs(workflow: dict, node_defs: dict | None = None) -> dict:
    """Extract inputs from linearData.inputs."""
    nodes = workflow.get("nodes", [])
    node_map = {n["id"]: n for n in nodes}

    linear_inputs = []  # list of (node_id, widget_name)
    extra = workflow.get("extra", {})
    if isinstance(extra, dict):
        linear = extra.get("linearData", {})
        if isinstance(linear, dict):
            li = linear.get("inputs")
            if isinstance(li, list):
                for item in li:
                    # item = [node_id, widget_name]
                    node_id = int(item[0]) if isinstance(item, list) else int(item)
                    widget = item[1] if isinstance(item, list) and len(item) > 1 else None
                    linear_inputs.append((node_id, widget))

    inputs = {}
    for node_id, target_widget in linear_inputs:
        node = node_map.get(node_id)
        if not node:
            continue
        widgets_values = node.get("widgets_values", [])

        for inp in node.get("inputs", []):
            widget_info = inp.get("widget")
            if not widget_info:
                continue
            widget_name = widget_info.get("name", inp.get("name", ""))
            # Only register the widget specified in linearData
            if target_widget and widget_name != target_widget:
                continue
            label = inp.get("label") or widget_name

            entry = {
                "node_id": node_id,
                "widget": widget_name,
                "type": inp.get("type", "STRING"),
            }

            if widgets_values and node_defs:
                default = _read_widget_default(node, widget_name, node_defs)
                if default is not None:
                    entry["default"] = default

            inputs[label] = entry
    return inputs


def _read_widget_default(node: dict, widget_name: str, node_defs: dict):
    """Read the current widget value from a node's widgets_values by widget name.

    Uses the same index computation as _ui_workflow_to_api_prompt to account
    for hidden control_after_generate widgets.
    """
    class_type = node.get("type", "")
    widgets_values = node.get("widgets_values", [])
    if not widgets_values:
        return None

    node_def = node_defs.get(class_type, {})
    input_def = node_def.get("input", {})
    required = input_def.get("required", {})
    optional = input_def.get("optional", {})

    # Build ordered widget names (same logic as _get_node_widget_names)
    widget_names = []
    for input_name in list(required.keys()) + list(optional.keys()):
        spec = required.get(input_name) or optional.get(input_name)
        if spec and _is_widget_input(spec):
            widget_names.append(input_name)

    # Build all_widgets with hidden controls and dynamic sub-inputs
    # (same logic as _ui_workflow_to_api_prompt)
    all_widgets = []  # [(name, is_hidden)]
    vi = 0
    for wname in widget_names:
        all_widgets.append((wname, False))
        vi += 1
        spec = required.get(wname) or optional.get(wname)
        is_dynamic_combo = spec and isinstance(spec, list) and isinstance(spec[0], str) and spec[0].startswith("COMFY_DYNAMICCOMBO")
        is_int_float = spec and isinstance(spec, list) and spec[0] in ("INT", "FLOAT")
        # After a dynamic combo widget, add its active sub-inputs
        if is_dynamic_combo and vi > 0:
            selected_key = widgets_values[vi - 1] if vi - 1 < len(widgets_values) else None
            combo_options = spec[1].get("options", []) if len(spec) > 1 and isinstance(spec[1], dict) else []
            for opt in combo_options:
                if isinstance(opt, dict) and opt.get("key") == selected_key:
                    req = opt.get("inputs", {}).get("required", {})
                    for sub_name in req:
                        all_widgets.append((f"{wname}.{sub_name}", False))
                        vi += 1
                    break
        elif is_int_float and vi < len(widgets_values):
            next_val = widgets_values[vi]
            if next_val in ("randomize", "increment", "decrement", "fixed"):
                all_widgets.append(("_hidden_" + wname, True))
                vi += 1

    # Find the target widget and return its value
    vi = 0
    for wname, is_hidden in all_widgets:
        if vi >= len(widgets_values):
            break
        if is_hidden:
            vi += 1
            continue
        if wname == widget_name:
            return widgets_values[vi]
        vi += 1

    return None


def _detect_output_nodes(workflow: dict) -> dict:
    """Detect output nodes from linearData.outputs (explicit user selection),
    falling back to auto-detection of terminal nodes."""
    nodes = workflow.get("nodes", [])

    # Build node_id → node mapping
    node_map = {}
    for node in nodes:
        nid = node.get("id")
        if nid is not None:
            node_map[str(nid)] = node

    # Try linearData.outputs first (explicit user selection in editor)
    linear_outputs = None
    extra = workflow.get("extra", {})
    if isinstance(extra, dict):
        linear = extra.get("linearData", {})
        if isinstance(linear, dict):
            lo = linear.get("outputs")
            if isinstance(lo, list) and lo:
                linear_outputs = [str(x) for x in lo]

    outputs = {}
    if linear_outputs:
        for nid in linear_outputs:
            node = node_map.get(nid)
            if not node:
                continue
            class_type = node.get("type", "")
            title = node.get("title") or class_type
            if class_type in _UI_ONLY_TYPES:
                continue
            node_outputs = node.get("outputs", [])
            if node_outputs:
                for out in node_outputs:
                    out_type = out.get("type", "")
                    name = f"{title}_{nid}_{out.get('name', 'out')}"
                    outputs[name] = {
                        "node_id": int(nid),
                        "type": _output_type_from_comfy(out_type),
                        "comfy_type": out_type,
                        "title": title,
                    }
            else:
                # Terminal node with no outputs (SaveImage, SaveAudio, etc.)
                name = f"{title}_{nid}_output"
                outputs[name] = {
                    "node_id": int(nid),
                    "type": "unknown",
                    "comfy_type": "unknown",
                    "title": title,
                }
        return outputs

    # Fallback: auto-detect terminal nodes
    links = workflow.get("links", [])
    used_outputs = set()
    for link in links:
        if len(link) >= 3:
            used_outputs.add((link[1], link[2]))

    for node in nodes:
        node_id = node.get("id")
        class_type = node.get("type", "")
        title = node.get("title") or class_type
        if class_type in _UI_ONLY_TYPES:
            continue
        for out_idx, out in enumerate(node.get("outputs", [])):
            if (node_id, out_idx) not in used_outputs:
                out_type = out.get("type", "")
                name = f"{title}_{node_id}_{out.get('name', out_idx)}"
                outputs[name] = {
                    "node_id": node_id,
                    "type": _output_type_from_comfy(out_type),
                    "comfy_type": out_type,
                    "title": title,
                }
    return outputs


def _output_type_from_comfy(comfy_type: str) -> str:
    """Map ComfyUI output type to template output type."""
    if comfy_type in ("IMAGE", "LATENT"):
        return "image"
    if comfy_type == "AUDIO":
        return "audio"
    if comfy_type in ("STRING", "TEXT"):
        return "text"
    return "text"



async def extract_template_info(workflow: dict) -> dict:
    """Auto-extract template metadata from a workflow."""
    node_defs = await _get_node_definitions()
    title, description = _extract_title_and_description(workflow)
    return {
        "title": title,
        "description": description,
        "inputs": _extract_inputs(workflow, node_defs),
        "outputs": _detect_output_nodes(workflow),
    }


# ── Template CRUD ─────────────────────────────────────────

def is_template_disabled(template: dict) -> bool:
    return bool(template.get("disabled", False))


def list_templates(include_disabled: bool = False) -> list[dict]:
    _ensure_dir()
    templates = []
    for f in sorted(config.get_template_dir().glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            disabled = is_template_disabled(data)
            if disabled and not include_disabled:
                continue
            # title for list display; fall back to description for old templates
            title = data.get("title") or data.get("description", "")
            templates.append({
                "name": data.get("name", f.stem),
                "title": title,
                "description": data.get("description", ""),
                "disabled": disabled,
                "input_count": len(data.get("inputs", {})),
                "output_count": len(data.get("outputs", {})),
            })
        except Exception as e:
            logger.warning(f"Failed to load template {f}: {e}")
    return templates


def get_template(name: str) -> dict | None:
    path = config.get_template_dir() / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_template_doc(name: str, title: str) -> dict:
    template = get_template(name)
    if not template:
        return {"error": f"Template '{name}' not found"}
    if is_template_disabled(template):
        return {"error": f"Template '{name}' is disabled"}

    workflow = template.get("workflow", {})
    content = _extract_markdown_note(workflow, title)
    if content is None:
        return {"error": f"Document '{title}' not found in template '{name}'"}

    return {
        "template": name,
        "title": title,
        "content": content,
    }

async def _fetch_history_entry(prompt_id: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
        resp.raise_for_status()
        history = resp.json()
    return history.get(prompt_id)


async def _upload_media_to_input(media_item: dict) -> dict:
    """Download a generated media file from ComfyUI output storage and upload it to input."""
    filename = media_item.get("filename", "") or "pipeline_input.png"
    subfolder = media_item.get("subfolder", "")
    item_type = media_item.get("item_type", "output")
    media_url = (
        f"{COMFYUI_URL}/view?"
        f"filename={filename}"
        f"&subfolder={subfolder}"
        f"&type={item_type}"
    )
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(media_url, timeout=60)
        resp.raise_for_status()
        image_bytes = resp.content

        upload_resp = await client.post(
            f"{COMFYUI_URL}/upload/image",
            files={"image": (filename or "pipeline_input.png", image_bytes)},
            data={"overwrite": "true"},
            timeout=60,
        )
        if upload_resp.status_code != 200:
            try:
                error_body = upload_resp.json()
            except Exception:
                error_body = upload_resp.text
            raise RuntimeError(f"Upload failed ({upload_resp.status_code}): {error_body}")
        return upload_resp.json()


async def _resolve_binding_value(result_sources: dict, binding: dict):
    """Resolve a binding against previously completed structured results."""
    from_key = binding.get("from")
    output_name = binding.get("output")
    binding_type = binding.get("type")
    index = int(binding.get("index", 0))

    if from_key not in result_sources:
        raise ValueError(f"Binding source '{from_key}' not found")

    outputs = result_sources[from_key].get("outputs", {})
    if output_name not in outputs:
        raise ValueError(f"Output '{output_name}' not found in source '{from_key}'")

    output_data = outputs[output_name]

    if binding_type == "text":
        texts = output_data.get("text", [])
        if index >= len(texts):
            raise ValueError(f"Text output index {index} out of range for '{output_name}' in source '{from_key}'")
        return texts[index]

    media = output_data.get("media", [])
    if index >= len(media):
        raise ValueError(f"Media output index {index} out of range for '{output_name}' in source '{from_key}'")

    media_item = media[index]
    if binding_type == "media_url":
        return media_item.get("url", "")
    if binding_type == "media_filename":
        return media_item.get("filename", "")
    if binding_type == "image":
        if media_item.get("type") not in {"image", "gif"}:
            raise ValueError(f"Binding '{output_name}' from source '{from_key}' is not an image output")
        return media_item

    raise ValueError(f"Unsupported binding type '{binding_type}'")


async def _resolve_run_bindings(bindings: dict) -> dict:
    if not isinstance(bindings, dict):
        raise ValueError("bindings must be an object")

    result_sources = {}
    resolved_params = {}
    for param_name, binding in bindings.items():
        if not isinstance(binding, dict):
            raise ValueError(f"Binding for param '{param_name}' must be an object")
        from_key = binding.get("from")
        if not from_key:
            raise ValueError(f"Binding for param '{param_name}' requires a non-empty 'from'")
        if from_key not in result_sources:
            entry = await _fetch_history_entry(str(from_key))
            if not entry:
                raise ValueError(f"Prompt result '{from_key}' not found")
            source_outputs = binding.get("source_outputs")
            if isinstance(source_outputs, dict) and source_outputs:
                result_sources[from_key] = _extract_outputs(entry, source_outputs, str(from_key))
            else:
                # Check entry cache first, then module-level cache
                cached_outputs = entry.get("mcp_outputs") or _mcp_outputs_cache.get(str(from_key))
                if not isinstance(cached_outputs, dict):
                    raise ValueError(
                        f"Prompt result '{from_key}' cannot be used for bindings without source_outputs metadata"
                    )
                result_sources[from_key] = {
                    "status": "completed",
                    "prompt_id": str(from_key),
                    "outputs": cached_outputs,
                }

        resolved_value = await _resolve_binding_value(result_sources, binding)
        if binding.get("type") == "image":
            upload_result = await _upload_media_to_input(resolved_value)
            resolved_params[param_name] = upload_result.get("name", "")
        else:
            resolved_params[param_name] = resolved_value
    return resolved_params


async def run_templates(pipeline: dict, timeout_per_step: float = 300) -> dict:
    """Run multiple templates sequentially with explicit output-to-input bindings."""
    steps = pipeline.get("steps")
    if not isinstance(steps, list) or not steps:
        return {"error": "pipeline.steps must be a non-empty list"}

    seen_ids = set()
    step_results = {}
    completed_steps = []

    for raw_step in steps:
        if not isinstance(raw_step, dict):
            return {"error": "Each pipeline step must be an object", "steps": completed_steps}

        step_id = str(raw_step.get("id", "")).strip()
        template_name = str(raw_step.get("template", "")).strip()
        params = raw_step.get("params", {})
        bindings = raw_step.get("bindings", {})

        if not step_id:
            return {"error": "Each pipeline step requires a non-empty id", "steps": completed_steps}
        if step_id in seen_ids:
            return {"error": f"Duplicate pipeline step id '{step_id}'", "steps": completed_steps}
        if not template_name:
            return {"error": f"Pipeline step '{step_id}' requires a template name", "steps": completed_steps}
        if not isinstance(params, dict):
            return {"error": f"Pipeline step '{step_id}' params must be an object", "steps": completed_steps}
        if not isinstance(bindings, dict):
            return {"error": f"Pipeline step '{step_id}' bindings must be an object", "steps": completed_steps}

        seen_ids.add(step_id)

        resolved_params = dict(params)
        try:
            for param_name, binding in bindings.items():
                if not isinstance(binding, dict):
                    raise ValueError(f"Binding for param '{param_name}' in step '{step_id}' must be an object")
                resolved_value = await _resolve_binding_value(step_results, binding)
                if binding.get("type") == "image":
                    upload_result = await _upload_media_to_input(resolved_value)
                    resolved_params[param_name] = upload_result.get("name", "")
                else:
                    resolved_params[param_name] = resolved_value
        except Exception as e:
            return {
                "status": "failed",
                "failed_step": step_id,
                "error": str(e),
                "steps": completed_steps,
            }

        result = await execute_template(template_name, resolved_params, wait=True, timeout=timeout_per_step)
        step_record = {
            "id": step_id,
            "template": template_name,
            "params": resolved_params,
            "status": result.get("status", "failed" if result.get("error") else "completed"),
        }
        if "prompt_id" in result:
            step_record["prompt_id"] = result["prompt_id"]
        if "outputs" in result:
            step_record["outputs"] = result["outputs"]
        if result.get("error"):
            step_record["error"] = result["error"]
            if "details" in result:
                step_record["details"] = result["details"]
            completed_steps.append(step_record)
            return {
                "status": "failed",
                "failed_step": step_id,
                "error": result["error"],
                "steps": completed_steps,
            }

        step_results[step_id] = result
        completed_steps.append(step_record)

    final_step = completed_steps[-1] if completed_steps else {}
    final_outputs = final_step.get("outputs", {})
    final_step_id = final_step.get("id", "")

    # Generate binding_hint for pipeline outputs (uses step id instead of prompt_id)
    binding_hint = {}
    for output_name, output_data in final_outputs.items():
        media = output_data.get("media", [])
        text = output_data.get("text", [])
        if media:
            media_item = media[0]
            binding_hint[output_name] = {
                "from": final_step_id,
                "output": output_name,
                "type": "image" if media_item.get("type") in ("image", "gif") else media_item.get("type", "image"),
                "index": 0,
            }
        elif text:
            binding_hint[output_name] = {
                "from": final_step_id,
                "output": output_name,
                "type": "text",
                "index": 0,
            }

    result = {
        "status": "completed",
        "steps": completed_steps,
        "final": final_outputs,
    }
    if binding_hint:
        result["binding_hint"] = binding_hint
    return result


async def save_template(name: str, workflow: dict, outputs: dict | None = None) -> dict:
    _ensure_dir()
    info = await extract_template_info(workflow)
    template = {
        "name": name,
        "title": info["title"],
        "description": info["description"],
        "disabled": False,
        "workflow": workflow,
        "inputs": info["inputs"],
        "outputs": outputs or info["outputs"],
    }
    path = config.get_template_dir() / f"{name}.json"
    path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    return template


def update_template(name: str, updates: dict) -> dict | None:
    template = get_template(name)
    if not template:
        return None
    if "workflow" in updates:
        template["workflow"] = updates["workflow"]
    if "outputs" in updates:
        template["outputs"] = updates["outputs"]
    if "title" in updates:
        template["title"] = updates["title"]
    if "description" in updates:
        template["description"] = updates["description"]
    if "inputs" in updates:
        template["inputs"] = updates["inputs"]
    if "disabled" in updates:
        template["disabled"] = bool(updates["disabled"])
    path = config.get_template_dir() / f"{name}.json"
    path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    return template


def delete_template(name: str) -> bool:
    path = config.get_template_dir() / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# ── Execution ─────────────────────────────────────────────

def _get_node_widget_names(node: dict, node_defs: dict) -> list[str]:
    """Get ordered list of widget input names for a node from node definitions."""
    class_type = node.get("type", "")
    node_def = node_defs.get(class_type, {})
    input_def = node_def.get("input", {})
    required = input_def.get("required", {})
    optional = input_def.get("optional", {})
    names = []
    for input_name in list(required.keys()) + list(optional.keys()):
        spec = required.get(input_name) or optional.get(input_name)
        if spec and _is_widget_input(spec):
            names.append(input_name)
    return names


def _apply_inputs(workflow: dict, inputs: dict, params: dict, node_defs: dict) -> dict:
    """Apply parameter values to the workflow's widget_values."""
    workflow = copy.deepcopy(workflow)
    nodes_by_id = {n["id"]: n for n in workflow.get("nodes", [])}

    for param_name, value in params.items():
        if param_name not in inputs:
            continue
        inp = inputs[param_name]
        node = nodes_by_id.get(inp["node_id"])
        if not node:
            continue
        widget_name = inp["widget"]

        # Get node definition to compute correct widget index
        class_type = node.get("type", "")
        node_def = node_defs.get(class_type, {})
        input_def = node_def.get("input", {})
        required = input_def.get("required", {})
        optional = input_def.get("optional", {})
        widget_names = _get_node_widget_names(node, node_defs)

        _set_widget_value(node, widget_name, value, widget_names, required, optional)

    return workflow


def _set_widget_value(node: dict, widget_name: str, value,
                      widget_names: list[str] | None = None,
                      required: dict | None = None,
                      optional: dict | None = None):
    """Set a widget value on a node by widget name.

    Uses widget_names and input specs to compute the correct index in widgets_values,
    accounting for hidden UI widgets like control_after_generate and dynamic sub-inputs.
    """
    values = node.get("widgets_values", [])
    if not values:
        return

    required = required or {}
    optional = optional or {}

    if widget_names:
        # Build ordered list of ALL widgets (definition + hidden + dynamic sub-inputs)
        # Detect hidden control_after_generate widgets by value pattern,
        # and dynamic sub-inputs by checking the node's inputs array.
        all_widgets = []
        vi = 0
        for wname in widget_names:
            all_widgets.append(wname)
            vi += 1
            spec = required.get(wname) or optional.get(wname)
            is_dynamic_combo = spec and isinstance(spec, list) and isinstance(spec[0], str) and spec[0].startswith("COMFY_DYNAMICCOMBO")
            is_int_float = spec and isinstance(spec, list) and spec[0] in ("INT", "FLOAT")
            # After a dynamic combo widget, add its active sub-inputs
            if is_dynamic_combo and vi > 0:
                selected_key = values[vi - 1] if vi - 1 < len(values) else None
                combo_options = spec[1].get("options", []) if len(spec) > 1 and isinstance(spec[1], dict) else []
                for opt in combo_options:
                    if isinstance(opt, dict) and opt.get("key") == selected_key:
                        req = opt.get("inputs", {}).get("required", {})
                        for sub_name in req:
                            all_widgets.append(f"{wname}.{sub_name}")
                            vi += 1
                        break
            elif is_int_float and vi < len(values):
                next_val = values[vi]
                if next_val in ("randomize", "increment", "decrement", "fixed"):
                    all_widgets.append(None)
                    vi += 1

        # Find the target widget's index in all_widgets
        for vi, wname in enumerate(all_widgets):
            if wname == widget_name:
                if 0 <= vi < len(values):
                    values[vi] = value
                return
        return

    # Single-widget fallback
    if len(values) == 1:
        values[0] = value


def _resolve_widget_value(value, spec):
    """Resolve UI-specific widget values to API-compatible values."""
    if not isinstance(spec, list) or len(spec) < 1:
        return value
    type_name = spec[0] if isinstance(spec[0], str) else None
    if type_name == "INT" and isinstance(value, str):
        if value == "randomize":
            return random.randint(0, 2**32 - 1)
        if value in ("increment", "decrement"):
            return spec[1].get("default", 0) if len(spec) > 1 and isinstance(spec[1], dict) else 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if type_name == "FLOAT" and isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    return value


def _is_widget_input(spec) -> bool:
    """Check if an input spec describes a widget (not a data connection).

    Widget inputs have specs like:
    - ["INT", {"default": 0, "min": 0, "max": 4096}]  → widget
    - [["option1", "option2"]]  → combo widget
    - ["FLOAT", {"default": 1.0}]  → widget
    - ["STRING", {"multiline": True}]  → widget
    - ["BOOLEAN", {"default": True}]  → widget
    - ["COMFY_DYNAMICCOMBO_V3", {...}]  → dynamic combo widget (e.g. RTX resize_type)
    - "MODEL"  → data connection (just a type string)
    - ["MODEL"]  → data connection (single-element list with a type string that's not a basic type)
    """
    if isinstance(spec, str):
        return False  # Simple type name = data connection
    if isinstance(spec, list) and len(spec) >= 1:
        first = spec[0]
        if isinstance(first, str):
            # Basic widget types
            if first in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"):
                return True
            # Dynamic combo widget (e.g. RTX nodes' resize_type)
            if first.startswith("COMFY_DYNAMICCOMBO"):
                return True
            # Combo: list of options
            if first.startswith(","):
                return True
            return False  # Type name like "MODEL", "IMAGE" = data connection
        if isinstance(first, list):
            return True  # Combo options list
    return False


def _ui_workflow_to_api_prompt(workflow: dict, node_defs: dict) -> dict:
    """Convert UI workflow format to API prompt format using object_info definitions.

    For each node:
    1. Get input order from node_defs[class_type]["input"]["required"] + ["optional"]
    2. Map widgets_values to inputs by matching widget names
    3. Map linked inputs to [source_node, output_index]
    """
    nodes = workflow.get("nodes", [])
    links = workflow.get("links", [])

    # Filter out UI-only nodes
    exec_nodes = [n for n in nodes if n.get("type") not in _UI_ONLY_TYPES]
    exec_node_ids = {n["id"] for n in exec_nodes}

    # Build link map: link_id -> (source_node_id, source_output_idx)
    link_map = {}
    for link in links:
        if len(link) >= 6:
            link_id, src_node, src_output = link[0], link[1], link[2]
            if src_node in exec_node_ids:
                link_map[link_id] = (src_node, src_output)

    prompt = {}
    for node in exec_nodes:
        node_id = str(node["id"])
        class_type = node["type"]

        # Get node definition from object_info
        node_def = node_defs.get(class_type, {})
        input_def = node_def.get("input", {})
        required_inputs = input_def.get("required", {})
        optional_inputs = input_def.get("optional", {})

        # Build ordered list of widget input names from the definition
        all_input_names = list(required_inputs.keys()) + list(optional_inputs.keys())
        widget_names = []
        for input_name in all_input_names:
            spec = required_inputs.get(input_name) or optional_inputs.get(input_name)
            if spec and _is_widget_input(spec):
                widget_names.append(input_name)

        # Map connected inputs (data connections with links)
        connected_inputs = {}
        for inp in node.get("inputs", []):
            link_id = inp.get("link")
            if link_id is not None and link_id in link_map:
                src_node, src_output = link_map[link_id]
                connected_inputs[inp["name"]] = [str(src_node), src_output]

        # Map converted widgets (widget → input with different name)
        converted_widgets = {}
        for inp in node.get("inputs", []):
            w = inp.get("widget")
            if w:
                converted_widgets[w["name"]] = inp["name"]

        # Build API inputs
        api_inputs = {}
        api_inputs.update(connected_inputs)

        widget_values = node.get("widgets_values", [])

        # Key insight: widgets_values contains ALL widgets including hidden UI controls
        # (e.g. control_after_generate after INT seed) and dynamic sub-inputs
        # (e.g. resize_type.scale for COMFY_DYNAMICCOMBO_V3).
        #
        # For dynamic combos, widgets_values stores:
        #   [selected_key, sub_input_value, ...]
        # where selected_key identifies which sub-inputs are active, and the following
        # values are the sub-input values (one per active sub-input).
        if widget_values:
            all_widgets = []  # [(name, is_hidden)]
            vi = 0
            for wname in widget_names:
                all_widgets.append((wname, False))
                vi += 1
                spec = required_inputs.get(wname) or optional_inputs.get(wname)
                is_dynamic_combo = spec and isinstance(spec, list) and isinstance(spec[0], str) and spec[0].startswith("COMFY_DYNAMICCOMBO")
                is_int_float = spec and isinstance(spec, list) and spec[0] in ("INT", "FLOAT")
                # After a dynamic combo widget, check for sub-input values.
                # The selected key determines which sub-inputs are active.
                # For each active sub-input, there's a value in widgets_values.
                if is_dynamic_combo and vi > 0:
                    selected_key = widget_values[vi - 1]
                    # Find the selected option's sub-inputs
                    combo_options = spec[1].get("options", []) if len(spec) > 1 and isinstance(spec[1], dict) else []
                    sub_inputs = []
                    for opt in combo_options:
                        if isinstance(opt, dict) and opt.get("key") == selected_key:
                            req = opt.get("inputs", {}).get("required", {})
                            sub_inputs = list(req.keys())
                            break
                    # Add sub-input widgets (they consume values from widgets_values)
                    for sub_name in sub_inputs:
                        full_name = f"{wname}.{sub_name}"
                        all_widgets.append((full_name, False))
                        vi += 1
                elif is_int_float and vi < len(widget_values):
                    next_val = widget_values[vi]
                    if next_val in ("randomize", "increment", "decrement", "fixed"):
                        all_widgets.append(("_hidden_" + wname, True))
                        vi += 1

            # Now map: iterate all_widgets and widgets_values together
            vi = 0
            for wname, is_hidden in all_widgets:
                if vi >= len(widget_values):
                    break
                if is_hidden:
                    # Skip hidden widget value
                    vi += 1
                    continue
                input_name = converted_widgets.get(wname, wname)
                if input_name in connected_inputs:
                    # Connected: skip value (link wins)
                    vi += 1
                    continue
                # Use widget value
                widget_spec = required_inputs.get(wname) or optional_inputs.get(wname)
                api_inputs[input_name] = _resolve_widget_value(widget_values[vi], widget_spec) if widget_spec else widget_values[vi]
                vi += 1

        prompt[node_id] = {
            "class_type": class_type,
            "inputs": api_inputs,
        }

    return prompt


async def _wait_for_result(prompt_id: str, outputs: dict, timeout: float) -> dict:
    """Poll /history until the prompt completes or times out."""
    interval = 1.0  # poll interval in seconds
    elapsed = 0.0
    checked_queue = False
    async with httpx.AsyncClient() as client:
        while elapsed < timeout:
            try:
                resp = await client.get(
                    f"{config.get_comfyui_api_url()}/history/{prompt_id}",
                    headers=config.get_comfyui_headers(),
                    timeout=10,
                )
                resp.raise_for_status()
                history = resp.json()
                if prompt_id in history:
                    entry = history[prompt_id]
                    status = entry.get("status", {})
                    if status.get("completed", False):
                        return _extract_outputs(entry, outputs, prompt_id)
                    if status.get("status_str") == "error":
                        return {"error": "Execution failed", "prompt_id": prompt_id,
                                "details": status.get("messages", [])}
                elif elapsed >= 3.0 and not checked_queue:
                    # After 3s, check if the prompt is in the queue
                    # If not in queue AND not in history, the prompt_id is likely invalid
                    checked_queue = True
                    try:
                        queue_resp = await client.get(f"{COMFYUI_URL}/queue", timeout=10)
                        queue_resp.raise_for_status()
                        queue_data = queue_resp.json()
                        queue_ids = set()
                        for item in queue_data.get("queue_pending", []):
                            if isinstance(item, list) and len(item) >= 2:
                                queue_ids.add(item[1])
                        for item in queue_data.get("queue_running", []):
                            if isinstance(item, list) and len(item) >= 2:
                                queue_ids.add(item[1])
                        if prompt_id not in queue_ids:
                            return {"error": f"Prompt '{prompt_id}' not found in queue or history",
                                    "prompt_id": prompt_id}
                    except Exception:
                        pass  # Queue check failed, continue polling
            except Exception as e:
                logger.warning(f"Poll error: {e}")
            await asyncio.sleep(interval)
            elapsed += interval
    return {"error": f"Timed out after {timeout}s", "prompt_id": prompt_id}


def _extract_outputs(entry: dict, outputs: dict, prompt_id: str) -> dict:
    """Extract output values from a completed history entry.

    If outputs are configured, only return those nodes.
    Otherwise return all nodes with output data.
    """
    output_data = entry.get("outputs", {})

    # Build node_id → name mapping
    prompt_data = entry.get("prompt", [])
    node_names = {}
    if isinstance(prompt_data, list) and len(prompt_data) >= 3:
        prompt_nodes = prompt_data[2]
        if isinstance(prompt_nodes, dict):
            for nid, node_info in prompt_nodes.items():
                node_names[str(nid)] = node_info.get("class_type", f"node_{nid}")

    output_meta_by_node_id = {}
    for output_name, output_meta in outputs.items():
        node_id = output_meta.get("node_id")
        if node_id is None:
            continue
        output_meta_by_node_id[str(node_id)] = {
            "output_name": output_name,
            "title": output_meta.get("title", ""),
            "node_id": node_id,
        }

    # If outputs are configured, only include those nodes
    if outputs:
        target_node_ids = {str(v.get("node_id")) for v in outputs.values()}
    else:
        target_node_ids = set(output_data.keys())

    result = {}
    for node_id, node_output in output_data.items():
        if not node_output:
            continue
        if node_id not in target_node_ids:
            continue
        output_meta = output_meta_by_node_id.get(node_id, {})
        name = output_meta.get("output_name") or node_names.get(node_id, f"node_{node_id}")
        node_title = output_meta.get("title") or node_names.get(node_id, f"node_{node_id}")

        # Build simplified media entries (images, audio, gifs, etc.)
        media_urls = []
        for media_key in ("images", "audio", "gifs"):
            items = node_output.get(media_key, [])
            if not items:
                continue
            for item in items:
                filename = item.get("filename", "")
                subfolder = item.get("subfolder", "")
                item_type = item.get("type", "output")
                media_type = item.get("mediaType", media_key.rstrip("s"))  # "image", "audio", "gif"
                base_url = _comfyui_public_url.get() or config.get_comfyui_public_url()
                url = (f"{base_url}/view?"
                       f"filename={filename}"
                       f"&subfolder={subfolder}"
                       f"&type={item_type}")
                media_urls.append({
                    "url": url,
                    "type": media_type,
                    "filename": filename,
                    "subfolder": subfolder,
                    "item_type": item_type,
                })
        # Build simplified output: keep text, add media, remove raw ComfyUI data
        node_result = {}
        if node_output.get("text"):
            node_result["text"] = node_output["text"]
        if media_urls:
            node_result["media"] = media_urls
            # Generate markdown for easy rendering
            first_media = media_urls[0]
            media_url = first_media.get("url", "")
            media_type = first_media.get("type", "image")
            if media_type in ("image", "gif"):
                node_result["markdown"] = f"![{name}]({media_url})"
            elif media_type == "audio":
                node_result["markdown"] = f"[🔊 {name}]({media_url})"
        result[name] = node_result

    result_payload = {
        "status": "completed",
        "prompt_id": prompt_id,
        "outputs": result,
    }
    entry["mcp_outputs"] = result
    _mcp_outputs_cache[prompt_id] = result
    return result_payload


async def execute_template(name: str, params: dict, wait: bool = True, timeout: float = 300, bindings: dict | None = None) -> dict:
    """Execute a template with given parameters.

    Args:
        name: Template name.
        params: Parameter values to apply.
        wait: If True, poll for results and return them directly.
        timeout: Max seconds to wait for completion (only when wait=True).
    """
    logger.info(f"[Template] execute_template: {name}, params={params}, wait={wait}")
    template = get_template(name)
    if not template:
        logger.warning(f"[Template] not found: {name}")
        return {"error": f"Template '{name}' not found"}
    if is_template_disabled(template):
        logger.warning(f"[Template] disabled: {name}")
        return {"error": f"Template '{name}' is disabled"}

    inputs = template.get("inputs", {})
    outputs = template.get("outputs", {})
    workflow = template.get("workflow", {})
    params = dict(params)

    if bindings:
        resolved_binding_params = await _resolve_run_bindings(bindings)
        params.update(resolved_binding_params)

    # Get node definitions from ComfyUI (needed for widget index computation)
    node_defs = await _get_node_definitions()

    # Apply input parameters to workflow
    workflow = _apply_inputs(workflow, inputs, params, node_defs)

    # Convert UI workflow to API prompt
    api_prompt = _ui_workflow_to_api_prompt(workflow, node_defs)

    # Submit to ComfyUI
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{config.get_comfyui_api_url()}/prompt",
            headers=config.get_comfyui_headers(),
            json={"prompt": api_prompt},
            timeout=30,
        )
        if resp.status_code != 200:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            logger.error(f"[Template] ComfyUI rejected prompt ({resp.status_code}): {error_body}")
            return {"error": f"ComfyUI error ({resp.status_code})", "details": error_body}
        result = resp.json()

    prompt_id = result.get("prompt_id")
    if not prompt_id:
        logger.error(f"[Template] Failed to queue prompt: {result}")
        return {"error": "Failed to queue prompt", "details": result}

    logger.info(f"[Template] Prompt queued: {prompt_id}")

    if not wait:
        return {
            "prompt_id": prompt_id,
            "status": "queued",
            "template": name,
            "params": params,
        }

    # Poll for completion
    result = await _wait_for_result(prompt_id, outputs, timeout)
    logger.info(f"[Template] Execution completed: {result.get('status', 'unknown')}")
    return result


async def get_template_outputs(prompt_id: str, outputs: dict, wait: bool = False, timeout: float = 300) -> dict:
    """Fetch execution results and extract output values.

    If wait is True, poll until completion or timeout.
    """
    if wait:
        return await _wait_for_result(prompt_id, outputs, timeout)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{config.get_comfyui_api_url()}/history/{prompt_id}",
            headers=config.get_comfyui_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        history = resp.json()

    if prompt_id not in history:
        return {"status": "pending", "prompt_id": prompt_id}

    entry = history[prompt_id]
    status = entry.get("status", {})
    if not status.get("completed", False):
        return {"status": "running", "prompt_id": prompt_id}

    return _extract_outputs(entry, outputs, prompt_id)
