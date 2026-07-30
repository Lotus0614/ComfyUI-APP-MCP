import unittest

from mcp import Client
from mcp.server import MCPServer

from server import create_mcp_http_app, create_mcp_server


class MCPServerSDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_supports_modern_and_legacy_clients(self) -> None:
        server = create_mcp_server(object())

        self.assertIsInstance(server, MCPServer)

        async with Client(server) as client:
            modern_tools = await client.list_tools()

        async with Client(server, mode="legacy") as client:
            legacy_tools = await client.list_tools()

        modern_names = [tool.name for tool in modern_tools.tools]
        legacy_names = [tool.name for tool in legacy_tools.tools]
        self.assertEqual(modern_names, legacy_names)
        self.assertIn("list_templates", modern_names)
        self.assertIn("run_template", modern_names)

    async def test_streamable_http_app_runs_its_lifespan(self) -> None:
        app = create_mcp_http_app(object())

        self.assertTrue(any(getattr(route, "path", None) == "/mcp" for route in app.routes))
        async with app.router.lifespan_context(app):
            pass


if __name__ == "__main__":
    unittest.main()
