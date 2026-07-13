# 独立部署与远程访问

[← 返回 README](../../README.md) | [文档索引](../README.md) | [工具参考](./tools.md) | [故障排查](./troubleshooting.md)

默认情况下，插件会跟随 ComfyUI 启动，并同时提供两个 MCP 入口：ComfyUI 代理入口和 MCP 直接入口。两者用法一致，任选一个连接即可。

## 两个连接入口

| 入口 | MCP 地址 | 特点 |
| --- | --- | --- |
| ComfyUI 代理入口 | `http://127.0.0.1:8188/app-mcp` | 通过 ComfyUI 端口访问 MCP |
| MCP 直接入口 | `http://127.0.0.1:8189/mcp` | 随 ComfyUI 一起启动，不经过 ComfyUI 代理路径 |

远程访问 ComfyUI 时，使用：

```bash
python main.py --listen
```

局域网访问时，把 `127.0.0.1` 换成运行 ComfyUI 的机器地址。

如果需要让 MCP 和 ComfyUI 分开部署，再使用下面的独立运行配置。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | MCP 访问 ComfyUI API 使用的地址 |
| `COMFYUI_PUBLIC_URL` | 同 `COMFYUI_URL` | 关闭媒体代理时返回媒体链接使用 |
| `MCP_CONFIG` | 空 | 独立运行模式的 JSON 配置文件路径 |
| `MCP_TEMPLATE_DIR` | `./templates` | 模板 JSON 目录 |
| `MCP_HOST` | `0.0.0.0` | MCP 服务监听地址 |
| `MCP_PORT` | `8189` | MCP 服务端口 |
| `MCP_MEDIA_PROXY` | `true` | 媒体链接是否通过 MCP `/view` 代理 |

## 独立配置文件

创建 `mcp.config.json`：

```json
{
  "comfyui": {
    "apiUrl": "http://192.168.1.20:8188",
    "headers": {}
  },
  "mcp": {
    "host": "0.0.0.0",
    "port": 8189,
    "mediaProxy": true
  },
  "templates": {
    "dir": "./templates"
  }
}
```

字段说明：

- `comfyui.apiUrl`：MCP 访问 ComfyUI API 的地址。MCP 和 ComfyUI 不在同一台机器时不要写 `127.0.0.1`。
- `mcp.mediaProxy`：为 `true` 时，结果中的媒体链接指向 MCP `/view`，由 MCP 转发到 ComfyUI `/view`。
- `templates.dir`：MCP 本机模板目录。独立模式不读取 ComfyUI 机器上的模板目录。

通常建议保持 `mcp.mediaProxy=true`。只有关闭媒体代理，或希望媒体链接返回自定义 ComfyUI 公网地址时，才配置：

```json
{
  "comfyui": {
    "publicUrl": "https://comfy.example.com"
  }
}
```

## 启动独立 MCP 服务

```bash
python standalone.py --config ./mcp.config.json
```

客户端连接：

```text
http://<mcp机器地址>:8189/mcp
```

## MCP 客户端配置

多数 MCP 客户端都可以使用下面的 JSON：

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://127.0.0.1:8188/app-mcp"
    }
  }
}
```

如需直连 MCP 端口，把 `url` 换成：

```text
http://127.0.0.1:8189/mcp
```

### Claude Desktop

把上面的 JSON 写入 `claude_desktop_config.json`。

### Cursor

把上面的 JSON 写入 `.cursor/mcp.json`。

### 局域网示例

```json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://192.168.0.113:8188/app-mcp"
    }
  }
}
```

## 模板迁移

在 ComfyUI 前端 **Settings → MCP Server → Templates → Export Templates** 导出 `mcp-templates.zip`。

独立部署时，把压缩包中的 `templates/` 解压到 MCP 机器，并在 `mcp.config.json` 的 `templates.dir` 指向该目录。
