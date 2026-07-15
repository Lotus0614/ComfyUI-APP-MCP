# Development Notes

[← Back to README](../../README_EN.md) | [Docs Index](../README.md) | [Tool Reference](./tools.md) | [Troubleshooting](./troubleshooting.md)

## File Layout

```text
ComfyUI-APP-MCP/
├── __init__.py          # ComfyUI plugin entry, starts MCP service
├── server.py            # MCP tool definitions
├── standalone.py        # Standalone MCP HTTP entry
├── config.py            # JSON config and environment variables
├── template_manager.py  # Template CRUD, workflow conversion, execution engine
├── comfyui_client.py    # ComfyUI HTTP client
├── routes.py            # ComfyUI frontend API routes and MCP proxy
├── js/                  # ComfyUI frontend settings panel
├── docs/                # Detailed documentation
├── templates/           # Template JSON storage, ignored by Git
└── TEST_PLAN.md         # Manual test plan
```

## Common Commands

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start standalone:

```bash
python standalone.py --config standalone_example/mcp.config.json
```

Python syntax check:

```bash
python -m compileall .
```

## Frontend Development

Frontend code lives under `js/`:

- `js/core/`: reusable logic such as API helpers, settings, i18n, and workflow conversion
- `js/ui/`: settings panel, dialogs, template management UI
- `js/index.js`: ComfyUI extension registration entry

ComfyUI loads files from `js/` directly. There is no separate build step.

## Testing Guidance

The project mainly relies on manual integration testing. Focus on:

- Template create, refresh, disable, and delete
- `list_templates()`, `get_template()`, `run_template()`
- `run_templates()` multi-task execution and step bindings
- `upload_image()` local path, URL, and base64
- `get_template_result()` after timeouts
- Standalone MCP service and media proxy

See `TEST_PLAN.md` for the full scenario list.

## Contribution Notes

- Update both `README.md` and `README_EN.md` for user-facing behavior changes.
- Include screenshots for settings-panel UI changes when possible.
- Do not commit credentials, local `mcp_enabled.json`, or generated `templates/`.
