import unittest

from server import _filter_models


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

