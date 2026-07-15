# 工具参考

[← 返回 README](../../README.md) | [文档索引](../README.md) | [独立部署](./standalone.md) | [故障排查](./troubleshooting.md)

本文描述 MCP 工具的参数、返回结构和推荐调用方式。

## 推荐调用流程

1. 调用 `list_templates()` 查看可用模板。
2. 调用 `get_template(name)` 读取输入参数、输出和文档入口。
3. 如 `description` 提到更多说明，再调用 `read_template_doc(name, title)`。
4. 调用 `run_template()` 执行单个任务，或用 `run_templates()` 一次运行多个独立任务或关联步骤。
5. 如果返回超时，用 `get_template_result()` 继续查询。

## 工具速览

| 工具 | 作用 |
| --- | --- |
| `list_templates()` | 列出可用模板，只返回名称和标题 |
| `get_template(name)` | 获取模板输入、输出、描述和可读取文档标题 |
| `read_template_doc(name, title)` | 读取模板文档中的指定章节 |
| `run_template(name, params, wait, bindings)` | 执行单个模板 |
| `run_templates(pipeline, timeout_per_step)` | 一次顺序运行多个任务，可选绑定前序输出 |
| `upload_image(source)` | 上传用户提供的新图片 |
| `list_models(folder, keywords)` | 查询模型目录或模型文件 |
| `get_template_result(name, run_id, wait, timeout)` | 查询或继续等待执行结果 |

## `list_templates()`

列出所有可用模板。已禁用模板不会返回。

返回内容保持轻量，只包含 AI 需要选择模板所需的信息：

```json
[
  {
    "name": "txt2img.app",
    "title": "文生图"
  }
]
```

## `get_template(name)`

读取模板详情。常用于执行前确认参数。

返回字段：

- `name`：模板名称
- `title`：模板标题，来自工作流中的 `title` Markdown Note
- `description`：模板说明，来自 `description` Markdown Note
- `inputs`：AI 可填写的公共参数，只包含类型、默认值和可用约束
- `outputs`：稳定的业务输出名称和类型，不暴露 ComfyUI 节点 ID
- `docs`：可通过 `read_template_doc()` 读取的文档标题

说明：

- `node_id`、`api_key`、`widget` 等内部执行字段不会返回给 AI。
- 名为 `seed` 的输入会由运行时自动填入随机值，不需要 AI 传参。
- 已禁用模板不可查询。

## `read_template_doc(name, title)`

读取模板文档中的指定章节。

参数：

- `name`：模板名称
- `title`：文档标题，例如 `usage`、`examples`、`tips`

建议把详细提示词规则、示例、注意事项放到 Markdown Note 中，通过 `description` 提醒 AI 在需要时读取。

## `run_template(name, params, wait=true, bindings="{}")`

执行单个模板。

参数：

- `name`：模板名称
- `params`：JSON 字符串，填写模板输入参数，例如 `'{"prompt": "a cat"}'`
- `wait`：是否等待执行完成，默认 `true`
- `bindings`：JSON 字符串，把输入参数名映射到历史输出 `ref`

`wait=true` 时，默认等待超时由 **Settings → MCP Server → Execution → Run Template Timeout** 控制，默认 `120` 秒。

### 完成结果

```json
{
  "status": "completed",
  "outputs": {
    "最终提示词": {
      "type": "text",
      "value": "a cute cat, masterpiece",
      "ref": "result://abc-123/%E6%9C%80%E7%BB%88%E6%8F%90%E7%A4%BA%E8%AF%8D/0"
    },
    "输出图片": {
      "type": "image",
      "url": "http://127.0.0.1:8188/view?filename=output.png&type=output",
      "ref": "result://abc-123/%E8%BE%93%E5%87%BA%E5%9B%BE%E7%89%87/0",
      "markdown": "![输出图片](http://127.0.0.1:8188/view?filename=output.png&type=output)"
    }
  }
}
```

说明：

- 文本输出包含 `type`、`value`、`ref`。
- 图片、音频、GIF 等媒体输出包含 `type`、`url`、`ref`、`markdown`。
- `markdown` 只在需要展示媒体资源时返回，纯文本输出不会带该字段。
- `ref` 是不透明引用，可直接用于下一次调用的 `bindings`。

### 超时结果

```json
{
  "status": "timeout",
  "run_id": "abc-123",
  "template": "txt2img.app",
  "outputs": {},
  "error": "Timed out after 120s",
  "continue_hint": "Use get_template_result(name, run_id, wait=true) to continue waiting for the same prompt."
}
```

超时不代表任务失败。继续调用 `get_template_result(name, run_id, wait=true)` 即可等待同一次运行。

## Bindings 串联

处理模板生成的图片时，必须使用输出里的 `ref`，不要先下载再上传。

单步串联示例：

```python
result1 = run_template("txt2img.app", '{"prompt": "a cute cat"}')

result2 = run_template(
    "upscale.app",
    '{}',
    bindings='{"image": "result://abc-123/%E8%BE%93%E5%87%BA%E5%9B%BE%E7%89%87/0"}'
)
```

`upload_image()` 只用于用户提供的新图片，不用于模板生成的图片。

## `run_templates(pipeline, timeout_per_step=300)`

一次调用中按顺序执行多个任务，并返回每一步的完整结果。步骤可以彼此独立；只有后续任务依赖前序输出时，才需要配置 `bindings`。

多个独立任务示例：

```json
{
  "steps": [
    {
      "id": "cat",
      "template": "txt2img",
      "params": {"prompt": "a cat"}
    },
    {
      "id": "dog",
      "template": "txt2img",
      "params": {"prompt": "a dog"}
    }
  ]
}
```

需要使用前序输出时，再添加 `bindings`：

```json
{
  "steps": [
    {
      "id": "generate",
      "template": "txt2img",
      "params": {
        "prompt": "a cat"
      }
    },
    {
      "id": "upscale",
      "template": "upscale",
      "params": {
        "scale": 2
      },
      "bindings": {
        "image": "step://generate/%E8%BE%93%E5%87%BA%E5%9B%BE%E7%89%87/0"
      }
    }
  ]
}
```

成功时，每一步都会返回与 `run_template()` 相同结构的完整输出：

```json
{
  "status": "completed",
  "steps": [
    {
      "id": "generate",
      "template": "txt2img",
      "status": "completed",
      "outputs": {
        "输出图片": {
          "type": "image",
          "url": "http://127.0.0.1:8188/view?filename=generated.png&type=output",
          "ref": "result://generate-run-id/%E8%BE%93%E5%87%BA%E5%9B%BE%E7%89%87/0",
          "markdown": "![输出图片](http://127.0.0.1:8188/view?filename=generated.png&type=output)"
        }
      }
    },
    {
      "id": "upscale",
      "template": "upscale",
      "status": "completed",
      "outputs": {
        "输出图片": {
          "type": "image",
          "url": "http://127.0.0.1:8188/view?filename=upscaled.png&type=output",
          "ref": "result://upscale-run-id/%E8%BE%93%E5%87%BA%E5%9B%BE%E7%89%87/0",
          "markdown": "![输出图片](http://127.0.0.1:8188/view?filename=upscaled.png&type=output)"
        }
      }
    }
  ]
}
```

说明：

- `timeout_per_step` 是每一步超时时间，单位秒。
- 不配置 `bindings` 时，各步骤是相互独立的任务。
- `run_templates()` 内部使用 `step://<步骤 id>/<输出名>/<索引>`。
- 普通 `run_template()` 返回的引用使用 `result://`。
- 每个 step 都包含 `id`、`template`，以及和单模板执行一致的 `status`、`outputs`、`error`、`run_id` 等结果字段。
- 顶层只描述流水线整体状态，不重复返回最后一步输出。

## `upload_image(source)`

上传用户提供的新图片到 ComfyUI。

支持来源：

- 本地路径：`E:/photos/input.png`
- HTTP URL：`https://example.com/image.png`
- Base64：`data:image/png;base64,iVBOR...`

上传时会保留原扩展名并生成唯一文件名，例如 `mcp_4b2f...a91c.png`，避免同名文件互相覆盖。返回的 `name` 可直接填入模板参数。

## `list_models(folder="", keywords="")`

查询 ComfyUI 模型目录或目录中的模型文件。

- 不传 `folder`：返回可查询的模型目录。
- 传 `folder`：返回该目录下的模型文件，例如 `checkpoints`、`loras`、`vae`、`controlnet`。
- `keywords`：可选搜索关键词，大小写不敏感，多个关键词为空格分隔的 AND 条件。

## `get_template_result(name, run_id, wait=false, timeout=300)`

查询执行状态或继续等待结果。

- `wait=false`：立即返回当前状态，适合轮询。
- `wait=true`：阻塞等待直到完成或超时。
- `timeout`：等待超时时间，单位秒。

## ComfyUI 前端管理

在 **Settings → MCP Server** 中：

- **Status**：查看 MCP 服务状态和连接地址
- **Execution → Run Template Timeout**：设置 `run_template(wait=true)` 默认等待超时
- **Templates**：查看、刷新、启用、禁用、删除模板
- **Auto Extract Templates**：扫描工作流，为包含 `title` Markdown Note 且尚未存在模板的工作流创建模板
- **Batch Refresh Templates**：从同名工作流重新提取输入、输出、标题和描述
- **Export Templates**：导出当前模板 JSON 为 `mcp-templates.zip`

导出的压缩包只包含模板文件：

```text
mcp-templates.zip
└── templates/
    ├── txt2img.json
    └── upscale.json
```
