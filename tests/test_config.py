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


if __name__ == "__main__":
    unittest.main()
