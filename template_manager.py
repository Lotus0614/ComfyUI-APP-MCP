"""Template manager — wraps ComfyUI workflows as reusable templates with typed inputs/outputs."""

from __future__ import annotations

import asyncio
import contextvars
import copy
import hashlib
import json
import logging
import secrets
import re
import time
from urllib.parse import quote, unquote, urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

try:
    from . import config
    from .comfyui_client import ComfyUIClient
    from .template_tokens import template_token_store
except ImportError:
    import config
    from comfyui_client import ComfyUIClient
    from template_tokens import template_token_store

# Set by middleware from MCP request query param or comfyui_url header.
# Used for media links returned to remote MCP clients.
_comfyui_public_url: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_comfyui_public_url", default=None
)

# Module-level cache for public outputs (keyed by prompt_id), used to resolve
# inline @{result://...} and @{step://...} references.
# Bounded FIFO: oldest entries are evicted past _MCP_OUTPUTS_CACHE_MAX.
_mcp_outputs_cache: dict[str, dict] = {}
_MCP_OUTPUTS_CACHE_MAX = 256

_SEED_INPUT_NAME = "seed"
_MAX_COMFY_SEED = 2**50 - 1

# UI-only node types that should not be submitted for execution
_UI_ONLY_TYPES = {
    "MarkdownNote", "Note", "Reroute", "PrimitiveNode",
}

# Cache for object_info node definitions (refreshed after _NODE_DEFS_TTL seconds
# so newly installed custom nodes are picked up without restarting).
_node_defs_cache: dict | None = None
_node_defs_cache_time: float = 0.0
_NODE_DEFS_TTL = 300.0

# Characters that are unsafe in a template filename (path separators,
# traversal, Windows-reserved and control characters).
_UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _template_filename(name: str) -> str:
    """Map a template name to a safe filename, rejecting path traversal.

    Path separators and other unsafe characters are replaced with ``_`` so
    nested workflow names like ``sub/wf`` map to a flat ``sub_wf.json`` while
    the stored ``name`` field keeps the original value.
    """
    raw = str(name or "").strip()
    if not raw:
        raise ValueError("Template name must not be empty")
    safe = _UNSAFE_NAME_CHARS.sub("_", raw)
    # Reject names that collapse to nothing meaningful or are pure dots
    if not safe.strip("._ ") or safe in {".", ".."}:
        raise ValueError(f"Invalid template name: {name!r}")
    return f"{safe}.json"


def _template_path(name: str):
    return config.get_template_dir() / _template_filename(name)


def _cache_outputs(prompt_id: str, outputs: dict) -> None:
    """Store binding outputs for a prompt with a bounded cache size."""
    _mcp_outputs_cache[prompt_id] = outputs
    while len(_mcp_outputs_cache) > _MCP_OUTPUTS_CACHE_MAX:
        _mcp_outputs_cache.pop(next(iter(_mcp_outputs_cache)))


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
            "Use get_template_result(name, run_id, wait=true) "
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


async def _get_node_definitions(force: bool = False) -> dict:
    """Fetch and cache node definitions from ComfyUI /object_info (TTL-based)."""
    global _node_defs_cache, _node_defs_cache_time
    now = time.monotonic()
    if (
        not force
        and _node_defs_cache is not None
        and now - _node_defs_cache_time < _NODE_DEFS_TTL
    ):
        return _node_defs_cache
    try:
        _node_defs_cache = await _comfyui_client().list_nodes()
        _node_defs_cache_time = now
    except Exception:
        # Keep serving a stale cache rather than failing outright.
        if _node_defs_cache is not None:
            logger.warning("[Template] object_info refresh failed; using cached node defs")
            return _node_defs_cache
        raise
    return _node_defs_cache


def _ensure_dir():
    config.get_template_dir().mkdir(parents=True, exist_ok=True)


def _public_value_type(value_type: str) -> str:
    """Map ComfyUI/template types to a small AI-facing type set."""
    normalized = str(value_type or "").upper()
    return {
        "INT": "integer",
        "FLOAT": "number",
        "STRING": "string",
        "BOOLEAN": "boolean",
        "COMBO": "string",
        "IMAGE": "image",
        "LATENT": "image",
        "AUDIO": "audio",
        "TEXT": "text",
    }.get(normalized, str(value_type or "string").lower())


def _clean_public_name(value: str) -> str:
    """Remove generated node-id fragments from an AI-facing name."""
    name = str(value or "").strip()
    name = re.sub(r"_\d+_(?:output|out|STRING|TEXT|IMAGE|AUDIO|LATENT)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_\d+$", "", name)
    return name.strip(" _-")


def build_public_output_names(outputs: dict) -> dict[str, str]:
    """Return stable, node-id-free aliases for configured outputs."""
    aliases = {}
    used = set()
    for internal_name, output_meta in outputs.items():
        title = _clean_public_name(output_meta.get("title", ""))
        fallback = _clean_public_name(internal_name)
        output_type = _public_value_type(output_meta.get("type", "output"))
        base = title or fallback or output_type or "output"
        alias = base
        suffix = 2
        while alias in used:
            alias = f"{base}_{suffix}"
            suffix += 1
        aliases[internal_name] = alias
        used.add(alias)
    return aliases


def build_public_template_schema(template: dict) -> dict:
    """Project stored execution metadata into a concise AI-facing schema."""
    public_inputs = {}
    for input_name, input_meta in template.get("inputs", {}).items():
        if input_name == _SEED_INPUT_NAME:
            continue
        public_input = {"type": _public_value_type(input_meta.get("type", "string"))}
        for field in ("default", "options", "min", "max", "step"):
            if field in input_meta:
                public_input[field] = input_meta[field]
        public_inputs[input_name] = public_input

    output_aliases = build_public_output_names(template.get("outputs", {}))
    public_outputs = {
        output_aliases[internal_name]: {
            "type": _public_value_type(output_meta.get("type", "output")),
        }
        for internal_name, output_meta in template.get("outputs", {}).items()
    }

    return {
        "name": template["name"],
        "title": template.get("title", ""),
        "description": template.get("description", ""),
        "inputs": public_inputs,
        "outputs": public_outputs,
        "docs": list_template_docs(template),
    }


def build_template_schema_revision(template: dict) -> str:
    """Return a stable digest for the AI-facing template schema and guidance."""
    payload = json.dumps(
        build_public_template_schema(template),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def build_template_token_fields(template: dict) -> dict:
    """Issue token metadata for get_template when token protection is enabled."""
    if not config.get_template_token_enabled():
        return {"template_token_required": False}
    max_uses = config.get_template_token_max_uses()
    ttl_seconds = config.get_template_token_ttl_hours() * 3600
    return {
        "template_token_required": True,
        **template_token_store.issue(
            template["name"],
            build_template_schema_revision(template),
            max_uses=max_uses,
            ttl_seconds=ttl_seconds,
        ),
    }


def build_public_execution_result(result: dict) -> dict:
    """Return the public result shape shared by template execution tools."""
    payload = {
        "status": result.get("status", "failed" if result.get("error") else "completed"),
        "outputs": result.get("outputs", {}),
    }

    if result.get("prompt_id") and result.get("status") != "completed":
        payload["run_id"] = result["prompt_id"]
    if result.get("template"):
        payload["template"] = result["template"]
    if result.get("error"):
        payload["error"] = result["error"]
    if result.get("continue_hint"):
        payload["continue_hint"] = result["continue_hint"]
    for field in (
        "error_code",
        "recovery",
        "template_token_remaining_uses",
        "template_token_expires_at",
    ):
        if field in result:
            payload[field] = result[field]

    return payload


def _build_output_ref(scheme: str, source_id: str, output_name: str, index: int) -> str:
    return f"{scheme}://{quote(str(source_id), safe='')}/{quote(output_name, safe='')}/{index}"


def _parse_output_ref(ref: str, expected_scheme: str) -> tuple[str, str, int]:
    parsed = urlparse(ref)
    if parsed.scheme != expected_scheme or not parsed.netloc:
        raise ValueError(f"Expected a {expected_scheme}:// output reference")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid {expected_scheme} output reference")
    try:
        index = int(parts[1])
    except ValueError as e:
        raise ValueError(f"Invalid output index in reference '{ref}'") from e
    return unquote(parsed.netloc), unquote(parts[0]), index


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


def _subgraph_definitions(workflow: dict) -> dict:
    """Return subgraph definitions keyed by their UUID."""
    definitions = workflow.get("definitions") or {}
    subgraphs = (
        definitions.get("subgraphs") if isinstance(definitions, dict) else None
    )
    if not isinstance(subgraphs, list):
        return {}
    return {
        subgraph.get("id"): subgraph
        for subgraph in subgraphs
        if isinstance(subgraph, dict) and subgraph.get("id") is not None
    }


def _parse_linear_input_entry(item) -> tuple[list[int], str, bool] | None:
    """Parse old and new ``linearData.inputs`` entries.

    Old ComfyUI versions store a plain node id, for example ``["10",
    "width"]``. New versions store a node-locator plus the widget name, for
    example ``["<opaque-uuid>:6:width", "width"]``. The opaque locator prefix
    is intentionally ignored; only its trailing numeric node path is needed to
    locate the workflow node and build the API prompt key.

    Returns ``(node_path, widget_name, is_locator)``. ``node_path`` contains
    one id for a top-level node and may contain more ids for nested subgraphs.
    """
    raw_locator = item[0] if isinstance(item, list) and item else item
    listed_widget = item[1] if isinstance(item, list) and len(item) > 1 else None

    if isinstance(raw_locator, bool):
        return None
    if isinstance(raw_locator, int):
        return [raw_locator], str(listed_widget or ""), False
    if not isinstance(raw_locator, str) or not raw_locator:
        return None

    try:
        return [int(raw_locator)], str(listed_widget or ""), False
    except ValueError:
        pass

    parts = raw_locator.split(":")
    locator_widget = ""
    if parts and listed_widget is not None and parts[-1] == str(listed_widget):
        locator_widget = parts.pop()

    node_path = []
    for part in reversed(parts):
        try:
            node_path.append(int(part))
        except (TypeError, ValueError):
            break
    node_path.reverse()
    widget_name = str(listed_widget or locator_widget)
    if not node_path or not widget_name:
        return None
    return node_path, widget_name, True


def _find_node_by_path(workflow: dict, node_path: list[int]) -> dict | None:
    """Resolve a top-level/subgraph node path such as ``[11, 2]``."""
    if not node_path:
        return None

    subgraphs = _subgraph_definitions(workflow)
    nodes = workflow.get("nodes", []) or []
    node = None
    for index, node_id in enumerate(node_path):
        node = next((item for item in nodes if item.get("id") == node_id), None)
        if node is None:
            return None
        if index < len(node_path) - 1:
            subgraph = subgraphs.get(node.get("type"))
            if not subgraph:
                return None
            nodes = subgraph.get("nodes", []) or []
    return node


def _find_node_by_api_key(workflow: dict, api_key: str) -> dict | None:
    """Resolve the numeric node path used by converted API prompts."""
    try:
        node_path = [int(part) for part in str(api_key).split(":")]
    except (TypeError, ValueError):
        return None
    return _find_node_by_path(workflow, node_path)


def _resolve_subgraph_widget_binding(
    workflow: dict,
    instance_node: dict,
    instance_path: list[int],
    exposed_widget: str,
) -> dict | None:
    """Resolve a subgraph instance widget to its internal executable input."""
    subgraph = _subgraph_definitions(workflow).get(instance_node.get("type"))
    if not subgraph:
        return None

    subgraph_inputs = subgraph.get("inputs", []) or []
    input_index = next(
        (
            index
            for index, input_meta in enumerate(subgraph_inputs)
            if input_meta.get("name") == exposed_widget
        ),
        None,
    )
    if input_index is None:
        return None
    subgraph_input = subgraph_inputs[input_index]
    link_ids = set(subgraph_input.get("linkIds") or [])

    for link in subgraph.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        matches_slot = (
            link.get("origin_id") == -10 and link.get("origin_slot") == input_index
        )
        if not matches_slot and (not link_ids or link.get("id") not in link_ids):
            continue

        target_id = link.get("target_id")
        target_slot = link.get("target_slot")
        internal_node = next(
            (
                node
                for node in subgraph.get("nodes", []) or []
                if node.get("id") == target_id
            ),
            None,
        )
        internal_inputs = internal_node.get("inputs", []) if internal_node else []
        if (
            not isinstance(target_slot, int)
            or target_slot < 0
            or target_slot >= len(internal_inputs)
        ):
            continue
        internal_input = internal_inputs[target_slot]
        widget_info = internal_input.get("widget") or {}
        internal_widget = widget_info.get("name") or internal_input.get("name")
        if not internal_widget:
            continue

        instance_input = next(
            (
                input_meta
                for input_meta in instance_node.get("inputs", []) or []
                if (input_meta.get("widget") or {}).get("name") == exposed_widget
                or input_meta.get("name") == exposed_widget
            ),
            {},
        )
        label = (
            subgraph_input.get("label")
            or internal_input.get("label")
            or instance_input.get("label")
            or exposed_widget
        )
        target_path = [*instance_path, target_id]
        return {
            "node": internal_node,
            "node_id": target_id,
            "api_key": ":".join(str(node_id) for node_id in target_path),
            "widget": internal_widget,
            "label": label,
        }
    return None


def _infer_workflow_widget_binding(
    workflow: dict,
    api_key: str,
    widget_name: str,
) -> tuple[str, str] | None:
    """Infer the outer subgraph widget for templates saved without UI metadata."""
    try:
        node_path = [int(part) for part in str(api_key).split(":")]
    except (TypeError, ValueError):
        return None
    if len(node_path) < 2:
        return None

    instance_path = node_path[:-1]
    internal_node_id = node_path[-1]
    instance_node = _find_node_by_path(workflow, instance_path)
    if instance_node is None:
        return None
    subgraph = _subgraph_definitions(workflow).get(instance_node.get("type"))
    if not subgraph:
        return None

    internal_node = next(
        (
            node
            for node in subgraph.get("nodes", []) or []
            if node.get("id") == internal_node_id
        ),
        None,
    )
    if internal_node is None:
        return None
    target_slot = next(
        (
            index
            for index, input_meta in enumerate(internal_node.get("inputs", []) or [])
            if (
                (input_meta.get("widget") or {}).get("name")
                or input_meta.get("name")
            )
            == widget_name
        ),
        None,
    )
    if target_slot is None:
        return None

    subgraph_inputs = subgraph.get("inputs", []) or []
    for link in subgraph.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        if (
            link.get("origin_id") != -10
            or link.get("target_id") != internal_node_id
            or link.get("target_slot") != target_slot
        ):
            continue
        origin_slot = link.get("origin_slot")
        if (
            not isinstance(origin_slot, int)
            or origin_slot < 0
            or origin_slot >= len(subgraph_inputs)
        ):
            continue
        exposed_widget = subgraph_inputs[origin_slot].get("name")
        if exposed_widget:
            return (
                ":".join(str(path_node_id) for path_node_id in instance_path),
                exposed_widget,
            )
    return None


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
    subgraphs = _subgraph_definitions(workflow)

    linear_inputs = []
    extra = workflow.get("extra", {})
    if isinstance(extra, dict):
        linear = extra.get("linearData", {})
        if isinstance(linear, dict):
            li = linear.get("inputs")
            if isinstance(li, list):
                for item in li:
                    parsed = _parse_linear_input_entry(item)
                    if parsed is None:
                        logger.warning(f"[Template] Skipping malformed linearData input entry: {item!r}")
                        continue
                    linear_inputs.append(parsed)

    inputs = {}
    for node_path, target_widget, is_locator in linear_inputs:
        binding = None
        workflow_key = None
        workflow_widget = None
        if is_locator:
            node = _find_node_by_path(workflow, node_path)
            if node and node.get("type") in subgraphs:
                binding = _resolve_subgraph_widget_binding(
                    workflow, node, node_path, target_widget
                )
                if not binding:
                    logger.warning(
                        "[Template] Could not resolve subgraph input locator: "
                        f"{node_path!r}:{target_widget}"
                    )
                    continue
                # The converted API prompt targets the internal executable
                # node, while the serialized UI workflow also keeps the value
                # on the outer subgraph instance's promoted widget. Preserve
                # both locations so embedded workflows reopen with run values.
                workflow_key = ":".join(
                    str(path_node_id) for path_node_id in node_path
                )
                workflow_widget = target_widget
            node_id = binding["node_id"] if binding else node_path[-1]
            api_key = (
                binding["api_key"]
                if binding
                else ":".join(str(path_node_id) for path_node_id in node_path)
            )
            instance = None
        else:
            node_id = node_path[0]
            node = node_map.get(node_id)
            api_key = api_key_map.get(node_id, str(node_id))
            instance = instance_by_internal.get(node_id)

        if binding:
            node = binding["node"]
        if not node:
            continue
        widgets_values = node.get("widgets_values", [])
        found = False

        for inp in node.get("inputs", []):
            widget_info = inp.get("widget")
            if not widget_info:
                continue
            widget_name = widget_info.get("name", inp.get("name", ""))
            # Only register the widget specified in linearData
            resolved_widget = binding["widget"] if binding else target_widget
            if resolved_widget and widget_name != resolved_widget:
                continue
            label = (
                binding["label"]
                if binding
                else _resolve_input_label(instance, inp, widget_name)
            )
            found = True

            entry = {
                "node_id": node_id,
                "api_key": api_key,
                "widget": widget_name,
                "type": inp.get("type", "STRING"),
            }
            if workflow_key is not None:
                entry["workflow_key"] = workflow_key
                entry["workflow_widget"] = workflow_widget

            if widgets_values and node_defs:
                default = _read_widget_default(node, widget_name, node_defs)
                if default is not None:
                    entry["default"] = default

            inputs[label] = entry

        # New ComfyUI workflows may omit non-favorited widgets from a node's
        # serialized inputs. Recover them from object_info, including hidden
        # inputs such as lora_loader_data.
        resolved_widget = binding["widget"] if binding else target_widget
        if resolved_widget and not found and node_defs:
            class_type = node.get("type", "")
            node_def = node_defs.get(class_type, {})
            input_def = node_def.get("input", {})
            spec = None
            spec_section = None
            for section_name in ("required", "optional", "hidden"):
                section = input_def.get(section_name, {})
                if resolved_widget in section:
                    spec = section[resolved_widget]
                    spec_section = section_name
                    break
            if spec is not None and (
                spec_section == "hidden" or _is_widget_input(spec)
            ):
                widget_type = spec[0] if isinstance(spec, list) and spec else "STRING"
                if isinstance(widget_type, list):
                    widget_type = "COMBO"
                entry = {
                    "node_id": node_id,
                    "api_key": api_key,
                    "widget": resolved_widget,
                    "type": widget_type if isinstance(widget_type, str) else "STRING",
                }
                if workflow_key is not None:
                    entry["workflow_key"] = workflow_key
                    entry["workflow_widget"] = workflow_widget
                if widgets_values:
                    default = _read_widget_default(node, resolved_widget, node_defs)
                    if default is not None:
                        entry["default"] = default
                label = binding["label"] if binding else resolved_widget
                inputs[label] = entry
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


def _write_widget_value(
    node: dict,
    widget_name: str,
    value,
    node_defs: dict,
) -> bool:
    """Write one serialized widget value, including subgraph proxy widgets."""
    widgets_values = node.get("widgets_values")
    if not isinstance(widgets_values, list):
        return False

    for current_name, index in _widget_value_slots(node, node_defs):
        if current_name == widget_name and index < len(widgets_values):
            widgets_values[index] = value
            return True

    # Subgraph instance types are UUIDs and therefore absent from object_info.
    # Their serialized inputs still identify promoted widgets in the same
    # order as widgets_values, so use that order as the UI-graph fallback.
    value_index = 0
    for input_meta in node.get("inputs", []) or []:
        widget_meta = input_meta.get("widget")
        if not isinstance(widget_meta, dict):
            continue
        current_name = widget_meta.get("name") or input_meta.get("name")
        if current_name == widget_name and value_index < len(widgets_values):
            widgets_values[value_index] = value
            return True
        value_index += 1
    return False


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
    wf = copy.deepcopy(workflow)
    node_map, _api_key_map, _inst = _collect_workflow_nodes(wf)
    for param_name, value in params.items():
        inp = inputs.get(param_name)
        if not inp:
            continue
        # api_key contains the exact subgraph instance path (for example
        # ``11:2``). Older templates without it keep using the node-id lookup.
        api_key = inp.get("api_key")
        node = _find_node_by_api_key(wf, api_key) if api_key is not None else None
        if node is None:
            node = node_map.get(inp.get("node_id"))
        if node:
            _write_widget_value(node, inp["widget"], value, node_defs)

        # New App Mode locators for promoted subgraph widgets resolve to an
        # internal API node, but ComfyUI serializes a second copy of the value
        # on the outer subgraph instance. Keep that copy in sync as well.
        workflow_key = inp.get("workflow_key")
        workflow_widget = inp.get("workflow_widget")
        if workflow_key is None or not workflow_widget:
            inferred_binding = _infer_workflow_widget_binding(
                wf,
                api_key,
                inp["widget"],
            )
            if inferred_binding is not None:
                workflow_key, workflow_widget = inferred_binding
        if workflow_key is not None and workflow_widget:
            workflow_node = _find_node_by_api_key(wf, workflow_key)
            if workflow_node is not None and workflow_node is not node:
                _write_widget_value(
                    workflow_node,
                    workflow_widget,
                    value,
                    node_defs,
                )
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
        for out_idx, out in enumerate(node.get("outputs") or []):
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


def list_public_templates() -> list[dict]:
    """List concise template summaries for AI clients."""
    _ensure_dir()
    templates = []
    for path in sorted(config.get_template_dir().glob("*.json")):
        try:
            template = json.loads(path.read_text(encoding="utf-8"))
            if is_template_disabled(template):
                continue
            templates.append({
                "name": template.get("name", path.stem),
                "title": template.get("title") or template.get("description", ""),
            })
        except Exception as e:
            logger.warning(f"Failed to load template {path}: {e}")
    return templates


def get_template(name: str) -> dict | None:
    try:
        path = _template_path(name)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load template '{name}': {e}")
        return None


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
    path = _template_path(name)
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
    return await client.upload_image_bytes(filename or "pipeline_input.png", image_bytes)


async def _resolve_output_value(outputs: dict, output_name: str, index: int):
    """Resolve one public output reference to a template parameter value."""
    if output_name not in outputs:
        # Tolerant fallback: if there is exactly one output, use it — refs
        # rebuilt from raw history may carry class-based names instead of the
        # template's public aliases.
        if len(outputs) == 1:
            output_name = next(iter(outputs))
        else:
            available = ", ".join(sorted(outputs)) or "none"
            raise ValueError(
                f"Output '{output_name}' not found. Available outputs: {available}"
            )

    output_data = outputs[output_name]
    texts = output_data.get("text", [])
    if texts:
        if index >= len(texts):
            raise ValueError(f"Text output index {index} out of range for '{output_name}'")
        return texts[index]

    media = output_data.get("media", [])
    if index >= len(media):
        raise ValueError(f"Media output index {index} out of range for '{output_name}'")

    media_item = media[index]
    if media_item.get("type") in {"image", "gif"}:
        upload_result = await _upload_media_to_input(media_item)
        return upload_result.get("name", "")
    return media_item.get("url", "")


async def _resolve_inline_ref(ref: str, step_results: dict | None = None):
    """Resolve a single `result://` or `step://` output reference to a value.

    Dispatches on scheme: `step://` looks up ``step_results[source_step]``;
    `result://` consults the in-memory cache with a history fallback.
    Raises ``ValueError`` on parse/lookup failure; the caller decides whether
    to raise or return an error dict.
    """
    if ref.startswith("step://"):
        source_step, output_name, index = _parse_output_ref(ref, "step")
        if not isinstance(step_results, dict) or source_step not in step_results:
            raise ValueError(f"Step '{source_step}' is unavailable for reference")
        return await _resolve_output_value(step_results[source_step], output_name, index)

    prompt_id, output_name, index = _parse_output_ref(ref, "result")
    outputs = _mcp_outputs_cache.get(prompt_id)
    if not isinstance(outputs, dict):
        # Cache miss (e.g. server restarted): rebuild public outputs from the
        # ComfyUI history entry for this prompt.
        entry = await _fetch_history_entry(prompt_id)
        if entry and entry.get("status", {}).get("completed", False):
            _extract_outputs(entry, {}, prompt_id)  # repopulates the cache
            outputs = _mcp_outputs_cache.get(prompt_id)
    if not isinstance(outputs, dict):
        raise ValueError(
            f"Result '{prompt_id}' is unavailable for reference "
            "(not found in history or not completed yet)"
        )
    return await _resolve_output_value(outputs, output_name, index)


# Inline @{ref} markers embedded in parameter string values, e.g.
#   "Caption: @{step://caption/描述/0}. 风格: 动漫"
# Refs are URL-encoded by _build_output_ref, so they never contain `}`.
_INLINE_REF_RE = re.compile(r"@\{(?P<ref>(?:result|step)://[^}]*)\}")


async def _substitute_string(s: str, step_results: dict | None = None) -> str:
    """Replace every ``@{ref}`` occurrence in *s* with its resolved value.

    Returns *s* unchanged when it contains no inline refs. Resolutions run
    concurrently; each distinct ref is resolved once per call (memoized) so the
    same image is not re-downloaded/re-uploaded multiple times.
    """
    matches = list(_INLINE_REF_RE.finditer(s))
    if not matches:
        return s

    resolved: dict[str, str] = {}
    pending: list[str] = []
    for m in matches:
        ref = m.group("ref")
        if ref not in resolved and ref not in pending:
            pending.append(ref)

    if pending:
        values = await asyncio.gather(*(_resolve_inline_ref(r, step_results) for r in pending))
        for ref, value in zip(pending, values):
            resolved[ref] = "" if value is None else str(value)

    out: list[str] = []
    last = 0
    for m in matches:
        out.append(s[last:m.start()])
        out.append(resolved[m.group("ref")])
        last = m.end()
    out.append(s[last:])
    return "".join(out)


async def _apply_inline_refs(value, step_results: dict | None = None):
    """Recursively resolve ``@{ref}`` markers inside parameter values.

    Strings are substituted; lists/tuples and dict values are walked; every
    other type (int/float/bool/None/…) is returned unchanged.
    """
    if isinstance(value, str):
        return await _substitute_string(value, step_results)
    if isinstance(value, list):
        return [await _apply_inline_refs(v, step_results) for v in value]
    if isinstance(value, tuple):
        return tuple(await _apply_inline_refs(v, step_results) for v in value)
    if isinstance(value, dict):
        return {k: await _apply_inline_refs(v, step_results) for k, v in value.items()}
    return value




async def run_templates(pipeline: dict, timeout_per_step: float = 300) -> dict:
    """Run multiple templates sequentially; outputs are referenced inline via @{ref}."""
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
        template_token = raw_step.get("template_token")

        if not step_id:
            return {"error": "Each pipeline step requires a non-empty id", "steps": completed_steps}
        if step_id in seen_ids:
            return {"error": f"Duplicate pipeline step id '{step_id}'", "steps": completed_steps}
        if not template_name:
            return {"error": f"Pipeline step '{step_id}' requires a template name", "steps": completed_steps}
        if not isinstance(params, dict):
            return {"error": f"Pipeline step '{step_id}' params must be an object", "steps": completed_steps}

        seen_ids.add(step_id)

        result = await execute_template(
            template_name,
            params,
            wait=True,
            timeout=timeout_per_step,
            step_results=step_results,
            template_token=template_token,
            enforce_template_token=True,
        )
        step_record = {
            "id": step_id,
            "template": template_name,
            **build_public_execution_result(result),
        }
        if result.get("error"):
            completed_steps.append(step_record)
            return {
                "status": "failed",
                "failed_step": step_id,
                "error": result["error"],
                "steps": completed_steps,
            }

        prompt_id = result.get("prompt_id", "")
        step_results[step_id] = _mcp_outputs_cache.get(prompt_id, {})
        completed_steps.append(step_record)

    return {
        "status": "completed",
        "steps": completed_steps,
    }


async def save_template(name: str, workflow: dict, outputs: dict | None = None, api_prompt: dict | None = None) -> dict:
    _ensure_dir()
    path = _template_path(name)  # Validate the name before doing any work
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
    path = _template_path(name)
    path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    return template


def delete_template(name: str) -> bool:
    try:
        path = _template_path(name)
    except ValueError:
        return False
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
    checked_queue = False
    client = _comfyui_client()
    start = time.monotonic()
    deadline = start + timeout
    while time.monotonic() < deadline:
        elapsed = time.monotonic() - start
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
    output_aliases = build_public_output_names(outputs)
    for output_name, output_meta in outputs.items():
        # Match by api_key (the node's key in history, e.g. "150:124" inside a
        # subgraph); fall back to node_id for older templates.
        key = output_meta.get("api_key", output_meta.get("node_id"))
        if key is None:
            continue
        output_meta_by_node_id[str(key)] = {
            "output_name": output_name,
            "public_name": output_aliases.get(output_name, output_name),
            "title": output_meta.get("title", ""),
            "node_id": output_meta.get("node_id"),
        }

    # If outputs are configured, only include those nodes
    if outputs:
        target_node_ids = {str(v.get("api_key", v.get("node_id"))) for v in outputs.values()}
    else:
        target_node_ids = set(output_data.keys())

    result = {}
    public_outputs = {}
    for node_id, node_output in output_data.items():
        if not node_output:
            continue
        if node_id not in target_node_ids:
            continue
        output_meta = output_meta_by_node_id.get(node_id, {})
        name = output_meta.get("output_name") or node_names.get(node_id, f"node_{node_id}")
        public_name = output_meta.get("public_name") or _clean_public_name(name) or "output"

        # Build simplified media entries (images, audio, gifs, etc.)
        base_url = _comfyui_public_url.get() or config.get_comfyui_public_url()
        media_urls = []
        for media_key in ("images", "audio", "gifs"):
            items = node_output.get(media_key) or []
            for item in items:
                filename = item.get("filename", "")
                subfolder = item.get("subfolder", "")
                item_type = item.get("type", "output")
                media_type = item.get("mediaType", media_key.rstrip("s"))  # "image", "audio", "gif"
                query = urlencode({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": item_type,
                })
                url = f"{base_url}/view?{query}"
                media_urls.append({
                    "url": url,
                    "type": media_type,
                    "filename": filename,
                    "subfolder": subfolder,
                    "item_type": item_type,
                })
        output_entry = {}
        if node_output.get("text"):
            output_entry["text"] = node_output["text"]
        if media_urls:
            output_entry["media"] = media_urls

        public_result = {}
        texts = node_output.get("text", [])
        if texts:
            if len(texts) == 1:
                public_result = {
                    "type": "text",
                    "value": texts[0],
                    "ref": _build_output_ref("result", prompt_id, public_name, 0),
                }
            else:
                public_result = {
                    "type": "text_list",
                    "items": [
                        {
                            "value": text,
                            "ref": _build_output_ref("result", prompt_id, public_name, index),
                        }
                        for index, text in enumerate(texts)
                    ],
                }
        if media_urls:
            public_items = [
                {
                    "type": item.get("type", "media"),
                    "url": item.get("url", ""),
                    "ref": _build_output_ref("result", prompt_id, public_name, index),
                }
                for index, item in enumerate(media_urls)
            ]
            public_result = public_items[0] if len(public_items) == 1 else {
                "type": f"{public_items[0]['type']}_list",
                "items": public_items,
            }
            first_media = public_items[0]
            media_type = first_media.get("type", "media")
            media_url = first_media.get("url", "")
            if media_type in ("image", "gif"):
                public_result["markdown"] = f"![{public_name}]({media_url})"
            elif media_type == "audio":
                public_result["markdown"] = f"[{public_name}]({media_url})"

        result[public_name] = public_result
        public_outputs[public_name] = output_entry

    result_payload = {
        "status": "completed",
        "prompt_id": prompt_id,
        "outputs": result,
    }
    _cache_outputs(prompt_id, public_outputs)
    return result_payload


def _coerce_param_value(value, input_type: str):
    """Best-effort coercion of a parameter value to its declared input type.

    AI clients frequently send numbers/booleans as strings; ComfyUI would then
    fail with an obscure node validation error. Raises ValueError with a clear
    message when the value cannot be interpreted.
    """
    t = str(input_type or "").upper()
    if t == "INT":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            return int(float(value.strip()))
        raise ValueError(f"expected an integer, got {value!r}")
    if t == "FLOAT":
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            return float(value.strip())
        raise ValueError(f"expected a number, got {value!r}")
    if t == "BOOLEAN":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"expected a boolean, got {value!r}")
    return value


def _validate_and_coerce_params(inputs: dict, params: dict) -> tuple[dict, str | None]:
    """Validate parameter names against template inputs and coerce types.

    Returns (coerced_params, error_message). Unknown parameter names produce an
    error listing the valid ones so AI clients can self-correct.
    """
    known = set(inputs) | {_SEED_INPUT_NAME}
    unknown = [p for p in params if p not in known]
    if unknown:
        available = ", ".join(sorted(n for n in inputs if n != _SEED_INPUT_NAME)) or "none"
        return params, (
            f"Unknown parameter(s): {', '.join(unknown)}. "
            f"Valid parameters: {available}. "
            "Call get_template to see the current input schema."
        )

    coerced = {}
    errors = []
    for name, value in params.items():
        meta = inputs.get(name)
        if not meta:
            coerced[name] = value
            continue
        try:
            coerced[name] = _coerce_param_value(value, meta.get("type", ""))
        except (ValueError, TypeError) as e:
            errors.append(f"'{name}': {e}")
    if errors:
        return params, "Invalid parameter value(s): " + "; ".join(errors)
    return coerced, None


def _inject_widget_values(api_prompt_data: dict, inputs: dict, params: dict) -> dict:
    """Inject user parameters into pre-converted API prompt.

    The API prompt is already in the correct format - we just need to replace widget values.
    """
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
    step_results: dict | None = None,
    template_token: str | None = None,
    enforce_template_token: bool = False,
) -> dict:
    """Execute a template with given parameters.

    Args:
        name: Template name.
        params: Parameter values to apply.
        wait: If True, poll for results and return them directly.
        timeout: Max seconds to wait for completion (only when wait=True).
        template_token: Token returned by get_template when protection is enabled.
        enforce_template_token: Apply MCP template token policy to this execution.
    """
    logger.info(f"[Template] execute_template: {name}, params={params}, wait={wait}")
    template = get_template(name)
    if not template:
        logger.warning(f"[Template] not found: {name}")
        return {"error": f"Template '{name}' not found"}
    if is_template_disabled(template):
        logger.warning(f"[Template] disabled: {name}")
        return {"error": f"Template '{name}' is disabled"}

    token_required = enforce_template_token and config.get_template_token_enabled()
    token_max_uses = config.get_template_token_max_uses()
    token_ttl_seconds = config.get_template_token_ttl_hours() * 3600
    schema_revision = build_template_schema_revision(template) if token_required else ""
    if token_required:
        token_error = template_token_store.validate(
            template_token,
            name,
            schema_revision,
            max_uses=token_max_uses,
            ttl_seconds=token_ttl_seconds,
        )
        if token_error:
            return token_error

    inputs = template.get("inputs", {})
    outputs = template.get("outputs", {})
    params = {
        **{
            input_name: secrets.randbelow(_MAX_COMFY_SEED + 1)
            for input_name in inputs
            if input_name == _SEED_INPUT_NAME
        },
        **dict(params),
    }

    # Inline @{ref} substitution — resolve references embedded inside string
    # parameter values (e.g. "Caption: @{step://caption/描述/0}"). Supports both
    # result:// (cache/history) and step:// (step_results, passed by run_templates).
    if step_results is not None or any(isinstance(v, str) and "@{" in v for v in params.values()):
        new_params = {}
        for k, v in params.items():
            try:
                new_params[k] = await _apply_inline_refs(v, step_results)
            except Exception as e:
                return {"error": f"Failed to resolve inline reference in '{k}': {e}"}
        params = new_params

    params, param_error = _validate_and_coerce_params(inputs, params)
    if param_error:
        return {"error": param_error, "template": name}

    # Generate API prompt
    api_prompt_data = template.get("api_prompt")
    if not api_prompt_data:
        return {"error": "Template missing api_prompt. Please refresh the template in the frontend."}
    api_prompt = _inject_widget_values(api_prompt_data, inputs, params)

    # Build a UI-workflow copy with the same values injected when metadata
    # embedding is enabled, so output images can carry a workflow that reflects
    # this actual run. Best-effort: metadata must never block execution.
    ui_workflow = template.get("workflow") if config.get_embed_workflow_metadata() else None
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

    token_reservation = None
    if token_required:
        token_reservation, token_error = template_token_store.reserve(
            template_token,
            name,
            schema_revision,
            max_uses=token_max_uses,
            ttl_seconds=token_ttl_seconds,
        )
        if token_error:
            return token_error
    try:
        result = await client.queue_prompt(api_prompt, workflow=ui_workflow)
    except httpx.HTTPStatusError as e:
        template_token_store.release(template_token, token_reservation)
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        logger.error(f"[Template] ComfyUI rejected prompt ({e.response.status_code}): {error_body}")
        return {"error": f"ComfyUI error ({e.response.status_code})", "details": error_body}
    except Exception:
        template_token_store.release(template_token, token_reservation)
        raise

    prompt_id = result.get("prompt_id")
    if not prompt_id:
        template_token_store.release(template_token, token_reservation)
        logger.error(f"[Template] Failed to queue prompt: {result}")
        return {"error": "Failed to queue prompt", "details": result}

    token_result = {}
    if token_required and template_token and token_reservation:
        token_result = template_token_store.commit(template_token, token_reservation)

    logger.info(f"[Template] Prompt queued: {prompt_id}")

    if not wait:
        return {
            "prompt_id": prompt_id,
            "status": "queued",
            "template": name,
            "params": params,
            **token_result,
        }

    # Poll for completion
    result = await _wait_for_result(
        prompt_id,
        outputs,
        timeout,
        template_name=name,
    )
    result.update(token_result)
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
