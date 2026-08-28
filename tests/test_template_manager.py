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


class AppModeInputFormatTests(unittest.TestCase):
    @staticmethod
    def _new_format_workflow() -> dict:
        subgraph_id = "subgraph-uuid"
        return {
            "nodes": [
                {
                    "id": 5,
                    "type": "KSamplerAdvanced",
                    "inputs": [
                        {
                            "name": "steps",
                            "type": "INT",
                            "widget": {"name": "steps"},
                            "link": None,
                        }
                    ],
                    "widgets_values": [20, 8.0],
                },
                {
                    "id": 6,
                    "type": "EmptyLatentImage",
                    "inputs": [
                        {
                            "name": "width",
                            "type": "INT",
                            "widget": {"name": "width"},
                            "link": None,
                        },
                        {
                            "name": "height",
                            "type": "INT",
                            "widget": {"name": "height"},
                            "link": None,
                        },
                    ],
                    "widgets_values": [1024, 1024],
                },
                {
                    "id": 11,
                    "type": subgraph_id,
                    "inputs": [
                        {"name": "clip", "type": "CLIP", "link": 11},
                        {
                            "name": "text",
                            "label": "stale_prompt_label",
                            "type": "STRING",
                            "widget": {"name": "text"},
                            "link": None,
                        },
                        {
                            "name": "text_1",
                            "label": "stale_negative_label",
                            "type": "STRING",
                            "widget": {"name": "text_1"},
                            "link": None,
                        },
                    ],
                    "widgets_values": ["", ""],
                },
            ],
            "definitions": {
                "subgraphs": [
                    {
                        "id": subgraph_id,
                        "inputs": [
                            {"name": "clip", "type": "CLIP", "linkIds": [1, 2]},
                            {
                                "name": "text",
                                "label": "negative_prompt",
                                "type": "STRING",
                                "linkIds": [14],
                            },
                            {
                                "name": "text_1",
                                "label": "prompt",
                                "type": "STRING",
                                "linkIds": [15],
                            },
                        ],
                        "nodes": [
                            {
                                "id": 2,
                                "type": "CLIPTextEncode",
                                "inputs": [
                                    {"name": "clip", "type": "CLIP", "link": 1},
                                    {
                                        "name": "text",
                                        "label": "prompt",
                                        "type": "STRING",
                                        "widget": {"name": "text"},
                                        "link": 15,
                                    },
                                ],
                                "widgets_values": [""],
                            },
                            {
                                "id": 3,
                                "type": "CLIPTextEncode",
                                "inputs": [
                                    {"name": "clip", "type": "CLIP", "link": 2},
                                    {
                                        "name": "text",
                                        "label": "negative_prompt",
                                        "type": "STRING",
                                        "widget": {"name": "text"},
                                        "link": 14,
                                    },
                                ],
                                "widgets_values": [""],
                            },
                        ],
                        "links": [
                            {
                                "id": 14,
                                "origin_id": -10,
                                "origin_slot": 1,
                                "target_id": 3,
                                "target_slot": 1,
                                "type": "STRING",
                            },
                            {
                                "id": 15,
                                "origin_id": -10,
                                "origin_slot": 2,
                                "target_id": 2,
                                "target_slot": 1,
                                "type": "STRING",
                            },
                        ],
                    }
                ]
            },
            "extra": {
                "linearData": {
                    "inputs": [
                        ["opaque-uuid:6:width", "width"],
                        ["opaque-uuid:6:height", "height"],
                        ["opaque-uuid:5:steps", "steps"],
                        ["opaque-uuid:5:cfg", "cfg"],
                        ["opaque-uuid:11:text_1", "text_1"],
                        ["opaque-uuid:11:text", "text"],
                    ]
                }
            },
        }

    @staticmethod
    def _node_defs() -> dict:
        return {
            "KSamplerAdvanced": {
                "input": {
                    "required": {
                        "steps": ["INT", {"default": 20}],
                        "cfg": ["FLOAT", {"default": 8.0}],
                    }
                }
            },
            "EmptyLatentImage": {
                "input": {
                    "required": {
                        "width": ["INT", {"default": 1024}],
                        "height": ["INT", {"default": 1024}],
                    }
                }
            },
            "CLIPTextEncode": {
                "input": {
                    "required": {
                        "clip": ["CLIP"],
                        "text": ["STRING", {"default": ""}],
                    }
                }
            },
        }

    def test_parses_old_and_new_linear_input_ids(self) -> None:
        self.assertEqual(
            tm._parse_linear_input_entry(["10", "width"]),
            ([10], "width", False),
        )
        self.assertEqual(
            tm._parse_linear_input_entry(["opaque-uuid:11:text", "text"]),
            ([11], "text", True),
        )
        self.assertIsNone(tm._parse_linear_input_entry(["bad", "text"]))

    def test_extracts_new_top_level_and_subgraph_inputs(self) -> None:
        inputs = tm._extract_inputs(self._new_format_workflow(), self._node_defs())

        self.assertEqual(
            set(inputs),
            {"width", "height", "steps", "cfg", "prompt", "negative_prompt"},
        )
        self.assertEqual(inputs["cfg"]["api_key"], "5")
        self.assertEqual(inputs["cfg"]["type"], "FLOAT")
        self.assertEqual(inputs["prompt"]["api_key"], "11:2")
        self.assertEqual(inputs["prompt"]["widget"], "text")
        self.assertEqual(inputs["negative_prompt"]["api_key"], "11:3")

    def test_new_format_values_reach_api_prompt_and_ui_workflow(self) -> None:
        workflow = self._new_format_workflow()
        node_defs = self._node_defs()
        inputs = tm._extract_inputs(workflow, node_defs)
        params = {
            "width": 768,
            "cfg": 6.5,
            "prompt": "a lighthouse",
            "negative_prompt": "fog",
        }
        api_prompt = {
            "5": {"inputs": {"steps": 20, "cfg": 8.0}},
            "6": {"inputs": {"width": 1024, "height": 1024}},
            "11:2": {"inputs": {"text": ""}},
            "11:3": {"inputs": {"text": ""}},
        }

        injected_prompt = tm._inject_widget_values(api_prompt, inputs, params)
        self.assertEqual(injected_prompt["6"]["inputs"]["width"], 768)
        self.assertEqual(injected_prompt["5"]["inputs"]["cfg"], 6.5)
        self.assertEqual(injected_prompt["11:2"]["inputs"]["text"], "a lighthouse")
        self.assertEqual(injected_prompt["11:3"]["inputs"]["text"], "fog")

        injected_workflow = tm._inject_widget_values_into_workflow(
            workflow, inputs, params, node_defs
        )
        self.assertEqual(
            tm._find_node_by_api_key(injected_workflow, "6")["widgets_values"][0],
            768,
        )
        self.assertEqual(
            tm._find_node_by_api_key(injected_workflow, "5")["widgets_values"][1],
            6.5,
        )
        self.assertEqual(
            tm._find_node_by_api_key(injected_workflow, "11:2")["widgets_values"][0],
            "a lighthouse",
        )
        self.assertEqual(
            tm._find_node_by_api_key(injected_workflow, "11:3")["widgets_values"][0],
            "fog",
        )

    def test_legacy_internal_node_id_still_resolves(self) -> None:
        workflow = self._new_format_workflow()
        workflow["extra"]["linearData"]["inputs"] = [["2", "text"]]

        inputs = tm._extract_inputs(workflow, self._node_defs())

        self.assertEqual(inputs["stale_prompt_label"]["node_id"], 2)
        self.assertEqual(inputs["stale_prompt_label"]["api_key"], "11:2")

    def test_subgraph_default_prefers_instance_copy(self) -> None:
        """Canvas edits land on the instance node; the internal copy can lag.

        Refresh must extract the instance copy so user-entered values survive.
        """
        workflow = self._new_format_workflow()
        subgraph = workflow["definitions"]["subgraphs"][0]
        instance = workflow["nodes"][2]
        instance["widgets_values"] = ["negative-instance", "prompt-instance"]
        for node in subgraph["nodes"]:
            if node["id"] == 2:
                node["widgets_values"] = ["prompt-internal"]
            elif node["id"] == 3:
                node["widgets_values"] = ["negative-internal"]

        inputs = tm._extract_inputs(workflow, self._node_defs())

        self.assertEqual(inputs["prompt"]["default"], "prompt-instance")
        self.assertEqual(inputs["negative_prompt"]["default"], "negative-instance")
        self.assertEqual(inputs["prompt"]["workflow_key"], "11")
        self.assertEqual(inputs["prompt"]["workflow_widget"], "text_1")

    def test_subgraph_default_falls_back_to_internal_node(self) -> None:
        """When the instance copy is unreadable, the internal node still works."""
        workflow = self._new_format_workflow()
        subgraph = workflow["definitions"]["subgraphs"][0]
        instance = workflow["nodes"][2]
        instance["widgets_values"] = []
        for node in subgraph["nodes"]:
            if node["id"] == 2:
                node["widgets_values"] = ["prompt-internal"]
            elif node["id"] == 3:
                node["widgets_values"] = ["negative-internal"]

        inputs = tm._extract_inputs(workflow, self._node_defs())

        self.assertEqual(inputs["prompt"]["default"], "prompt-internal")
        self.assertEqual(inputs["negative_prompt"]["default"], "negative-internal")

    def test_top_level_default_still_reads_from_own_node(self) -> None:
        """Non-subgraph locators (top-level nodes) keep reading their own copy."""
        workflow = self._new_format_workflow()
        workflow["nodes"][1]["widgets_values"] = [640, 480]

        inputs = tm._extract_inputs(workflow, self._node_defs())

        self.assertEqual(inputs["width"]["default"], 640)
        self.assertEqual(inputs["height"]["default"], 480)
        self.assertNotIn("workflow_key", inputs["width"])


if __name__ == "__main__":
    unittest.main()
