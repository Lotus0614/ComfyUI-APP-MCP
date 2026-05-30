# ComfyUI MCP Server

一个 ComfyUI 自定义节点插件，将 ComfyUI 应用封装为 **模板（Template）**，通过 MCP（Model Context Protocol）协议让 AI 助手（Claude、Cursor 等）直接调用 ComfyUI 进行图片、音频等多媒体生成。

## 核心概念

### 模板（Template）

模板 = ComfyUI 应用 + 自动提取的输入/输出定义。

- **输入（Inputs）**：从工作流中标记为 `linearData.inputs` 的节点自动提取，AI 只需提供参数值即可
- **输出（Outputs）**：从工作流中 `linearData.outputs` 标记的节点提取，生成完成后返回结果
- AI 无需了解 ComfyUI 内部结构，只需调用 `run_template` 传入参数

### 如何创建模板

- 模板依赖 Comfyui App Mode ！需要支持 App Mode 的 ComfyUI 版本。
- 在工作流构菜单中点击构建应用，标记输入输出节点，将输入节点重命名为AI好理解的名字。
- 加入 Markdown 节点，将标题重命名为 [README] （只有这个标题会被提取），可以详细描述模板的功能、输入参数、输出节点等信息，方便AI理解。
- 保存工作流，打开ComfyUI设置，找到 MCP Server → Templates，点击 Create from Workflow 选择已保存的工作流，系统自动提取输入参数和输出节点，点击 Create Template 完成创建。
- 在其他支持MCP的平台添加对应MCP，类型为 streamable_http，地址为 http://127.0.0.1:8189/mcp。
- 让ai列出模板测试是否能正常工作

```
ComfyUI/
  custom_nodes/
    mcp-server/
      __init__.py
      server.py
      template_manager.py
      comfyui_client.py
      routes.py
      js/
        index.js
      skill_guide.md
      README.md
```

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
| `MCP_PORT`    | `8189`                  | MCP 服务端口     |
| `MCP_HOST`    | `127.0.0.1`             | MCP 服务监听地址 |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI 服务地址 |

### 启动

正常启动 ComfyUI，插件会自动加载并在 `8189` 端口启动 MCP 服务：

```
MCP Server starting at http://127.0.0.1:8189/mcp
```

MCP 端点地址：`http://127.0.0.1:8189/mcp`

## 使用流程

### 1. 创建模板

在 ComfyUI 前端 **Settings → MCP Server → Templates** 中：

1. 点击 **Create from Workflow**
2. 从下拉列表选择已保存的工作流
3. 系统自动提取输入参数和输出节点
4. 点击 **Create Template** 完成创建

也可以通过前端对已有模板点 **Refresh** 重新提取输入/输出定义。

### 2. AI 调用模板

AI 助手通过 MCP 协议使用以下工具：

#### `list_templates`

列出所有可用模板，返回模板名称、描述、输入/输出数量。

#### `get_template(name)`

获取模板详情，包括：

- `description`：模板描述（从工作流中的 README 节点提取）
- `inputs`：可配置的输入参数列表（名称、类型、默认值）
- `outputs`：输出节点列表

#### `run_template(name, params, wait=true)`

执行模板，传入参数值。

- `name`：模板名称
- `params`：JSON 格式的参数值，如 `'{"positive_prompt": "a cat", "seed": 42}'`
- `wait`：是否等待执行完成（默认 `true`）。等待完成后直接返回格式化结果

返回结果包含：

- 文本输出：直接展示
- 图片输出：Markdown 图片链接 `![image](url)`
- 音频输出：`🔊 **Audio**: [filename](url)`

#### `upload_image(source, overwrite=true)`

上传图片到 ComfyUI（用于需要图片输入的模板）。

支持三种来源：

- **本地路径**：`E:/photos/input.png`
- **HTTP URL**：`https://example.com/image.png`
- **Base64**：`data:image/png;base64,iVBOR...`

上传后返回文件名，填入模板参数即可使用。

#### `get_template_result(name, prompt_id)`

轮询获取执行结果（当 `wait=false` 时使用）。

### 3. ComfyUI 前端管理

在 **Settings → MCP Server** 中：

- **Status**：查看 MCP 服务状态和连接地址
- **Templates**：查看、刷新、删除模板

## MCP 客户端配置

### Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
    "mcpServers": {
        "comfyui": {
            "url": "http://127.0.0.1:8189/mcp"
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
            "url": "http://127.0.0.1:8189/mcp"
        }
    }
}
```

### 其他 MCP 客户端

连接地址：`http://127.0.0.1:8189/mcp`（Streamable HTTP 传输）

## 日志

所有 MCP 调用都会在 ComfyUI 控制台打印，以 `[MCP]` 前缀标识：

```
[MCP] list_templates() → 3 templates
[MCP] run_template(name='txt2img', params={"positive_prompt": "a cat"}) → completed
[MCP] upload_image(source=E:/photos/input.png) → {"name": "input.png", "subfolder": "", "type": "input"}
```

## 常见问题

### 模板列表为空

确保工作流已通过 ComfyUI 的 **Save**（非 Export）保存到服务器。

### 输出为空

确保工作流中 `linearData.outputs` 包含了需要返回的节点 ID。

### 参数映射错误

如果 ComfyUI 报 `value_not_in_list` 错误，说明 widget 值映射错位。重启 ComfyUI 让插件重新加载，或对模板点 **Refresh** 重新提取。

### 图片输入不生效

先调用 `upload_image` 上传图片，将返回的文件名填入模板参数。

## 文件结构

```
mcp-server/
├── __init__.py          # ComfyUI 插件入口，启动 MCP 服务
├── server.py            # MCP 工具定义（list_templates, run_template 等）
├── template_manager.py  # 模板 CRUD、工作流转换、执行引擎
├── comfyui_client.py    # ComfyUI HTTP 客户端
├── routes.py            # ComfyUI 前端 API 路由
├── js/
│   └── index.js         # 前端设置面板（模板管理 UI）
├── templates/           # 模板 JSON 存储目录（自动创建）
├── skill_guide.md       # AI 角色扮演技能指南
└── README.md            # 本文件
```
