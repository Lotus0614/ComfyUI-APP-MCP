"""Template manager — wraps ComfyUI workflows as reusable templates with typed inputs/outputs."""

import asyncio
import copy
import json
import logging
import contextvars
import random

import httpx

logger = logging.getLogger(__name__)

try:
    from . import config
    from .comfyui_client import ComfyUIClient
except ImportError:
    import config
    from comfyui_client import ComfyUIClient

# Set by middleware from MCP request query param or comfyui_url header.
# Used for media links returned to remote MCP clients.
_comfyui_public_url: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_comfyui_public_url", default=None
)

# Module-level cache for mcp_outputs, keyed by prompt_id.
# Allows cross-call binding resolution without requiring source_outputs.
_mcp_outputs_cache: dict[str, dict] = {}

_SEED_INPUT_NAME = "seed"
_MAX_COMFY_SEED = 2**50 - 1

# UI-only node types that should not be submitted for execution
_UI_ONLY_TYPES = {
    "MarkdownNote", "Note", "Reroute", "PrimitiveNode",
}

# Cache for object_info node definitions
_node_defs_cache: dict | None = None


def _build_timeout_result(
    prompt_id: str,
    timeout: float,
    *,
    template_name: str | None = None,
) -> dict:
    result = {
        "status": "timeout",
        "error": f"Timed out after {timeout}s",
        "prompt_id": prompt_id,
        "outputs": {},
        "continue_hint": (
            "Use get_template_result(name, prompt_id, wait=true) "
            "to continue waiting for the same prompt."
        ),
    }
    if template_name:
        result["template"] = template_name
    return result


def _comfyui_client() -> ComfyUIClient:
    return ComfyUIClient(
        base_url=config.get_comfyui_api_url(),
        headers=config.get_comfyui_headers(),
    )


async def _get_node_definitions() -> dict:
    """Fetch and cache node definitions from ComfyUI /object_info."""
    global _node_defs_cache
    if _node_defs_cache is not None:
        return _node_defs_cache
    _node_defs_cache = await _comfyui_client().list_nodes()
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


def _list_readable_markdown_notes(workflow: dict) -> list[str]:
    """List MarkdownNote titles that can be read by read_template_doc."""
    docs = []
    seen = set()
    for node in workflow.get("nodes", []):
        if node.get("type") != "MarkdownNote":
            continue

        title = node.get("title")
        if not isinstance(title, str) or not title or title in seen:
            continue

        values = node.get("widgets_values", [])
        if not values:
            continue

        docs.append(title)
        seen.add(title)
    return docs


def _upsert_markdown_note(workflow: dict, note_title: str, content: str, mode: str = "replace") -> dict:
    """Update or insert a MarkdownNote node in the workflow.

    Args:
        workflow: The workflow dict (will be mutated).
        note_title: Title of the MarkdownNote node.
        content: Markdown content to write.
        mode: "replace" to overwrite, "append" to add to existing content.

    Returns:
        The mutated workflow dict.
    """
    nodes = workflow.get("nodes", [])
    for node in nodes:
        if node.get("type") == "MarkdownNote" and node.get("title") == note_title:
            values = node.get("widgets_values", [])
            if not values:
                node["widgets_values"] = [content]
            elif mode == "append":
                existing = str(values[0])
                node["widgets_values"][0] = existing + "\n" + content if existing else content
            else:
                node["widgets_values"][0] = content
            return workflow

    # Node not found — create a new one
    max_id = max((n.get("id", 0) for n in nodes), default=0)
    new_node = {
        "id": max_id + 1,
        "type": "MarkdownNote",
        "title": note_title,
        "widgets_values": [content],
        "color": "#432",
        "bgcolor": "#653",
        "pos": [0, 0],
        "size": [300, 200],
        "flags": {},
        "order": len(nodes),
        "mode": 0,
    }
    nodes.append(new_node)
    return workflow


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


def _collect_workflow_nodes(workflow: dict) -> tuple[dict, dict, dict]:
    """Build a node lookup covering top-level AND subgraph-internal nodes.

    ComfyUI subgraphs store their real nodes under
    ``workflow.definitions.subgraphs[*].nodes``. The top-level graph only holds
    *instance* nodes whose ``type`` is the subgraph UUID. When the frontend
    converts the graph to an API prompt, internal nodes are keyed as
    ``"<instance_id>:<internal_id>"`` (e.g. ``"150:124"``), while top-level
    nodes keep their plain id (e.g. ``"110"``).

    Returns:
        (node_by_id, api_key_by_id, instance_by_internal_id) — keyed by the node
        id as found in linearData (an int). ``api_key_by_id`` gives the key used
        for that node in the converted api_prompt, which is what
        injection/output-extraction must match against.
        ``instance_by_internal_id`` maps a subgraph-internal node id to its
        top-level instance node (the instance holds the user-facing input
        labels); top-level nodes are absent from it. Top-level nodes take
        precedence on id collisions; for a subgraph instantiated more than
        once, the first instance wins.
    """
    node_by_id: dict = {}
    api_key_by_id: dict = {}
    instance_by_internal_id: dict = {}

    top_nodes = workflow.get("nodes", []) or []
    for n in top_nodes:
        nid = n.get("id")
        if nid is None:
            continue
        node_by_id[nid] = n
        api_key_by_id[nid] = str(nid)

    defs = workflow.get("definitions") or {}
    subgraphs = defs.get("subgraphs") if isinstance(defs, dict) else None
    if not isinstance(subgraphs, list):
        return node_by_id, api_key_by_id, instance_by_internal_id

    subgraph_by_uuid = {sg.get("id"): sg for sg in subgraphs if isinstance(sg, dict)}
    # A top-level node whose `type` is a subgraph UUID instantiates that subgraph.
    for inst in top_nodes:
        sg = subgraph_by_uuid.get(inst.get("type"))
        if not sg:
            continue
        inst_id = inst.get("id")
        for internal in sg.get("nodes", []) or []:
            iid = internal.get("id")
            if iid is None or iid in node_by_id:
                continue  # id already known (top-level or earlier instance)
            node_by_id[iid] = internal
            api_key_by_id[iid] = f"{inst_id}:{iid}"
            instance_by_internal_id.setdefault(iid, inst)

    return node_by_id, api_key_by_id, instance_by_internal_id


def _resolve_input_label(instance_node: dict | None, internal_input: dict, widget_name: str) -> str:
    """Pick the display label for a subgraph-internal (or top-level) input.

    The user-facing labels live on the subgraph *instance* node's proxied
    inputs; internal nodes often have stale or colliding labels (e.g. two slots
    both labeled '画师'). Prefer the instance's label for the matching widget,
    then the internal input's own label, then the widget name.
    """
    if instance_node:
        for ii in instance_node.get("inputs", []) or []:
            iwi = ii.get("widget") or {}
            if (iwi.get("name") or ii.get("name")) == widget_name:
                return ii.get("label") or internal_input.get("label") or widget_name
    return internal_input.get("label") or widget_name


def _extract_inputs(workflow: dict, node_defs: dict | None = None) -> dict:
    """Extract inputs from linearData.inputs."""
    node_map, api_key_map, instance_by_internal = _collect_workflow_nodes(workflow)

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
        api_key = api_key_map.get(node_id, str(node_id))
        instance = instance_by_internal.get(node_id)  # None for top-level nodes
        widgets_values = node.get("widgets_values", [])
        found = False

        for inp in node.get("inputs", []):
            widget_info = inp.get("widget")
            if not widget_info:
                continue
            widget_name = widget_info.get("name", inp.get("name", ""))
            # Only register the widget specified in linearData
            if target_widget and widget_name != target_widget:
                continue
            label = _resolve_input_label(instance, inp, widget_name)
            found = True

            entry = {
                "node_id": node_id,
                "api_key": api_key,
                "widget": widget_name,
                "type": inp.get("type", "STRING"),
            }

            if widgets_values and node_defs:
                default = _read_widget_default(node, widget_name, node_defs)
                if default is not None:
                    entry["default"] = default

            inputs[label] = entry

        # Fallback: check hidden inputs from node_defs (e.g., lora_loader_data)
        if target_widget and not found and node_defs:
            class_type = node.get("type", "")
            node_def = node_defs.get(class_type, {})
            input_def = node_def.get("input", {})
            hidden = input_def.get("hidden", {})
            if target_widget in hidden:
                spec = hidden[target_widget]
                widget_type = spec[0] if isinstance(spec, list) and spec else "STRING"
                if isinstance(widget_type, list):
                    widget_type = "COMBO"
                entry = {
                    "node_id": node_id,
                    "api_key": api_key,
                    "widget": target_widget,
                    "type": widget_type if isinstance(widget_type, str) else "STRING",
                }
                if widgets_values:
                    default = _read_widget_default(node, target_widget, node_defs)
                    if default is not None:
                        entry["default"] = default
                inputs[target_widget] = entry
    return inputs


def _widget_value_slots(node: dict, node_defs: dict) -> list[tuple[str, int]]:
    """Map each widget name to its positional index in the node's widgets_values.

    Mirrors ComfyUI's widget serialization order, including hidden
    ``control_after_generate`` slots (which advance the index without producing
    a user-facing widget) and dynamic-combo sub-inputs. Returns ``[]`` if the
    node has no widgets_values or its class is missing from ``node_defs``.
    Shared by the default-value reader and the UI-workflow value injector so
    reads and writes always agree on slot positions.
    """
    class_type = node.get("type", "")
    widgets_values = node.get("widgets_values", [])
    if not widgets_values:
        return []

    node_def = node_defs.get(class_type, {})
    input_def = node_def.get("input", {})
    required = input_def.get("required", {})
    optional = input_def.get("optional", {})

    # Build ordered widget names from the node definition
    widget_names = []
    for input_name in list(required.keys()) + list(optional.keys()):
        spec = required.get(input_name) or optional.get(input_name)
        if spec and _is_widget_input(spec):
            widget_names.append(input_name)

    slots: list[tuple[str, int]] = []
    vi = 0
    for wname in widget_names:
        slots.append((wname, vi))
        vi += 1
        spec = required.get(wname) or optional.get(wname)
        is_dynamic_combo = spec and isinstance(spec, list) and isinstance(spec[0], str) and spec[0].startswith("COMFY_DYNAMICCOMBO")
        is_int_float = spec and isinstance(spec, list) and spec[0] in ("INT", "FLOAT")
        # After a dynamic combo widget, its active sub-inputs occupy slots too.
        if is_dynamic_combo and vi > 0:
            selected_key = widgets_values[vi - 1] if vi - 1 < len(widgets_values) else None
            combo_options = spec[1].get("options", []) if len(spec) > 1 and isinstance(spec[1], dict) else []
            for opt in combo_options:
                if isinstance(opt, dict) and opt.get("key") == selected_key:
                    req = opt.get("inputs", {}).get("required", {})
                    for sub_name in req:
                        slots.append((f"{wname}.{sub_name}", vi))
                        vi += 1
                    break
        elif is_int_float and vi < len(widgets_values):
            # Hidden control_after_generate slot advances the index silently.
            if widgets_values[vi] in ("randomize", "increment", "decrement", "fixed"):
                vi += 1
    return slots


def _read_widget_default(node: dict, widget_name: str, node_defs: dict):
    """Read the current widget value from a node's widgets_values by widget name."""
    widgets_values = node.get("widgets_values", [])
    for wname, idx in _widget_value_slots(node, node_defs):
        if wname == widget_name and idx < len(widgets_values):
            return widgets_values[idx]
    return None


def _inject_widget_values_into_workflow(
    workflow: dict, inputs: dict, params: dict, node_defs: dict
) -> dict:
    """Return a deep copy of the UI workflow with user params written into the
    matching nodes' ``widgets_values``.

    This is the UI-graph counterpart of ``_inject_widget_values`` (which targets
    the API prompt). The result is meant for ``extra_data.extra_pnginfo.workflow``
    so images embed a workflow that reflects the actual run values. Top-level and
    subgraph-internal nodes are both resolved via ``_collect_workflow_nodes``.

    Best-effort: params whose node/widget can't be located (or whose class is
    missing from node_defs) are silently skipped — execution correctness is not
    affected, only the embedded metadata. The input ``workflow`` is never
    mutated (a deep copy is returned).
    """
    import copy
    wf = copy.deepcopy(workflow)
    node_map, _api_key_map, _inst = _collect_workflow_nodes(wf)
    for param_name, value in params.items():
        inp = inputs.get(param_name)
        if not inp:
            continue
        node = node_map.get(inp["node_id"])
        if not node:
            continue
        widgets_values = node.get("widgets_values")
        if not isinstance(widgets_values, list) or not widgets_values:
            continue
        widget_name = inp["widget"]
        for wname, idx in _widget_value_slots(node, node_defs):
            if wname == widget_name and idx < len(widgets_values):
                widgets_values[idx] = value
                break
    return wf


def _detect_output_nodes(workflow: dict) -> dict:
    """Detect output nodes from linearData.outputs (explicit user selection),
    falling back to auto-detection of terminal nodes."""
    node_map, api_key_map, _ = _collect_workflow_nodes(workflow)

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
            try:
                node_id = int(nid)
            except (TypeError, ValueError):
                continue
            node = node_map.get(node_id)
            if not node:
                continue
            class_type = node.get("type", "")
            title = node.get("title") or class_type
            if class_type in _UI_ONLY_TYPES:
                continue
            api_key = api_key_map.get(node_id, str(node_id))
            node_outputs = node.get("outputs", [])
            if node_outputs:
                for out in node_outputs:
                    out_type = out.get("type", "")
                    name = f"{title}_{nid}_{out.get('name', 'out')}"
                    outputs[name] = {
                        "node_id": node_id,
                        "api_key": api_key,
                        "type": _output_type_from_comfy(out_type),
                        "comfy_type": out_type,
                        "title": title,
                    }
            else:
                # Terminal node with no outputs (SaveImage, SaveAudio, etc.)
                name = f"{title}_{nid}_output"
                outputs[name] = {
                    "node_id": node_id,
                    "api_key": api_key,
                    "type": "unknown",
                    "comfy_type": "unknown",
                    "title": title,
                }
        return outputs

    # Fallback: auto-detect terminal nodes whose outputs nothing consumes.
    # Collect used output slots from top-level links and every subgraph's
    # internal links (subgraph links are dicts; top-level links are lists).
    subgraph_uuids = set()
    defs = workflow.get("definitions") or {}
    subgraphs = defs.get("subgraphs") if isinstance(defs, dict) else None
    if isinstance(subgraphs, list):
        subgraph_uuids = {sg.get("id") for sg in subgraphs if isinstance(sg, dict)}

    used_outputs = set()
    for link in workflow.get("links", []) or []:
        if isinstance(link, list) and len(link) >= 3:
            used_outputs.add((link[1], link[2]))
    if isinstance(subgraphs, list):
        for sg in subgraphs:
            for link in sg.get("links", []) or []:
                if isinstance(link, dict):
                    used_outputs.add((link.get("origin_id"), link.get("origin_slot")))

    for node_id, node in node_map.items():
        class_type = node.get("type", "")
        title = node.get("title") or class_type
        # Skip UI-only nodes and subgraph *instance* nodes (their outputs are
        # proxies with no real api_prompt key).
        if class_type in _UI_ONLY_TYPES or class_type in subgraph_uuids:
            continue
        for out_idx, out in enumerate(node.get("outputs", [])):
            if (node_id, out_idx) not in used_outputs:
                out_type = out.get("type", "")
                name = f"{title}_{node_id}_{out.get('name', out_idx)}"
                outputs[name] = {
                    "node_id": node_id,
                    "api_key": api_key_map.get(node_id, str(node_id)),
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


def list_template_docs(template: dict) -> list[str]:
    """Return doc titles available through read_template_doc for a template."""
    return _list_readable_markdown_notes(template.get("workflow", {}))


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


async def update_template_doc(name: str, title: str, content: str, mode: str = "replace") -> dict:
    """Update a documentation section in a template.

    Updates the MarkdownNote node in the embedded workflow, syncs the
    top-level 'title'/'description' field when applicable, and writes
    the workflow back to ComfyUI's userdata storage.

    Args:
        name: Template name.
        title: Documentation section title (e.g. "description", "usage", "tips").
        content: Markdown content to write.
        mode: "replace" to overwrite entirely, "append" to add to the end.
    """
    if mode not in ("replace", "append"):
        return {"error": f"Invalid mode '{mode}', must be 'replace' or 'append'"}

    template = get_template(name)
    if not template:
        return {"error": f"Template '{name}' not found"}
    if is_template_disabled(template):
        return {"error": f"Template '{name}' is disabled"}

    workflow = template.get("workflow", {})
    _upsert_markdown_note(workflow, title, content, mode)

    # Sync top-level fields when the section is title or description
    updated_content = _extract_markdown_note(workflow, title)
    if title == "title":
        template["title"] = updated_content or ""
    elif title == "description":
        template["description"] = updated_content or ""

    # Persist template file
    path = config.get_template_dir() / f"{name}.json"
    path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write back to ComfyUI's original workflow storage
    try:
        await _comfyui_client().save_workflow(name, workflow)
    except Exception as e:
        logger.warning(f"[update_template_doc] Failed to sync workflow back to ComfyUI: {e}")

    return {
        "template": name,
        "title": title,
        "mode": mode,
        "content": updated_content,
    }


async def _fetch_history_entry(prompt_id: str) -> dict | None:
    history = await _comfyui_client().get_history(prompt_id)
    return history.get(prompt_id)


async def _upload_media_to_input(media_item: dict) -> dict:
    """Download a generated media file from ComfyUI output storage and upload it to input."""
    filename = media_item.get("filename", "") or "pipeline_input.png"
    subfolder = media_item.get("subfolder", "")
    item_type = media_item.get("item_type", "output")
    client = _comfyui_client()
    image_bytes = await client.download_view(filename, subfolder=subfolder, file_type=item_type)
    return await client.upload_image_bytes(filename or "pipeline_input.png", image_bytes, overwrite=True)


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


async def save_template(name: str, workflow: dict, outputs: dict | None = None, api_prompt: dict | None = None) -> dict:
    _ensure_dir()
    info = await extract_template_info(workflow)
    template = {
        "name": name,
        "title": info["title"],
        "description": info["description"],
        "disabled": False,
        "workflow": workflow,
        "api_prompt": api_prompt,  # Pre-converted API format from frontend
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
    if "api_prompt" in updates:
        template["api_prompt"] = updates["api_prompt"]
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


async def _enforce_queue_capacity(client) -> dict | None:
    """Reject the run if the ComfyUI queue is at capacity.

    Reads ``max_concurrency`` from config (<= 0 means unlimited → returns None).
    Counts ``queue_running`` + ``queue_pending``. If that total is >= the limit,
    returns an error dict (status ``queue_full``) so the caller can surface it
    without submitting. If the queue probe fails, logs a warning and returns
    None (best-effort: never block execution on a transient queue error).
    """
    max_concurrency = config.get_max_concurrency()
    if max_concurrency <= 0:  # -1 / 0 = unlimited
        return None
    try:
        queue_data = await client.get_queue()
    except Exception as e:
        logger.warning(f"[Template] queue capacity check failed, proceeding: {e}")
        return None
    running = len(queue_data.get("queue_running", []))
    pending = len(queue_data.get("queue_pending", []))
    in_flight = running + pending
    if in_flight >= max_concurrency:
        logger.info(
            f"[Template] queue at capacity ({in_flight}/{max_concurrency}); rejecting run"
        )
        return {
            "status": "queue_full",
            "error": (
                f"ComfyUI queue is at capacity: {in_flight} task(s) in flight "
                f"(running={running}, pending={pending}), max_concurrency={max_concurrency}. "
                "Retry later."
            ),
            "max_concurrency": max_concurrency,
            "running": running,
            "pending": pending,
        }
    return None


async def _wait_for_result(
    prompt_id: str,
    outputs: dict,
    timeout: float,
    *,
    template_name: str | None = None,
) -> dict:
    """Poll /history until the prompt completes or times out."""
    interval = 1.0  # poll interval in seconds
    elapsed = 0.0
    checked_queue = False
    client = _comfyui_client()
    while elapsed < timeout:
        try:
            history = await client.get_history(prompt_id)
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False):
                    return _extract_outputs(entry, outputs, prompt_id)
                if status.get("status_str") == "error":
                    return {"error": "Execution failed", "prompt_id": prompt_id,
                            "details": status.get("messages", [])}
            elif elapsed >= 3.0 and not checked_queue:
                # After 3s, check if the prompt is in the queue.
                checked_queue = True
                try:
                    queue_data = await client.get_queue()
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
                    pass  # Queue check failed, continue polling.
        except Exception as e:
            logger.warning(f"Poll error: {e}")
        await asyncio.sleep(interval)
        elapsed += interval
    return _build_timeout_result(
        prompt_id,
        timeout,
        template_name=template_name,
    )


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
        # Match by api_key (the node's key in history, e.g. "150:124" inside a
        # subgraph); fall back to node_id for older templates.
        key = output_meta.get("api_key", output_meta.get("node_id"))
        if key is None:
            continue
        output_meta_by_node_id[str(key)] = {
            "output_name": output_name,
            "title": output_meta.get("title", ""),
            "node_id": output_meta.get("node_id"),
        }

    # If outputs are configured, only include those nodes
    if outputs:
        target_node_ids = {str(v.get("api_key", v.get("node_id"))) for v in outputs.values()}
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


def _inject_widget_values(api_prompt_data: dict, inputs: dict, params: dict) -> dict:
    """Inject user parameters into pre-converted API prompt.

    The API prompt is already in the correct format - we just need to replace widget values.
    """
    import copy
    api_prompt = copy.deepcopy(api_prompt_data)

    for param_name, value in params.items():
        if param_name not in inputs:
            continue
        inp = inputs[param_name]
        # api_key matches the node's key in the converted api_prompt — for a
        # node inside a subgraph this is "<instance>:<internal>" (e.g. "150:124").
        # Older templates without api_key fall back to str(node_id).
        api_key = str(inp.get("api_key") or inp["node_id"])
        widget_name = inp["widget"]

        if api_key in api_prompt:
            api_prompt[api_key]["inputs"][widget_name] = value

    return api_prompt


async def execute_template(
    name: str,
    params: dict,
    wait: bool = True,
    timeout: float = 300,
    bindings: dict | None = None,
) -> dict:
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
    params = {
        **{
            input_name: random.randint(0, _MAX_COMFY_SEED)
            for input_name in inputs
            if input_name == _SEED_INPUT_NAME
        },
        **dict(params),
    }

    if bindings:
        resolved_binding_params = await _resolve_run_bindings(bindings)
        params.update(resolved_binding_params)

    # Generate API prompt
    api_prompt_data = template.get("api_prompt")
    if not api_prompt_data:
        return {"error": "Template missing api_prompt. Please refresh the template in the frontend."}
    api_prompt = _inject_widget_values(api_prompt_data, inputs, params)

    # Build a UI-workflow copy with the same values injected, so output images
    # embed a workflow (extra_pnginfo.workflow) that reflects this actual run.
    # Best-effort: metadata must never block or break execution.
    ui_workflow = template.get("workflow")
    if ui_workflow:
        try:
            node_defs = await _get_node_definitions()
            ui_workflow = _inject_widget_values_into_workflow(ui_workflow, inputs, params, node_defs)
        except Exception as e:
            logger.warning(f"[Template] UI-workflow metadata injection failed, embedding as-is: {e}")

    # Submit to ComfyUI
    client = _comfyui_client()
    capacity_error = await _enforce_queue_capacity(client)
    if capacity_error:
        return capacity_error
    try:
        result = await client.queue_prompt(api_prompt, workflow=ui_workflow)
    except httpx.HTTPStatusError as e:
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        logger.error(f"[Template] ComfyUI rejected prompt ({e.response.status_code}): {error_body}")
        return {"error": f"ComfyUI error ({e.response.status_code})", "details": error_body}

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
    result = await _wait_for_result(
        prompt_id,
        outputs,
        timeout,
        template_name=name,
    )
    logger.info(f"[Template] Execution completed: {result.get('status', 'unknown')}")
    return result


async def get_template_outputs(
    prompt_id: str,
    outputs: dict,
    wait: bool = False,
    timeout: float = 300,
    *,
    template_name: str | None = None,
) -> dict:
    """Fetch execution results and extract output values.

    If wait is True, poll until completion or timeout.
    """
    if wait:
        return await _wait_for_result(
            prompt_id,
            outputs,
            timeout,
            template_name=template_name,
        )

    history = await _comfyui_client().get_history(prompt_id)

    if prompt_id not in history:
        return {"status": "pending", "prompt_id": prompt_id}

    entry = history[prompt_id]
    status = entry.get("status", {})
    if not status.get("completed", False):
        return {"status": "running", "prompt_id": prompt_id}

    return _extract_outputs(entry, outputs, prompt_id)
