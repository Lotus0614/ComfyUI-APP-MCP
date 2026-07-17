# ComfyUI MCP Server

[中文](./README.md) | [English](./README_EN.md)

Wrap ComfyUI App Mode workflows as MCP tools, so AI assistants can discover templates, run workflows, chain multi-step generation, and handle media outputs without understanding the underlying node graph.

## What It Is For

- **Expose ComfyUI to AI assistants**: the AI fills template parameters instead of editing nodes.
- **Reuse App Mode workflows**: mark inputs and outputs in the ComfyUI frontend, then create MCP templates.
- **Batch and multi-step execution**: run multiple independent tasks in one call, or pass outputs into later processing steps.
- **Browse local models**: let the AI query `checkpoints`, `loras`, `vae`, and other model folders.

## Quick Start

1. Install the plugin under ComfyUI `custom_nodes` and install dependencies:

   ```bash
   cd ComfyUI/custom_nodes
   git clone <this-repo-url> ComfyUI-APP-MCP
   cd ComfyUI-APP-MCP
   python -m pip install -r requirements.txt
   ```

2. Start ComfyUI with a version that supports App Mode.
3. Open a workflow and enter **App Builder** from the top-left menu.
4. Mark AI-editable fields as inputs, mark result nodes as outputs, and give inputs clear parameter names.
5. Add Markdown Note nodes for template docs:
   - `title`: short title shown in the template list
   - `description`: detailed description shown in template details
   - Other headings: extra docs that can be read on demand
6. Go to **Settings → MCP Server → Templates** and click **Create from Workflow**.
7. Connect your MCP client to `http://127.0.0.1:8188/app-mcp` or `http://127.0.0.1:8189/mcp`.
8. Ask the AI to call `list_templates()` first, then `get_template()`, `run_template()`, or `run_templates()`.

After changing a workflow, click **Refresh** on the same-name template in the settings panel. If inputs changed, ask the AI to read the template again.

If a workflow should use a random seed on every run, name the corresponding App Builder input `seed`. Runtime fills it automatically, so the AI does not need to pass it.

## Connection URLs

| Entry | URL | Notes |
| --- | --- | --- |
| ComfyUI proxy entry | `http://127.0.0.1:8188/app-mcp` | Access MCP through the ComfyUI port |
| Direct MCP entry | `http://127.0.0.1:8189/mcp` | Starts with ComfyUI and works the same way |

MCP client config example:

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

You can also set `url` to:

```text
http://127.0.0.1:8189/mcp
```

For remote ComfyUI access, start ComfyUI with `python main.py --listen`.

For LAN or remote access, replace `127.0.0.1` with the actual ComfyUI/MCP host. See [Standalone and Remote Access](./docs/en/standalone.md) for deployment details.

## Common Tools

| Tool | Purpose | When To Use |
| --- | --- | --- |
| `list_templates()` | List available templates | First step before using the service |
| `get_template(name)` | Read parameters, outputs, and doc entries | Before running a template |
| `read_template_doc(name, title)` | Read extra template docs | When `description` points to more docs |
| `run_template()` | Run one template | Text-to-image, image-to-image, upscale, post-process, etc. |
| `run_templates()` | Run multiple tasks and return every step result | Batch generation or generate → upscale workflows |
| `upload_image(source)` | Upload a new user-provided image | When the image comes from local path, URL, or base64 |
| `list_models(folder, keywords)` | Browse model folders | When selecting checkpoints, LoRAs, VAEs, etc. |
| `get_template_result()` | Poll or continue waiting | When a run times out or is async |
| `interrupt_task(run_id)` | Interrupt a running or queued task | When an async or timed-out run is no longer needed |

See [Tool Reference](./docs/en/tools.md) for full parameters, return formats, and examples.

## Frontend Management

In **Settings → MCP Server**, you can:

- View MCP status and connection URLs
- Configure the default `run_template(wait=true)` timeout
- Create, refresh, enable, disable, and delete templates
- Scan workflows and create missing templates
- Batch refresh existing templates
- Export templates as a zip for standalone deployment

See [Tool Reference: Frontend Management](./docs/en/tools.md#comfyui-frontend-management) for details.

## Documentation

| Doc | Content |
| --- | --- |
| [Tool Reference](./docs/en/tools.md) | MCP tool parameters, return formats, template chaining, uploads, model lookup |
| [Standalone and Remote Access](./docs/en/standalone.md) | Environment variables, standalone config, media proxy, client setup |
| [Troubleshooting](./docs/en/troubleshooting.md) | Empty templates, empty outputs, image inputs, remote access, logs |
| [Development Notes](./docs/en/development.md) | Code layout, testing guidance, development commands |
| [Documentation Index](./docs/README.md) | Chinese and English doc entry points |

## Most Common Issues

### Template List Is Empty

Make sure the workflow was saved to the ComfyUI server through **Save**, not only exported locally through **Export**.

### Image Input Does Not Work

For a new image provided by the user, call `upload_image()` first and use the returned `name` as the template parameter. Template-generated images can be chained by the AI and do not need to be uploaded manually.

### Workflow Not Found When Creating a Template

Check whether ComfyUI is running on port `8188`. The plugin reads workflows through `COMFYUI_URL=http://127.0.0.1:8188` by default. If your ComfyUI port is not `8188`, set it before startup:

```bash
COMFYUI_URL=http://127.0.0.1:<your-port>
```

### Images Cannot Be Sent Through AstrBot or Similar Platforms

Check that the AI passes the correct argument type to the platform's send tool. A common mistake is passing an image URL into a local-file `path` argument. If the tool distinguishes `url`, `image_url`, `file`, and `path`, use the field required by that tool.

See [Troubleshooting](./docs/en/troubleshooting.md) for more checks.
