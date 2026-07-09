# ComfyUI MCP Server

[中文](./README.md) | [English](./README_EN.md)

A ComfyUI plugin that wraps ComfyUI apps as MCP-callable templates, so AI assistants can use ComfyUI as a multimedia capability service that is queryable, executable, and chainable. If you find bugs or have feature requests, join the QQ group: 1082160486, or open an issue.

Key capabilities:

- Mark inputs and outputs through ComfyUI App Mode, so the AI only needs to pass input/output parameters and does not need to understand the ComfyUI node graph.
- Template documentation with progressive disclosure through on-demand doc reads
- Multi-template chaining, passing outputs from one step into later steps
- Model directory lookup for folders such as `checkpoints` and `loras`

## Quick Start

1. Install this project as a ComfyUI plugin by placing it under the `custom_nodes` directory.
2. Open a workflow in ComfyUI and click **Enter App Builder** from the top-left menu.
3. Mark content that you want the AI to modify, such as prompt text boxes, as inputs. Mark Save Image nodes as outputs, and rename input nodes to AI-friendly parameter names.
4. Add Markdown Note nodes to describe the template. The AI reads these node contents when it reads the template:
   - Title `title`: short title shown when listing templates
   - Title `description`: template description shown when fetching template details
   - Other titles: on-demand template docs. Mention the title in `description` so the AI knows to read it
5. In the ComfyUI frontend, go to **Settings → MCP Server → Templates** and click **Create from Workflow** to create a template from the configured workflow.
6. Connect your MCP client to `http://127.0.0.1:8188/app-mcp` (or `http://127.0.0.1:8189/mcp`).
7. Call `list_templates()` first to verify visibility, then use `get_template()`, `run_template()`, or `run_templates()`.
8. If the workflow changes, click **Refresh** in the settings panel. If parameters changed, ask the AI to read the template again.
   > Templates depend on ComfyUI App Mode. Use a ComfyUI version that supports App Mode.

## Dependencies

This plugin depends on the following Python packages:

| Package   | Version     | Purpose                                    |
| --------- | ----------- | ------------------------------------------ |
| `fastmcp` | >= 1.0.0    | MCP protocol framework                     |
| `uvicorn` | >= 0.30.0   | ASGI server                                |
| `httpx`   | >= 0.27.0   | HTTP client for communicating with ComfyUI |

### Installation

### Environment Variables

| Variable             | Default                 | Description                                                                 |
| -------------------- | ----------------------- | --------------------------------------------------------------------------- |
| `COMFYUI_URL`        | `http://127.0.0.1:8188` | ComfyUI server URL                                                          |
| `COMFYUI_PUBLIC_URL` | Same as `COMFYUI_URL`   | Optional advanced setting; used for media links when the media proxy is off |
| `MCP_CONFIG`         | Empty                   | JSON config file path for standalone mode                                   |
| `MCP_TEMPLATE_DIR`   | `./templates`           | Template JSON directory                                                     |
| `MCP_HOST`           | `0.0.0.0`               | MCP server bind host                                                        |
| `MCP_PORT`           | `8189`                  | MCP server port                                                             |
| `MCP_MEDIA_PROXY`    | `true`                  | Whether media links use the MCP `/view` proxy when accessing the MCP port directly |

### Standalone Configuration

The plugin can also run as a standalone MCP service without being loaded through ComfyUI's plugin flow. In this mode, ComfyUI and MCP can be deployed on different machines, but executing templates still requires the MCP service to access the ComfyUI HTTP API.

Create `mcp.config.json`:

```json
{
  "comfyui": {
    "apiUrl": "http://192.168.1.20:8188",
    "headers": {}
  },
  "mcp": {
    "host": "0.0.0.0",
    "port": 8189,
    "mediaProxy": true
  },
  "templates": {
    "dir": "./templates"
  }
}
```

- `comfyui.apiUrl`: the address MCP uses to access the ComfyUI API. Do not use `127.0.0.1` if MCP and ComfyUI are not on the same machine.
- `mcp.mediaProxy`: when connecting directly to the standalone MCP port, media links in results point to MCP `/view`, and MCP forwards them to ComfyUI `/view`. This means clients do not need to expose or access the ComfyUI port.
- `templates.dir`: local template JSON directory on the MCP machine. Standalone mode does not read the template directory on the ComfyUI machine.

The recommended default is `mcp.mediaProxy=true`; usually `comfyui.publicUrl` is not needed. Add it only when the media proxy is disabled, or when you want media links to return a custom public or reverse-proxy ComfyUI address:

```json
{
  "comfyui": {
    "publicUrl": "https://comfy.example.com"
  }
}
```

Start the standalone MCP service:

```bash
python standalone.py --config ./mcp.config.json
```

MCP client URL:

```text
http://<mcp-machine-address>:8189/mcp
```

### Startup

Start ComfyUI normally. The plugin will be loaded automatically and expose MCP through the ComfyUI port:

```text
MCP endpoint: http://127.0.0.1:8188/app-mcp
```

In plugin mode, there are two MCP connection options:

- **Connect through the ComfyUI port**: `http://<comfyui-address>:8188/app-mcp`
  - Suitable when the ComfyUI port is already exposed
  - MCP requests are proxied by ComfyUI to the internal MCP service
- **Connect directly through the MCP port**: `http://<mcp-address>:8189/mcp`
  - Suitable when you do not want MCP clients to access the ComfyUI port
  - Media links in generated results point to MCP `/view`, then MCP forwards them to ComfyUI

For remote access, start ComfyUI with `--listen`:

```bash
python main.py --listen
```

## Tool List

AI assistants can use the following MCP tools:

#### `list_templates`

Lists all available templates and returns template name, title, and input/output counts. Disabled templates are excluded.

#### `get_template(name)`

Returns template details including:

- `title`: template title, extracted from the workflow `title` Markdown node
- `description`: detailed description, extracted from the workflow `description` Markdown node
- `inputs`: configurable input parameters, including name, type, and default value. Inputs named `seed` are automatically randomized at runtime and are not returned to AI clients by MCP `get_template`.
- `outputs`: output node definitions
- `docs`: doc title list readable through `read_template_doc(name, title)`

Disabled templates cannot be queried.

#### `read_template_doc(name, title)`

Reads a template documentation section by title for progressive disclosure of more detailed guidance, examples, or notes.

- `name`: template name
- `title`: doc title such as `usage`, `examples`, or `tips`

Disabled templates cannot expose template docs.

#### `run_template(name, params, wait=true, bindings="{}")`

Executes a template with parameter values.

- `name`: template name
- `params`: JSON string of parameter values, for example `'{"positive_prompt": "a cat"}'`. If the template contains an input named `seed`, the runtime injects a random seed automatically.
- `wait`: whether to wait for completion, defaults to `true`
- `bindings`: optional JSON string used to pull values from a previous result and inject them into current parameters

When `wait=true`, the default wait timeout is controlled by **Settings → MCP Server → Execution → Run Template Timeout** in the ComfyUI frontend. The default is `120` seconds.

Disabled templates cannot be run.

##### Output Format

On success, returns a clean structured result:

```json
{
  "status": "completed",
  "prompt_id": "abc-123",
  "outputs": {
    "final_prompt_119_STRING": {
      "text": ["a cute cat, masterpiece, best quality..."]
    },
    "output_image_122_output": {
      "media": [
        {
          "url": "http://127.0.0.1:8188/view?filename=output.png&subfolder=prompt_gallery&type=output",
          "type": "image",
          "filename": "output.png",
          "subfolder": "prompt_gallery",
          "item_type": "output"
        }
      ],
      "markdown": "![output_image_122_output](http://127.0.0.1:8188/view?filename=output.png&subfolder=prompt_gallery&type=output)"
    }
  },
  "binding_hint": {
    "output_image_122_output": {
      "from": "abc-123",
      "output": "output_image_122_output",
      "type": "image",
      "index": 0
    }
  }
}
```

If waiting times out, the result looks like:

```json
{
  "status": "timeout",
  "prompt_id": "abc-123",
  "template": "anima mcp.app",
  "outputs": {},
  "error": "Timed out after 120s",
  "continue_hint": "Use get_template_result(name, prompt_id, wait=true) to continue waiting for the same prompt."
}
```

- `outputs`: simplified output containing only `media` (media items), `text` (text content), and `markdown` (ready-to-render Markdown)
- `binding_hint`: auto-generated binding config that can be copied directly into the next call's `bindings` parameter

##### Using Bindings to Chain Templates (Recommended)

**Important: When processing template-generated images, you MUST use bindings. Do NOT upload manually!**

Each `run_template` result includes a `binding_hint` field. To chain templates, copy the value from `binding_hint` directly into the next call's `bindings` parameter:

```python
# Step 1: Generate image
result1 = run_template("anima mcp.app", '{"prompt": "a cute cat"}')
# result1.binding_hint = {"output_image": {"from": "abc-123", ...}}

# Step 2: Encrypt (use binding_hint directly)
result2 = run_template("encrypt.app", '{}', bindings='{"image": {"from": "abc-123", "output": "output_image_122_output", "type": "image", "index": 0}}')
```

`upload_image` is only for new images provided by the user (not generated by templates).

#### `run_templates(pipeline, timeout_per_step=300)`

Runs multiple templates sequentially and binds outputs from earlier steps into later step inputs.

- `pipeline`: JSON string such as:

```json
{
  "steps": [
    {
      "id": "generate",
      "template": "txt2img",
      "params": {
        "prompt": "a cat"
      }
    },
    {
      "id": "upscale",
      "template": "upscale",
      "params": {
        "scale": 2
      },
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
```

- `timeout_per_step`: timeout in seconds for each step, default `300`
- Supported binding `type` values:
  - `text`: read `text[index]` from the upstream output
  - `image`: re-upload upstream image media into ComfyUI input storage, then pass the returned filename
  - `media_filename`: pass the upstream media filename directly
  - `media_url`: pass the upstream media URL directly

Here, `from` refers to a pipeline step `id`; in `run_template(..., bindings=...)`, `from` refers to a historical `prompt_id`.

On failure, the tool returns the failed step and all completed step results. On success, it returns the full step list, the final step outputs, and `binding_hint` (where `from` is the step `id`).

#### `upload_image(source, overwrite=true)`

Uploads an image to ComfyUI for use as an image input.

**Note: Only for new images provided by the user!** When processing template-generated images, use `binding_hint` instead of manual upload.

Supported sources:

- **Local path**: `E:/photos/input.png`
- **HTTP URL**: `https://example.com/image.png`
- **Base64**: `data:image/png;base64,iVBOR...`

The upload returns a filename that can be used as a template parameter.

#### `list_models(folder="", keywords="")`

Lists ComfyUI model folders or models inside a specific folder.

- Without `folder`: returns available model directories
- With `folder`: returns models in that directory, such as `checkpoints`, `loras`, `vae`, or `controlnet`
- `keywords`: optional search keywords, case-insensitive, multiple keywords separated by spaces act as AND conditions, e.g. `keywords="sdxl"` or `keywords="detail anime"`

#### `get_template_result(name, prompt_id, wait=false, timeout=300)`

Fetches execution results.

- `wait=false`: return the current status immediately (`pending`, `running`, `completed`) for manual polling
- `wait=true`: block until completion or timeout. If the `prompt_id` does not exist (not in queue or history), returns an error within a few seconds instead of waiting until timeout
- `timeout`: wait timeout in seconds, default `300`

## ComfyUI Frontend Management

In **Settings → MCP Server**:

- **Status**: view MCP server status and connection address
- **Execution → Run Template Timeout**: set the default wait timeout for `run_template(wait=true)`, default `120` seconds; after timeout, call `get_template_result(name, prompt_id, wait=true)` to continue waiting
- **Templates**: view, refresh, disable or enable, and delete templates
- **Auto Extract Templates**: scan all workflows and auto-create templates for those with a `title` Markdown node that don't have a template yet
- **Batch Refresh Templates**: refresh all templates from their source workflows, re-extracting inputs, outputs, title, and description
- **Export Templates**: export the current template JSON files and download `mcp-templates.zip`

The exported archive only contains templates:

```text
mcp-templates.zip
└── templates/
    ├── txt2img.json
    └── upscale.json
```

For standalone deployment, extract `templates/` onto the MCP machine and point `templates.dir` in `mcp.config.json` to that directory.

## MCP Client Setup

In plugin mode, you can choose either connection URL:

- `http://<comfyui-address>:8188/app-mcp`: access MCP through the ComfyUI port
- `http://<mcp-address>:8189/mcp`: access the MCP port directly

If you do not want to expose the ComfyUI port, clients can connect only to `8189/mcp`. In this case, media links such as images, audio, and GIFs return as `http://<mcp-address>:8189/view?...`, and MCP proxies them to ComfyUI `/view`.

### Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

### Cursor

Add this to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

### Other MCP Clients

Connection URL: `http://<comfyui-address>/app-mcp` (Streamable HTTP transport)

### Remote Access

Start ComfyUI with `--listen 0.0.0.0` to accept LAN connections. Then phones or other devices can connect directly, and image links will automatically use the correct address:

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://192.168.0.113:8188/app-mcp"
    }
  }
}
```

> You do not need to configure `comfyui_url` manually. The server derives it from the request automatically.

## Logs

All MCP calls are printed in the ComfyUI console with the `[MCP]` prefix:

```text
[MCP] list_templates() → 3 templates
[MCP] run_template(name='txt2img', params={"positive_prompt": "a cat"}) → completed
[MCP] upload_image(source=E:/photos/input.png) → {"name": "input.png", "subfolder": "", "type": "input"}
```

Proxy requests are printed with the `[MCP Proxy]` prefix:

```text
[MCP Proxy] POST /app-mcp → http://127.0.0.1:8189/mcp
[MCP Proxy] upstream error: ...  (failed to connect to the internal MCP server)
```

## FAQ

### Template list is empty

Make sure the workflow was saved to the server through ComfyUI **Save**, not **Export**.

### Outputs are empty

Make sure `linearData.outputs` in the workflow includes the node IDs you want to return.

### How to use random seed

In the app builder, name the seed input that should refresh automatically as `seed`. At runtime, the template injects a random seed automatically. `get_template` does not return this parameter to AI clients, and AI clients do not need to pass `seed` to `run_template`.

### Parameter mapping errors

If ComfyUI reports `value_not_in_list`, widget value mapping is likely misaligned. Restart ComfyUI so the plugin reloads, or click **Refresh** on the template in the settings panel.

### Remote access returns 421

Make sure ComfyUI was started with `--listen`. The plugin already disables MCP DNS rebinding protection, so LAN IP access should work directly.

### Image input does not work

If it's a new image provided by the user, call `upload_image` first and use the returned filename as the template parameter.

If it's a template-generated image, use `binding_hint` for chaining instead of manual upload.

### Binding fails

If binding returns an error, check:
1. `from` is a valid `prompt_id` (`run_template`) or step `id` (`run_templates`)
2. `output` exists in the source result's `outputs`
3. `index` is within range

## File Layout

```text
mcp-server/
├── __init__.py          # ComfyUI plugin entrypoint
├── server.py            # MCP tool definitions
├── standalone.py        # Standalone MCP HTTP service entrypoint
├── config.py            # JSON config and environment variable loading
├── template_manager.py  # Template CRUD, workflow conversion, execution engine
├── comfyui_client.py    # ComfyUI HTTP client
├── routes.py            # Frontend API routes and MCP proxy
├── js/
│   └── index.js         # Frontend settings panel UI
├── templates/           # Template JSON storage
├── TEST_PLAN.md         # Test plan document
├── README.md            # Chinese README
└── README_EN.md         # English README
```
