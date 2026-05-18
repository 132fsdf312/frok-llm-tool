"""
Frok Code 智能体核心
思考-行动-观察循环，自动调用工具完成任务
"""

import json
import sys
import os
from typing import Dict, List, Optional
from pathlib import Path

from tools import ToolExecutor, TOOLS_SCHEMA, get_tools_for_prompt, parse_tool_calls
from memory import MemoryManager, MEMORY_TOOLS
from skills import SkillManager, SKILL_TOOLS
from hooks import HookManager, HOOK_TOOLS
from plan import PlanManager, PLAN_TOOLS, PlanStatus
from subagent import SubagentManager, SUBAGENT_TOOLS, SubagentConfig
from git_enhanced import GitEnhanced, GIT_ENHANCED_TOOLS
from worktree import WorktreeManager, WORKTREE_TOOLS
from codemap import CodeMapGenerator, CODEMAP_TOOLS
from multi_edit import MultiFileEditor, MULTI_EDIT_TOOLS
from completion import CodeCompletion, COMPLETION_TOOLS
from sandbox import SandboxExecutor, SANDBOX_TOOLS, SandboxConfig, ResourceLimits
from cli import FrokCLI, Colors, cli
from diff_viewer import DiffGenerator, DiffFormatter, CodeReviewer, DIFF_VIEWER_TOOLS

# 嵌入式工具（可选依赖）
try:
    from embedded import EMBEDDED_TOOLS, get_executor as get_embedded_executor, EmbeddedToolExecutor
    _HAS_EMBEDDED = True
except ImportError:
    _HAS_EMBEDDED = False
    EmbeddedToolExecutor = None

# ==================== 系统提示词 ====================

SYSTEM_PROMPT = """你是 Frok Code，一个智能编程助手。你不是普通聊天机器人，你是一个能操作电脑的智能体。

# 核心行为规则
- 用户的每个请求都必须通过调用工具来完成，绝对不能只用文字回复
- 不要说"我无法创建文件"——你有 write_file 工具，可以直接创建文件
- 不要说"请手动操作"——你有 execute_command 工具，可以直接执行命令
- 每次回复都必须包含至少一个 tool_call

# 工具列表
你可以调用以下工具：

## 文件操作
- write_file(path, content): 创建或写入文件
- read_file(path, start_line, end_line): 读取文件
- edit_file(path, old_string, new_string): 编辑文件（精确替换）
- append_file(path, content): 追加内容到文件
- delete_file(path): 删除文件
- copy_file(source, destination): 复制文件
- move_file(source, destination): 移动文件
- create_directory(path): 创建文件夹

## 搜索
- search_files(directory, pattern, glob): 搜索文件内容
- find_files(directory, pattern): 查找文件
- list_directory(path, show_hidden): 列出目录
- get_tree(path, max_depth): 目录树

## 系统
- execute_command(command, working_directory): 执行命令
- git_command(subcommand, args): Git操作
- ask_user(question): 向用户提问
- finish(result): 完成任务

## 记忆
- remember_user(key, value): 记住用户信息
- remember_project(key, value): 记住项目信息
- remember_feedback(feedback, category): 记住反馈
- recall_memory(type, key): 回忆记忆

## 技能
- list_skills(): 列出技能
- use_skill(skill_name, task): 使用技能
- create_skill(name, description, trigger, system_prompt, steps): 创建技能

## Plan模式 (复杂任务规划)
- create_plan(task, description, steps): 创建执行计划
- approve_plan(plan_id): 批准计划
- execute_plan(plan_id): 执行计划
- show_plan(plan_id): 显示计划
- list_plans(): 列出所有计划

## Subagent (并行执行)
- spawn_agent(task, tools): 创建子代理
- parallel_tasks(tasks): 并行执行多个任务
- list_agents(): 列出子代理
- collect_result(agent_id): 收集结果

## Hooks (事件钩子)
- list_hooks(event): 列出Hook
- register_hook(event, name, action, tools, description, blocking): 注册Hook
- enable_hook(hook_id): 启用Hook
- disable_hook(hook_id): 禁用Hook

## Git增强 (深度Git集成)
- git_status(): 获取详细Git状态
- git_diff(file, staged): 查看差异
- git_auto_commit(message, files, add_all): 自动提交
- git_log(count, graph): 查看历史
- git_blame(file, start_line, end_line): 代码追溯
- git_stash(action, message, index): 暂存管理
- git_branch(action, name, remote): 分支管理
- git_push(remote, branch, force): 推送
- git_pull(remote, branch): 拉取

## Worktree (隔离工作空间)
- worktree_list(): 列出工作树
- worktree_create(name, branch, new_branch): 创建工作树
- worktree_remove(name, force): 删除工作树
- worktree_switch(name): 切换工作树
- worktree_merge(source, message): 合并工作树
- worktree_snapshot(name, message): 创建快照

## CodeMap (代码地图)
- generate_codemap(directory, detailed): 生成代码地图
- find_symbol(directory, symbol): 查找符号定义
- find_references(directory, symbol): 查找符号引用
- file_summary(file): 获取文件摘要
- list_symbols(directory, kind): 列出符号

## 多文件编辑 (批量编辑)
- edit_multiple(edits, description): 批量编辑多个文件
- preview_edits(edits): 预览编辑结果
- undo_edit(operation_id): 撤销编辑
- redo_edit(operation_id): 重做编辑
- edit_history(): 查看编辑历史

## 代码补全
- get_completions(file, line, column): 获取补全建议
- get_inline_suggestion(file, line, column): 获取内联建议

## 沙箱执行 (安全代码执行)
- execute_python(code, timeout): 执行Python代码
- execute_javascript(code, timeout): 执行JavaScript代码
- execute_shell(command, timeout): 执行Shell命令
- validate_code(code, language): 验证代码语法

## 嵌入式编程 (Arduino/ESP32/STM32)
- embedded_detect(platform): 检测工具链安装状态和连接的设备
- embedded_generate(platform, description, board, language): 生成嵌入式代码
- embedded_compile(platform, sketch_path, board): 编译嵌入式固件
- embedded_upload(platform, sketch_path, port, board): 烧录固件到开发板
- embedded_monitor(port, baud, duration): 打开串口监视器
- embedded_list_boards(platform): 列出可用开发板
- embedded_list_ports(platform): 列出连接的串口设备
- embedded_stop_monitor(): 停止串口监视器

# 工具调用格式
调用工具时必须使用以下格式，一个工具一个代码块：

```tool_call
{"name": "工具名", "parameters": {"参数名": "参数值"}}
```

# 完整示例

用户说："帮我创建一个hello.py文件"

你的回复：
好的，我来创建这个文件。

```tool_call
{"name": "write_file", "parameters": {"path": "hello.py", "content": "print('Hello, World!')"}}
```

用户说："创建一个项目文件夹 src/utils"

你的回复：
好的，我来创建这个目录。

```tool_call
{"name": "create_directory", "parameters": {"path": "src/utils"}}
```

用户说："帮我写一份个人简历"

你的回复：
好的，我来为你创建一份个人简历文档。

```tool_call
{"name": "write_file", "parameters": {"path": "个人简历.md", "content": "# 个人简历\\n\\n## 基本信息\\n姓名：\\n电话：\\n邮箱：\\n\\n## 教育背景\\n\\n## 工作经历\\n\\n## 技能特长\\n"}}
```

# 工作流程
1. 理解用户需求
2. 立即调用工具执行（不要空谈）
3. 查看工具返回结果
4. 继续下一步操作
5. 任务完成时调用 finish 工具

# 学习机制
遇到以下情况时创建新技能：
- 用户多次请求类似任务
- 某个任务需要多个步骤
- 花了很多时间调试某个问题
- 发现某种方法特别有效

# 绝对禁止
1. 绝对不能说"我无法创建文件/执行命令"——你有工具可以做到
2. 绝对不能只给文字建议而不调用工具
3. 绝对不能让用户"手动操作"——你来操作
"""

# ==================== 智能体 ====================

class FrokAgent:
    def __init__(self, config: Dict, provider_name: str = None):
        self.config = config
        self.provider_name = provider_name or config.get("default_provider", "deepseek")
        self.provider_config = config["providers"][self.provider_name]

        # 初始化组件
        self.tool_executor = ToolExecutor()
        self.memory = MemoryManager()
        self.skills = SkillManager()
        self.hooks = HookManager()
        self.plan_manager = PlanManager()
        self.subagent_manager = SubagentManager(
            tool_executor=self.tool_executor,
            llm_caller=lambda msgs, stream=False: self._call_llm(msgs, stream)
        )
        self.git = GitEnhanced()
        self.worktree = WorktreeManager()
        self.codemap = CodeMapGenerator()
        self.multi_editor = MultiFileEditor()
        self.completion = CodeCompletion()
        self.sandbox = SandboxExecutor(SandboxConfig(
            limits=ResourceLimits(
                max_memory_mb=256,
                max_cpu_seconds=30,
                max_output_size=10000,
                network_access=False,
            )
        ))
        self.cli = cli
        self.diff_generator = DiffGenerator()
        self.diff_formatter = DiffFormatter()
        self.code_reviewer = CodeReviewer()

        # 嵌入式工具（可选）
        self.embedded_executor: Optional[EmbeddedToolExecutor] = None
        if _HAS_EMBEDDED:
            try:
                self.embedded_executor = get_embedded_executor()
            except Exception:
                pass  # 平台模块不可用时静默忽略

        # 对话历史
        self.messages = []
        self.max_history = 50  # 最大历史消息数

        # Plan模式
        self.plan_mode = False  # 是否处于Plan模式

        # 加载记忆上下文
        self._init_context()

    def _init_context(self):
        """初始化上下文"""
        # 加载记忆摘要
        memory_context = self.memory.get_context_summary()
        if memory_context:
            self.messages.append({
                "role": "system",
                "content": f"## 记忆信息\n{memory_context}"
            })

    def _call_llm(self, messages: List[Dict], stream: bool = True) -> str:
        """调用大模型"""
        try:
            if self.provider_name == "anthropic":
                return self._call_anthropic(messages, stream)
            else:
                return self._call_openai(messages, stream)
        except Exception as e:
            return f"[错误] 调用失败: {e}"

    def _call_openai(self, messages: List[Dict], stream: bool) -> str:
        """调用OpenAI兼容API"""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config.get("base_url")
        )

        response = client.chat.completions.create(
            model=self.provider_config["default_model"],
            messages=messages,
            max_tokens=self.config.get("max_tokens", 4096),
            temperature=self.config.get("temperature", 0.7),
            stream=stream
        )

        if stream:
            full_response = ""
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        print(delta.content, end="", flush=True)
                        full_response += delta.content
            print()
            return full_response
        else:
            return response.choices[0].message.content

    def _call_anthropic(self, messages: List[Dict], stream: bool) -> str:
        """调用Anthropic API"""
        from anthropic import Anthropic

        client = Anthropic(api_key=self.provider_config["api_key"])

        # 分离system消息
        system_msg = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += msg["content"] + "\n"
            else:
                user_messages.append(msg)

        response = client.messages.create(
            model=self.provider_config["default_model"],
            system=system_msg if system_msg else None,
            messages=user_messages,
            max_tokens=self.config.get("max_tokens", 4096),
            temperature=self.config.get("temperature", 0.7),
            stream=stream
        )

        if stream:
            full_response = ""
            for chunk in response:
                if chunk.type == "content_block_delta":
                    print(chunk.delta.text, end="", flush=True)
                    full_response += chunk.delta.text
            print()
            return full_response
        else:
            return response.content[0].text

    def _compose_llm_messages(self) -> List[Dict]:
        """组装当前轮次发给模型的消息（system + 近期 self.messages，避免重复追加 user）"""
        system_prompt = SYSTEM_PROMPT + "\n\n" + get_tools_for_prompt()
        return [{"role": "system", "content": system_prompt}] + self.messages[-self.max_history :]

    def _execute_tool_call(self, tool_call: Dict) -> str:
        """执行工具调用"""
        name = tool_call["name"]
        params = tool_call.get("parameters", {})

        # 触发pre_tool_call hook
        hook_results = self.hooks.trigger("pre_tool_call", {
            "tool_name": name,
            "parameters": params,
        })
        for hr in hook_results:
            if hr.blocked:
                return f"[被Hook阻止] {hr.hook_name}: {hr.error}"

        # 记忆工具
        if name == "remember_user":
            self.memory.update_user_memory(params["key"], params["value"])
            result = f"[已记住用户信息] {params['key']}"
        elif name == "remember_project":
            self.memory.update_project_memory(params["key"], params["value"])
            result = f"[已记住项目信息] {params['key']}"
        elif name == "remember_feedback":
            self.memory.add_feedback(params["feedback"], params.get("category", "general"))
            result = "[已记住反馈]"
        elif name == "recall_memory":
            memory_type = params["type"]
            key = params.get("key")
            if memory_type == "user":
                result = self.memory.get_user_memory(key)
            elif memory_type == "project":
                result = self.memory.get_project_memory(key)
            elif memory_type == "feedback":
                result = self.memory.get_feedback(key)
            else:
                result = "[错误] 未知记忆类型"

        # Skill工具
        elif name == "list_skills":
            result = self.skills.list_skills()
        elif name == "use_skill":
            skill_name = params["skill_name"]
            task = params.get("task", "")
            skill_prompt = self.skills.get_skill_prompt(skill_name)
            if skill_prompt.startswith("[错误]"):
                result = skill_prompt
            else:
                result = f"[使用技能]\n{skill_prompt}\n\n任务: {task}"
        elif name == "create_skill":
            self.skills.save_skill(params)
            result = f"[已创建技能] {params['name']}"

        # Plan工具
        elif name == "create_plan":
            plan = self.plan_manager.create_plan(
                task=params["task"],
                description=params.get("description", ""),
                steps=params.get("steps", [])
            )
            result = f"[已创建计划] {plan.id}\n{self.plan_manager.format_plan(plan.id)}"
        elif name == "approve_plan":
            if self.plan_manager.approve_plan(params["plan_id"]):
                result = f"[已批准计划] {params['plan_id']}"
            else:
                result = f"[错误] 无法批准计划: {params['plan_id']}"
        elif name == "execute_plan":
            plan_id = params["plan_id"]
            if self.plan_manager.start_execution(plan_id):
                result = self._execute_plan(plan_id)
            else:
                result = f"[错误] 无法执行计划: {plan_id}"
        elif name == "show_plan":
            plan_id = params.get("plan_id")
            result = self.plan_manager.format_plan(plan_id)
        elif name == "list_plans":
            result = self.plan_manager.list_plans()

        # Subagent工具
        elif name == "spawn_agent":
            agent_id = self.subagent_manager.spawn(
                task=params["task"],
                config=SubagentConfig(tools=params.get("tools", []))
            )
            result = f"[已创建子代理] {agent_id}"
        elif name == "run_agent":
            result_obj = self.subagent_manager.run_agent(params["agent_id"])
            result = self.subagent_manager.format_result(params["agent_id"])
        elif name == "parallel_tasks":
            results = self.subagent_manager.parallel(params["tasks"])
            result_lines = ["[并行执行结果]"]
            for r in results:
                result_lines.append(f"- {r.agent_id}: {r.status.value} - {r.result[:100]}")
            result = "\n".join(result_lines)
        elif name == "collect_result":
            result_obj = self.subagent_manager.collect(params["agent_id"])
            if result_obj:
                result = self.subagent_manager.format_result(params["agent_id"])
            else:
                result = f"[错误] 子代理结果不可用: {params['agent_id']}"
        elif name == "list_agents":
            result = self.subagent_manager.list_agents()
        elif name == "cancel_agent":
            if self.subagent_manager.cancel(params["agent_id"]):
                result = f"[已取消子代理] {params['agent_id']}"
            else:
                result = f"[错误] 无法取消: {params['agent_id']}"

        # Hooks工具
        elif name == "list_hooks":
            result = self.hooks.list_hooks(params.get("event"))
        elif name == "register_hook":
            hook_id = self.hooks.register(
                event=params["event"],
                name=params["name"],
                action=params["action"],
                tools=params.get("tools", []),
                description=params.get("description", ""),
                blocking=params.get("blocking", False)
            )
            result = f"[已注册Hook] {hook_id}"
        elif name == "enable_hook":
            if self.hooks.enable(params["hook_id"]):
                result = f"[已启用Hook] {params['hook_id']}"
            else:
                result = f"[错误] Hook不存在: {params['hook_id']}"
        elif name == "disable_hook":
            if self.hooks.disable(params["hook_id"]):
                result = f"[已禁用Hook] {params['hook_id']}"
            else:
                result = f"[错误] Hook不存在: {params['hook_id']}"

        # Git增强工具
        elif name == "git_status":
            result = self.git.format_status()
        elif name == "git_diff":
            result = self.git.show_diff(
                file=params.get("file"),
                staged=params.get("staged", False)
            )
        elif name == "git_auto_commit":
            success, msg = self.git.auto_commit(
                message=params.get("message", self.git.generate_commit_message()),
                files=params.get("files"),
                add_all=params.get("add_all", False)
            )
            result = msg if success else f"[错误] {msg}"
        elif name == "git_log":
            if params.get("graph"):
                result = self.git.log_graph(params.get("count", 20))
            else:
                result = self.git.log(params.get("count", 10))
        elif name == "git_blame":
            result = self.git.blame_formatted(
                file=params["file"],
                start_line=params.get("start_line"),
                end_line=params.get("end_line")
            )
        elif name == "git_stash":
            action = params["action"]
            if action == "save":
                success, msg = self.git.stash_save(params.get("message"))
                result = msg
            elif action == "list":
                result = self.git.format_stash_list()
            elif action == "pop":
                success, msg = self.git.stash_pop(params.get("index", 0))
                result = msg
            elif action == "drop":
                success, msg = self.git.stash_drop(params.get("index", 0))
                result = msg
            else:
                result = f"[错误] 未知操作: {action}"
        elif name == "git_branch":
            action = params["action"]
            if action == "list":
                result = self.git.branch_list(params.get("remote", False))
            elif action == "create":
                success, msg = self.git.branch_create(params["name"])
                result = msg
            elif action == "delete":
                success, msg = self.git.branch_delete(params["name"])
                result = msg
            elif action == "checkout":
                success, msg = self.git.checkout(params["name"])
                result = msg
            else:
                result = f"[错误] 未知操作: {action}"
        elif name == "git_push":
            success, msg = self.git.push(
                remote=params.get("remote", "origin"),
                branch=params.get("branch"),
                force=params.get("force", False)
            )
            result = msg
        elif name == "git_pull":
            success, msg = self.git.pull(
                remote=params.get("remote", "origin"),
                branch=params.get("branch")
            )
            result = msg

        # Worktree工具
        elif name == "worktree_list":
            result = self.worktree.format_list()
        elif name == "worktree_create":
            success, msg = self.worktree.create(
                name=params["name"],
                branch=params.get("branch"),
                new_branch=params.get("new_branch", True)
            )
            result = msg
        elif name == "worktree_remove":
            success, msg = self.worktree.remove(
                name=params["name"],
                force=params.get("force", False)
            )
            result = msg
        elif name == "worktree_switch":
            success, msg = self.worktree.switch(params["name"])
            result = msg
        elif name == "worktree_merge":
            success, msg = self.worktree.merge(
                source=params["source"],
                message=params.get("message")
            )
            result = msg
        elif name == "worktree_snapshot":
            success, msg = self.worktree.snapshot(
                name=params["name"],
                message=params.get("message")
            )
            result = msg
        elif name == "worktree_status":
            result = self.worktree.get_status(params["name"])

        # CodeMap工具
        elif name == "generate_codemap":
            code_map = self.codemap.generate(params["directory"])
            result = self.codemap.format_map(code_map, params.get("detailed", False))
        elif name == "find_symbol":
            code_map = self.codemap.generate(params["directory"])
            symbols = self.codemap.find_definition(code_map, params["symbol"])
            if symbols:
                lines = [f"找到 {len(symbols)} 个定义:"]
                for s in symbols:
                    rel_path = os.path.relpath(s.file, params["directory"])
                    lines.append(f"  {s.name} ({s.kind}) - {rel_path}:{s.line}")
                result = "\n".join(lines)
            else:
                result = f"未找到符号: {params['symbol']}"
        elif name == "find_references":
            code_map = self.codemap.generate(params["directory"])
            refs = self.codemap.find_references(code_map, params["symbol"])
            if refs:
                lines = [f"找到 {len(refs)} 个引用:"]
                for path, line in refs[:20]:
                    rel_path = os.path.relpath(path, params["directory"])
                    lines.append(f"  {rel_path}:{line}")
                result = "\n".join(lines)
            else:
                result = f"未找到引用: {params['symbol']}"
        elif name == "file_summary":
            result = self.codemap.get_file_summary(params["file"])
        elif name == "list_symbols":
            code_map = self.codemap.generate(params["directory"])
            result = self.codemap.format_symbols(code_map, params.get("kind"))

        # 多文件编辑工具
        elif name == "edit_multiple":
            edit_result = self.multi_editor.edit_multiple(
                edits=params["edits"],
                description=params.get("description", "")
            )
            result = edit_result.to_string()
        elif name == "preview_edits":
            result = self.multi_editor.preview(params["edits"])
        elif name == "undo_edit":
            success, msg = self.multi_editor.undo(params.get("operation_id"))
            result = msg
        elif name == "redo_edit":
            success, msg = self.multi_editor.redo(params.get("operation_id"))
            result = msg
        elif name == "edit_history":
            result = self.multi_editor.get_history()

        # 代码补全工具
        elif name == "get_completions":
            from completion import Position
            pos = Position(line=params["line"], column=params["column"])
            completions = self.completion.get_completions(params["file"], pos)
            result = self.completion.format_completions(completions)
        elif name == "get_inline_suggestion":
            from completion import Position
            pos = Position(line=params["line"], column=params["column"])
            suggestion = self.completion.get_inline_suggestion(params["file"], pos)
            if suggestion:
                result = f"内联建议: {suggestion.text}"
            else:
                result = "无内联建议"

        # 沙箱执行工具
        elif name == "execute_python":
            exec_result = self.sandbox.execute_python(
                code=params["code"],
                timeout=params.get("timeout")
            )
            result = exec_result.to_string()
        elif name == "execute_javascript":
            exec_result = self.sandbox.execute_javascript(
                code=params["code"],
                timeout=params.get("timeout")
            )
            result = exec_result.to_string()
        elif name == "execute_shell":
            exec_result = self.sandbox.execute_shell(
                command=params["command"],
                timeout=params.get("timeout")
            )
            result = exec_result.to_string()
        elif name == "execute_in_sandbox":
            exec_result = self.sandbox.execute(
                code=params["code"],
                language=params["language"],
                timeout=params.get("timeout")
            )
            result = exec_result.to_string()
        elif name == "validate_code":
            valid, error = self.sandbox.validate_code(
                code=params["code"],
                language=params["language"]
            )
            if valid:
                result = "代码语法正确"
            else:
                result = f"语法错误: {error}"

        # 嵌入式工具
        elif _HAS_EMBEDDED and name.startswith("embedded_") and self.embedded_executor:
            result = self.embedded_executor.execute(name, params)

        # 通用工具
        else:
            result = self.tool_executor.execute(name, params)

        # 触发post_tool_call hook
        self.hooks.trigger("post_tool_call", {
            "tool_name": name,
            "parameters": params,
            "result": result,
        })

        return result

    def _execute_plan(self, plan_id: str) -> str:
        """执行计划中的所有步骤"""
        results = []
        while True:
            step = self.plan_manager.get_next_step(plan_id)
            if not step:
                break

            # 更新步骤状态
            self.plan_manager.update_step_status(plan_id, step.id, "executing")

            # 执行步骤
            if step.tool:
                tool_call = {"name": step.tool, "parameters": step.params}
                step_result = self._execute_tool_call(tool_call)
            else:
                step_result = f"[跳过] 无工具调用: {step.description}"

            # 更新步骤结果
            if step_result.startswith("[错误]"):
                self.plan_manager.update_step_status(plan_id, step.id, "failed", error=step_result)
            else:
                self.plan_manager.update_step_status(plan_id, step.id, "completed", result=step_result)

            results.append(f"步骤: {step.description}\n结果: {step_result[:200]}")

        # 检查是否所有步骤都完成
        progress = self.plan_manager.get_plan_progress(plan_id)
        if progress["failed"] > 0:
            self.plan_manager.fail_plan(plan_id, f"有 {progress['failed']} 个步骤失败")
        else:
            self.plan_manager.complete_plan(plan_id, "所有步骤完成")

        return self.plan_manager.format_plan(plan_id)

    def run(self, user_input: str) -> str:
        """执行一次智能体循环"""
        # 检查是否有相关技能
        related_skill = self.skills.find_skill_by_trigger(user_input)
        if related_skill:
            self.cli.print_info(f"发现相关技能: {related_skill['name']}")
            self.cli.print_info(related_skill['description'])

        # 用户消息写入历史后再组装请求（多轮时与工具结果衔接一致）
        self.messages.append({"role": "user", "content": user_input})
        messages = self._compose_llm_messages()

        # 记录任务信息用于学习
        task_info = {
            "user_input": user_input,
            "tool_calls": [],
            "iterations": 0,
            "errors": [],
            "related_skill": related_skill["name"] if related_skill else None
        }

        # 智能体循环
        max_iterations = 10
        iteration = 0
        final_result = ""
        parse_retries = 0
        max_parse_retries = 2

        while iteration < max_iterations:
            iteration += 1
            task_info["iterations"] = iteration

            # 调用模型
            self.cli.print_assistant("")
            response = self._call_llm(messages, stream=True)

            if not response:
                final_result = "[错误] 模型未返回响应"
                break

            # 解析工具调用
            tool_calls = parse_tool_calls(response)

            if not tool_calls:
                if response.startswith("[错误]"):
                    final_result = response
                    break
                if parse_retries < max_parse_retries:
                    parse_retries += 1
                    self.messages.append({"role": "assistant", "content": response})
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "上一次回复里没有解析到有效工具调用。请必须用 ```tool_call 代码块输出 JSON，例如：\n"
                            "```tool_call\n"
                            '{"name": "write_file", "parameters": {"path": "a.py", "content": "print(1)"}}\n'
                            "```\n"
                            "其中 parameters 必须是 JSON 对象（可嵌套）；任务结束时调用 finish。"
                        ),
                    })
                    messages = self._compose_llm_messages()
                    continue
                final_result = response
                break

            parse_retries = 0

            # 执行工具调用
            tool_results = []
            for call in tool_calls:
                self.cli.print_tool(call['name'], json.dumps(call.get('parameters', {}), ensure_ascii=False))
                result = self._execute_tool_call(call)
                tool_results.append({
                    "tool": call["name"],
                    "result": result
                })
                task_info["tool_calls"].append(call["name"])
                self.cli.print_result(result[:200] + "..." if len(result) > 200 else result)

                # 记录错误
                if result.startswith("[错误]"):
                    task_info["errors"].append(result)

                # 检查是否是finish调用
                if call["name"] == "finish":
                    final_result = call["parameters"].get("result", "任务完成")
                    break

            if final_result:
                break

            # 将工具结果添加到消息中
            self.messages.append({"role": "assistant", "content": response})

            tool_result_text = "工具执行结果:\n"
            for tr in tool_results:
                tool_result_text += f"\n### {tr['tool']}\n{tr['result']}\n"

            self.messages.append({"role": "user", "content": tool_result_text})

            # 下一轮请求：助手回复 + 工具结果已由 append 写入 self.messages
            messages = self._compose_llm_messages()

        # 记录助手回复
        if final_result:
            self.messages.append({"role": "assistant", "content": final_result})

        # 学习机制：分析任务并考虑创建技能
        self._learn_from_task(task_info, final_result)

        return final_result

    def _learn_from_task(self, task_info: Dict, result: str):
        """从任务中学习，考虑创建新技能"""
        try:
            # 判断是否值得创建技能
            should_create = False
            skill_name = ""
            skill_desc = ""

            # 条件1: 多次迭代（复杂任务）
            if task_info["iterations"] >= 3:
                should_create = True
                skill_desc = f"处理复杂任务: {task_info['user_input'][:50]}"

            # 条件2: 使用了多种工具
            unique_tools = set(task_info["tool_calls"])
            if len(unique_tools) >= 3:
                should_create = True
                skill_desc = f"多工具协作任务: {', '.join(unique_tools)}"

            # 条件3: 遇到了错误并解决了
            if task_info["errors"] and result and not result.startswith("[错误]"):
                should_create = True
                skill_desc = f"错误修复任务: {task_info['errors'][0][:50]}"

            # 条件4: 任务完成且结果良好
            if result and not result.startswith("[错误]") and task_info["iterations"] >= 2:
                should_create = True
                skill_desc = f"任务完成: {task_info['user_input'][:50]}"

            if should_create:
                # 生成技能名称
                import hashlib
                hash_input = task_info["user_input"].encode()
                hash_value = hashlib.md5(hash_input).hexdigest()[:8]
                skill_name = f"auto_{hash_value}"

                # 检查是否已存在类似技能
                existing_skills = self.skills.skills
                for existing_name, existing_skill in existing_skills.items():
                    if existing_name.startswith("auto_"):
                        # 检查描述是否相似
                        if self._is_similar(skill_desc, existing_skill.get("description", "")):
                            print(f"[学习] 已存在类似技能: {existing_name}")
                            return

                # 创建新技能
                skill = {
                    "name": skill_name,
                    "description": skill_desc,
                    "trigger": task_info["user_input"][:30],
                    "system_prompt": f"你正在处理一个类似的任务: {task_info['user_input']}\n\n根据之前的经验，这个任务需要以下步骤:\n" + "\n".join(f"- {tool}" for tool in task_info["tool_calls"]),
                    "steps": [f"步骤{i+1}: 使用{tool}" for i, tool in enumerate(task_info["tool_calls"])]
                }

                self.skills.save_skill(skill)
                print(f"\n[学习] 已创建新技能: {skill_name}")
                print(f"[学习] 描述: {skill_desc}")

        except Exception as e:
            # 学习失败不影响主任务
            print(f"\n[学习] 技能创建失败: {e}")

    def _is_similar(self, text1: str, text2: str) -> bool:
        """判断两段文本是否相似"""
        # 简单的相似度判断
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return False
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) > 0.5

    def save_session(self):
        """保存会话"""
        if self.messages:
            summary = ""
            if len(self.messages) > 0:
                # 取第一条用户消息作为摘要
                for msg in self.messages:
                    if msg["role"] == "user":
                        summary = msg["content"][:50]
                        break
            self.memory.save_session(self.messages, summary)

    def get_status(self) -> str:
        """获取状态"""
        lines = []
        lines.append(f"模型: {self.provider_config['name']} ({self.provider_config['default_model']})")
        lines.append(f"消息数: {len(self.messages)}")
        lines.append(f"技能数: {len(self.skills.skills)}")
        lines.append(f"记忆: {len(self.memory.user_memory)} 用户 | {len(self.memory.project_memory)} 项目")
        return "\n".join(lines)

# ==================== 交互模式 ====================

def interactive_mode(config: Dict):
    """交互模式"""
    provider_name = config.get("default_provider", "deepseek")
    provider_config = config["providers"][provider_name]

    cli.show_banner()
    cli.show_status_bar(
        model=provider_config['default_model'],
        provider=provider_config['name']
    )
    print()
    cli.print_assistant("我是 Frok Code，你的智能编程助手。告诉我你想做什么，我会自动规划和执行。")
    cli.print_info("输入 /help 查看命令 | 输入 /skills 查看技能 | 直接描述任务开始工作")
    print("─" * 65)

    agent = FrokAgent(config, provider_name)

    while True:
        try:
            user_input = cli.input().strip()
        except (EOFError, KeyboardInterrupt):
            cli.print_system("再见")
            agent.save_session()
            break

        if not user_input:
            continue

        # 命令处理
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            args = user_input[len(cmd):].strip()

            if cmd == "/quit" or cmd == "/exit":
                cli.print_system("再见")
                agent.save_session()
                break

            elif cmd == "/help":
                cli.show_help()

            elif cmd == "/skills":
                cli.show_box(agent.skills.list_skills(), title="可用技能")

            elif cmd == "/status":
                cli.show_box(agent.get_status(), title="状态信息")

            elif cmd == "/memory":
                cli.print_info("## 用户记忆")
                print(agent.memory.get_user_memory())
                cli.print_info("## 项目记忆")
                print(agent.memory.get_project_memory())

            elif cmd == "/plan":
                plan_output = agent.plan_manager.format_plan()
                if plan_output:
                    cli.show_box(plan_output, title="当前计划")
                else:
                    cli.print_info("当前没有活动计划")

            elif cmd == "/planmode":
                agent.plan_mode = not agent.plan_mode
                status = "开启" if agent.plan_mode else "关闭"
                cli.print_result(f"Plan模式已{status}")

            elif cmd == "/hooks":
                hooks_output = agent.hooks.list_hooks()
                cli.show_box(hooks_output, title="Hook列表")

            elif cmd == "/agents":
                agents_output = agent.subagent_manager.list_agents()
                cli.show_box(agents_output, title="子代理列表")

            elif cmd == "/diff":
                if args:
                    diff_result = agent.git.show_diff(args)
                    print(cli.format_diff(diff_result))
                else:
                    diff_result = agent.git.show_diff()
                    print(cli.format_diff(diff_result))

            elif cmd == "/blame":
                if args:
                    blame_result = agent.git.blame(args)
                    cli.show_box(blame_result, title=f"Blame: {args}")
                else:
                    cli.print_error("请指定文件路径，如: /blame main.py")

            elif cmd == "/map":
                code_map = agent.codemap.generate(".")
                summary = agent.codemap.get_file_summary(code_map)
                cli.show_box(summary, title="代码地图")

            elif cmd == "/sandbox":
                if args:
                    result = agent.sandbox.execute_python(args)
                    cli.print_result(result.to_string(), result.success)
                else:
                    cli.print_info("用法: /sandbox <python代码>")

            elif cmd == "/switch":
                cli.print_info("可用厂商:")
                provider_options = []
                for name, p in config["providers"].items():
                    status = "✓" if p["api_key"] else "✗"
                    provider_options.append(f"[{status}] {p['name']} - {', '.join(p['models'])}")

                choice = cli.show_menu("选择厂商", provider_options)
                if choice is not None:
                    providers = list(config["providers"].keys())
                    new_provider = providers[choice]
                    if not config["providers"][new_provider]["api_key"]:
                        cli.print_error(f"{config['providers'][new_provider]['name']} 未配置 API Key")
                        continue
                    provider_name = new_provider
                    provider_config = config["providers"][provider_name]

                    models = provider_config["models"]
                    cli.print_info("可用模型:")
                    model_choice = cli.show_menu("选择模型", models)
                    if model_choice is not None:
                        provider_config["default_model"] = models[model_choice]

                    agent = FrokAgent(config, provider_name)
                    cli.print_result(f"已切换到 {provider_config['name']} ({provider_config['default_model']})")

            elif cmd == "/clear":
                agent.save_session()
                agent = FrokAgent(config, provider_name)
                cli.print_result("已清空对话")

            elif cmd == "/save":
                agent.save_session()
                cli.print_result("已保存会话")

            else:
                cli.print_warning(f"未知命令: {cmd}，输入 /help 查看帮助")

            continue

        # 智能体执行
        try:
            result = agent.run(user_input)
            if result:
                # 结果已经在run中打印了
                pass
        except Exception as e:
            cli.print_error(str(e))

# ==================== 主入口 ====================

def main():
    # 加载配置
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.json"

    if not config_path.exists():
        cli.print_error("未找到 config.json")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 检查参数
    if len(sys.argv) > 1:
        # 单次调用模式
        query = " ".join(sys.argv[1:])
        agent = FrokAgent(config)
        agent.run(query)
        agent.save_session()
    else:
        # 交互模式
        interactive_mode(config)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        cli.print_error(str(e))
        input("\n按回车键退出...")
