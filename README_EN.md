# ComfyUI MCP Server

[中文](./README.md) | [English](./README_EN.md)

A ComfyUI plugin that wraps ComfyUI workflows as MCP-callable templates, so AI assistants can use ComfyUI as a multimedia capability service that is queryable, executable, and chainable.

Key capabilities:

- Template-based inputs and outputs, so the AI does not need to understand the ComfyUI node graph
- Template documentation with progressive disclosure through on-demand doc reads
- Multi-template chaining, passing outputs from one step into later steps
- Model directory lookup for folders such as `checkpoints` and `loras`

## Core Concepts

A template is a ComfyUI app plus auto-extracted input and output definitions.

- **Inputs**: extracted from nodes marked in `linearData.inputs`
- **Outputs**: extracted from nodes marked in `linearData.outputs`
- The AI only needs to provide parameters and consume results; it does not need to understand the internal ComfyUI graph

Template documentation conventions:

- `title`: short template title shown in template lists
- `description`: summary shown in template details
- Other Markdown nodes: on-demand template docs retrievable with `read_template_doc(name, title)`

This keeps templates concise by default while still allowing more detailed instructions, examples, prompt guidance, or notes when needed.

## Quick Start

1. Build your workflow as an App in ComfyUI, mark input and output nodes, and rename input nodes to AI-friendly parameter names.
2. Add Markdown nodes for template docs:
   - Title `title`: short title
   - Title `description`: template summary
   - Other titles: on-demand template docs
3. In the ComfyUI frontend, go to **Settings → MCP Server → Templates** and click **Create from Workflow**.
4. Connect your MCP client to `http://127.0.0.1:8188/app-mcp`.
5. Call `list_templates()` first to verify visibility, then use `get_template()`, `run_template()`, or `run_templates()`.

> Templates depend on ComfyUI App Mode. Use a ComfyUI version that supports App Mode.

## Dependencies

This plugin depends on the following Python packages:

| Package   | Version     | Purpose                                    |
| --------- | ----------- | ------------------------------------------ |
| `fastmcp` | >= 1.0.0    | MCP protocol framework                     |
| `uvicorn` | >= 0.30.0   | ASGI server                                |
| `httpx`   | >= 0.27.0   | HTTP client for communicating with ComfyUI |

### Installation

#### Option 1: Use `requirements.txt` (recommended)

```bash
cd ComfyUI/custom_nodes/mcp-server
pip install -r requirements.txt
```

#### Option 2: Install manually

```bash
pip install fastmcp>=1.0.0 uvicorn>=0.30.0 httpx>=0.27.0
```

#### Option 3: Use ComfyUI Manager

If you use [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager), it will prompt you to install missing dependencies after installing this plugin.

> **Note**: For the Windows Portable build of ComfyUI, use its bundled Python:
>
> ```bash
> ..\..\..\python_embeded\python.exe -m pip install -r requirements.txt
> ```

## Configuration

### Environment Variables

| Variable      | Default                 | Description        |
| ------------- | ----------------------- | ------------------ |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI server URL |

### Startup

Start ComfyUI normally. The plugin will be loaded automatically and expose MCP on the same ComfyUI port:

```text
MCP endpoint: http://127.0.0.1:8188/app-mcp
```

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
- `inputs`: configurable input parameters, including name, type, and default value
- `outputs`: output node definitions

Disabled templates cannot be queried.

#### `read_template_doc(name, title)`

Reads a template documentation section by title for progressive disclosure of more detailed guidance, examples, or notes.

- `name`: template name
- `title`: doc title such as `usage`, `examples`, or `tips`

Disabled templates cannot expose template docs.

#### `run_template(name, params, wait=true, bindings="{}")`

Executes a template with parameter values.

- `name`: template name
- `params`: JSON string of parameter values, for example `'{"positive_prompt": "a cat", "seed": 42}'`
- `wait`: whether to wait for completion, defaults to `true`
- `bindings`: optional JSON string used to pull values from a previous result and inject them into current parameters

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

#### `list_models(folder="")`

Lists ComfyUI model folders or models inside a specific folder.

- Without `folder`: returns available model directories
- With `folder`: returns models in that directory, such as `checkpoints`, `loras`, `vae`, or `controlnet`

#### `get_template_result(name, prompt_id, wait=false, timeout=300)`

Fetches execution results.

- `wait=false`: return the current status immediately (`pending`, `running`, `completed`) for manual polling
- `wait=true`: block until completion or timeout. If the `prompt_id` does not exist (not in queue or history), returns an error within a few seconds instead of waiting until timeout
- `timeout`: wait timeout in seconds, default `300`

## ComfyUI Frontend Management

In **Settings → MCP Server**:

- **Status**: view MCP server status and connection address
- **Templates**: view, refresh, disable or enable, and delete templates
- **Auto Extract Templates**: scan all workflows and auto-create templates for those with a `title` Markdown node that don't have a template yet
- **Batch Refresh Templates**: refresh all templates from their source workflows, re-extracting inputs, outputs, title, and description

## MCP Client Setup

The MCP endpoint reuses the ComfyUI port:

```text
http://<comfyui-address>/app-mcp
```

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

Connection URL:

```text
http://<comfyui-address>/app-mcp
```

### Remote Access

Start ComfyUI with `--listen 0.0.0.0` to accept LAN connections. Image links will automatically use the correct address:

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
