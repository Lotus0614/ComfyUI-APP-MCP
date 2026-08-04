import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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


class TemplateTokenSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        tm.template_token_store.clear()
        self.template = {
            "name": "demo.app",
            "title": "Demo",
            "description": "Initial guidance",
            "inputs": {"prompt": {"type": "STRING"}},
            "outputs": {},
            "workflow": {},
        }

    def tearDown(self) -> None:
        tm.template_token_store.clear()

    def test_disabled_response_does_not_issue_token(self) -> None:
        with patch.object(tm.config, "get_template_token_enabled", return_value=False):
            fields = tm.build_template_token_fields(self.template)
        self.assertEqual(fields, {"template_token_required": False})

    def test_enabled_response_issues_token_with_limits(self) -> None:
        with (
            patch.object(tm.config, "get_template_token_enabled", return_value=True),
            patch.object(tm.config, "get_template_token_max_uses", return_value=50),
            patch.object(tm.config, "get_template_token_ttl_hours", return_value=12),
        ):
            fields = tm.build_template_token_fields(self.template)
        self.assertTrue(fields["template_token_required"])
        self.assertEqual(fields["template_token_max_uses"], 50)
        self.assertTrue(fields["template_token"])

    def test_description_change_updates_schema_revision(self) -> None:
        first = tm.build_template_schema_revision(self.template)
        self.template["description"] = "Updated guidance"
        second = tm.build_template_schema_revision(self.template)
        self.assertNotEqual(first, second)


class TemplateTokenIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tm.template_token_store.clear()
        self.template = {
            "name": "demo.app",
            "title": "Demo",
            "description": "Generate a demo image",
            "inputs": {
                "prompt": {
                    "type": "STRING",
                    "default": "",
                    "node_id": 1,
                    "widget": "prompt",
                }
            },
            "outputs": {},
            "workflow": {},
            "api_prompt": {"1": {"inputs": {"prompt": ""}}},
        }

    def tearDown(self) -> None:
        tm.template_token_store.clear()

    def _issue(self, max_uses: int = 1) -> str:
        return tm.template_token_store.issue(
            self.template["name"],
            tm.build_template_schema_revision(self.template),
            max_uses=max_uses,
            ttl_seconds=3600,
        )["template_token"]

    async def test_missing_token_returns_structured_recovery(self) -> None:
        with (
            patch.object(tm, "get_template", return_value=self.template),
            patch.object(tm.config, "get_template_token_enabled", return_value=True),
            patch.object(tm.config, "get_template_token_max_uses", return_value=1),
            patch.object(tm.config, "get_template_token_ttl_hours", return_value=1),
        ):
            result = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                enforce_template_token=True,
            )

        self.assertEqual(result["error_code"], "TEMPLATE_TOKEN_REQUIRED")
        self.assertEqual(result["recovery"]["tool"], "get_template")
        self.assertIn("read the current template information", result["error"])
        self.assertIn(
            "read the current template information",
            result["recovery"]["instruction"],
        )

    async def test_disabled_protection_preserves_existing_execution(self) -> None:
        client = SimpleNamespace(
            queue_prompt=AsyncMock(return_value={"prompt_id": "prompt-disabled"}),
        )
        with (
            patch.object(tm, "get_template", return_value=self.template),
            patch.object(tm.config, "get_template_token_enabled", return_value=False),
            patch.object(tm.config, "get_embed_workflow_metadata", return_value=False),
            patch.object(tm, "_comfyui_client", return_value=client),
            patch.object(tm, "_enforce_queue_capacity", AsyncMock(return_value=None)),
            patch.object(
                tm,
                "_wait_for_result",
                AsyncMock(return_value={"status": "completed", "outputs": {}}),
            ),
        ):
            result = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                enforce_template_token=True,
            )

        self.assertEqual(result["status"], "completed")
        self.assertNotIn("template_token_remaining_uses", result)

    async def test_successful_queue_consumes_one_use(self) -> None:
        token = self._issue()
        client = SimpleNamespace(
            queue_prompt=AsyncMock(return_value={"prompt_id": "prompt-1"}),
        )
        with (
            patch.object(tm, "get_template", return_value=self.template),
            patch.object(tm.config, "get_template_token_enabled", return_value=True),
            patch.object(tm.config, "get_template_token_max_uses", return_value=1),
            patch.object(tm.config, "get_template_token_ttl_hours", return_value=1),
            patch.object(tm.config, "get_embed_workflow_metadata", return_value=False),
            patch.object(tm, "_comfyui_client", return_value=client),
            patch.object(tm, "_enforce_queue_capacity", AsyncMock(return_value=None)),
            patch.object(
                tm,
                "_wait_for_result",
                AsyncMock(return_value={"status": "completed", "outputs": {}}),
            ),
        ):
            result = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                template_token=token,
                enforce_template_token=True,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["template_token_remaining_uses"], 0)

    async def test_failed_queue_submission_releases_reserved_use(self) -> None:
        token = self._issue()
        client = SimpleNamespace(
            queue_prompt=AsyncMock(side_effect=[{}, {"prompt_id": "prompt-2"}]),
        )
        with (
            patch.object(tm, "get_template", return_value=self.template),
            patch.object(tm.config, "get_template_token_enabled", return_value=True),
            patch.object(tm.config, "get_template_token_max_uses", return_value=1),
            patch.object(tm.config, "get_template_token_ttl_hours", return_value=1),
            patch.object(tm.config, "get_embed_workflow_metadata", return_value=False),
            patch.object(tm, "_comfyui_client", return_value=client),
            patch.object(tm, "_enforce_queue_capacity", AsyncMock(return_value=None)),
            patch.object(
                tm,
                "_wait_for_result",
                AsyncMock(return_value={"status": "completed", "outputs": {}}),
            ),
        ):
            failed = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                template_token=token,
                enforce_template_token=True,
            )
            retried = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                template_token=token,
                enforce_template_token=True,
            )

        self.assertIn("error", failed)
        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["template_token_remaining_uses"], 0)

    async def test_invalid_params_do_not_consume_use(self) -> None:
        token = self._issue()
        client = SimpleNamespace(
            queue_prompt=AsyncMock(return_value={"prompt_id": "prompt-valid"}),
        )
        with (
            patch.object(tm, "get_template", return_value=self.template),
            patch.object(tm.config, "get_template_token_enabled", return_value=True),
            patch.object(tm.config, "get_template_token_max_uses", return_value=1),
            patch.object(tm.config, "get_template_token_ttl_hours", return_value=1),
            patch.object(tm.config, "get_embed_workflow_metadata", return_value=False),
            patch.object(tm, "_comfyui_client", return_value=client),
            patch.object(tm, "_enforce_queue_capacity", AsyncMock(return_value=None)),
            patch.object(
                tm,
                "_wait_for_result",
                AsyncMock(return_value={"status": "completed", "outputs": {}}),
            ),
        ):
            invalid = await tm.execute_template(
                "demo.app",
                {"wrong": "cat"},
                template_token=token,
                enforce_template_token=True,
            )
            valid = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                template_token=token,
                enforce_template_token=True,
            )

        self.assertIn("Unknown parameter", invalid["error"])
        self.assertEqual(valid["template_token_remaining_uses"], 0)

    async def test_queue_full_does_not_consume_use(self) -> None:
        token = self._issue()
        client = SimpleNamespace(
            queue_prompt=AsyncMock(return_value={"prompt_id": "prompt-after-full"}),
        )
        capacity = AsyncMock(
            side_effect=[{"status": "queue_full", "error": "queue full"}, None]
        )
        with (
            patch.object(tm, "get_template", return_value=self.template),
            patch.object(tm.config, "get_template_token_enabled", return_value=True),
            patch.object(tm.config, "get_template_token_max_uses", return_value=1),
            patch.object(tm.config, "get_template_token_ttl_hours", return_value=1),
            patch.object(tm.config, "get_embed_workflow_metadata", return_value=False),
            patch.object(tm, "_comfyui_client", return_value=client),
            patch.object(tm, "_enforce_queue_capacity", capacity),
            patch.object(
                tm,
                "_wait_for_result",
                AsyncMock(return_value={"status": "completed", "outputs": {}}),
            ),
        ):
            rejected = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                template_token=token,
                enforce_template_token=True,
            )
            accepted = await tm.execute_template(
                "demo.app",
                {"prompt": "cat"},
                template_token=token,
                enforce_template_token=True,
            )

        self.assertEqual(rejected["status"], "queue_full")
        self.assertEqual(accepted["template_token_remaining_uses"], 0)

    async def test_pipeline_forwards_each_step_token(self) -> None:
        execute = AsyncMock(
            return_value={"status": "completed", "prompt_id": "prompt-3", "outputs": {}}
        )
        with patch.object(tm, "execute_template", execute):
            result = await tm.run_templates(
                {
                    "steps": [
                        {
                            "id": "generate",
                            "template": "demo.app",
                            "template_token": "step-token",
                            "params": {"prompt": "cat"},
                        }
                    ]
                }
            )

        self.assertEqual(result["status"], "completed")
        kwargs = execute.await_args.kwargs
        self.assertEqual(kwargs["template_token"], "step-token")
        self.assertTrue(kwargs["enforce_template_token"])


if __name__ == "__main__":
    unittest.main()
