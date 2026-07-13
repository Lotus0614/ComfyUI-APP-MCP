# Standalone and Remote Access

[← Back to README](../../README_EN.md) | [Docs Index](../README.md) | [Tool Reference](./tools.md) | [Troubleshooting](./troubleshooting.md)

By default, the plugin starts with ComfyUI and exposes two MCP entries: the ComfyUI proxy entry and the direct MCP entry. They work the same way, so use either one.

## Connection Entries

| Entry | MCP URL | Notes |
| --- | --- | --- |
| ComfyUI proxy entry | `http://127.0.0.1:8188/app-mcp` | Access MCP through the ComfyUI port |
| Direct MCP entry | `http://127.0.0.1:8189/mcp` | Starts with ComfyUI and bypasses the ComfyUI proxy path |

For remote ComfyUI access, start it with:

```bash
python main.py --listen
```

For LAN access, replace `127.0.0.1` with the host running ComfyUI.

Use the standalone configuration below only when MCP and ComfyUI need to run as separate deployments.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI API URL used by MCP |
| `COMFYUI_PUBLIC_URL` | Same as `COMFYUI_URL` | Public media URL when media proxy is disabled |
| `MCP_CONFIG` | Empty | JSON config path for standalone mode |
| `MCP_TEMPLATE_DIR` | `./templates` | Template JSON directory |
| `MCP_HOST` | `0.0.0.0` | MCP listen host |
| `MCP_PORT` | `8189` | MCP listen port |
| `MCP_MEDIA_PROXY` | `true` | Whether media links go through MCP `/view` proxy |

## Standalone Config

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

Fields:

- `comfyui.apiUrl`: URL used by MCP to access the ComfyUI API. Do not use `127.0.0.1` when MCP and ComfyUI run on different machines.
- `mcp.mediaProxy`: when `true`, media URLs point to MCP `/view`, which forwards to ComfyUI `/view`.
- `templates.dir`: local template directory on the MCP machine. Standalone mode does not read templates from the ComfyUI machine.

Usually keep `mcp.mediaProxy=true`. Configure `publicUrl` only when disabling media proxy or when media URLs should point to a custom public ComfyUI proxy:

```json
{
  "comfyui": {
    "publicUrl": "https://comfy.example.com"
  }
}
```

## Start Standalone MCP

```bash
python standalone.py --config ./mcp.config.json
```

Client URL:

```text
http://<mcp-host>:8189/mcp
```

## MCP Client Setup

Most MCP clients can use this JSON:

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

To connect directly to the MCP port, set `url` to:

```text
http://127.0.0.1:8189/mcp
```

### Claude Desktop

Add the JSON above to `claude_desktop_config.json`.

### Cursor

Add the JSON above to `.cursor/mcp.json`.

### LAN Example

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://192.168.0.113:8188/app-mcp"
    }
  }
}
```

## Template Migration

In the ComfyUI frontend, use **Settings → MCP Server → Templates → Export Templates** to export `mcp-templates.zip`.

For standalone deployment, extract `templates/` on the MCP machine and point `templates.dir` in `mcp.config.json` to that directory.
