# ComfyUI MCP Server

[中文](./README.md) | [English](./README_EN.md)

把 ComfyUI App Mode 工作流包装成 MCP 工具，让 AI 助手可以像调用普通工具一样查询模板、执行工作流、串联多步生成，并处理图片等媒体结果。

如果有 BUG 或想要的功能，可以加群 `1082160486` 或提 issue。

## 适合什么场景

- **给 AI 暴露 ComfyUI 能力**：AI 只需要填写模板参数，不需要理解节点图。
- **复用 App Mode 工作流**：用 ComfyUI 前端标记输入、输出，再生成 MCP 模板。
- **批量与多步执行**：一次调用可运行多个独立任务，也可把前一步输出继续交给下一步处理。
- **查询本地模型**：支持让 AI 查询 `checkpoints`、`loras`、`vae` 等模型目录。

## 快速开始

1. 安装插件到 ComfyUI 的 `custom_nodes` 目录，并安装依赖：

   ```bash
   cd ComfyUI/custom_nodes
   git clone <this-repo-url> ComfyUI-APP-MCP
   cd ComfyUI-APP-MCP
   python -m pip install -r requirements.txt
   ```

2. 启动 ComfyUI，并确保使用支持 App Mode 的版本。
3. 打开工作流，在左上角菜单进入 **App Builder**。
4. 标记希望 AI 修改的内容为输入，标记保存图片等节点为输出，并把输入命名成清晰参数名。
5. 添加 Markdown Note 说明模板：
   - `title`：模板短标题，显示在模板列表中
   - `description`：模板详细说明，显示在模板详情中
   - 其他标题：作为可按需读取的模板文档
6. 在 **Settings → MCP Server → Templates** 点击 **Create from Workflow** 创建模板。
7. 在 MCP 客户端连接 `http://127.0.0.1:8188/app-mcp` 或 `http://127.0.0.1:8189/mcp`。
8. 让 AI 先调用 `list_templates()`，再调用 `get_template()`、`run_template()` 或 `run_templates()`。

工作流变更后，在设置面板对同名模板点击 **Refresh**。如果输入参数发生变化，提醒 AI 重新读取模板。

如果希望每次运行自动随机 seed，把 App Builder 中对应输入命名为 `seed`。运行时会自动填入随机值，AI 不需要传这个参数。

## 连接地址

| 入口             | 地址                            | 说明                                |
| ---------------- | ------------------------------- | ----------------------------------- |
| ComfyUI 代理入口 | `http://127.0.0.1:8188/app-mcp` | 通过 ComfyUI 端口访问 MCP           |
| MCP 直接入口     | `http://127.0.0.1:8189/mcp`     | 随 ComfyUI 一起启动，和上面用法一致 |

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

也可以把 `url` 换成：

```text
http://127.0.0.1:8189/mcp
```

远程访问 ComfyUI 时，使用 `python main.py --listen` 启动。

局域网或远程访问时，把 `127.0.0.1` 换成实际 ComfyUI/MCP 机器地址。更多部署方式见 [独立部署与远程访问](./docs/zh/standalone.md)。

## 常用工具

| 工具                             | 用途                         | 什么时候用                           |
| -------------------------------- | ---------------------------- | ------------------------------------ |
| `list_templates()`               | 查看可用模板                 | 开始任务前先查有哪些能力             |
| `get_template(name)`             | 读取模板参数、输出、文档入口 | 执行前确认参数怎么填                 |
| `read_template_doc(name, title)` | 读取模板的扩展说明           | `description` 提到更多文档时使用     |
| `run_template()`                 | 执行单个模板                 | 文生图、图生图、放大、加密等单步任务 |
| `run_templates()`                | 一次运行多个任务并返回每一步结果 | 批量生成，或生成 → 放大等多步处理    |
| `upload_image(source)`           | 上传用户提供的新图片         | 图片来自用户本地、URL 或 base64 时   |
| `list_models(folder, keywords)`  | 查询模型目录                 | 需要选择 checkpoint、LoRA、VAE 时    |
| `get_template_result()`          | 查询或继续等待结果           | `run_template` 超时或异步等待时      |
| `interrupt_task(run_id)`         | 中断运行中或排队中的任务     | 不再需要某次异步或超时任务时         |

完整参数、返回结构和示例见 [工具参考](./docs/zh/tools.md)。

## 前端管理

在 **Settings → MCP Server** 中可以：

- 查看 MCP 服务状态和连接地址
- 设置 `run_template(wait=true)` 默认等待超时
- 创建、刷新、启用、禁用、删除模板
- 扫描工作流并自动创建缺失模板
- 批量刷新已有模板
- 导出模板 zip，用于独立部署

更多说明见 [工具参考：前端管理](./docs/zh/tools.md#comfyui-前端管理)。

## 文档导航

| 文档                                          | 内容                                                 |
| --------------------------------------------- | ---------------------------------------------------- |
| [工具参考](./docs/zh/tools.md)                | MCP 工具参数、返回格式、模板串联、上传图片、模型查询 |
| [独立部署与远程访问](./docs/zh/standalone.md) | 环境变量、独立配置、媒体代理、客户端连接             |
| [故障排查](./docs/zh/troubleshooting.md)      | 模板为空、输出为空、图片输入、远程访问、日志         |
| [开发说明](./docs/zh/development.md)          | 代码结构、测试建议、开发命令                         |
| [文档索引](./docs/README.md)                  | 中英文文档入口                                       |

## 最常见问题

### 模板列表为空

确保工作流已通过 ComfyUI 的 **Save** 保存到服务器，而不是只用 **Export** 导出到本地。

### 图片输入不生效

用户提供的新图片先用 `upload_image()` 上传，再把返回的 `name` 填入模板参数。模板生成的图片交给 AI 串联即可，不需要手动上传。

### 创建模板时找不到工作流

确认 ComfyUI 是否运行在 `8188` 端口。插件默认通过 `COMFYUI_URL=http://127.0.0.1:8188` 读取工作流；如果你的 ComfyUI 端口不是 `8188`，启动前设置：

```bash
COMFYUI_URL=http://127.0.0.1:<你的端口>
```

### 接入 AstrBot 等平台后图片发不出来

确认 AI 调用平台发送工具时参数类型正确。常见错误是把图片 URL 填到 `path` 这类本地文件路径参数里；如果平台工具区分 `url`、`image_url`、`file`、`path`，应按工具要求传对应字段。

更多排查方式见 [故障排查](./docs/zh/troubleshooting.md)。
