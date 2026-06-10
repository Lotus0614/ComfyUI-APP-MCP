# ComfyUI MCP Server 测试计划

> 每次重大更新后，按本文档逐项测试，确保功能正常。

## 前置条件

- [ ] ComfyUI 已启动
- [ ] MCP 服务端点可访问：`http://127.0.0.1:8188/app-mcp`
- [ ] 至少有一个可用模板（如 `anima mcp.app`）

---

## 一、基础查询

### 1.1 list_templates

```
调用: list_templates()
```

**验证点：**
- [ ] 返回 JSON 包含 `templates` 数组
- [ ] 每个模板有 `name`、`title`、`disabled`、`input_count`、`output_count`
- [ ] 已禁用的模板不出现在列表中
- [ ] 模板数量 > 0

### 1.2 get_template

```
调用: get_template(name="anima mcp.app")
```

**验证点：**
- [ ] 返回 JSON 包含 `name`、`description`、`inputs`、`outputs`
- [ ] `inputs` 是 dict，每个输入有 `node_id`、`widget`、`type`、`default`
- [ ] `outputs` 是 dict，每个输出有 `node_id`、`type`、`title`
- [ ] description 不为空

### 1.3 get_template — 不存在的模板

```
调用: get_template(name="不存在的模板")
```

**验证点：**
- [ ] 返回 `{"error": "Template '不存在的模板' not found"}`

### 1.4 get_template — 已禁用的模板

```
调用: get_template(name="<已禁用的模板名>")
```

**验证点：**
- [ ] 返回 `{"error": "Template 'xxx' is disabled"}`

### 1.5 read_template_doc

```
调用: read_template_doc(name="anima mcp.app", title="usage")
```

**验证点：**
- [ ] 返回 JSON 包含 `template`、`title`、`content`
- [ ] `content` 为 Markdown 文本
- [ ] 如果文档不存在，返回合理的错误或空内容

### 1.6 list_models

```
调用: list_models()
```

**验证点：**
- [ ] 返回 `{"folders": [...]}` 格式
- [ ] 包含 `checkpoints`、`loras` 等常见目录

```
调用: list_models(folder="checkpoints")
```

**验证点：**
- [ ] 返回 `{"folder": "checkpoints", "models": [...]}`
- [ ] models 列表不为空

---

## 二、模板执行

### 2.1 基本执行（wait=true）

```
调用: run_template(
  name="anima mcp.app",
  params='{"提示词": "a cute anime girl with blue hair, simple background, detailed anime style"}'
)
```

**验证点：**
- [ ] 返回 JSON 包含 `status`、`prompt_id`、`outputs`
- [ ] `status` 为 `"completed"`
- [ ] `prompt_id` 是有效 UUID 字符串
- [ ] `outputs` 中至少有一个输出包含 `media` 数组
- [ ] `media` 数组中每个元素有 `url`、`type`、`filename`
- [ ] `url` 可以在浏览器中打开并显示图片
- [ ] 返回结果包含 `binding_hint` 字段
- [ ] `binding_hint` 中每个条目有 `from`、`output`、`type`、`index`
- [ ] `binding_hint.from` 等于 `prompt_id`

### 2.2 异步执行（wait=false）+ get_template_result

```
调用: run_template(
  name="anima mcp.app",
  params='{"提示词": "a cute anime girl, simple background"}',
  wait=false
)
```

**验证点：**
- [ ] 返回立即，不阻塞
- [ ] `status` 为 `"queued"`
- [ ] 包含有效的 `prompt_id`
- [ ] `outputs` 为空（未完成）

```
调用: get_template_result(
  name="anima mcp.app",
  prompt_id="<上一步的 prompt_id>",
  wait=true
)
```

**验证点：**
- [ ] 阻塞直到完成
- [ ] `status` 为 `"completed"`
- [ ] `outputs` 包含生成的媒体
- [ ] 包含 `binding_hint`

### 2.3 get_template_result — 轮询模式

```
调用: run_template(name="anima mcp.app", params='{"提示词": "..."}', wait=false)
循环调用: get_template_result(name="anima mcp.app", prompt_id="...", wait=false)
```

**验证点：**
- [ ] 第一次调用可能返回 `{"status": "pending"}` 或 `{"status": "running"}`
- [ ] 最终返回 `{"status": "completed"}`
- [ ] 完成后 `outputs` 包含生成的媒体

### 2.4 使用最快速度参数

```
调用: run_template(
  name="anima mcp.app",
  params='{"提示词": "a cute anime girl", "加速Lora强度": 1, "采样cfg": 1, "采样步数": 10}'
)
```

**验证点：**
- [ ] 执行成功
- [ ] 执行时间明显短于默认参数

---

## 三、Binding（跨模板）

### 3.1 使用 binding_hint 进行放大

```
步骤1: run_template(name="anima mcp.app", params='{"提示词": "a cute anime girl"}')
步骤2: 使用步骤1返回的 binding_hint，调用:
  run_template(
    name="anima 放大 mcp.app",
    params='{"降噪": 0.3}',
    bindings='{"输入图片": <binding_hint 中的配置>}'
  )
```

**验证点：**
- [ ] 步骤2 不需要手动上传图片
- [ ] 步骤2 执行成功
- [ ] 输出图片分辨率大于原图
- [ ] 步骤2 返回新的 `binding_hint`

### 3.2 使用 binding 进行加密

```
步骤1: run_template(name="anima mcp.app", params='{"提示词": "...", "加速Lora强度": 1, "采样cfg": 1, "采样步数": 10}')
步骤2: 使用 binding_hint，调用:
  run_template(name="图片加密.app", params='{}', bindings='{"image": <binding_hint>}')
```

**验证点：**
- [ ] 加密后的图片是噪点/乱码图
- [ ] 执行成功

### 3.3 加密 → 解密完整流程

```
步骤1: 生成图片
步骤2: 加密（使用 binding）
步骤3: 解密（使用步骤2 的 binding_hint）
```

**验证点：**
- [ ] 解密后的图片与原图一致
- [ ] 三步都执行成功

### 3.4 手动构造 binding（不用 binding_hint）

```
步骤1: run_template(...) 获取 prompt_id
步骤2: 手动构造 binding:
  {
    "from": "<prompt_id>",
    "output": "<outputs 中的 key>",
    "type": "image",
    "index": 0
  }
```

**验证点：**
- [ ] 手动构造的 binding 也能正常工作
- [ ] 不需要 `source_outputs`（因为 `mcp_outputs` 已缓存）

---

## 四、流水线（run_templates）

### 4.1 两步流水线：生成 + 放大

```
调用: run_templates(pipeline='{
  "steps": [
    {
      "id": "generate",
      "template": "anima mcp.app",
      "params": {"提示词": "a cute anime girl, simple background, detailed anime style"}
    },
    {
      "id": "upscale",
      "template": "anima 放大 mcp.app",
      "params": {"降噪": 0.3},
      "bindings": {
        "输入图片": {
          "from": "generate",
          "output": "输出图片_122_output",
          "type": "image",
          "index": 0
        }
      }
    }
  ]
}')
```

**验证点：**
- [ ] 返回 `{"status": "completed", "steps": [...], "final": {...}}`
- [ ] `steps` 数组有 2 个元素
- [ ] 每个 step 有 `id`、`template`、`params`、`status`、`prompt_id`、`outputs`
- [ ] 所有 step 的 `status` 为 `"completed"`
- [ ] `final` 包含最后一步的 outputs
- [ ] 返回结果包含 `binding_hint`
- [ ] `binding_hint.from` 是步骤 id（不是 prompt_id）

### 4.2 两步流水线：生成 + 加密

```
调用: run_templates(pipeline='{
  "steps": [
    {
      "id": "generate",
      "template": "anima mcp.app",
      "params": {"提示词": "...", "加速Lora强度": 1, "采样cfg": 1, "采样步数": 10}
    },
    {
      "id": "encrypt",
      "template": "图片加密.app",
      "bindings": {
        "image": {
          "from": "generate",
          "output": "输出图片_122_output",
          "type": "image",
          "index": 0
        }
      }
    }
  ]
}')
```

**验证点：**
- [ ] 执行成功
- [ ] 加密后的图片是噪点图

### 4.3 三步流水线：生成 + 加密 + 解密

```
调用: run_templates(pipeline='{
  "steps": [
    {"id": "generate", "template": "anima mcp.app", "params": {"提示词": "..."}},
    {"id": "encrypt", "template": "图片加密.app", "bindings": {"image": {"from": "generate", "output": "输出图片_122_output", "type": "image", "index": 0}}},
    {"id": "decrypt", "template": "图片解密.app", "bindings": {"image": {"from": "encrypt", "output": "PreviewImage_3_output", "type": "image", "index": 0}}}
  ]
}')
```

**验证点：**
- [ ] 三步都执行成功
- [ ] 解密后的图片与原图一致
- [ ] `steps` 数组有 3 个元素

### 4.4 流水线错误处理 — 无效模板

```
调用: run_templates(pipeline='{
  "steps": [
    {"id": "step1", "template": "不存在的模板", "params": {}}
  ]
}')
```

**验证点：**
- [ ] 返回 `{"status": "failed", "failed_step": "step1", "error": "..."}`
- [ ] 包含 `steps` 数组（可能为空或包含失败的 step）

### 4.5 流水线错误处理 — 重复 step id

```
调用: run_templates(pipeline='{
  "steps": [
    {"id": "same", "template": "anima mcp.app", "params": {"提示词": "..."}},
    {"id": "same", "template": "anima mcp.app", "params": {"提示词": "..."}}
  ]
}')
```

**验证点：**
- [ ] 返回错误信息包含 "Duplicate pipeline step id"

### 4.6 流水线错误处理 — 空 steps

```
调用: run_templates(pipeline='{"steps": []}')
```

**验证点：**
- [ ] 返回错误信息包含 "non-empty list"

---

## 五、输出格式验证

### 5.1 输出精简

对任意 `run_template` 或 `get_template_result` 的返回结果：

**验证点：**
- [ ] `outputs` 中每个输出只有 `media` 字段（无 `images`、`audio`、`gifs` 原始数据）
- [ ] `media` 中每个元素只有 `url`、`type`、`filename`、`subfolder`、`item_type`
- [ ] 无 `output_name`、`node_id`、`title` 等冗余字段
- [ ] 图片/音频输出包含 `markdown` 字段，格式为 `![名称](url)` 或 `[🔊 名称](url)`
- [ ] 文本输出包含 `text` 字段

### 5.2 binding_hint 格式

对任意执行成功的返回结果：

**验证点：**
- [ ] 存在 `binding_hint` 字段
- [ ] `binding_hint` 是 dict，key 与 `outputs` 中有 media 的输出名对应
- [ ] 每个 binding 有 `from`、`output`、`type`、`index`
- [ ] `type` 值为 `"image"`、`"audio"`、`"gif"` 之一
- [ ] `index` 为 `0`

### 5.3 run_templates 输出格式

**验证点：**
- [ ] 顶层有 `status`、`steps`、`final`
- [ ] 成功时有 `binding_hint`，失败时无
- [ ] `binding_hint.from` 是步骤 id（字符串），不是 prompt_id

---

## 六、upload_image

### 6.1 上传本地文件

```
调用: upload_image(source="<本地图片路径>")
```

**验证点：**
- [ ] 返回 ComfyUI 上传响应，包含 `name`、`subfolder`、`type`
- [ ] 返回的 `name` 可以作为模板的图片输入参数

### 6.2 上传 HTTP URL

```
调用: upload_image(source="https://example.com/image.png")
```

**验证点：**
- [ ] 下载并上传成功
- [ ] 返回有效的文件名

### 6.3 上传 Base64

```
调用: upload_image(source="data:image/png;base64,iVBOR...")
```

**验证点：**
- [ ] 上传成功
- [ ] 返回有效的文件名

### 6.4 上传不存在的文件

```
调用: upload_image(source="E:/不存在的文件.png")
```

**验证点：**
- [ ] 返回错误信息

---

## 七、边界情况

### 7.1 无效 JSON 参数

```
调用: run_template(name="anima mcp.app", params='无效JSON')
```

**验证点：**
- [ ] 返回 `{"error": "Invalid params JSON: ..."}`

### 7.2 无效 binding JSON

```
调用: run_template(name="anima mcp.app", params='{}', bindings='无效JSON')
```

**验证点：**
- [ ] 返回 `{"error": "Invalid bindings JSON: ..."}`

### 7.3 无效 pipeline JSON

```
调用: run_templates(pipeline='无效JSON')
```

**验证点：**
- [ ] 返回 `{"error": "Invalid pipeline JSON: ..."}`

### 7.4 binding 引用不存在的 prompt_id

```
调用: run_template(
  name="anima 放大 mcp.app",
  params='{}',
  bindings='{"输入图片": {"from": "不存在的id", "output": "xxx", "type": "image", "index": 0}}'
)
```

**验证点：**
- [ ] 返回错误信息包含 "not found"

### 7.5 binding 引用不存在的 output

```
调用: run_template(
  name="anima 放大 mcp.app",
  params='{}',
  bindings='{"输入图片": {"from": "<有效prompt_id>", "output": "不存在的output", "type": "image", "index": 0}}'
)
```

**验证点：**
- [ ] 返回错误信息包含 "not found in source"

### 7.6 binding index 越界

```
调用: run_template(
  name="anima 放大 mcp.app",
  params='{}',
  bindings='{"输入图片": {"from": "<有效prompt_id>", "output": "<有效output>", "type": "image", "index": 999}}'
)
```

**验证点：**
- [ ] 返回错误信息包含 "out of range"

---

## 八、快速回归清单

每次重大更新后，至少完成以下快速验证：

- [ ] `list_templates()` 返回模板列表
- [ ] `get_template("anima mcp.app")` 返回模板详情
- [ ] `run_template("anima mcp.app", '{"提示词": "test"}')` 生成图片成功
- [ ] 返回结果包含 `binding_hint`
- [ ] 返回结果中 `outputs` 无冗余字段
- [ ] 用 `binding_hint` 执行放大模板成功
- [ ] `run_templates` 两步流水线成功
- [ ] 流水线返回 `binding_hint`（from 为步骤 id）

---

## 附录：测试结果记录模板

```
日期: YYYY-MM-DD
版本/提交: xxx
测试人: xxx

| 测试项 | 结果 | 备注 |
|--------|------|------|
| 1.1 list_templates | ✅/❌ | |
| 1.2 get_template | ✅/❌ | |
| ... | ... | ... |

发现的问题:
- 
```
