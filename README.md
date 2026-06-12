# ComfyUI MCP Server

[中文](./README.md) | [English](./README_EN.md)

一个 ComfyUI 插件，把 ComfyUI 工作流包装成可由 MCP 调用的模板，让 AI 助手直接把 ComfyUI 当成一个"可查询、可执行、可串联"的多媒体能力服务来使用。

主要能力：

- 模板化输入输出，AI 不需要理解 ComfyUI 节点图
- 支持配置模板文档，可对文档进行渐进式披露
- 支持多模板串联执行，把上一步输出传给下一步输入
- 支持查询 `checkpoints`、`loras` 等模型目录

## 核心概念

模板 = ComfyUI 应用 + 自动提取的输入/输出定义。

- **输入（Inputs）**：从工作流中标记为 `linearData.inputs` 的节点自动提取
- **输出（Outputs）**：从工作流中 `linearData.outputs` 标记的节点提取
- AI 只需要传参数和读取结果，不需要理解 ComfyUI 内部节点图

模板文档约定：

- `title`：模板标题，展示在模板列表
- `description`：模板简介，展示在模板详情
- 其他 Markdown 节点：作为可按需读取的模板文档，通过 `read_template_doc(name, title)` 获取

这种设计可以让模板默认保持简洁，同时在需要时再展开更详细的说明、示例、提示词规范或注意事项。

## 快速开始

1. 在 ComfyUI 中把工作流做成 App，标记输入输出节点，并把输入节点命名成 AI 容易理解的参数名。
2. 加入 Markdown 节点描述模板：
   - 标题为 `title`：简短标题
   - 标题为 `description`：模板说明
   - 其他标题：作为按需读取的模板文档
3. 在 ComfyUI 前端 **Settings → MCP Server → Templates** 中点击 **Create from Workflow** 创建模板。
4. 在 MCP 客户端中接入 `http://127.0.0.1:8188/app-mcp`。
5. 先调用 `list_templates()` 验证模板可见，再调用 `get_template()`、`run_template()` 或 `run_templates()` 使用。

> 模板依赖 ComfyUI App Mode，需要使用支持 App Mode 的 ComfyUI 版本。

## 安装依赖

本插件依赖以下 Python 包：

| 包名      | 版本要求  | 说明                             |
| --------- | --------- | -------------------------------- |
| `fastmcp` | >= 1.0.0  | MCP 协议框架                     |
| `uvicorn` | >= 0.30.0 | ASGI 服务器                      |
| `httpx`   | >= 0.27.0 | HTTP 客户端，用于与 ComfyUI 通信 |

### 安装方式

#### 方式一：使用 requirements.txt（推荐）

```bash
cd ComfyUI/custom_nodes/mcp-server
pip install -r requirements.txt
```

#### 方式二：手动安装

```bash
pip install fastmcp>=1.0.0 uvicorn>=0.30.0 httpx>=0.27.0
```

#### 方式三：使用 ComfyUI Manager

如果你使用 [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager)，安装本插件后会自动提示安装缺失的依赖。

> **注意**：如果使用 ComfyUI 便携版（Windows Portable），请使用自带的 Python 环境：
>
> ```bash
> ..\..\..\python_embeded\python.exe -m pip install -r requirements.txt
> ```

## 配置

### 环境变量

| 变量          | 默认值                  | 说明             |
| ------------- | ----------------------- | ---------------- |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI 服务地址 |
| `COMFYUI_PUBLIC_URL` | 同 `COMFYUI_URL` | 返回媒体链接时使用的公开访问地址 |
| `MCP_CONFIG` | 空 | 独立运行模式的 JSON 配置文件路径 |
| `MCP_TEMPLATE_DIR` | `./templates` | 模板 JSON 目录 |
| `MCP_HOST` | `0.0.0.0` | MCP 服务监听地址 |
| `MCP_PORT` | `8189` | MCP 服务端口 |

### 独立运行配置

插件也可以作为独立 MCP 服务运行，不依赖 ComfyUI 插件加载流程。此模式下 ComfyUI 和 MCP 可以部署在不同机器上，但执行模板仍需要 MCP 能访问 ComfyUI HTTP API。

创建 `mcp.config.json`：

```json
{
  "comfyui": {
    "apiUrl": "http://192.168.1.20:8188",
    "publicUrl": "http://192.168.1.20:8188",
    "headers": {}
  },
  "mcp": {
    "host": "0.0.0.0",
    "port": 8189
  },
  "templates": {
    "dir": "./templates"
  }
}
```

- `comfyui.apiUrl`：MCP 访问 ComfyUI API 使用的地址。MCP 和 ComfyUI 不在同一台机器时不要写 `127.0.0.1`。
- `comfyui.publicUrl`：返回图片、音频、GIF 链接时使用的地址。通常和 `apiUrl` 一样；如果经过反向代理，可写公网地址。
- `templates.dir`：MCP 本机的模板 JSON 目录。独立模式不读取 ComfyUI 机器上的模板目录。

启动独立 MCP 服务：

```bash
python standalone.py --config ./mcp.config.json
```

MCP 客户端连接：

```text
http://<mcp机器地址>:8189/mcp
```

### 启动

正常启动 ComfyUI，插件会自动加载并通过 ComfyUI 端口提供 MCP 服务：

```
MCP endpoint: http://127.0.0.1:8188/app-mcp
```

远程访问时需以 `--listen` 启动 ComfyUI：

```bash
python main.py --listen
```

## 工具列表

AI 助手通过 MCP 协议使用以下工具：

#### `list_templates`

列出所有可用模板，返回模板名称、标题、输入/输出数量。已禁用的模板不会出现在结果中。

#### `get_template(name)`

获取模板详情，包括：

- `title`：模板标题（从工作流中的 `title` MarkdownNote 节点提取，兼容 README）
- `description`：模板详细描述（从工作流中的 `description` MarkdownNote 节点提取，兼容 README）
- `inputs`：可配置的输入参数列表（名称、类型、默认值）
- `outputs`：输出节点列表

已禁用的模板不可查询，调用会返回错误。

#### `read_template_doc(name, title)`

读取模板文档中指定标题的内容，用于渐进式披露更详细的使用说明、示例或注意事项。

- `name`：模板名称
- `title`：文档标题，如 `usage`、`examples`、`tips`

已禁用的模板不可读取模板文档，调用会返回错误。

#### `run_template(name, params, wait=true, bindings="{}")`

执行模板，传入参数值。

- `name`：模板名称
- `params`：JSON 格式的参数值，如 `'{"positive_prompt": "a cat", "seed": 42}'`
- `wait`：是否等待执行完成（默认 `true`）。等待完成后直接返回格式化结果
- `bindings`：可选 JSON 字符串，用于从历史结果中取值并自动填入当前模板参数

已禁用的模板不可运行，调用会返回错误。

##### 输出格式

执行成功后返回精简的结构化结果：

```json
{
  "status": "completed",
  "prompt_id": "abc-123",
  "outputs": {
    "最终提示词_119_STRING": {
      "text": ["a cute cat, masterpiece, best quality..."]
    },
    "输出图片_122_output": {
      "media": [
        {
          "url": "http://127.0.0.1:8188/view?filename=output.png&subfolder=prompt_gallery&type=output",
          "type": "image",
          "filename": "output.png",
          "subfolder": "prompt_gallery",
          "item_type": "output"
        }
      ],
      "markdown": "![输出图片_122_output](http://127.0.0.1:8188/view?filename=output.png&subfolder=prompt_gallery&type=output)"
    }
  },
  "binding_hint": {
    "输出图片_122_output": {
      "from": "abc-123",
      "output": "输出图片_122_output",
      "type": "image",
      "index": 0
    }
  }
}
```

- `outputs`：精简后的输出，只包含 `media`（媒体）、`text`（文本）、`markdown`（可直接渲染的 Markdown）
- `binding_hint`：自动生成的 binding 配置，可直接复制到下一个调用的 `bindings` 参数

##### 使用 Binding 串联模板（推荐）

**重要：处理模板生成的图片时，必须使用 binding，不要手动上传！**

每次 `run_template` 执行后，结果中会包含 `binding_hint` 字段。串联模板时，直接将 `binding_hint` 中的值复制到下一个调用的 `bindings` 参数即可：

```python
# 第一步：生成图片
result1 = run_template("anima mcp.app", '{"提示词": "a cute cat"}')
# result1.binding_hint = {"输出图片_122_output": {"from": "abc-123", ...}}

# 第二步：加密（直接用 binding_hint）
result2 = run_template("图片加密.app", '{}', bindings='{"image": {"from": "abc-123", "output": "输出图片_122_output", "type": "image", "index": 0}}')
```

`upload_image` 仅用于用户提供的新图片（非模板生成的图片）。

#### `run_templates(pipeline, timeout_per_step=300)`

按顺序运行多个模板，并将上一步或任意前序步骤的输出绑定到后续步骤输入。

- `pipeline`：JSON 字符串，格式如下：

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
        "image": {
          "from": "generate",
          "output": "SaveImage_12_output",
          "type": "image",
          "index": 0
        }
      }
    }
  ]
}
```

- `timeout_per_step`：每一步的超时时间，单位秒，默认 `300`
- `bindings` 支持的 `type`：
  - `text`：读取上游 `text[index]`
  - `image`：读取上游图片媒体并重新上传到 ComfyUI input，再把返回文件名传给当前参数
  - `media_filename`：直接传上游媒体文件名
  - `media_url`：直接传上游媒体 URL

这里的 `from` 指向的是流水线中的步骤 `id`；而 `run_template(..., bindings=...)` 里的 `from` 指向的是历史 `prompt_id`。

执行失败时会返回失败步骤和已完成步骤结果，执行成功时返回所有步骤的结构化结果与最后一步输出，以及 `binding_hint`（`from` 为步骤 `id`）。

#### `upload_image(source, overwrite=true)`

上传图片到 ComfyUI（用于需要图片输入的模板）。

**注意：仅用于用户提供的新图片！** 处理模板生成的图片时，请使用 `binding_hint` 而非手动上传。

支持三种来源：

- **本地路径**：`E:/photos/input.png`
- **HTTP URL**：`https://example.com/image.png`
- **Base64**：`data:image/png;base64,iVBOR...`

上传后返回文件名，填入模板参数即可使用。

#### `list_models(folder="")`

查询 ComfyUI 模型目录或指定目录下的模型列表。

- 不传 `folder`：返回可查询的模型目录
- 传 `folder`：返回该目录下的模型文件，如 `checkpoints`、`loras`、`vae`、`controlnet`

#### `get_template_result(name, prompt_id, wait=false, timeout=300)`

获取执行结果。

- `wait=false`：立即返回当前状态（`pending`、`running`、`completed`），适合手动轮询
- `wait=true`：阻塞等待直到执行完成或超时。如果 `prompt_id` 不存在（不在队列也不在历史中），会在几秒内返回错误，不会傻等
- `timeout`：等待超时时间，单位秒，默认 `300`

### 3. ComfyUI 前端管理

在 **Settings → MCP Server** 中：

- **Status**：查看 MCP 服务状态和连接地址
- **Templates**：查看、刷新、禁用/启用、删除模板
- **Auto Extract Templates**：扫描所有工作流，自动为包含 `title` Markdown 节点且尚未存在模板的工作流创建模板
- **Batch Refresh Templates**：对当前所有模板执行批量刷新，从同名工作流重新提取输入、输出、标题和描述
- **Export Templates**：导出当前模板 JSON，下载 `mcp-templates.zip`

导出的压缩包只包含模板：

```text
mcp-templates.zip
└── templates/
    ├── txt2img.json
    └── upscale.json
```

独立部署时把 `templates/` 解压到 MCP 机器，并在 `mcp.config.json` 的 `templates.dir` 指向该目录即可。

## MCP 客户端配置

MCP 端点复用 ComfyUI 的端口，地址为 `http://<comfyui地址>/app-mcp`。

### Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

### Cursor

在 `.cursor/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

### 其他 MCP 客户端

连接地址：`http://<comfyui地址>/app-mcp`（Streamable HTTP 传输）

### 远程访问

ComfyUI 需要以 `--listen 0.0.0.0` 启动以接受局域网连接。之后手机或其他设备直接连接即可，图片链接会自动使用正确的地址：

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://192.168.0.113:8188/app-mcp"
    }
  }
}
```

> 无需手动配置 `comfyui_url`，服务端会从请求中自动推导。

## 日志

所有 MCP 调用都会在 ComfyUI 控制台打印，以 `[MCP]` 前缀标识：

```
[MCP] list_templates() → 3 templates
[MCP] run_template(name='txt2img', params={"positive_prompt": "a cat"}) → completed
[MCP] upload_image(source=E:/photos/input.png) → {"name": "input.png", "subfolder": "", "type": "input"}
```

代理请求以 `[MCP Proxy]` 标识，排查连接问题时可查看：

```
[MCP Proxy] POST /app-mcp → http://127.0.0.1:8189/mcp
[MCP Proxy] upstream error: ...  (连接内部 MCP 服务失败)
```

## 常见问题

### 模板列表为空

确保工作流已通过 ComfyUI 的 **Save**（非 Export）保存到服务器。

### 输出为空

确保工作流中 `linearData.outputs` 包含了需要返回的节点 ID。

### 参数映射错误

如果 ComfyUI 报 `value_not_in_list` 错误，说明 widget 值映射错位。重启 ComfyUI 让插件重新加载，或对模板点 **Refresh** 重新提取。

### 远程访问返回 421

确保 ComfyUI 以 `--listen` 启动。插件已自动禁用 MCP 的 DNS 重绑定保护，局域网 IP 应可直接访问。

### 图片输入不生效

如果是用户提供的新图片，先调用 `upload_image` 上传图片，将返回的文件名填入模板参数。

如果是模板生成的图片，请使用 `binding_hint` 进行串联，不要手动上传。

### Binding 失败

如果 binding 返回错误，检查：
1. `from` 是否是有效的 `prompt_id`（`run_template`）或步骤 `id`（`run_templates`）
2. `output` 是否是源结果中 `outputs` 存在的 key
3. `index` 是否在范围内

## 文件结构

```
mcp-server/
├── __init__.py          # ComfyUI 插件入口，启动 MCP 服务
├── server.py            # MCP 工具定义（list_templates, run_template 等）
├── standalone.py        # 独立 MCP HTTP 服务入口
├── config.py            # JSON 配置和环境变量读取
├── template_manager.py  # 模板 CRUD、工作流转换、执行引擎
├── comfyui_client.py    # ComfyUI HTTP 客户端
├── routes.py            # ComfyUI 前端 API 路由 + MCP 代理
├── js/
│   └── index.js         # 前端设置面板（模板管理 UI）
├── templates/           # 模板 JSON 存储目录（自动创建）
├── TEST_PLAN.md         # 测试计划文档
└── README.md            # 本文件
```
