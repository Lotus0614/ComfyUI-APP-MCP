# ComfyUI MCP Server 数据流程

## 一、创建模板阶段

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 (index.js)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  用户点击 "Create from Workflow"                                             │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────┐                                                    │
│  │ GET /workflows/{name}│ ──→ 获取原始 workflow JSON                         │
│  └─────────────────────┘                                                    │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │ generateApiPrompt(workflow)                          │                    │
│  │   1. 保存当前画布状态 (app.graph.serialize())         │                    │
│  │   2. app.graph.configure(workflow) ← 配置到画布       │                    │
│  │   3. app.graphToPrompt()          ← 前端转换          │                    │
│  │   4. 恢复原始画布状态                                  │                    │
│  │                                                      │                    │
│  │   返回: { output: api_prompt }                        │                    │
│  └─────────────────────────────────────────────────────┘                    │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │ POST /templates                                      │                    │
│  │ {                                                    │                    │
│  │   name: "anima mcp.app",                             │                    │
│  │   workflow: { nodes, links, extra, ... },             │                    │
│  │   api_prompt: { "19": { class_type, inputs }, ... }   │                    │
│  │ }                                                    │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            后端 (routes.py)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  create_template(request)                                                   │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │ save_template(name, workflow, api_prompt=api_prompt)  │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        后端 (template_manager.py)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  save_template(name, workflow, api_prompt)                                  │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │ extract_template_info(workflow)                       │                    │
│  │   ├─ _extract_title_and_description()                 │                    │
│  │   │    └─ 从 MarkdownNote 节点提取 title/description   │                    │
│  │   ├─ _extract_inputs(workflow, node_defs)             │                    │
│  │   │    └─ 从 linearData.inputs 提取输入参数            │                    │
│  │   │         ├─ 遍历 node.inputs 查找 widget            │                    │
│  │   │         └─ fallback: 查找 hidden inputs            │                    │
│  │   └─ _detect_output_nodes(workflow)                   │                    │
│  │        └─ 从 linearData.outputs 或终端节点提取输出      │                    │
│  └─────────────────────────────────────────────────────┘                    │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │ 构建 template 对象                                    │                    │
│  │ {                                                    │                    │
│  │   name: "anima mcp.app",                             │                    │
│  │   title: "二次元风格文生图模板",                         │                    │
│  │   description: "...",                                 │                    │
│  │   disabled: false,                                    │                    │
│  │   workflow: { ... },           ← 原始工作流（用于编辑） │                    │
│  │   api_prompt: { ... },         ← 预转换 API 格式       │                    │
│  │   inputs: {                   ← 提取的输入参数定义      │                    │
│  │     "提示词": { node_id: 124, widget: "text_3", ... }, │                    │
│  │     "lora_loader_data": { node_id: 128, ... },        │                    │
│  │     ...                                               │                    │
│  │   },                                                  │                    │
│  │   outputs: {                  ← 提取的输出定义          │                    │
│  │     "输出图片_122_output": { node_id: 122, ... },      │                    │
│  │     ...                                               │                    │
│  │   }                                                   │                    │
│  │ }                                                    │                    │
│  └─────────────────────────────────────────────────────┘                    │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │ 写入 JSON 文件                                        │                    │
│  │ templates/anima mcp.app.json                         │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 二、存储格式

```json
{
  "name": "anima mcp.app",
  "title": "二次元风格文生图模板",
  "description": "...",
  "disabled": false,

  "workflow": {
    // 原始工作流（前端编辑用）
    "nodes": [ ... ],
    "links": [ ... ],
    "extra": { "linearData": { ... } }
  },

  "api_prompt": {
    // 预转换的 API 格式（执行用）
    "19": {
      "class_type": "KSampler",
      "inputs": {
        "model": ["128", 0],          // 连接引用 [源节点id, 输出索引]
        "seed": 589352040529576,       // widget 值
        "steps": 15,
        "cfg": 2.0
      }
    },
    "128": {
      "class_type": "ZmlPowerLoraLoader",
      "inputs": {
        "model": ["44", 0],
        "clip": ["45", 0],
        "lora_loader_data": "{\"entries\":[]}",  // hidden input
        "lora_names_hidden": ""
      }
    }
  },

  "inputs": {
    // 输入参数定义
    "提示词": {
      "node_id": 124,
      "widget": "text_3",
      "type": "STRING",
      "default": "1girl."
    },
    "lora_loader_data": {
      "node_id": 128,
      "widget": "lora_loader_data",
      "type": "STRING",
      "default": "{\"entries\":[]}"
    },
    "width": { "node_id": 110, "widget": "width", "type": "INT", "default": 1024 }
  },

  "outputs": {
    // 输出定义
    "最终提示词_119_STRING": { "node_id": 119, "type": "text", ... },
    "输出图片_122_output": { "node_id": 122, "type": "unknown", ... }
  }
}
```

## 三、运行时执行阶段

```
用户调用: run_template("anima mcp.app", {"提示词": "a cute cat", "lora_loader_data": "..."})
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      execute_template() 执行流程                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ① 加载模板                                                                  │
│     template = get_template("anima mcp.app")                                │
│         │                                                                   │
│         ▼                                                                   │
│  ② 验证模板                                                                  │
│     ├─ 模板是否存在？                                                          │
│     └─ 模板是否禁用？                                                          │
│         │                                                                   │
│         ▼                                                                   │
│  ③ 解析 bindings（如果有）                                                     │
│     params = {"提示词": "a cute cat", "lora_loader_data": "..."}             │
│     bindings = {"输入图片": {"from": "xxx", "output": "...", ...}}           │
│         │                                                                   │
│         ▼                                                                   │
│     _resolve_run_bindings(bindings)                                          │
│       ├─ 从 mcp_outputs_cache 获取历史结果                                    │
│       ├─ 对 image 类型：下载 → 重传到 input 目录                               │
│       └─ 合并到 params                                                       │
│         │                                                                   │
│         ▼                                                                   │
│  ④ 注入参数到 API prompt                                                      │
│     api_prompt_data = template["api_prompt"]                                 │
│         │                                                                   │
│         ▼                                                                   │
│     _inject_widget_values(api_prompt_data, inputs, params)                   │
│       ┌─────────────────────────────────────────────────────┐               │
│       │ api_prompt = copy.deepcopy(api_prompt_data)          │               │
│       │                                                      │               │
│       │ for param_name, value in params.items():             │               │
│       │   inp = inputs[param_name]    // {node_id, widget}   │               │
│       │   node_id = str(inp["node_id"])  // "124"            │               │
│       │   widget = inp["widget"]         // "text_3"         │               │
│       │                                                      │               │
│       │   api_prompt["124"]["inputs"]["text_3"] = value      │               │
│       │                                                      │               │
│       │ return api_prompt                                    │               │
│       └─────────────────────────────────────────────────────┘               │
│         │                                                                   │
│         ▼                                                                   │
│  ⑤ 提交到 ComfyUI                                                            │
│     result = await queue_prompt(api_prompt)                                  │
│         │                                                                   │
│         ▼                                                                   │
│  ⑥ 等待结果（如果 wait=true）                                                  │
│     _wait_for_result(prompt_id, outputs, timeout)                           │
│       ├─ 轮询 /history/{prompt_id}                                           │
│       ├─ 检查队列状态（避免无效 prompt 傻等）                                    │
│       └─ 完成后调用 _extract_outputs() 提取结果                                │
│         │                                                                   │
│         ▼                                                                   │
│  ⑦ 返回结果                                                                  │
│     {                                                                       │
│       "status": "completed",                                                │
│       "prompt_id": "xxx",                                                   │
│       "outputs": {                                                          │
│         "输出图片_122_output": {                                              │
│           "media": [{ "url": "...", "type": "image", ... }],                │
│           "markdown": "![输出图片](http://...)"                               │
│         }                                                                   │
│       },                                                                    │
│       "binding_hint": { ... }                                               │
│     }                                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 四、关键数据依赖

```
                    ┌──────────────────┐
                    │   /object_info   │  ← ComfyUI 节点定义
                    └────────┬─────────┘
                             │
                             ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│   workflow   │───→│ extract_template │───→│   inputs     │
│  (UI 格式)   │    │     _info()      │    │  (参数定义)   │
└──────────────┘    └──────────────────┘    └──────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   api_prompt     │  ← 前端 graphToPrompt()
                    │  (API 格式)      │
                    └──────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│   存储到     │    │   运行时注入      │    │   提交到     │
│   JSON 文件  │    │   widget 值       │    │   ComfyUI    │
└──────────────┘    └──────────────────┘    └──────────────┘
```

## 五、代码结构

```
template_manager.py
├── 模板管理
│   ├── save_template()          # 保存模板
│   ├── get_template()           # 获取模板
│   ├── update_template()        # 更新模板
│   └── delete_template()        # 删除模板
│
├── 输入提取
│   ├── _extract_inputs()        # 从 linearData 提取输入
│   ├── _read_widget_default()   # 读取 widget 默认值
│   └── _is_widget_input()       # 判断是否为 widget
│
├── 输出提取
│   └── _detect_output_nodes()   # 检测输出节点
│
├── 执行
│   ├── execute_template()       # 执行模板
│   ├── _inject_widget_values()  # 注入参数（15 行）
│   ├── _resolve_run_bindings()  # 解析 bindings
│   └── _wait_for_result()       # 等待结果
│
└── 输出处理
    └── _extract_outputs()       # 提取输出结果
```

## 六、前端 graphToPrompt 转换逻辑

前端 `app.graphToPrompt()` 的核心逻辑：

```javascript
graphToPrompt = async (graph) => {
  // 1. 应用虚拟节点（如 Reroute）
  for (let node of graph.computeExecutionOrder(false)) {
    node.isVirtualNode && node.applyToGraph?.();
  }

  // 2. 序列化工作流
  let workflow = graph.serialize();

  // 3. 构建 API 格式
  let output = {};
  for (let node of nodeMap.values()) {
    let inputs = {};
    let { widgets } = node;

    // 4. 处理 widgets（直接从 node.widgets 获取值）
    if (widgets) {
      for (let [index, widget] of widgets.entries()) {
        let value = widget.serializeValue 
          ? await widget.serializeValue(node, index) 
          : widget.value;
        inputs[widget.name] = value;
      }
    }

    // 5. 处理输入连接
    for (let [index, input] of node.inputs.entries()) {
      let resolved = node.resolveInput(index);
      if (resolved) {
        if (resolved.widgetInfo) {
          inputs[input.name] = resolved.widgetInfo.value;
          continue;
        }
        inputs[input.name] = [String(resolved.origin_id), parseInt(resolved.origin_slot)];
      }
    }

    output[String(node.id)] = {
      inputs,
      class_type: node.comfyClass,
      _meta: { title: node.title }
    };
  }

  return { workflow, output };
};
```

**关键点：**
- 前端直接从 `node.widgets` 获取值，不需要复杂的索引计算
- `node.resolveInput()` 自动处理连接关系
- Hidden inputs 自动包含在 `node.widgets` 中
