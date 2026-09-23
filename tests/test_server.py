import unittest

from server import _UPLOAD_IMAGE_TIP, _filter_models, _format_upload_result


class ModelFilterTests(unittest.TestCase):
    MODELS = ["foo_bar.safetensors", "foo_baz.safetensors", "bar.safetensors", "other.safetensors"]

    def test_spaces_and_ampersand_are_and(self) -> None:
        self.assertEqual(
            _filter_models(self.MODELS, "foo&bar"),
            ["foo_bar.safetensors"],
        )
        self.assertEqual(
            _filter_models(self.MODELS, "foo bar"),
            ["foo_bar.safetensors"],
        )

    def test_pipe_is_or_and_and_has_precedence(self) -> None:
        self.assertEqual(
            _filter_models(self.MODELS, "foo&bar|other"),
            ["foo_bar.safetensors", "other.safetensors"],
        )

    def test_filter_is_case_insensitive(self) -> None:
        self.assertEqual(_filter_models(self.MODELS, "FOO"), self.MODELS[:2])


class UploadResultTests(unittest.TestCase):
    def test_compact_template_input_shape(self) -> None:
        result = _format_upload_result({
            "name": "mcp_cache/mcp_image.png",
            "subfolder": "mcp_cache",
            "type": "input",
            "mcp_cache_dir": "mcp_cache",
        })
        self.assertEqual(result["image"], "mcp_cache/mcp_image.png")
        self.assertEqual(set(result), {"image", "tip"})
        self.assertIn("result://", result["tip"])
        self.assertIn("step://", result["tip"])
        self.assertIn("https://", result["tip"])
        self.assertIn("data:image", result["tip"])

    def test_upload_result_requires_path(self) -> None:
        with self.assertRaises(ValueError):
            _format_upload_result({})
