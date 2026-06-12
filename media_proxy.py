"""ASGI middleware for MCP public URLs and ComfyUI media proxying."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
from starlette.types import ASGIApp, Receive, Scope, Send

try:
    from . import config, template_manager
except ImportError:
    import config
    import template_manager

_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})


def _headers(scope: Scope) -> dict[bytes, bytes]:
    return {k.lower(): v for k, v in scope.get("headers", [])}


def _request_base_url(scope: Scope) -> str:
    headers = _headers(scope)
    scheme = headers.get(b"x-forwarded-proto", scope.get("scheme", "http").encode()).decode()
    host = headers.get(b"x-forwarded-host") or headers.get(b"host")
    if host:
        return f"{scheme}://{host.decode()}".rstrip("/")
    server = scope.get("server")
    if server:
        name, port = server
        default_port = 443 if scheme == "https" else 80
        return f"{scheme}://{name}" if port == default_port else f"{scheme}://{name}:{port}"
    return config.get_comfyui_public_url()


def _request_public_url(scope: Scope) -> str | None:
    query = parse_qs(scope.get("query_string", b"").decode())
    url = query.get("comfyui_url", [None])[0]
    if url:
        return url.rstrip("/")

    headers = _headers(scope)
    if b"comfyui_url" in headers:
        return headers[b"comfyui_url"].decode().rstrip("/")

    if config.use_mcp_media_proxy():
        return _request_base_url(scope)

    return config.get_comfyui_public_url()


class PublicURLMiddleware:
    """Set the base URL used for media links returned by template execution."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            url = _request_public_url(scope)
            if url:
                template_manager._comfyui_public_url.set(url)
        await self.app(scope, receive, send)


class MediaProxyMiddleware:
    """Proxy /view requests on the MCP server to ComfyUI /view."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope.get("path") != "/view":
            await self.app(scope, receive, send)
            return

        query = scope.get("query_string", b"").decode()
        target = f"{config.get_comfyui_api_url()}/view"
        if query:
            target += f"?{query}"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                upstream = await client.get(
                    target,
                    headers=config.get_comfyui_headers(),
                    timeout=60,
                )
        except Exception as e:
            body = f"MCP media proxy error: {e}".encode()
            await send({
                "type": "http.response.start",
                "status": 502,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            })
            await send({"type": "http.response.body", "body": body})
            return

        headers = []
        for key, value in upstream.headers.items():
            if key.lower() not in _HOP_BY_HOP:
                headers.append((key.lower().encode(), value.encode()))

        await send({
            "type": "http.response.start",
            "status": upstream.status_code,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": upstream.content})
