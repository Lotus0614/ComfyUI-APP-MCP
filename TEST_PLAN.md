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
- [ ] 每个模板只有 `name`、`title`
- [ ] 已禁用的模板不出现在列表中
- [ ] 模板数量 > 0

### 1.2 get_template

```
调用: get_template(name="anima mcp.app")
```

**验证点：**
- [ ] 返回 JSON 包含 `name`、`description`、`inputs`、`outputs`、`docs`
- [ ] `inputs` 是 dict，每个输入只有公共字段，如 `type`、`default`、`options`、`min`、`max`、`step`
- [ ] `outputs` 是 dict，每个输出只有 `type`
- [ ] 整个结果不包含 `node_id`、`api_key`、`widget`、`comfy_type`
- [ ] 输出名称不包含自动附加的节点 ID
- [ ] `docs` 是数组，包含所有可通过 `read_template_doc(name, title)` 读取的 MarkdownNote 标题
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
- [ ] 返回 JSON 包含 `status`、`outputs`
- [ ] `status` 为 `"completed"`
- [ ] 完成结果顶层不包含 `prompt_id` 或 `run_id`
- [ ] `outputs` 中至少有一个输出包含 `type`、`url`、`ref`
- [ ] 图片/音频输出包含 `markdown`
- [ ] `ref` 使用 `result://` 协议
- [ ] `url` 可以在浏览器中打开并显示图片
- [ ] 返回结果不包含 `binding_hint`、`filename`、`subfolder`、`item_type`

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
- [ ] 包含有效的 `run_id`
- [ ] `outputs` 为空（未完成）

```
调用: get_template_result(
  name="anima mcp.app",
  run_id="<上一步的 run_id>",
  wait=true
)
```

**验证点：**
- [ ] 阻塞直到完成
- [ ] `status` 为 `"completed"`
- [ ] `outputs` 包含生成的媒体
- [ ] 输出包含 `result://` 引用

### 2.3 get_template_result — 轮询模式

```
调用: run_template(name="anima mcp.app", params='{"提示词": "..."}', wait=false)
循环调用: get_template_result(name="anima mcp.app", run_id="...", wait=false)
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

### 3.1 使用 result ref 进行放大

```
步骤1: run_template(name="anima mcp.app", params='{"提示词": "a cute anime girl"}')
步骤2: 使用步骤1输出的 `ref`，调用:
  run_template(
    name="anima 放大 mcp.app",
    params='{"降噪": 0.3}',
    bindings='{"输入图片": "result://<run-id>/<输出名>/0"}'
  )
```

**验证点：**
- [ ] 步骤2 不需要手动上传图片
- [ ] 步骤2 执行成功
- [ ] 输出图片分辨率大于原图
- [ ] 步骤2 输出包含新的 `ref`

### 3.2 使用 binding 进行加密

```
步骤1: run_template(name="anima mcp.app", params='{"提示词": "...", "加速Lora强度": 1, "采样cfg": 1, "采样步数": 10}')
步骤2: 使用输出 ref，调用:
  run_template(name="图片加密.app", params='{}', bindings='{"image": "result://<run-id>/<输出名>/0"}')
```

**验证点：**
- [ ] 加密后的图片是噪点/乱码图
- [ ] 执行成功

### 3.3 加密 → 解密完整流程

```
步骤1: 生成图片
步骤2: 加密（使用 binding）
步骤3: 解密（使用步骤2 的输出 ref）
```

**验证点：**
- [ ] 解密后的图片与原图一致
- [ ] 三步都执行成功

### 3.4 手动构造 result ref

```
步骤1: run_template(...) 获取输出名和 ref 格式
步骤2: 手动构造 `result://<run-id>/<输出名>/<索引>`
```

**验证点：**
- [ ] 手动构造的 ref 能正常工作

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
        "输入图片": "step://generate/<输出名>/0"
      }
    }
  ]
}')
```

**验证点：**
- [ ] 返回 `{"status": "completed", "steps": [...], "outputs": {...}}`
- [ ] `steps` 数组有 2 个元素
- [ ] 每个 step 只有 `id`、`template`、`status`
- [ ] 所有 step 的 `status` 为 `"completed"`
- [ ] 顶层 `outputs` 是最后一步输出
- [ ] 结果不包含 `final`、`binding_hint`、步骤 `params`、步骤 `prompt_id`

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
        "image": "step://generate/<输出名>/0"
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
    {"id": "encrypt", "template": "图片加密.app", "bindings": {"image": "step://generate/<输出名>/0"}},
    {"id": "decrypt", "template": "图片解密.app", "bindings": {"image": "step://encrypt/<输出名>/0"}}
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
- [ ] 单个媒体输出包含 `type`、`url`、`ref`、`markdown`
- [ ] 单个文本输出只包含 `type`、`value`、`ref`
- [ ] 多值输出使用 `items`，每个元素带自己的 `ref`
- [ ] 无 `output_name`、`node_id`、`title`、`filename`、`subfolder`、`item_type`
- [ ] 输出名称不包含节点 ID

### 5.2 ref 格式

对任意执行成功的返回结果：

**验证点：**
- [ ] 每个输出值包含 `ref`
- [ ] 普通执行输出使用 `result://<run-id>/<输出名>/<索引>`
- [ ] `ref` 中的输出名经过 URL 编码
- [ ] 不存在 `binding_hint`

### 5.3 run_templates 输出格式

**验证点：**
- [ ] 顶层有 `status`、`steps`、`outputs`
- [ ] `steps` 只记录步骤 id、模板名和状态
- [ ] 不存在 `final` 或 `binding_hint`

---

## 六、upload_image

### 6.1 上传本地文件

```
调用: upload_image(source="<本地图片路径>")
```

**验证点：**
- [ ] 返回 ComfyUI 上传响应，包含 `name`、`subfolder`、`type`
- [ ] 返回的 `name` 可以作为模板的图片输入参数
- [ ] 返回的 `name` 格式为 `mcp_<32位十六进制随机值>.<原扩展名>`
- [ ] 连续上传同一个文件两次，返回的 `name` 不同且两份文件都可用

### 6.2 上传 HTTP URL

```
调用: upload_image(source="https://example.com/image.png")
```

**验证点：**
- [ ] 下载并上传成功
- [ ] 返回唯一文件名并保留 `.png` 扩展名

### 6.3 上传 Base64

```
调用: upload_image(source="data:image/png;base64,iVBOR...")
```

**验证点：**
- [ ] 上传成功
- [ ] 返回唯一文件名并保留数据 URL 对应的扩展名

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

### 7.4 result ref 引用不存在的 run_id

```
调用: run_template(
  name="anima 放大 mcp.app",
  params='{}',
  bindings='{"输入图片": "result://不存在的id/xxx/0"}'
)
```

**验证点：**
- [ ] 返回错误信息包含 "not found"

### 7.5 result ref 引用不存在的 output

```
调用: run_template(
  name="anima 放大 mcp.app",
  params='{}',
  bindings='{"输入图片": "result://<有效run-id>/不存在的output/0"}'
)
```

**验证点：**
- [ ] 返回错误信息包含 "not found"

### 7.6 binding index 越界

```
调用: run_template(
  name="anima 放大 mcp.app",
  params='{}',
  bindings='{"输入图片": "result://<有效run-id>/<有效output>/999"}'
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
- [ ] 返回结果包含 `result://` 输出引用
- [ ] 返回结果中 `outputs` 无冗余字段
- [ ] 用输出 `ref` 执行放大模板成功
- [ ] `run_templates` 两步流水线成功
- [ ] 流水线使用 `step://` 引用并仅返回最终输出

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
