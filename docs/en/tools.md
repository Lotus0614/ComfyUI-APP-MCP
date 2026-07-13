# Tool Reference

[← Back to README](../../README_EN.md) | [Docs Index](../README.md) | [Standalone](./standalone.md) | [Troubleshooting](./troubleshooting.md)

This page describes MCP tool parameters, return formats, and recommended usage.

## Recommended Flow

1. Call `list_templates()` to discover available templates.
2. Call `get_template(name)` to read inputs, outputs, and doc entries.
3. If `description` points to extra docs, call `read_template_doc(name, title)`.
4. Call `run_template()` for a single template, or `run_templates()` for a pipeline.
5. If a run times out, continue with `get_template_result()`.

## Tool Summary

| Tool | Purpose |
| --- | --- |
| `list_templates()` | List available templates with names and titles only |
| `get_template(name)` | Read template inputs, outputs, description, and doc titles |
| `read_template_doc(name, title)` | Read a specific template doc section |
| `run_template(name, params, wait, bindings)` | Run one template |
| `run_templates(pipeline, timeout_per_step)` | Run multiple templates sequentially |
| `upload_image(source)` | Upload a new image provided by the user |
| `list_models(folder, keywords)` | Browse model folders or files |
| `get_template_result(name, run_id, wait, timeout)` | Poll or continue waiting for a result |

## `list_templates()`

Lists all enabled templates.

The response stays lightweight and only includes information needed for choosing a template:

```json
[
  {
    "name": "txt2img.app",
    "title": "Text to Image"
  }
]
```

## `get_template(name)`

Reads template details before execution.

Returned fields:

- `name`: template name
- `title`: title from the workflow `title` Markdown Note
- `description`: description from the `description` Markdown Note
- `inputs`: public parameters with type, default value, and constraints
- `outputs`: stable output names and types without ComfyUI node IDs
- `docs`: doc titles readable through `read_template_doc()`

Notes:

- Internal execution fields such as `node_id`, `api_key`, and `widget` are hidden from AI clients.
- An input named `seed` is randomized at runtime and does not need to be passed by the AI.
- Disabled templates cannot be queried.

## `read_template_doc(name, title)`

Reads a specific template doc section.

Parameters:

- `name`: template name
- `title`: doc title, such as `usage`, `examples`, or `tips`

Use Markdown Notes for detailed prompt rules, examples, and caveats. Mention the doc title in `description` when the AI should read it on demand.

## `run_template(name, params, wait=true, bindings="{}")`

Runs one template.

Parameters:

- `name`: template name
- `params`: JSON string for template inputs, for example `'{"prompt": "a cat"}'`
- `wait`: whether to wait for completion, default `true`
- `bindings`: JSON string mapping input names to historical output refs

For `wait=true`, the default timeout is controlled by **Settings → MCP Server → Execution → Run Template Timeout** and defaults to `120` seconds.

### Completed Result

```json
{
  "status": "completed",
  "outputs": {
    "final_prompt": {
      "type": "text",
      "value": "a cute cat, masterpiece",
      "ref": "result://abc-123/final_prompt/0"
    },
    "output_image": {
      "type": "image",
      "url": "http://127.0.0.1:8188/view?filename=output.png&type=output",
      "ref": "result://abc-123/output_image/0",
      "markdown": "![output_image](http://127.0.0.1:8188/view?filename=output.png&type=output)"
    }
  }
}
```

Notes:

- Text outputs include `type`, `value`, and `ref`.
- Media outputs such as images, audio, and GIFs include `type`, `url`, `ref`, and `markdown`.
- `markdown` is returned only when a media resource should be displayed. Plain text outputs do not include it.
- `ref` is an opaque reference that can be passed directly into the next call's `bindings`.

### Timeout Result

```json
{
  "status": "timeout",
  "run_id": "abc-123",
  "template": "txt2img.app",
  "outputs": {},
  "error": "Timed out after 120s",
  "continue_hint": "Use get_template_result(name, run_id, wait=true) to continue waiting for the same prompt."
}
```

A timeout does not mean the generation failed. Continue waiting with `get_template_result(name, run_id, wait=true)`.

## Bindings

When processing template-generated images, use the output `ref`. Do not download and upload the image again.

Single-step chaining example:

```python
result1 = run_template("txt2img.app", '{"prompt": "a cute cat"}')

result2 = run_template(
    "upscale.app",
    '{}',
    bindings='{"image": "result://abc-123/output_image/0"}'
)
```

`upload_image()` is only for new images provided by the user, not template-generated images.

## `run_templates(pipeline, timeout_per_step=300)`

Runs multiple templates sequentially and binds outputs from previous steps to later inputs.

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
        "image": "step://generate/output_image/0"
      }
    }
  ]
}
```

Notes:

- `timeout_per_step` is the timeout for each step in seconds.
- `run_templates()` uses `step://<step-id>/<output-name>/<index>`.
- A normal `run_template()` result uses `result://`.

## `upload_image(source)`

Uploads a new user-provided image to ComfyUI.

Supported sources:

- Local path: `E:/photos/input.png`
- HTTP URL: `https://example.com/image.png`
- Base64: `data:image/png;base64,iVBOR...`

The upload preserves the original extension and generates a unique filename such as `mcp_4b2f...a91c.png`, so identical source names do not overwrite each other. The returned `name` can be used as a template parameter.

## `list_models(folder="", keywords="")`

Queries ComfyUI model folders or model files.

- Without `folder`: returns queryable model folders.
- With `folder`: returns files in that folder, such as `checkpoints`, `loras`, `vae`, or `controlnet`.
- `keywords`: optional case-insensitive AND search. Separate multiple keywords with spaces.

## `get_template_result(name, run_id, wait=false, timeout=300)`

Polls execution status or continues waiting for a result.

- `wait=false`: returns current status immediately.
- `wait=true`: blocks until completion or timeout.
- `timeout`: wait timeout in seconds.

## ComfyUI Frontend Management

In **Settings → MCP Server**:

- **Status**: view MCP server status and connection URLs
- **Execution → Run Template Timeout**: configure the default timeout for `run_template(wait=true)`
- **Templates**: view, refresh, enable, disable, and delete templates
- **Auto Extract Templates**: scan workflows and create templates for workflows with a `title` Markdown Note
- **Batch Refresh Templates**: re-extract inputs, outputs, title, and description from same-name workflows
- **Export Templates**: export current template JSON files as `mcp-templates.zip`

The exported archive contains only template files:

```text
mcp-templates.zip
└── templates/
    ├── txt2img.json
    └── upscale.json
```
