import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class ComfyUIURLConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        config.configure(Path(__file__).with_name("missing-mcp.config.json"))
        config.set_runtime_comfyui_api_url(None)

    def tearDown(self) -> None:
        config.configure(None)
        config.set_runtime_comfyui_api_url(None)

    def test_runtime_url_replaces_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config.set_runtime_comfyui_api_url("http://127.0.0.1:9000/")
            self.assertEqual(config.get_comfyui_api_url(), "http://127.0.0.1:9000")

    def test_environment_url_overrides_runtime_url(self) -> None:
        with patch.dict(
            os.environ,
            {"COMFYUI_URL": "http://remote-comfyui:9100/"},
            clear=True,
        ):
            config.set_runtime_comfyui_api_url("http://127.0.0.1:9000")
            self.assertEqual(config.get_comfyui_api_url(), "http://remote-comfyui:9100")

    def test_file_url_overrides_runtime_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.config.json"
            path.write_text(
                '{"comfyui":{"apiUrl":"http://configured-comfyui:9200/"}}',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config.configure(path)
                config.set_runtime_comfyui_api_url("http://127.0.0.1:9000")
                self.assertEqual(
                    config.get_comfyui_api_url(),
                    "http://configured-comfyui:9200",
                )


class TemplateTokenConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        config.configure(Path(__file__).with_name("missing-mcp.config.json"))
        config._runtime_template_token_enabled = None
        config._runtime_template_token_max_uses = None
        config._runtime_template_token_ttl_hours = None

    def tearDown(self) -> None:
        config.configure(None)
        config._runtime_template_token_enabled = None
        config._runtime_template_token_max_uses = None
        config._runtime_template_token_ttl_hours = None

    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(config.get_template_token_enabled())
            self.assertEqual(config.get_template_token_max_uses(), 50)
            self.assertEqual(config.get_template_token_ttl_hours(), 12.0)

    def test_environment_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MCP_TEMPLATE_TOKEN_ENABLED": "true",
                "MCP_TEMPLATE_TOKEN_MAX_USES": "25",
                "MCP_TEMPLATE_TOKEN_TTL_HOURS": "6.5",
            },
            clear=True,
        ):
            self.assertTrue(config.get_template_token_enabled())
            self.assertEqual(config.get_template_token_max_uses(), 25)
            self.assertEqual(config.get_template_token_ttl_hours(), 6.5)

    def test_invalid_limits_fall_back_to_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MCP_TEMPLATE_TOKEN_MAX_USES": "0",
                "MCP_TEMPLATE_TOKEN_TTL_HOURS": "invalid",
            },
            clear=True,
        ):
            self.assertEqual(config.get_template_token_max_uses(), 50)
            self.assertEqual(config.get_template_token_ttl_hours(), 12.0)

    def test_file_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.config.json"
            path.write_text(
                json.dumps(
                    {
                        "mcp": {
                            "templateTokenEnabled": True,
                            "templateTokenMaxUses": 10,
                            "templateTokenTtlHours": 2,
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config.configure(path)
                self.assertTrue(config.get_template_token_enabled())
                self.assertEqual(config.get_template_token_max_uses(), 10)
                self.assertEqual(config.get_template_token_ttl_hours(), 2.0)

    def test_runtime_values_override_other_sources(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MCP_TEMPLATE_TOKEN_ENABLED": "false",
                "MCP_TEMPLATE_TOKEN_MAX_USES": "25",
                "MCP_TEMPLATE_TOKEN_TTL_HOURS": "6",
            },
            clear=True,
        ):
            config.set_template_token_enabled(True)
            config.set_template_token_max_uses(5)
            config.set_template_token_ttl_hours(1.5)
            self.assertTrue(config.get_template_token_enabled())
            self.assertEqual(config.get_template_token_max_uses(), 5)
            self.assertEqual(config.get_template_token_ttl_hours(), 1.5)


if __name__ == "__main__":
    unittest.main()
