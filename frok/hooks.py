"""
Frok Hooks系统
事件驱动的自动化，在工具调用前后执行自定义脚本
灵感来自Claude Code的Hooks机制
"""

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 数据结构 ====================

@dataclass
class HookResult:
    """Hook执行结果"""
    success: bool
    hook_name: str
    output: str = ""
    error: str = ""
    blocked: bool = False  # 是否阻止后续执行
    modified_params: Dict = field(default_factory=dict)  # 修改后的参数


@dataclass
class Hook:
    """Hook定义"""
    id: str
    name: str
    event: str
    action: str  # shell命令或Python函数名
    tools: List[str] = field(default_factory=list)  # 限制哪些工具触发，空=所有
    enabled: bool = True
    description: str = ""
    blocking: bool = False  # 是否可以阻止操作
    priority: int = 0  # 优先级，数字越小越先执行


# ==================== Hook管理器 ====================

class HookManager:
    """
    事件驱动的Hook系统

    支持的事件:
    - pre_tool_call: 工具调用前
    - post_tool_call: 工具调用后
    - pre_task: 任务开始前
    - post_task: 任务结束后
    - on_error: 错误发生时
    - on_file_change: 文件变更时
    """

    EVENTS = [
        "pre_tool_call",
        "post_tool_call",
        "pre_task",
        "post_task",
        "on_error",
        "on_file_change",
    ]

    def __init__(self, hooks_dir: str = None):
        self.hooks_dir = Path(hooks_dir or os.path.join(os.path.dirname(__file__), "hooks"))
        self.hooks_dir.mkdir(parents=True, exist_ok=True)

        self.hooks: Dict[str, Hook] = {}
        self.builtin_hooks: Dict[str, Callable] = {}

        # 加载配置
        self._load_hooks_config()

    def _load_hooks_config(self):
        """从配置文件加载hooks"""
        config_file = self.hooks_dir / "hooks.json"
        if not config_file.exists():
            self._create_default_config()
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            for event, hooks_list in config.items():
                if event not in self.EVENTS:
                    continue
                for hook_data in hooks_list:
                    hook = Hook(
                        id=hook_data.get("id", str(uuid.uuid4())[:8]),
                        name=hook_data["name"],
                        event=event,
                        action=hook_data["action"],
                        tools=hook_data.get("tools", []),
                        enabled=hook_data.get("enabled", True),
                        description=hook_data.get("description", ""),
                        blocking=hook_data.get("blocking", False),
                        priority=hook_data.get("priority", 0),
                    )
                    self.hooks[hook.id] = hook

        except Exception as e:
            print(f"[Hooks] 配置加载失败: {e}")

    def _create_default_config(self):
        """创建默认配置"""
        default_config = {
            "pre_tool_call": [
                {
                    "name": "backup_before_edit",
                    "description": "编辑文件前自动备份",
                    "action": "backup",
                    "tools": ["edit_file", "write_file"],
                    "enabled": False,
                    "priority": 10
                }
            ],
            "post_tool_call": [
                {
                    "name": "log_tool_call",
                    "description": "记录工具调用日志",
                    "action": "log",
                    "tools": [],
                    "enabled": True,
                    "priority": 0
                }
            ],
            "on_error": [
                {
                    "name": "error_notify",
                    "description": "错误发生时通知",
                    "action": "notify",
                    "tools": [],
                    "enabled": False,
                    "priority": 0
                }
            ]
        }

        config_file = self.hooks_dir / "hooks.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

    # ==================== Hook注册 ====================

    def register(self, event: str, name: str, action: str,
                 tools: List[str] = None, description: str = "",
                 blocking: bool = False, priority: int = 0) -> str:
        """注册一个新的Hook"""
        if event not in self.EVENTS:
            raise ValueError(f"不支持的事件类型: {event}")

        hook_id = str(uuid.uuid4())[:8]
        hook = Hook(
            id=hook_id,
            name=name,
            event=event,
            action=action,
            tools=tools or [],
            enabled=True,
            description=description,
            blocking=blocking,
            priority=priority,
        )
        self.hooks[hook_id] = hook
        self._save_hooks_config()
        return hook_id

    def unregister(self, hook_id: str) -> bool:
        """注销Hook"""
        if hook_id in self.hooks:
            del self.hooks[hook_id]
            self._save_hooks_config()
            return True
        return False

    def enable(self, hook_id: str) -> bool:
        """启用Hook"""
        if hook_id in self.hooks:
            self.hooks[hook_id].enabled = True
            self._save_hooks_config()
            return True
        return False

    def disable(self, hook_id: str) -> bool:
        """禁用Hook"""
        if hook_id in self.hooks:
            self.hooks[hook_id].enabled = False
            self._save_hooks_config()
            return True
        return False

    def _save_hooks_config(self):
        """保存hooks配置到文件"""
        config = {}
        for event in self.EVENTS:
            config[event] = []

        for hook in self.hooks.values():
            config[hook.event].append({
                "id": hook.id,
                "name": hook.name,
                "description": hook.description,
                "action": hook.action,
                "tools": hook.tools,
                "enabled": hook.enabled,
                "blocking": hook.blocking,
                "priority": hook.priority,
            })

        config_file = self.hooks_dir / "hooks.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    # ==================== Hook触发 ====================

    def trigger(self, event: str, context: Dict[str, Any]) -> List[HookResult]:
        """
        触发指定事件的所有Hook

        Args:
            event: 事件类型
            context: 上下文信息，包含:
                - tool_name: 工具名称 (pre/post_tool_call)
                - parameters: 工具参数
                - result: 工具结果 (post_tool_call)
                - error: 错误信息 (on_error)
                - file_path: 文件路径 (on_file_change)

        Returns:
            HookResult列表
        """
        if event not in self.EVENTS:
            return []

        results = []
        tool_name = context.get("tool_name", "")

        # 获取该事件的所有hook，按优先级排序
        event_hooks = sorted(
            [h for h in self.hooks.values()
             if h.event == event and h.enabled
             and (not h.tools or tool_name in h.tools)],
            key=lambda h: h.priority
        )

        for hook in event_hooks:
            result = self._execute_hook(hook, context)
            results.append(result)

            # 如果hook阻止了操作且是blocking的，停止执行后续hook
            if result.blocked and hook.blocking:
                break

        return results

    def _execute_hook(self, hook: Hook, context: Dict[str, Any]) -> HookResult:
        """执行单个Hook"""
        try:
            # 内置动作
            if hook.action in self.builtin_hooks:
                return self.builtin_hooks[hook.action](hook, context)

            # Shell命令
            if hook.action.startswith("shell:"):
                command = hook.action[6:].strip()
                command = self._interpolate(command, context)
                return self._execute_shell_hook(hook, command)

            # 内置动作名称
            if hook.action == "backup":
                return self._action_backup(hook, context)
            elif hook.action == "log":
                return self._action_log(hook, context)
            elif hook.action == "notify":
                return self._action_notify(hook, context)
            elif hook.action == "validate":
                return self._action_validate(hook, context)

            # 默认当作shell命令
            command = self._interpolate(hook.action, context)
            return self._execute_shell_hook(hook, command)

        except Exception as e:
            return HookResult(
                success=False,
                hook_name=hook.name,
                error=str(e)
            )

    def _execute_shell_hook(self, hook: Hook, command: str) -> HookResult:
        """执行Shell命令Hook"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return HookResult(
                success=result.returncode == 0,
                hook_name=hook.name,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
                blocked=result.returncode != 0 and hook.blocking
            )
        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                hook_name=hook.name,
                error="Hook执行超时 (30秒)"
            )

    def _interpolate(self, template: str, context: Dict[str, Any]) -> str:
        """替换模板中的变量"""
        result = template
        for key, value in context.items():
            if isinstance(value, (str, int, float)):
                result = result.replace(f"${{{key}}}", str(value))
        return result

    # ==================== 内置动作 ====================

    def _action_backup(self, hook: Hook, context: Dict[str, Any]) -> HookResult:
        """备份文件"""
        file_path = context.get("parameters", {}).get("path", "")
        if not file_path:
            return HookResult(success=True, hook_name=hook.name, output="无需备份")

        try:
            src = Path(file_path)
            if src.exists():
                dst = src.with_suffix(src.suffix + ".bak")
                import shutil
                shutil.copy2(src, dst)
                return HookResult(
                    success=True,
                    hook_name=hook.name,
                    output=f"已备份: {dst}"
                )
            return HookResult(success=True, hook_name=hook.name, output="文件不存在，无需备份")
        except Exception as e:
            return HookResult(success=False, hook_name=hook.name, error=str(e))

    def _action_log(self, hook: Hook, context: Dict[str, Any]) -> HookResult:
        """记录日志"""
        log_file = self.hooks_dir / "hooks.log"
        tool_name = context.get("tool_name", "unknown")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = f"[{timestamp}] {tool_name}: {json.dumps(context.get('parameters', {}), ensure_ascii=False)}\n"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            return HookResult(success=True, hook_name=hook.name, output="已记录日志")
        except Exception as e:
            return HookResult(success=False, hook_name=hook.name, error=str(e))

    def _action_notify(self, hook: Hook, context: Dict[str, Any]) -> HookResult:
        """通知（目前只打印）"""
        error = context.get("error", "未知错误")
        print(f"\n[Hook通知] 错误发生: {error}")
        return HookResult(success=True, hook_name=hook.name, output="已通知")

    def _action_validate(self, hook: Hook, context: Dict[str, Any]) -> HookResult:
        """验证参数"""
        # 示例：检查文件路径是否安全
        file_path = context.get("parameters", {}).get("path", "")
        if file_path:
            dangerous_paths = ["/etc", "/usr", "/bin", "/sbin", "C:\\Windows"]
            for dp in dangerous_paths:
                if file_path.startswith(dp):
                    return HookResult(
                        success=False,
                        hook_name=hook.name,
                        error=f"不允许访问系统目录: {dp}",
                        blocked=True
                    )
        return HookResult(success=True, hook_name=hook.name, output="验证通过")

    # ==================== 内置Hook注册 ====================

    def register_builtin(self, name: str, handler: Callable):
        """注册内置Hook处理器"""
        self.builtin_hooks[name] = handler

    # ==================== 查询 ====================

    def list_hooks(self, event: str = None) -> str:
        """列出所有Hook"""
        hooks_list = []
        for hook in self.hooks.values():
            if event and hook.event != event:
                continue
            status = "✓" if hook.enabled else "✗"
            blocking = " [阻塞]" if hook.blocking else ""
            hooks_list.append(
                f"  [{status}] {hook.id} - {hook.name}{blocking}\n"
                f"        事件: {hook.event} | 动作: {hook.action}\n"
                f"        {hook.description}"
            )

        if not hooks_list:
            return "暂无Hook"

        return "已注册的Hook:\n" + "\n".join(hooks_list)

    def get_hook(self, hook_id: str) -> Optional[Hook]:
        """获取Hook详情"""
        return self.hooks.get(hook_id)


# ==================== 工具定义 ====================

HOOK_TOOLS = [
    {
        "name": "list_hooks",
        "description": "列出所有Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "event": {
                    "type": "string",
                    "description": "按事件类型筛选 (可选)"
                }
            }
        }
    },
    {
        "name": "register_hook",
        "description": "注册一个新的Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "event": {
                    "type": "string",
                    "description": "事件类型 (pre_tool_call/post_tool_call/pre_task/post_task/on_error/on_file_change)"
                },
                "name": {
                    "type": "string",
                    "description": "Hook名称"
                },
                "action": {
                    "type": "string",
                    "description": "动作 (backup/log/notify/validate 或 shell:命令)"
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "限制哪些工具触发 (空=所有)"
                },
                "description": {
                    "type": "string",
                    "description": "描述"
                },
                "blocking": {
                    "type": "boolean",
                    "description": "是否可以阻止操作"
                }
            },
            "required": ["event", "name", "action"]
        }
    },
    {
        "name": "unregister_hook",
        "description": "注销一个Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "hook_id": {
                    "type": "string",
                    "description": "Hook ID"
                }
            },
            "required": ["hook_id"]
        }
    },
    {
        "name": "enable_hook",
        "description": "启用一个Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "hook_id": {
                    "type": "string",
                    "description": "Hook ID"
                }
            },
            "required": ["hook_id"]
        }
    },
    {
        "name": "disable_hook",
        "description": "禁用一个Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "hook_id": {
                    "type": "string",
                    "description": "Hook ID"
                }
            },
            "required": ["hook_id"]
        }
    }
]
