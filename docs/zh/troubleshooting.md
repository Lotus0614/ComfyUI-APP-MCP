# 故障排查

[← 返回 README](../../README.md) | [文档索引](../README.md) | [工具参考](./tools.md) | [独立部署](./standalone.md)

## 先看日志

MCP 调用会在 ComfyUI 控制台打印，以 `[MCP]` 为前缀：

```text
[MCP] list_templates() → 3 templates
[MCP] run_template(name='txt2img', params={"positive_prompt": "a cat"}) → completed
[MCP] upload_image(source=E:/photos/input.png) → {"name": "mcp_4b2f...a91c.png", "subfolder": "", "type": "input"}
```

代理请求以 `[MCP Proxy]` 为前缀：

```text
[MCP Proxy] POST /app-mcp → http://127.0.0.1:8189/mcp
[MCP Proxy] upstream error: ...
```

## 模板列表为空

检查：

1. 工作流是否通过 ComfyUI 的 **Save** 保存到服务器。
2. 是否只是使用了 **Export**。Export 只导出到本地，不一定进入服务器工作流列表。
3. 工作流是否已经在 **Settings → MCP Server → Templates** 中创建为模板。
4. 模板是否被禁用。禁用模板不会出现在 `list_templates()` 中。

## 创建模板时找不到工作流

插件模式会自动读取 ComfyUI 的实际启动端口，并通过本机回环地址访问 ComfyUI API。

如果需要覆盖自动检测的地址，启动前设置：

```bash
COMFYUI_URL=http://<ComfyUI 主机>:<端口>
```

如果是独立部署，也可以在 `mcp.config.json` 中设置 `comfyui.apiUrl`。详见 [独立部署与远程访问](./standalone.md)。

## 输出为空

检查 App Builder 中是否标记了输出节点。模板会优先读取工作流中的 `linearData.outputs`。

如果修改了输出配置，对同名模板点击 **Refresh** 重新提取。

## 随机 seed 不工作

把需要自动随机刷新的输入命名为 `seed`。运行时会自动填入随机 seed，`get_template()` 不会把该参数暴露给 AI，AI 也不需要传 `seed`。

## 参数映射错误

如果 ComfyUI 报 `value_not_in_list`，通常是 widget 值映射错位。

可尝试：

1. 重启 ComfyUI，让插件重新加载节点定义。
2. 在模板面板对该模板点击 **Refresh**。
3. 让 AI 重新调用 `get_template()` 获取最新参数。

## 远程访问返回 421

检查：

1. ComfyUI 是否以 `--listen` 启动。
2. MCP 客户端连接的地址是否是可访问的局域网 IP 或域名。
3. 如果使用反向代理，确认代理正确转发到 ComfyUI 或独立 MCP 端口。

## 图片输入不生效

判断图片来源：

- 用户提供的新图片：调用 `upload_image()`，把返回的 `name` 填入模板参数。
- 模板生成的图片：不要手动上传，交给 AI 使用模板串联能力处理。

## 接入 AstrBot 等平台后图片发不出来

优先检查 AI 调用平台发送工具时的参数类型。

常见问题：

- 把图片 URL 填进 `path`、`file_path` 这类本地文件路径参数。
- 平台发送工具要求 `url` 或 `image_url`，但 AI 传成了本地路径字段。
- 平台只接受本地文件，此时需要先下载图片，再把本地路径传给发送工具。

建议让 AI 重新查看平台发送工具的参数说明，并按 `url` / `path` / `file` 的实际含义传参。

## 模板串联失败

检查：

1. 让 AI 重新调用 `get_template()` 确认目标模板输入。
2. 确认上一步确实生成了需要的图片、音频或文本。
3. 让 AI 参考 [工具参考：Bindings 串联](./tools.md#bindings-串联) 重新组织调用。

## 生成超时

`run_template(wait=true)` 超时不代表任务失败。使用返回的 `run_id` 继续等待：

```text
get_template_result(name, run_id, wait=true)
```

默认等待时间可在 **Settings → MCP Server → Execution → Run Template Timeout** 中调整。
