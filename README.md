<p align="center">
  <img src="assets/header.svg" width="800" alt="Frok Banner">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/API-OpenAI%20|%20Anthropic%20|%20DeepSeek%20|%20阿里云-blue" alt="API">
  <img src="https://img.shields.io/badge/平台-Windows%20|%20Linux%20|%20macOS-lightgrey" alt="Platform">
</p>

---

**大模型API调用工具**，包含两个核心工具：

1. **api_tool** — 轻型命令行交互工具
2. **Frok** — 智能编程助手，自动调用工具完成任务

## 快速开始

```bash
# 安装依赖
pip install openai anthropic requests

# 使用轻型工具
python main.py

# 使用智能助手
python frok/main.py
```

## 演示

```
==================================================
    欢迎使用 Frok Code 智能编程助手
==================================================

你: 帮我写一个快速排序
Frok: [分析需求 → 编写代码 → 测试验证 → 完成]

你: 审查 main.py 的代码质量
Frok: [读取文件 → 代码分析 → 生成报告]

你: 帮我调试这个报错
Frok: [分析错误 → 定位问题 → 给出修复方案]
```

## 配置

编辑 `config.json`，填入 API Key:

```json
{
  "providers": {
    "deepseek": { "api_key": "你的密钥" },
    "mimo": { "api_key": "你的密钥" }
  }
}
```

## 轻型工具 (main.py)

手动输入命令操作的命令行交互工具。

```bash
python main.py
```

输入 `/help` 查看所有命令。

## Frok 智能助手 (frok/)

直接描述任务，Frok 会自动完成整个流程：

1. **理解需求** → 2. **规划步骤** → 3. **调用工具执行** → 4. **观察结果** → 5. **迭代优化** → 6. **完成任务**

### 示例

```
你: 帮我写一个快速排序
你: 审查 main.py 的代码质量
你: 初始化一个React项目
你: 调试这个报错
```

### 内置技能

| 技能    | 触发词               |
| ----- | ----------------- |
| 代码审查  | `审查` / `review`   |
| 调试助手  | `调试` / `debug`    |
| 代码重构  | `重构` / `refactor` |
| 文档生成  | `文档` / `docs`     |
| 代码解释  | `解释` / `explain`  |
| 测试生成  | `测试` / `test`     |
| 项目初始化 | `初始化` / `setup`   |
| 学习指南  | `学习` / `tutorial` |

## 支持的厂商

| 厂商        | 模型                              |
| --------- | ------------------------------- |
| OpenAI    | gpt-4, gpt-3.5-turbo            |
| Anthropic | claude-sonnet, claude-haiku     |
| 阿里云       | qwen-turbo, qwen-plus, qwen-max |
| DeepSeek  | deepseek-v4-pro, deepseek-chat  |
| MiMo      | mimo-v2.5-pro, mimo-v2-pro      |

## 核心功能

### 1. Plan 模式（规划执行）

复杂任务先生成计划，用户审核后再执行。

```
你: 帮我重构这个项目
Frok: [创建计划]
  1. 分析现有代码结构
  2. 设计新架构
  3. 逐步重构
  4. 运行测试验证
你: /plan 查看计划 → 批准
Frok: [执行计划...]
```

### 2. Subagent（并行执行）

多个独立任务并行执行，提高效率。

```
你: 并行执行: 检查代码风格 + 运行测试 + 生成文档
Frok: [创建3个子代理并行执行]
```

### 3. Hooks（事件钩子）

在工具调用前后执行自定义动作。

```json
{
  "post_tool_call": [
    {
      "name": "auto_format",
      "action": "black ${file}",
      "tools": ["write_file"]
    }
  ]
}
```

### 4. Git 增强（深度Git集成）

自动提交、差异展示、代码追溯。

```
你: 查看Git状态
你: 自动提交所有变更
你: 查看main.py的修改历史
```

### 5. Worktree（隔离工作空间）

创建隔离的开发环境，不影响主分支。

```
你: 创建一个新工作树开发feature-x
你: 查看所有工作树
你: 合并工作树的变更
```

### 6. CodeMap（代码地图）

分析代码结构，查找符号定义和引用。

```
你: 生成这个项目的代码地图
你: 查找FrokAgent类的定义
你: 查找所有使用tool_executor的地方
```

### 7. 多文件编辑（批量编辑）

同时编辑多个文件，支持撤销/重做。

```
你: 批量修改这10个文件的导入语句
你: 预览编辑结果
你: 撤销刚才的修改
```

### 8. 代码补全

智能代码补全建议。

```
你: 在这个位置获取补全建议
你: 获取内联代码建议
```

### 9. 沙箱执行（安全代码执行）

在隔离环境中执行代码，支持资源限制。

```
你: 执行这段Python代码
你: 运行这个JavaScript脚本
你: 执行Shell命令
```

## 命令列表

| 命令          | 说明         |
| ----------- | ---------- |
| `/help`     | 显示帮助       |
| `/skills`   | 列出技能       |
| `/status`   | 显示状态       |
| `/memory`   | 显示记忆       |
| `/plan`     | 显示当前计划     |
| `/planmode` | 切换 Plan 模式 |
| `/hooks`    | 列出 Hook    |
| `/agents`   | 列出子代理      |
| `/switch`   | 切换模型       |
| `/clear`    | 清空对话       |
| `/save`     | 保存会话       |
| `/quit`     | 退出         |

## 嵌入式开发

支持 Arduino/ESP32/STM32 嵌入式开发，提供串口通信工具：

```bash
# 串口调试工具
python serial_tool.py

# UART 通信演示
python uart_demo.py
```

## 文件结构

```
frok-llm-tool/
├── main.py               # 轻型工具入口
├── config.json           # 配置文件
├── requirements.txt      # 依赖
├── demo.py               # 演示脚本
├── serial_tool.py        # 串口调试工具
├── uart_demo.py          # UART 通信演示
│
├── frok/                 # 智能助手
│   ├── main.py           # 入口
│   ├── agent.py          # 智能体核心
│   ├── tools.py          # 工具系统
│   ├── memory.py         # 记忆系统
│   ├── skills.py         # 技能系统
│   ├── hooks.py          # Hooks 事件系统
│   ├── plan.py           # Plan 规划模式
│   ├── subagent.py       # Subagent 并行执行
│   ├── git_enhanced.py   # Git 深度集成
│   ├── worktree.py       # Worktree 隔离空间
│   ├── codemap.py        # 代码地图生成
│   ├── multi_edit.py     # 多文件批量编辑
│   ├── completion.py     # 代码补全引擎
│   ├── sandbox.py        # 沙箱执行环境
│   ├── diff_viewer.py    # 差异查看器
│   ├── embedded.py       # 嵌入式开发支持
│   ├── skills/           # 技能文件
│   ├── memory/           # 记忆文件
│   └── hooks/            # Hook 配置
│
├── arduino_serial/       # Arduino 串口示例
├── docs/                 # 文档
└── assets/               # 资源文件
```
