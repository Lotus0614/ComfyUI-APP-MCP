# 开发说明

[← 返回 README](../../README.md) | [文档索引](../README.md) | [工具参考](./tools.md) | [故障排查](./troubleshooting.md)

## 目录结构

```text
ComfyUI-APP-MCP/
├── __init__.py          # ComfyUI 插件入口，启动 MCP 服务
├── server.py            # MCP 工具定义
├── standalone.py        # 独立 MCP HTTP 服务入口
├── config.py            # JSON 配置和环境变量读取
├── template_manager.py  # 模板 CRUD、工作流转换、执行引擎
├── comfyui_client.py    # ComfyUI HTTP 客户端
├── routes.py            # ComfyUI 前端 API 路由与 MCP 代理
├── js/                  # ComfyUI 前端设置面板
├── docs/                # 详细文档
├── templates/           # 模板 JSON 存储目录，Git 忽略
└── TEST_PLAN.md         # 手动测试计划
```

## 常用命令

安装依赖：

```bash
python -m pip install -r requirements.txt
```

独立启动：

```bash
python standalone.py --config standalone_example/mcp.config.json
```

Python 语法检查：

```bash
python -m compileall .
```

## 前端开发

前端代码位于 `js/`：

- `js/core/`：API、配置、国际化、工作流转换等可复用逻辑
- `js/ui/`：设置面板、弹窗、模板管理 UI
- `js/index.js`：ComfyUI 扩展注册入口

ComfyUI 会直接加载 `js/` 文件，没有单独构建步骤。

## 测试建议

项目主要依赖手动集成测试。重点覆盖：

- 模板创建、刷新、禁用、删除
- `list_templates()`、`get_template()`、`run_template()`
- `run_templates()` 多步绑定
- `upload_image()` 本地路径、URL、base64
- 生成超时后 `get_template_result()`
- 独立 MCP 服务与媒体代理

更完整场景见 `TEST_PLAN.md`。

## 提交建议

- 用户可见行为变更同步更新 `README.md` 和 `README_EN.md`。
- 设置面板 UI 变更建议附截图。
- 不提交本地凭据、`mcp_enabled.json` 或生成的 `templates/`。
