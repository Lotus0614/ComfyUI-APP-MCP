import unittest

import template_manager as tm


class OutputRefTests(unittest.TestCase):
    def test_roundtrip_ascii(self) -> None:
        ref = tm._build_output_ref("result", "abc-123", "image", 0)
        self.assertEqual(tm._parse_output_ref(ref, "result"), ("abc-123", "image", 0))

    def test_roundtrip_cjk_output_name(self) -> None:
        ref = tm._build_output_ref("result", "abc-123", "输出图片", 2)
        self.assertEqual(
            tm._parse_output_ref(ref, "result"), ("abc-123", "输出图片", 2)
        )

    def test_roundtrip_special_chars(self) -> None:
        ref = tm._build_output_ref("step", "gen/1:a", "out put", 1)
        self.assertEqual(tm._parse_output_ref(ref, "step"), ("gen/1:a", "out put", 1))

    def test_wrong_scheme_rejected(self) -> None:
        ref = tm._build_output_ref("step", "gen", "out", 0)
        with self.assertRaises(ValueError):
            tm._parse_output_ref(ref, "result")

    def test_bad_index_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tm._parse_output_ref("result://abc/out/xyz", "result")


class TemplateFilenameTests(unittest.TestCase):
    def test_plain_name(self) -> None:
        self.assertEqual(tm._template_filename("txt2img"), "txt2img.json")

    def test_cjk_name(self) -> None:
        self.assertEqual(tm._template_filename("文生图"), "文生图.json")

    def test_path_traversal_neutralized(self) -> None:
        filename = tm._template_filename("../../etc/passwd")
        self.assertNotIn("/", filename)
        self.assertNotIn("\\", filename)
        self.assertTrue(filename.endswith(".json"))

    def test_nested_workflow_name_flattened(self) -> None:
        self.assertEqual(tm._template_filename("sub/wf"), "sub_wf.json")

    def test_empty_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tm._template_filename("")
        with self.assertRaises(ValueError):
            tm._template_filename("   ")

    def test_dot_names_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tm._template_filename("..")


class PublicOutputNameTests(unittest.TestCase):
    def test_dedupes_aliases(self) -> None:
        outputs = {
            "保存图片_10_output": {"title": "保存图片", "type": "image"},
            "保存图片_11_output": {"title": "保存图片", "type": "image"},
        }
        aliases = tm.build_public_output_names(outputs)
        self.assertEqual(len(set(aliases.values())), 2)
        self.assertIn("保存图片", aliases.values())

    def test_strips_node_id_fragments(self) -> None:
        outputs = {"SaveImage_12_IMAGE": {"title": "", "type": "image"}}
        aliases = tm.build_public_output_names(outputs)
        self.assertEqual(aliases["SaveImage_12_IMAGE"], "SaveImage")


class ParamCoercionTests(unittest.TestCase):
    def test_int_from_string(self) -> None:
        self.assertEqual(tm._coerce_param_value("42", "INT"), 42)
        self.assertEqual(tm._coerce_param_value("2.0", "INT"), 2)

    def test_float_from_string(self) -> None:
        self.assertEqual(tm._coerce_param_value("1.5", "FLOAT"), 1.5)

    def test_boolean_from_string(self) -> None:
        self.assertIs(tm._coerce_param_value("true", "BOOLEAN"), True)
        self.assertIs(tm._coerce_param_value("off", "BOOLEAN"), False)

    def test_string_passthrough(self) -> None:
        self.assertEqual(tm._coerce_param_value("hello", "STRING"), "hello")
        self.assertEqual(tm._coerce_param_value(5, "COMBO"), 5)

    def test_invalid_int_raises(self) -> None:
        with self.assertRaises(ValueError):
            tm._coerce_param_value("not-a-number", "INT")

    def test_unknown_param_reported(self) -> None:
        inputs = {"提示词": {"type": "STRING"}, "steps": {"type": "INT"}}
        _, error = tm._validate_and_coerce_params(inputs, {"prompt": "cat"})
        self.assertIsNotNone(error)
        self.assertIn("prompt", error)
        self.assertIn("提示词", error)

    def test_valid_params_coerced(self) -> None:
        inputs = {"steps": {"type": "INT"}}
        params, error = tm._validate_and_coerce_params(inputs, {"steps": "30"})
        self.assertIsNone(error)
        self.assertEqual(params, {"steps": 30})

    def test_seed_always_allowed(self) -> None:
        params, error = tm._validate_and_coerce_params({}, {"seed": 123})
        self.assertIsNone(error)
        self.assertEqual(params, {"seed": 123})


class CacheBoundTests(unittest.TestCase):
    def test_outputs_cache_is_bounded(self) -> None:
        tm._mcp_outputs_cache.clear()
        try:
            for i in range(tm._MCP_OUTPUTS_CACHE_MAX + 20):
                tm._cache_outputs(f"prompt-{i}", {})
            self.assertLessEqual(
                len(tm._mcp_outputs_cache), tm._MCP_OUTPUTS_CACHE_MAX
            )
            # Newest entries survive; oldest are evicted.
            self.assertIn(
                f"prompt-{tm._MCP_OUTPUTS_CACHE_MAX + 19}", tm._mcp_outputs_cache
            )
            self.assertNotIn("prompt-0", tm._mcp_outputs_cache)
        finally:
            tm._mcp_outputs_cache.clear()


if __name__ == "__main__":
    unittest.main()
