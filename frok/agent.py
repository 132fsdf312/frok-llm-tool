"""
Frok Code 智能体核心
思考-行动-观察循环，通过工具注册表统一调度
"""

import json
import logging
import os
import sys
from typing import Dict, List, Optional
from pathlib import Path

from tools import ToolExecutor, TOOLS_SCHEMA, parse_tool_calls
from tool_registry import ToolRegistry
from memory import MemoryManager
from skills import SkillManager
from hooks import HookManager
from plan import PlanManager, PlanStatus
from subagent import SubagentManager, SubagentConfig
from git_enhanced import GitEnhanced
from worktree import WorktreeManager
from codemap import CodeMapGenerator
from multi_edit import MultiFileEditor
from completion import CodeCompletion, Position
from sandbox import SandboxExecutor, SandboxConfig, ResourceLimits
from cli import FrokCLI, Colors, cli
from diff_viewer import DiffGenerator, DiffFormatter, CodeReviewer
from llm_client import LLMClient
from tool_handlers import ToolHandlers

logger = logging.getLogger(__name__)

# 嵌入式工具（可选依赖）
try:
    from embedded import get_executor as get_embedded_executor, EmbeddedToolExecutor
    _HAS_EMBEDDED = True
except ImportError:
    _HAS_EMBEDDED = False
    EmbeddedToolExecutor = None


# ==================== 系统提示词 ====================

SYSTEM_PROMPT_TEMPLATE = """你是 Frok Code，一个智能编程助手。

# 核心行为规则
- 需要操作文件、执行命令、修改代码时，必须调用工具，不要只给文字建议
- 不要说"我无法创建文件"——你有 write_file 工具
- 不要说"请手动操作"——你有 execute_command 工具
- 任务完成时调用 finish 工具

# 何时直接回复（不需要工具）
- 用户打招呼（你好、hi、hello）→ 简短问候即可，不要调用任何工具
- 用户问简单问题（你是什么、你能做什么）→ 简短回答
- 闲聊、感谢、告别 → 简短回复

# 何时调用工具
- 用户要求创建/编辑/删除文件
- 用户要求执行命令或运行代码
- 用户要求查看文件内容或目录结构
- 用户描述了一个具体的编程任务
- 用户要求调试、重构、审查代码

# 工具列表
{tools_description}

# 工具调用格式
调用工具时必须使用以下格式，一个工具一个代码块：

```tool_call
{{"name": "工具名", "parameters": {{"参数名": "参数值"}}}}
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

        # 读取 API Key：优先环境变量，fallback 到 config 中的 api_key 字段
        api_key_env = self.provider_config.get("api_key_env", "")
        self.provider_config["api_key"] = os.environ.get(api_key_env, "") or self.provider_config.get("api_key", "")

        # 初始化工具注册表
        self.registry = ToolRegistry()

        # 初始化子系统
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

        # LLM 客户端
        self.llm_client = LLMClient(self.provider_name, self.provider_config, self.config)

        # 工具 Handler
        self.handlers = ToolHandlers(self)

        # 嵌入式工具（可选）
        self.embedded_executor: Optional[EmbeddedToolExecutor] = None
        if _HAS_EMBEDDED:
            try:
                self.embedded_executor = get_embedded_executor()
            except Exception:
                pass

        # 注册所有工具
        self._register_all_tools()

        # 对话历史
        self.messages = []
        self.max_history = 50

        # Plan模式
        self.plan_mode = False

        # 加载记忆上下文
        self._init_context()

    def _register_all_tools(self) -> None:
        """注册所有子系统的工具到注册表"""

        # 1. 基础工具（文件操作、搜索、命令）
        self.registry.register_batch(TOOLS_SCHEMA, {
            "read_file": self.tool_executor.read_file,
            "write_file": self.tool_executor.write_file,
            "edit_file": self.tool_executor.edit_file,
            "append_file": self.tool_executor.append_file,
            "delete_file": self.tool_executor.delete_file,
            "copy_file": self.tool_executor.copy_file,
            "move_file": self.tool_executor.move_file,
            "list_directory": self.tool_executor.list_directory,
            "get_tree": self.tool_executor.get_tree,
            "search_files": self.tool_executor.search_files,
            "find_files": self.tool_executor.find_files,
            "create_directory": self.tool_executor.create_directory,
            "execute_command": self.tool_executor.execute_command,
            "git_command": self.tool_executor.git_command,
            "ask_user": self.tool_executor.ask_user,
            "finish": self.tool_executor.finish,
        })

        # 2. 记忆工具
        from memory import MEMORY_TOOLS
        self.registry.register_batch(MEMORY_TOOLS, {
            "remember_user": self.handlers.handle_remember_user,
            "remember_project": self.handlers.handle_remember_project,
            "remember_feedback": self.handlers.handle_remember_feedback,
            "recall_memory": self.handlers.handle_recall_memory,
        })

        # 3. 技能工具
        from skills import SKILL_TOOLS
        self.registry.register_batch(SKILL_TOOLS, {
            "list_skills": self.handlers.handle_list_skills,
            "use_skill": self.handlers.handle_use_skill,
            "create_skill": self.handlers.handle_create_skill,
        })

        # 4. Plan 工具
        from plan import PLAN_TOOLS
        self.registry.register_batch(PLAN_TOOLS, {
            "create_plan": self.handlers.handle_create_plan,
            "approve_plan": self.handlers.handle_approve_plan,
            "execute_plan": self.handlers.handle_execute_plan,
            "show_plan": self.handlers.handle_show_plan,
            "list_plans": self.handlers.handle_list_plans,
            "update_step": self.handlers.handle_update_step,
        })

        # 5. Subagent 工具
        from subagent import SUBAGENT_TOOLS
        self.registry.register_batch(SUBAGENT_TOOLS, {
            "spawn_agent": self.handlers.handle_spawn_agent,
            "run_agent": self.handlers.handle_run_agent,
            "parallel_tasks": self.handlers.handle_parallel_tasks,
            "collect_result": self.handlers.handle_collect_result,
            "list_agents": self.handlers.handle_list_agents,
            "cancel_agent": self.handlers.handle_cancel_agent,
        })

        # 6. Hooks 工具
        from hooks import HOOK_TOOLS
        self.registry.register_batch(HOOK_TOOLS, {
            "list_hooks": self.handlers.handle_list_hooks,
            "register_hook": self.handlers.handle_register_hook,
            "unregister_hook": self.handlers.handle_unregister_hook,
            "enable_hook": self.handlers.handle_enable_hook,
            "disable_hook": self.handlers.handle_disable_hook,
        })

        # 7. Git 增强工具
        from git_enhanced import GIT_ENHANCED_TOOLS
        self.registry.register_batch(GIT_ENHANCED_TOOLS, {
            "git_status": self.handlers.handle_git_status,
            "git_diff": self.handlers.handle_git_diff,
            "git_auto_commit": self.handlers.handle_git_auto_commit,
            "git_log": self.handlers.handle_git_log,
            "git_blame": self.handlers.handle_git_blame,
            "git_stash": self.handlers.handle_git_stash,
            "git_branch": self.handlers.handle_git_branch,
            "git_push": self.handlers.handle_git_push,
            "git_pull": self.handlers.handle_git_pull,
        })

        # 8. Worktree 工具
        from worktree import WORKTREE_TOOLS
        self.registry.register_batch(WORKTREE_TOOLS, {
            "worktree_list": self.handlers.handle_worktree_list,
            "worktree_create": self.handlers.handle_worktree_create,
            "worktree_remove": self.handlers.handle_worktree_remove,
            "worktree_switch": self.handlers.handle_worktree_switch,
            "worktree_merge": self.handlers.handle_worktree_merge,
            "worktree_snapshot": self.handlers.handle_worktree_snapshot,
            "worktree_status": self.handlers.handle_worktree_status,
        })

        # 9. CodeMap 工具
        from codemap import CODEMAP_TOOLS
        self.registry.register_batch(CODEMAP_TOOLS, {
            "generate_codemap": self.handlers.handle_generate_codemap,
            "find_symbol": self.handlers.handle_find_symbol,
            "find_references": self.handlers.handle_find_references,
            "file_summary": self.handlers.handle_file_summary,
            "list_symbols": self.handlers.handle_list_symbols,
        })

        # 10. 多文件编辑工具
        from multi_edit import MULTI_EDIT_TOOLS
        self.registry.register_batch(MULTI_EDIT_TOOLS, {
            "edit_multiple": self.handlers.handle_edit_multiple,
            "preview_edits": self.handlers.handle_preview_edits,
            "undo_edit": self.handlers.handle_undo_edit,
            "redo_edit": self.handlers.handle_redo_edit,
            "edit_history": self.handlers.handle_edit_history,
        })

        # 11. 代码补全工具
        from completion import COMPLETION_TOOLS
        self.registry.register_batch(COMPLETION_TOOLS, {
            "get_completions": self.handlers.handle_get_completions,
            "get_inline_suggestion": self.handlers.handle_get_inline_suggestion,
        })

        # 12. 沙箱工具
        from sandbox import SANDBOX_TOOLS
        self.registry.register_batch(SANDBOX_TOOLS, {
            "execute_python": self.handlers.handle_execute_python,
            "execute_javascript": self.handlers.handle_execute_javascript,
            "execute_shell": self.handlers.handle_execute_shell,
            "execute_in_sandbox": self.handlers.handle_execute_in_sandbox,
            "validate_code": self.handlers.handle_validate_code,
        })

        # 13. Diff Viewer 工具
        from diff_viewer import DIFF_VIEWER_TOOLS
        self.registry.register_batch(DIFF_VIEWER_TOOLS, {
            "show_diff": self.handlers.handle_show_diff,
            "diff_files": self.handlers.handle_diff_files,
            "review_changes": self.handlers.handle_review_changes,
        })

        # 14. 嵌入式工具（可选）
        if _HAS_EMBEDDED and self.embedded_executor:
            from embedded import EMBEDDED_TOOLS
            for schema in EMBEDDED_TOOLS:
                name = schema["name"]
                self.registry.register(schema, lambda params, n=name: self.embedded_executor.execute(n, params))

        logger.info(f"已注册 {len(self.registry.get_tool_names())} 个工具")

    # ==================== 上下文与 LLM ====================

    def _init_context(self) -> None:
        memory_context = self.memory.get_context_summary()
        if memory_context:
            self.messages.append({"role": "system", "content": f"## 记忆信息\n{memory_context}"})

    def _get_system_prompt(self) -> str:
        """动态生成系统提示词（工具列表从注册表获取）"""
        tools_desc = self.registry.format_tools_for_prompt()
        return SYSTEM_PROMPT_TEMPLATE.format(tools_description=tools_desc)

    def _call_llm(self, messages: List[Dict], stream: bool = True, silent: bool = False) -> tuple:
        """调用大模型（委托给 LLMClient）"""
        return self.llm_client.call(messages, stream, silent)

    def _compose_llm_messages(self) -> List[Dict]:
        system_prompt = self._get_system_prompt()
        return [{"role": "system", "content": system_prompt}] + self.messages[-self.max_history:]

    # ==================== 输出辅助 ====================

    def _print_once(self, shown: bool, text: str) -> bool:
        """打印 Frok 前缀 + 内容（仅首次显示前缀）"""
        if not shown:
            self.cli.print_assistant("")
        print(text)
        return True

    # ==================== 核心循环 ====================

    def run(self, user_input: str) -> str:
        # 检查相关技能
        related_skill = self.skills.find_skill_by_trigger(user_input)
        if related_skill:
            self.cli.print_info(f"发现相关技能: {related_skill['name']}")

        self.messages.append({"role": "user", "content": user_input})
        messages = self._compose_llm_messages()

        task_info = {
            "user_input": user_input,
            "tool_calls": [],
            "iterations": 0,
            "errors": [],
            "related_skill": related_skill["name"] if related_skill else None
        }

        max_iterations = 10
        max_continuations = 3
        iteration = 0
        final_result = ""
        known_names = self.registry.get_tool_names()
        shown_prefix = False

        while iteration < max_iterations:
            iteration += 1
            task_info["iterations"] = iteration

            response, truncated = self._call_llm(messages, stream=True)

            if not response:
                final_result = "[错误] 模型未返回响应"
                break

            # 自动续写
            continuation = 0
            while truncated and continuation < max_continuations:
                continuation += 1
                self.cli.print_info("[输出被截断，自动续写...]")
                cont_messages = messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": "内容被截断了，请从断点处继续写，不要重复已写的内容。"},
                ]
                cont_response, cont_truncated = self._call_llm(cont_messages, stream=False)
                if cont_response and not cont_response.startswith("[错误]"):
                    response += cont_response
                truncated = cont_truncated

            # 解析工具调用
            tool_calls = parse_tool_calls(response, known_names)

            if not tool_calls:
                if response.startswith("[错误]"):
                    self._print_once(shown_prefix, response)
                    final_result = response
                    break
                # 模型直接回复文本（问候、简单问答等）→ 作为最终结果
                if not shown_prefix:
                    self.cli.print_assistant("")
                final_result = response
                break

            # 有工具调用 → 显示前缀和工具执行
            if not shown_prefix:
                self.cli.print_assistant("")
                shown_prefix = True

            # 执行工具调用
            tool_results = []
            for call in tool_calls:
                name = call["name"]
                params = call.get("parameters", {})

                # Hook: pre_tool_call
                hook_results = self.hooks.trigger("pre_tool_call", {
                    "tool_name": name,
                    "parameters": params,
                })
                blocked = any(hr.blocked for hr in hook_results)
                if blocked:
                    result = f"[被Hook阻止] {name}"
                else:
                    # 通过注册表分发
                    self.cli.print_tool(name, json.dumps(params, ensure_ascii=False))
                    result = self.registry.execute(name, params)

                tool_results.append({"tool": name, "result": result})
                task_info["tool_calls"].append(name)
                self.cli.print_result(result[:200] + "..." if len(result) > 200 else result)

                if result.startswith("[错误]"):
                    task_info["errors"].append(result)

                # Hook: post_tool_call
                self.hooks.trigger("post_tool_call", {
                    "tool_name": name,
                    "parameters": params,
                    "result": result,
                })

                if name == "finish":
                    final_result = params.get("result", "任务完成")
                    break

            if final_result:
                break

            # 更新消息历史
            self.messages.append({"role": "assistant", "content": response})

            tool_result_text = "工具执行结果:\n"
            for tr in tool_results:
                tool_result_text += f"\n### {tr['tool']}\n{tr['result']}\n"

            self.messages.append({"role": "user", "content": tool_result_text})
            messages = self._compose_llm_messages()

        if final_result:
            self.messages.append({"role": "assistant", "content": final_result})

        self._learn_from_task(task_info, final_result)
        return final_result

    # ==================== 计划执行 ====================

    def _execute_plan(self, plan_id: str) -> str:
        results = []
        while True:
            step = self.plan_manager.get_next_step(plan_id)
            if not step:
                break

            self.plan_manager.update_step_status(plan_id, step.id, "executing")

            if step.tool:
                step_result = self.registry.execute(step.tool, step.params)
            else:
                step_result = f"[跳过] 无工具调用: {step.description}"

            if step_result.startswith("[错误]"):
                self.plan_manager.update_step_status(plan_id, step.id, "failed", error=step_result)
            else:
                self.plan_manager.update_step_status(plan_id, step.id, "completed", result=step_result)

            results.append(f"步骤: {step.description}\n结果: {step_result[:200]}")

        progress = self.plan_manager.get_plan_progress(plan_id)
        if progress["failed"] > 0:
            self.plan_manager.fail_plan(plan_id, f"有 {progress['failed']} 个步骤失败")
        else:
            self.plan_manager.complete_plan(plan_id, "所有步骤完成")

        return self.plan_manager.format_plan(plan_id)

    # ==================== 学习机制（调优） ====================

    def _learn_from_task(self, task_info: Dict, result: str) -> None:
        try:
            should_create = False
            skill_desc = ""

            # 提高阈值：5次迭代
            if task_info["iterations"] >= 5:
                should_create = True
                skill_desc = f"处理复杂任务: {task_info['user_input'][:50]}"

            # 提高阈值：5种不同工具
            unique_tools = set(task_info["tool_calls"])
            if len(unique_tools) >= 5:
                should_create = True
                skill_desc = f"多工具协作任务: {', '.join(unique_tools)}"

            # 有错误但最终成功
            if task_info["errors"] and result and not result.startswith("[错误]"):
                should_create = True
                skill_desc = f"错误修复任务: {task_info['errors'][0][:50]}"

            if not should_create:
                return

            # 技能数量上限
            auto_skills = [n for n in self.skills.skills if n.startswith("auto_")]
            if len(auto_skills) >= 20:
                logger.info("自动技能数量已达上限(20)，跳过创建")
                return

            import hashlib
            hash_value = hashlib.md5(task_info["user_input"].encode()).hexdigest()[:8]
            skill_name = f"auto_{hash_value}"

            # 提高相似度阈值
            for existing_name, existing_skill in self.skills.skills.items():
                if existing_name.startswith("auto_"):
                    if self._is_similar(skill_desc, existing_skill.get("description", "")):
                        return

            skill = {
                "name": skill_name,
                "description": skill_desc,
                "trigger": task_info["user_input"][:30],
                "system_prompt": f"处理类似任务: {task_info['user_input']}\n\n步骤:\n" + "\n".join(f"- {t}" for t in task_info["tool_calls"]),
                "steps": [f"步骤{i+1}: 使用{t}" for i, t in enumerate(task_info["tool_calls"])]
            }

            self.skills.save_skill(skill)
            logger.info(f"已创建新技能: {skill_name}")

        except Exception as e:
            logger.debug(f"技能创建失败: {e}")

    def _is_similar(self, text1: str, text2: str) -> bool:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return False
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) > 0.7

    # ==================== 会话管理 ====================

    def save_session(self) -> None:
        if self.messages:
            summary = ""
            for msg in self.messages:
                if msg["role"] == "user":
                    summary = msg["content"][:50]
                    break
            self.memory.save_session(self.messages, summary)

    def get_status(self) -> str:
        lines = []
        lines.append(f"模型: {self.provider_config['name']} ({self.provider_config['default_model']})")
        lines.append(f"消息数: {len(self.messages)}")
        lines.append(f"技能数: {len(self.skills.skills)}")
        lines.append(f"工具数: {len(self.registry.get_tool_names())}")
        lines.append(f"记忆: {len(self.memory.user_memory)} 用户 | {len(self.memory.project_memory)} 项目")
        return "\n".join(lines)


# ==================== 交互模式 ====================

def interactive_mode(config: Dict) -> None:
    provider_name = config.get("default_provider", "deepseek")
    provider_config = config["providers"][provider_name]

    # 启动界面
    cli.show_banner(provider=provider_config['name'], model=provider_config['default_model'])

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

        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            args = user_input[len(cmd):].strip()

            if cmd in ("/quit", "/exit", "/q"):
                cli.print_system("再见")
                agent.save_session()
                break
            elif cmd == "/help":
                _show_help()
            elif cmd == "/setkey":
                _handle_setkey(config, args)
            elif cmd == "/switch":
                _handle_switch(config, agent, args)
            elif cmd == "/status":
                cli.show_box(agent.get_status(), title="状态")
            elif cmd == "/skills":
                cli.show_box(agent.skills.list_skills(), title="技能")
            elif cmd == "/clear":
                agent.save_session()
                agent = FrokAgent(config, provider_name)
                cli.print_result("已清空对话")
            elif cmd == "/save":
                agent.save_session()
                cli.print_result("已保存")
            # 高级命令（不常用，不在 /help 主列表显示）
            elif cmd == "/plan":
                plan_output = agent.plan_manager.format_plan()
                cli.show_box(plan_output or "暂无计划", title="计划")
            elif cmd == "/planmode":
                agent.plan_mode = not agent.plan_mode
                cli.print_result(f"Plan模式: {'开' if agent.plan_mode else '关'}")
            elif cmd == "/hooks":
                cli.show_box(agent.hooks.list_hooks(), title="Hooks")
            elif cmd == "/agents":
                cli.show_box(agent.subagent_manager.list_agents(), title="子代理")
            elif cmd == "/diff":
                diff_result = agent.git.show_diff(args) if args else agent.git.show_diff()
                print(cli.format_diff(diff_result))
            elif cmd == "/map":
                code_map = agent.codemap.generate(".")
                cli.show_box(agent.codemap.get_file_summary(code_map), title="代码地图")
            elif cmd == "/sandbox":
                if args:
                    result = agent.sandbox.execute_python(args)
                    cli.print_result(result.to_string(), result.success)
                else:
                    cli.print_info("用法: /sandbox <python代码>")
            elif cmd == "/memory":
                cli.print_info(agent.memory.get_user_memory())
                cli.print_info(agent.memory.get_project_memory())
            else:
                cli.print_warning(f"未知命令: {cmd}，输入 /help 查看帮助")
            continue

        try:
            result = agent.run(user_input)
        except Exception as e:
            cli.print_error(str(e))


def _show_help():
    """简洁帮助信息"""
    print(f"""
{Colors.CYAN}常用{Colors.RESET}
  直接输入任务     描述你想做的事
  /setkey [m] [k]  配置 API Key
  /switch [名称]   切换模型
  /status          当前状态
  /clear           清空对话
  /quit            退出

{Colors.DIM}高级{Colors.RESET}
  /skills /plan /diff /map /sandbox /memory /hooks /agents
""")


def _handle_setkey(config: Dict, args: str):
    """配置 API Key"""
    from main import save_env_var, PROVIDERS

    parts = args.split() if args else []

    if len(parts) >= 2:
        # 直接模式: /setkey mimo tp-xxxx
        provider_hint = parts[0].lower()
        key_value = parts[1]

        # 查找匹配的厂商
        matched = None
        for num, (pid, pname, env_key, _) in PROVIDERS.items():
            if provider_hint in (pid, pname.lower(), num):
                matched = (pid, pname, env_key)
                break

        if not matched:
            cli.print_error(f"未知厂商: {provider_hint}")
            return

        pid, pname, env_key = matched
        save_env_var(env_key, key_value)
        # 更新 config 中的 key
        if pid in config["providers"]:
            config["providers"][pid]["api_key"] = key_value
        cli.print_result(f"{pname} Key 已保存到 .env")

    elif len(parts) == 1:
        # 只给了 key，用当前厂商
        key_value = parts[0]
        env_key = config["providers"][config.get("default_provider", "mimo")].get("api_key_env", "")
        if env_key:
            save_env_var(env_key, key_value)
            cli.print_result("Key 已保存")
    else:
        # 交互模式
        print()
        for num, (pid, pname, env_key, _) in PROVIDERS.items():
            has = "已配置" if os.environ.get(env_key) else "未配置"
            print(f"  {num}. {pname} [{has}]")
        choice = input("\n  选择厂商 [1]: ").strip() or "1"
        if choice not in PROVIDERS:
            return
        _, pname, env_key = PROVIDERS[choice]
        key = input(f"  输入 {pname} Key: ").strip()
        if key:
            save_env_var(env_key, key)
            cli.print_result(f"{pname} Key 已保存")


def _handle_switch(config: Dict, agent, args: str):
    """切换模型"""
    providers = list(config["providers"].keys())
    if args and args in providers:
        # 快速切换: /switch deepseek
        new_provider = args
    else:
        options = []
        for name, p in config["providers"].items():
            key_env = p.get("api_key_env", "")
            has_key = bool(os.environ.get(key_env, "") or p.get("api_key", ""))
            status = "v" if has_key else "x"
            options.append(f"[{status}] {p['name']} - {', '.join(p['models'])}")

        choice = cli.show_menu("选择厂商", options)
        if choice is None:
            return
        new_provider = providers[choice]

    key_env = config["providers"][new_provider].get("api_key_env", "")
    if not (os.environ.get(key_env, "") or config["providers"][new_provider].get("api_key", "")):
        cli.print_error("未配置 Key，先执行 /setkey")
        return

    provider_config = config["providers"][new_provider]
    models = provider_config["models"]
    if len(models) > 1:
        model_choice = cli.show_menu("选择模型", models)
        if model_choice is not None:
            provider_config["default_model"] = models[model_choice]

    agent.__init__(config, new_provider)
    cli.print_result(f"已切换到 {provider_config['name']} ({provider_config['default_model']})")


# ==================== 主入口 ====================

def main() -> None:
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.json"

    if not config_path.exists():
        cli.print_error("未找到 config.json")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        agent = FrokAgent(config)
        agent.run(query)
        agent.save_session()
    else:
        interactive_mode(config)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        cli.print_error(str(e))
        input("\n按回车键退出...")
