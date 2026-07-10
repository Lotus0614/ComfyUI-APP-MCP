# Repository Guidelines

## Project Structure & Module Organization

This ComfyUI custom node exposes App Mode workflows through MCP. Python modules live at the repository root: `__init__.py` registers the plugin, `server.py` defines MCP tools, `routes.py` provides frontend and proxy routes, and `template_manager.py` handles template storage and execution. HTTP logic is in `comfyui_client.py`; standalone startup and configuration are in `standalone.py` and `config.py`.

Browser code is under `js/`, split into `core/` utilities and `ui/` components. Example configuration lives in `standalone_example/`; workflow samples belong in `example_workflow/`. Generated `templates/` data is ignored by Git. Test scenarios are documented in `TEST_PLAN.md`.

## Build, Test, and Development Commands

- `python -m pip install -r requirements.txt` installs runtime dependencies.
- `python standalone.py --config standalone_example/mcp.config.json` starts the MCP service outside ComfyUI; ensure the configured ComfyUI URL is reachable.
- `python -m compileall .` performs a quick Python syntax check before submission.
- For plugin development, place or symlink this repository under `ComfyUI/custom_nodes/`, then start ComfyUI. Use `python main.py --listen` for LAN testing.

There is no separate build step for the JavaScript frontend; ComfyUI loads files from `js/` directly.

## Coding Style & Naming Conventions

Use four-space indentation and PEP 8 for Python. Prefer `snake_case` for functions and modules, `PascalCase` for classes, type hints for public interfaces, and concise docstrings. Group imports as standard library, third-party, then local modules.

JavaScript uses ES modules, four-space indentation, single quotes, trailing commas, and `camelCase` identifiers. Keep reusable logic in `js/core/` and DOM-focused code in `js/ui/`. No formatter or linter is currently configured, so match nearby code closely.

## Testing Guidelines

The project relies on manual integration testing. Follow `TEST_PLAN.md`, especially template discovery, synchronous and asynchronous execution, bindings, pipelines, uploads, and error cases. Test against a running ComfyUI instance with representative templates. Record the ComfyUI version, configuration, and results when reporting failures.

## Commit & Pull Request Guidelines

Recent history uses short Conventional Commit-style subjects, primarily `feat: ...`; use `fix:`, `docs:`, or `refactor:` when appropriate. Keep each commit focused. Pull requests should explain behavior changes, list manual verification steps, link related issues, and include screenshots for settings-panel changes. Update both `README.md` and `README_EN.md` when user-facing instructions change.

## Security & Configuration Tips

Do not commit credentials, local `mcp_enabled.json`, or generated `templates/`. Prefer environment variables such as `COMFYUI_URL` and `MCP_CONFIG`, and avoid exposing ComfyUI or MCP ports publicly without an appropriate reverse proxy and access controls.
