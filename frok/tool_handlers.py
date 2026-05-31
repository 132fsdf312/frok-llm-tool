"""
Frok 工具 Handler 集合
将 agent.py 中的 _handle_* 方法拆分到独立模块
"""

import json
import os
from typing import Dict, List


class ToolHandlers:
    """工具 Handler 集合类"""

    def __init__(self, agent):
        """
        Args:
            agent: FrokAgent 实例，用于访问各子系统
        """
        self.agent = agent

    # ==================== 记忆 ====================

    def handle_remember_user(self, key: str, value: str, **kw) -> str:
        self.agent.memory.update_user_memory(key, value)
        return f"[已记住用户信息] {key}"

    def handle_remember_project(self, key: str, value: str, **kw) -> str:
        self.agent.memory.update_project_memory(key, value)
        return f"[已记住项目信息] {key}"

    def handle_remember_feedback(self, feedback: str, category: str = "general", **kw) -> str:
        self.agent.memory.add_feedback(feedback, category)
        return "[已记住反馈]"

    def handle_recall_memory(self, type: str, key: str = None, **kw) -> str:
        if type == "user":
            return self.agent.memory.get_user_memory(key)
        elif type == "project":
            return self.agent.memory.get_project_memory(key)
        elif type == "feedback":
            return self.agent.memory.get_feedback(key)
        return "[错误] 未知记忆类型"

    # ==================== 技能 ====================

    def handle_list_skills(self, **kw) -> str:
        return self.agent.skills.list_skills()

    def handle_use_skill(self, skill_name: str, task: str = "", **kw) -> str:
        skill_prompt = self.agent.skills.get_skill_prompt(skill_name)
        if skill_prompt.startswith("[错误]"):
            return skill_prompt
        return f"[使用技能]\n{skill_prompt}\n\n任务: {task}"

    def handle_create_skill(self, **params) -> str:
        self.agent.skills.save_skill(params)
        return f"[已创建技能] {params['name']}"

    # ==================== Plan ====================

    def handle_create_plan(self, task: str, steps: List[Dict], description: str = "", **kw) -> str:
        from plan import PlanStatus
        plan = self.agent.plan_manager.create_plan(task=task, description=description, steps=steps)
        return f"[已创建计划] {plan.id}\n{self.agent.plan_manager.format_plan(plan.id)}"

    def handle_approve_plan(self, plan_id: str, **kw) -> str:
        if self.agent.plan_manager.approve_plan(plan_id):
            return f"[已批准计划] {plan_id}"
        return f"[错误] 无法批准计划: {plan_id}"

    def handle_execute_plan(self, plan_id: str, **kw) -> str:
        from plan import PlanStatus
        plan = self.agent.plan_manager._get_plan(plan_id)
        if not plan:
            return f"[错误] 计划不存在: {plan_id}"
        if plan.status != PlanStatus.APPROVED:
            return f"[错误] 计划尚未批准，当前状态: {plan.status.value}。请先调用 approve_plan。"
        if self.agent.plan_manager.start_execution(plan_id):
            return self.agent._execute_plan(plan_id)
        return f"[错误] 无法执行计划: {plan_id}"

    def handle_show_plan(self, plan_id: str = None, **kw) -> str:
        return self.agent.plan_manager.format_plan(plan_id)

    def handle_list_plans(self, **kw) -> str:
        return self.agent.plan_manager.list_plans()

    def handle_update_step(self, plan_id: str, step_id: str, status: str, result: str = "", **kw) -> str:
        if self.agent.plan_manager.update_step_status(plan_id, step_id, status, result=result):
            return f"[已更新步骤] {step_id} -> {status}"
        return "[错误] 更新失败"

    # ==================== Subagent ====================

    def handle_spawn_agent(self, task: str, tools: List[str] = None, **kw) -> str:
        from subagent import SubagentConfig
        agent_id = self.agent.subagent_manager.spawn(task=task, config=SubagentConfig(tools=tools or []))
        return f"[已创建子代理] {agent_id}"

    def handle_run_agent(self, agent_id: str, **kw) -> str:
        self.agent.subagent_manager.run_agent(agent_id)
        return self.agent.subagent_manager.format_result(agent_id)

    def handle_parallel_tasks(self, tasks: List[str], **kw) -> str:
        results = self.agent.subagent_manager.parallel(tasks)
        lines = ["[并行执行结果]"]
        for r in results:
            lines.append(f"- {r.agent_id}: {r.status.value} - {r.result[:100]}")
        return "\n".join(lines)

    def handle_collect_result(self, agent_id: str, **kw) -> str:
        result_obj = self.agent.subagent_manager.collect(agent_id)
        if result_obj:
            return self.agent.subagent_manager.format_result(agent_id)
        return f"[错误] 子代理结果不可用: {agent_id}"

    def handle_list_agents(self, **kw) -> str:
        return self.agent.subagent_manager.list_agents()

    def handle_cancel_agent(self, agent_id: str, **kw) -> str:
        if self.agent.subagent_manager.cancel(agent_id):
            return f"[已取消子代理] {agent_id}"
        return f"[错误] 无法取消: {agent_id}"

    # ==================== Hooks ====================

    def handle_list_hooks(self, event: str = None, **kw) -> str:
        return self.agent.hooks.list_hooks(event)

    def handle_register_hook(self, event: str, name: str, action: str, tools: List[str] = None,
                              description: str = "", blocking: bool = False, **kw) -> str:
        hook_id = self.agent.hooks.register(event=event, name=name, action=action,
                                             tools=tools or [], description=description, blocking=blocking)
        return f"[已注册Hook] {hook_id}"

    def handle_unregister_hook(self, hook_id: str, **kw) -> str:
        if self.agent.hooks.unregister(hook_id):
            return f"[已注销Hook] {hook_id}"
        return f"[错误] Hook不存在: {hook_id}"

    def handle_enable_hook(self, hook_id: str, **kw) -> str:
        if self.agent.hooks.enable(hook_id):
            return f"[已启用Hook] {hook_id}"
        return f"[错误] Hook不存在: {hook_id}"

    def handle_disable_hook(self, hook_id: str, **kw) -> str:
        if self.agent.hooks.disable(hook_id):
            return f"[已禁用Hook] {hook_id}"
        return f"[错误] Hook不存在: {hook_id}"

    # ==================== Git ====================

    def handle_git_status(self, **kw) -> str:
        return self.agent.git.format_status()

    def handle_git_diff(self, file: str = None, staged: bool = False, **kw) -> str:
        return self.agent.git.show_diff(file=file, staged=staged)

    def handle_git_auto_commit(self, message: str = None, files: List[str] = None, add_all: bool = False, **kw) -> str:
        success, msg = self.agent.git.auto_commit(
            message=message or self.agent.git.generate_commit_message(),
            files=files, add_all=add_all
        )
        return msg if success else f"[错误] {msg}"

    def handle_git_log(self, count: int = 10, graph: bool = False, **kw) -> str:
        if graph:
            return self.agent.git.log_graph(count)
        return self.agent.git.log(count)

    def handle_git_blame(self, file: str, start_line: int = None, end_line: int = None, **kw) -> str:
        return self.agent.git.blame_formatted(file=file, start_line=start_line, end_line=end_line)

    def handle_git_stash(self, action: str, message: str = None, index: int = 0, **kw) -> str:
        if action == "save":
            success, msg = self.agent.git.stash_save(message)
            return msg
        elif action == "list":
            return self.agent.git.format_stash_list()
        elif action == "pop":
            success, msg = self.agent.git.stash_pop(index)
            return msg
        elif action == "drop":
            success, msg = self.agent.git.stash_drop(index)
            return msg
        return f"[错误] 未知操作: {action}"

    def handle_git_branch(self, action: str, name: str = None, remote: bool = False, **kw) -> str:
        if action == "list":
            return self.agent.git.branch_list(remote)
        elif action == "create":
            success, msg = self.agent.git.branch_create(name)
            return msg
        elif action == "delete":
            success, msg = self.agent.git.branch_delete(name)
            return msg
        elif action == "checkout":
            success, msg = self.agent.git.checkout(name)
            return msg
        return f"[错误] 未知操作: {action}"

    def handle_git_push(self, remote: str = "origin", branch: str = None, force: bool = False, **kw) -> str:
        success, msg = self.agent.git.push(remote=remote, branch=branch, force=force)
        return msg

    def handle_git_pull(self, remote: str = "origin", branch: str = None, **kw) -> str:
        success, msg = self.agent.git.pull(remote=remote, branch=branch)
        return msg

    # ==================== Worktree ====================

    def handle_worktree_list(self, **kw) -> str:
        return self.agent.worktree.format_list()

    def handle_worktree_create(self, name: str, branch: str = None, new_branch: bool = True, **kw) -> str:
        success, msg = self.agent.worktree.create(name=name, branch=branch, new_branch=new_branch)
        return msg

    def handle_worktree_remove(self, name: str, force: bool = False, **kw) -> str:
        success, msg = self.agent.worktree.remove(name=name, force=force)
        return msg

    def handle_worktree_switch(self, name: str, **kw) -> str:
        success, msg = self.agent.worktree.switch(name)
        return msg

    def handle_worktree_merge(self, source: str, message: str = None, **kw) -> str:
        success, msg = self.agent.worktree.merge(source=source, message=message)
        return msg

    def handle_worktree_snapshot(self, name: str, message: str = None, **kw) -> str:
        success, msg = self.agent.worktree.snapshot(name=name, message=message)
        return msg

    def handle_worktree_status(self, name: str, **kw) -> str:
        return self.agent.worktree.get_status(name)

    # ==================== CodeMap ====================

    def handle_generate_codemap(self, directory: str, detailed: bool = False, **kw) -> str:
        code_map = self.agent.codemap.generate(directory)
        return self.agent.codemap.format_map(code_map, detailed)

    def handle_find_symbol(self, directory: str, symbol: str, **kw) -> str:
        code_map = self.agent.codemap.generate(directory)
        symbols = self.agent.codemap.find_definition(code_map, symbol)
        if symbols:
            lines = [f"找到 {len(symbols)} 个定义:"]
            for s in symbols:
                rel_path = os.path.relpath(s.file, directory)
                lines.append(f"  {s.name} ({s.kind}) - {rel_path}:{s.line}")
            return "\n".join(lines)
        return f"未找到符号: {symbol}"

    def handle_find_references(self, directory: str, symbol: str, **kw) -> str:
        code_map = self.agent.codemap.generate(directory)
        refs = self.agent.codemap.find_references(code_map, symbol)
        if refs:
            lines = [f"找到 {len(refs)} 个引用:"]
            for path, line in refs[:20]:
                rel_path = os.path.relpath(path, directory)
                lines.append(f"  {rel_path}:{line}")
            return "\n".join(lines)
        return f"未找到引用: {symbol}"

    def handle_file_summary(self, file: str, **kw) -> str:
        return self.agent.codemap.get_file_summary(file)

    def handle_list_symbols(self, directory: str, kind: str = None, **kw) -> str:
        code_map = self.agent.codemap.generate(directory)
        return self.agent.codemap.format_symbols(code_map, kind)

    # ==================== 多文件编辑 ====================

    def handle_edit_multiple(self, edits: List[Dict], description: str = "", **kw) -> str:
        edit_result = self.agent.multi_editor.edit_multiple(edits=edits, description=description)
        return edit_result.to_string()

    def handle_preview_edits(self, edits: List[Dict], **kw) -> str:
        return self.agent.multi_editor.preview(edits)

    def handle_undo_edit(self, operation_id: str = None, **kw) -> str:
        success, msg = self.agent.multi_editor.undo(operation_id)
        return msg

    def handle_redo_edit(self, operation_id: str = None, **kw) -> str:
        success, msg = self.agent.multi_editor.redo(operation_id)
        return msg

    def handle_edit_history(self, **kw) -> str:
        return self.agent.multi_editor.get_history()

    # ==================== 代码补全 ====================

    def handle_get_completions(self, file: str, line: int, column: int, **kw) -> str:
        from completion import Position
        pos = Position(line=line, column=column)
        completions = self.agent.completion.get_completions(file, pos)
        return self.agent.completion.format_completions(completions)

    def handle_get_inline_suggestion(self, file: str, line: int, column: int, **kw) -> str:
        from completion import Position
        pos = Position(line=line, column=column)
        suggestion = self.agent.completion.get_inline_suggestion(file, pos)
        if suggestion:
            return f"内联建议: {suggestion.text}"
        return "无内联建议"

    # ==================== Diff Viewer ====================

    def handle_show_diff(self, file: str = None, staged: bool = False, **kw) -> str:
        return self.agent.git.show_diff(file, staged)

    def handle_diff_files(self, old_file: str, new_file: str, **kw) -> str:
        file_diff = self.agent.diff_generator.generate_from_files(old_file, new_file)
        if file_diff:
            return self.agent.diff_formatter.format_diff(file_diff)
        return "无法生成差异"

    def handle_review_changes(self, file: str = None, **kw) -> str:
        diff_text = self.agent.git.show_diff(file)
        if diff_text in ("无差异", "[错误]"):
            return diff_text
        return diff_text

    # ==================== 沙箱 ====================

    def handle_execute_python(self, code: str, timeout: int = None, **kw) -> str:
        exec_result = self.agent.sandbox.execute_python(code=code, timeout=timeout)
        return exec_result.to_string()

    def handle_execute_javascript(self, code: str, timeout: int = None, **kw) -> str:
        exec_result = self.agent.sandbox.execute_javascript(code=code, timeout=timeout)
        return exec_result.to_string()

    def handle_execute_shell(self, command: str, timeout: int = None, **kw) -> str:
        exec_result = self.agent.sandbox.execute_shell(command=command, timeout=timeout)
        return exec_result.to_string()

    def handle_execute_in_sandbox(self, code: str, language: str, timeout: int = None, **kw) -> str:
        exec_result = self.agent.sandbox.execute(code=code, language=language, timeout=timeout)
        return exec_result.to_string()

    def handle_validate_code(self, code: str, language: str, **kw) -> str:
        valid, error = self.agent.sandbox.validate_code(code=code, language=language)
        return "代码语法正确" if valid else f"语法错误: {error}"
