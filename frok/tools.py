"""
Frok 工具系统
定义所有可用工具，供AI自动调用
"""

import json
from json import JSONDecoder
import os
import subprocess
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# ==================== 工具定义 ====================

TOOLS_SCHEMA = [
    {
        "name": "read_file",
        "description": "读取文件内容。支持指定行范围。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "start_line": {"type": "integer", "description": "起始行号（可选）"},
                "end_line": {"type": "integer", "description": "结束行号（可选）"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "写入文件。如果文件不存在会自动创建。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "edit_file",
        "description": "精确编辑文件。将old_string替换为new_string。old_string必须在文件中唯一。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "要替换的旧内容"},
                "new_string": {"type": "string", "description": "替换后的新内容"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "append_file",
        "description": "追加内容到文件末尾。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要追加的内容"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "delete_file",
        "description": "删除文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "copy_file",
        "description": "复制文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源文件路径"},
                "destination": {"type": "string", "description": "目标路径"}
            },
            "required": ["source", "destination"]
        }
    },
    {
        "name": "move_file",
        "description": "移动文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源文件路径"},
                "destination": {"type": "string", "description": "目标路径"}
            },
            "required": ["source", "destination"]
        }
    },
    {
        "name": "list_directory",
        "description": "列出目录内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径（默认当前目录）"},
                "show_hidden": {"type": "boolean", "description": "是否显示隐藏文件"}
            }
        }
    },
    {
        "name": "get_tree",
        "description": "获取目录树结构。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
                "max_depth": {"type": "integer", "description": "最大深度（默认3）"}
            }
        }
    },
    {
        "name": "search_files",
        "description": "在文件中搜索内容（类似grep）。",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "搜索目录"},
                "pattern": {"type": "string", "description": "搜索模式（正则表达式）"},
                "glob": {"type": "string", "description": "文件匹配模式（如 *.py）"}
            },
            "required": ["directory", "pattern"]
        }
    },
    {
        "name": "find_files",
        "description": "查找文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "搜索目录"},
                "pattern": {"type": "string", "description": "文件名模式"}
            },
            "required": ["directory", "pattern"]
        }
    },
    {
        "name": "create_directory",
        "description": "创建文件夹。如果文件夹已存在则忽略，会自动创建父目录。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件夹路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "execute_command",
        "description": "执行系统命令。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "working_directory": {"type": "string", "description": "工作目录"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "git_command",
        "description": "执行Git命令。",
        "parameters": {
            "type": "object",
            "properties": {
                "subcommand": {"type": "string", "description": "Git子命令（status/diff/log/add/commit/push/pull等）"},
                "args": {"type": "string", "description": "额外参数"}
            },
            "required": ["subcommand"]
        }
    },
    {
        "name": "ask_user",
        "description": "向用户提问。当需要用户确认或获取更多信息时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要问的问题"}
            },
            "required": ["question"]
        }
    },
    {
        "name": "finish",
        "description": "完成任务。当任务已完成时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "任务结果总结"}
            },
            "required": ["result"]
        }
    },
    # ===== 记忆工具 =====
    {
        "name": "remember_user",
        "description": "记住用户相关信息（偏好、角色、技能等）",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "value": {"type": "string", "description": "记忆内容"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "remember_project",
        "description": "记住项目相关信息（目标、进度、决策等）",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "value": {"type": "string", "description": "记忆内容"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "remember_feedback",
        "description": "记住用户反馈（纠正、确认、偏好等）",
        "parameters": {
            "type": "object",
            "properties": {
                "feedback": {"type": "string", "description": "反馈内容"},
                "category": {"type": "string", "description": "类别（correction/confirmation/preference）"}
            },
            "required": ["feedback"]
        }
    },
    {
        "name": "recall_memory",
        "description": "回忆记忆内容",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "记忆类型（user/project/feedback）"},
                "key": {"type": "string", "description": "特定键名（可选）"}
            },
            "required": ["type"]
        }
    },
    # ===== 技能工具 =====
    {
        "name": "list_skills",
        "description": "列出所有可用技能",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "use_skill",
        "description": "使用指定技能",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "技能名称"},
                "task": {"type": "string", "description": "具体任务描述"}
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "create_skill",
        "description": "创建新技能",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "技能名称"},
                "description": {"type": "string", "description": "技能描述"},
                "trigger": {"type": "string", "description": "触发词"},
                "system_prompt": {"type": "string", "description": "系统提示词"},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "执行步骤"}
            },
            "required": ["name", "description", "system_prompt"]
        }
    },
    # ===== Plan工具 =====
    {
        "name": "create_plan",
        "description": "创建执行计划。在执行复杂任务前，先创建计划供用户审核。",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "任务描述"},
                "description": {"type": "string", "description": "详细说明"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "tool": {"type": "string"},
                            "params": {"type": "object"}
                        }
                    },
                    "description": "执行步骤列表"
                }
            },
            "required": ["task", "steps"]
        }
    },
    {
        "name": "approve_plan",
        "description": "批准执行计划",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "计划ID"}
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "execute_plan",
        "description": "执行已批准的计划",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "计划ID"}
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "show_plan",
        "description": "显示当前计划",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "计划ID (可选)"}
            }
        }
    },
    # ===== Subagent工具 =====
    {
        "name": "spawn_agent",
        "description": "创建子代理执行独立任务",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "任务描述"},
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "允许使用的工具列表 (可选)"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "parallel_tasks",
        "description": "并行执行多个独立任务",
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "任务列表"
                }
            },
            "required": ["tasks"]
        }
    },
    {
        "name": "list_agents",
        "description": "列出所有子代理",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    # ===== Hooks工具 =====
    {
        "name": "list_hooks",
        "description": "列出所有Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "description": "按事件类型筛选 (可选)"}
            }
        }
    },
    {
        "name": "register_hook",
        "description": "注册一个新的Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "description": "事件类型 (pre_tool_call/post_tool_call/pre_task/post_task/on_error/on_file_change)"},
                "name": {"type": "string", "description": "Hook名称"},
                "action": {"type": "string", "description": "动作 (backup/log/notify/validate 或 shell:命令)"},
                "tools": {"type": "array", "items": {"type": "string"}, "description": "限制哪些工具触发"},
                "description": {"type": "string", "description": "描述"},
                "blocking": {"type": "boolean", "description": "是否可以阻止操作"}
            },
            "required": ["event", "name", "action"]
        }
    },
    {
        "name": "enable_hook",
        "description": "启用一个Hook",
        "parameters": {
            "type": "object",
            "properties": {
                "hook_id": {"type": "string", "description": "Hook ID"}
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
                "hook_id": {"type": "string", "description": "Hook ID"}
            },
            "required": ["hook_id"]
        }
    },
    # ===== Git增强工具 =====
    {
        "name": "git_status",
        "description": "获取详细的Git状态",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "git_diff",
        "description": "查看文件差异",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径 (可选)"},
                "staged": {"type": "boolean", "description": "是否查看暂存区"}
            }
        }
    },
    {
        "name": "git_auto_commit",
        "description": "自动提交变更",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "提交信息 (可选)"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "文件列表"},
                "add_all": {"type": "boolean", "description": "是否添加所有变更"}
            }
        }
    },
    {
        "name": "git_log",
        "description": "查看提交历史",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "显示数量"},
                "graph": {"type": "boolean", "description": "是否显示图形"}
            }
        }
    },
    {
        "name": "git_blame",
        "description": "代码追溯",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径"},
                "start_line": {"type": "integer", "description": "起始行"},
                "end_line": {"type": "integer", "description": "结束行"}
            },
            "required": ["file"]
        }
    },
    {
        "name": "git_stash",
        "description": "暂存管理",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作 (save/list/pop/drop)"},
                "message": {"type": "string", "description": "暂存信息"},
                "index": {"type": "integer", "description": "暂存索引"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "git_branch",
        "description": "分支管理",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作 (list/create/delete/checkout)"},
                "name": {"type": "string", "description": "分支名"},
                "remote": {"type": "boolean", "description": "是否显示远程分支"}
            },
            "required": ["action"]
        }
    },
    # ===== Worktree工具 =====
    {
        "name": "worktree_list",
        "description": "列出所有工作树",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "worktree_create",
        "description": "创建新的工作树",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工作树名称"},
                "branch": {"type": "string", "description": "分支名"},
                "new_branch": {"type": "boolean", "description": "是否创建新分支"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "worktree_remove",
        "description": "删除工作树",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工作树名称"},
                "force": {"type": "boolean", "description": "是否强制删除"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "worktree_merge",
        "description": "合并工作树变更",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源工作树名称"},
                "message": {"type": "string", "description": "合并信息"}
            },
            "required": ["source"]
        }
    },
    # ===== CodeMap工具 =====
    {
        "name": "generate_codemap",
        "description": "生成代码地图",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "目录路径"},
                "detailed": {"type": "boolean", "description": "是否显示详细信息"}
            },
            "required": ["directory"]
        }
    },
    {
        "name": "find_symbol",
        "description": "查找符号定义",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "搜索目录"},
                "symbol": {"type": "string", "description": "符号名称"}
            },
            "required": ["directory", "symbol"]
        }
    },
    {
        "name": "find_references",
        "description": "查找符号引用",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "搜索目录"},
                "symbol": {"type": "string", "description": "符号名称"}
            },
            "required": ["directory", "symbol"]
        }
    },
    {
        "name": "file_summary",
        "description": "获取文件摘要",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径"}
            },
            "required": ["file"]
        }
    },
    # ===== 多文件编辑工具 =====
    {
        "name": "edit_multiple",
        "description": "批量编辑多个文件",
        "parameters": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "文件路径"},
                            "action": {"type": "string", "description": "操作 (create/modify/delete)"},
                            "content": {"type": "string", "description": "新内容"},
                            "old_string": {"type": "string", "description": "要替换的旧内容"},
                            "new_string": {"type": "string", "description": "替换后的新内容"}
                        },
                        "required": ["file_path"]
                    },
                    "description": "编辑列表"
                },
                "description": {"type": "string", "description": "操作描述"}
            },
            "required": ["edits"]
        }
    },
    {
        "name": "preview_edits",
        "description": "预览编辑结果",
        "parameters": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "action": {"type": "string"},
                            "content": {"type": "string"},
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"}
                        },
                        "required": ["file_path"]
                    }
                }
            },
            "required": ["edits"]
        }
    },
    {
        "name": "undo_edit",
        "description": "撤销编辑操作",
        "parameters": {
            "type": "object",
            "properties": {
                "operation_id": {"type": "string", "description": "操作ID (可选)"}
            }
        }
    },
    {
        "name": "redo_edit",
        "description": "重做编辑操作",
        "parameters": {
            "type": "object",
            "properties": {
                "operation_id": {"type": "string", "description": "操作ID (可选)"}
            }
        }
    },
    {
        "name": "edit_history",
        "description": "查看编辑历史",
        "parameters": {"type": "object", "properties": {}}
    },
    # ===== 代码补全工具 =====
    {
        "name": "get_completions",
        "description": "获取代码补全建议",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径"},
                "line": {"type": "integer", "description": "行号"},
                "column": {"type": "integer", "description": "列号"}
            },
            "required": ["file", "line", "column"]
        }
    },
    {
        "name": "get_inline_suggestion",
        "description": "获取内联代码建议",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径"},
                "line": {"type": "integer", "description": "行号"},
                "column": {"type": "integer", "description": "列号"}
            },
            "required": ["file", "line", "column"]
        }
    },
    # ===== 沙箱执行工具 =====
    {
        "name": "execute_python",
        "description": "在沙箱中执行Python代码",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python代码"},
                "timeout": {"type": "integer", "description": "超时时间 (秒)"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "execute_javascript",
        "description": "在沙箱中执行JavaScript代码",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "JavaScript代码"},
                "timeout": {"type": "integer", "description": "超时时间 (秒)"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "execute_in_sandbox",
        "description": "在沙箱中执行代码 (自动检测语言)",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "代码内容"},
                "language": {"type": "string", "description": "语言 (python/javascript/shell)"},
                "timeout": {"type": "integer", "description": "超时时间 (秒)"}
            },
            "required": ["code", "language"]
        }
    },
    {
        "name": "validate_code",
        "description": "验证代码语法",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "代码内容"},
                "language": {"type": "string", "description": "语言 (python/javascript/shell)"}
            },
            "required": ["code", "language"]
        }
    }
]

# ==================== 嵌入式工具集成 ====================

def _get_embedded_tools() -> List[Dict]:
    """获取嵌入式工具定义（延迟导入避免循环依赖）"""
    from frok.embedded import EMBEDDED_TOOLS
    return EMBEDDED_TOOLS


def get_all_tools() -> List[Dict]:
    """获取所有可用工具（包括嵌入式工具）"""
    all_tools = TOOLS_SCHEMA.copy()
    try:
        all_tools.extend(_get_embedded_tools())
    except ImportError:
        pass  # 嵌入式模块不可用时忽略
    return all_tools


# 与 agent._execute_tool_call 中注册的工具名一致（用于从模型文本中可靠识别 tool_call）
KNOWN_TOOL_NAMES = frozenset(t["name"] for t in TOOLS_SCHEMA) | frozenset({
    "remember_user", "remember_project", "remember_feedback", "recall_memory",
    "list_skills", "use_skill", "create_skill",
    "create_plan", "approve_plan", "execute_plan", "show_plan", "list_plans", "update_step",
    "spawn_agent", "run_agent", "parallel_tasks", "collect_result", "list_agents", "cancel_agent",
    "list_hooks", "register_hook", "unregister_hook", "enable_hook", "disable_hook",
    "git_status", "git_diff", "git_auto_commit", "git_log", "git_blame", "git_stash", "git_branch", "git_push", "git_pull",
    "worktree_list", "worktree_create", "worktree_remove", "worktree_switch", "worktree_merge", "worktree_snapshot", "worktree_status",
    "generate_codemap", "find_symbol", "find_references", "file_summary", "list_symbols",
    "edit_multiple", "preview_edits", "undo_edit", "redo_edit", "edit_history",
    "get_completions", "get_inline_suggestion",
    "execute_python", "execute_javascript", "execute_shell", "execute_in_sandbox", "validate_code",
    # 嵌入式工具
    "embedded_detect", "embedded_generate", "embedded_compile", "embedded_upload",
    "embedded_monitor", "embedded_list_boards", "embedded_list_ports", "embedded_stop_monitor",
})

# ==================== 工具执行器 ====================

class ToolExecutor:
    def __init__(self, working_dir: str = None):
        self.working_dir = working_dir or os.getcwd()

    def _normalize_path(self, path: str) -> str:
        """标准化路径，处理Windows路径"""
        if '\\' in path and ':' in path:
            # Windows路径，转换为WSL路径
            drive = path[0].lower()
            rest = path[2:].replace('\\', '/')
            return f"/mnt/{drive}{rest}"
        return path

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """执行工具"""
        method = getattr(self, tool_name, None)
        if method:
            try:
                return method(**parameters)
            except Exception as e:
                return f"[错误] {tool_name} 执行失败: {e}"
        return f"[错误] 未知工具: {tool_name}"

    def read_file(self, path: str, start_line: int = None, end_line: int = None) -> str:
        """读取文件"""
        try:
            path = self._normalize_path(path)
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return f"[错误] 文件不存在: {path}"
            if file_path.stat().st_size > 100000:
                return f"[错误] 文件太大 ({file_path.stat().st_size} bytes)"

            with open(file_path, "r", encoding="utf-8") as f:
                if start_line or end_line:
                    lines = f.readlines()
                    start = (start_line or 1) - 1
                    end = end_line or len(lines)
                    result = []
                    for i in range(start, min(end, len(lines))):
                        result.append(f"{i+1:4d} | {lines[i]}".rstrip())
                    return "\n".join(result)
                else:
                    return f.read()
        except Exception as e:
            return f"[错误] {e}"

    def write_file(self, path: str, content: str) -> str:
        """写入文件"""
        try:
            path = self._normalize_path(path)
            file_path = Path(path).expanduser().resolve()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"[已写入] {file_path} ({len(content)} bytes)"
        except Exception as e:
            return f"[错误] {e}"

    def create_directory(self, path: str) -> str:
        """创建文件夹"""
        try:
            path = self._normalize_path(path)
            dir_path = Path(path).expanduser().resolve()
            dir_path.mkdir(parents=True, exist_ok=True)
            return f"[已创建目录] {dir_path}"
        except Exception as e:
            return f"[错误] {e}"

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        """编辑文件"""
        try:
            path = self._normalize_path(path)
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return f"[错误] 文件不存在: {path}"

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            count = content.count(old_string)
            if count == 0:
                return "[错误] 未找到匹配内容"
            if count > 1:
                return f"[错误] 找到 {count} 处匹配，请提供更精确的内容"

            new_content = content.replace(old_string, new_string, 1)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"[已编辑] {file_path}"
        except Exception as e:
            return f"[错误] {e}"

    def append_file(self, path: str, content: str) -> str:
        """追加内容"""
        try:
            file_path = Path(path).expanduser().resolve()
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"[已追加] {file_path}"
        except Exception as e:
            return f"[错误] {e}"

    def delete_file(self, path: str) -> str:
        """删除文件"""
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return f"[错误] 文件不存在: {path}"
            file_path.unlink()
            return f"[已删除] {file_path}"
        except Exception as e:
            return f"[错误] {e}"

    def copy_file(self, source: str, destination: str) -> str:
        """复制文件"""
        try:
            src = Path(source).expanduser().resolve()
            dst = Path(destination).expanduser().resolve()
            if not src.exists():
                return f"[错误] 源文件不存在: {source}"
            if dst.is_dir():
                dst = dst / src.name
            shutil.copy2(src, dst)
            return f"[已复制] {src} -> {dst}"
        except Exception as e:
            return f"[错误] {e}"

    def move_file(self, source: str, destination: str) -> str:
        """移动文件"""
        try:
            src = Path(source).expanduser().resolve()
            dst = Path(destination).expanduser().resolve()
            if not src.exists():
                return f"[错误] 源文件不存在: {source}"
            shutil.move(str(src), str(dst))
            return f"[已移动] {src} -> {dst}"
        except Exception as e:
            return f"[错误] {e}"

    def list_directory(self, path: str = ".", show_hidden: bool = False) -> str:
        """列出目录"""
        try:
            dir_path = Path(path).expanduser().resolve()
            if not dir_path.exists():
                return f"[错误] 目录不存在: {path}"

            entries = sorted(dir_path.iterdir(), key=lambda x: x.name.lower())
            if not show_hidden:
                entries = [e for e in entries if not e.name.startswith('.')]

            output = []
            for entry in entries:
                if entry.is_dir():
                    output.append(f"  📁 {entry.name}/")
                else:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024*1024:
                        size_str = f"{size//1024}KB"
                    else:
                        size_str = f"{size//(1024*1024)}MB"
                    output.append(f"  📄 {entry.name} ({size_str})")

            return "\n".join(output) if output else "空目录"
        except Exception as e:
            return f"[错误] {e}"

    def get_tree(self, path: str = ".", max_depth: int = 3) -> str:
        """获取目录树"""
        try:
            dir_path = Path(path).expanduser().resolve()
            if not dir_path.exists():
                return f"[错误] 目录不存在: {path}"

            output = [f"{dir_path.name}/"]
            self._build_tree(dir_path, "", max_depth, 0, output)
            return "\n".join(output)
        except Exception as e:
            return f"[错误] {e}"

    def _build_tree(self, path, prefix, max_depth, current_depth, output):
        """递归构建目录树"""
        if current_depth >= max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            dirs = [e for e in entries if e.is_dir() and not e.name.startswith('.')]
            files = [e for e in entries if e.is_file() and not e.name.startswith('.')]

            all_entries = dirs + files
            for i, entry in enumerate(all_entries):
                is_last = (i == len(all_entries) - 1)
                connector = "└── " if is_last else "├── "

                if entry.is_dir():
                    output.append(f"{prefix}{connector}{entry.name}/")
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    self._build_tree(entry, new_prefix, max_depth, current_depth + 1, output)
                else:
                    output.append(f"{prefix}{connector}{entry.name}")
        except PermissionError:
            output.append(f"{prefix}└── [权限不足]")

    def search_files(self, directory: str, pattern: str, glob: str = "*") -> str:
        """搜索文件内容"""
        try:
            dir_path = Path(directory).expanduser().resolve()
            if not dir_path.exists():
                return f"[错误] 目录不存在: {directory}"

            results = []
            files = list(dir_path.rglob(glob))

            for file_path in files:
                if file_path.is_file() and not any(skip in str(file_path) for skip in ['.git', 'node_modules', '__pycache__']):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                results.append(f"{file_path}:{i}: {line.rstrip()}")
                                if len(results) >= 50:
                                    break
                    except:
                        continue
                if len(results) >= 50:
                    break

            return "\n".join(results) if results else "未找到匹配内容"
        except Exception as e:
            return f"[错误] {e}"

    def find_files(self, directory: str, pattern: str) -> str:
        """查找文件"""
        try:
            dir_path = Path(directory).expanduser().resolve()
            if not dir_path.exists():
                return f"[错误] 目录不存在: {directory}"

            files = list(dir_path.rglob(pattern))
            return "\n".join(str(f) for f in files[:50]) if files else "未找到匹配文件"
        except Exception as e:
            return f"[错误] {e}"

    def execute_command(self, command: str, working_directory: str = None) -> str:
        """执行命令"""
        try:
            cwd = working_directory or self.working_dir
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[返回码: {result.returncode}]"
            return output if output else "[命令执行完成，无输出]"
        except subprocess.TimeoutExpired:
            return "[错误] 命令执行超时 (30秒)"
        except Exception as e:
            return f"[错误] {e}"

    def git_command(self, subcommand: str, args: str = "") -> str:
        """执行Git命令"""
        cmd = f"git {subcommand}"
        if args:
            cmd += f" {args}"
        return self.execute_command(cmd)

    def ask_user(self, question: str) -> str:
        """向用户提问（在智能体模式下返回问题文本）"""
        return f"[需要用户回答] {question}"

    def finish(self, result: str) -> str:
        """完成任务"""
        return f"[任务完成] {result}"

# ==================== 工具格式化 ====================

def get_tools_for_prompt() -> str:
    """获取工具描述，用于提示词"""
    lines = ["你可以使用以下工具:\n"]
    for tool in TOOLS_SCHEMA:
        params = []
        for name, info in tool["parameters"]["properties"].items():
            required = name in tool["parameters"].get("required", [])
            param_str = f"{name}" + (" (必填)" if required else " (可选)")
            params.append(param_str)

        lines.append(f"### {tool['name']}")
        lines.append(f"{tool['description']}")
        lines.append(f"参数: {', '.join(params)}")
        lines.append("")

    lines.append("## 使用格式")
    lines.append("要调用工具，请使用以下JSON格式:")
    lines.append('```tool_call')
    lines.append('{"name": "工具名", "parameters": {"参数1": "值1", "参数2": "值2"}}')
    lines.append('```\n')
    lines.append("你可以一次调用多个工具，每个工具用单独的tool_call块。")
    lines.append("当任务完成时，调用 finish 工具。")

    return "\n".join(lines)

def parse_tool_calls(text: str) -> List[Dict]:
    """从AI响应中解析工具调用（支持 markdown 围栏、嵌套 parameters、裸 JSON）"""
    if not text or not text.strip():
        return []

    calls: List[Dict] = []

    def fix_json_escapes(json_str: str) -> str:
        """修复JSON中的反斜杠转义问题"""
        fixed_chars = []
        i = 0
        while i < len(json_str):
            if json_str[i] == '\\' and i + 1 < len(json_str):
                next_char = json_str[i + 1]
                if next_char == '"':
                    fixed_chars.append('\\"')
                    i += 2
                elif next_char == '\\':
                    fixed_chars.append('\\\\')
                    i += 2
                elif next_char == '/':
                    fixed_chars.append('\\/')
                    i += 2
                elif next_char == 'n':
                    if i + 2 < len(json_str) and json_str[i + 2] in ['"', '}']:
                        fixed_chars.append('\\n')
                    else:
                        fixed_chars.append('\\\\n')
                    i += 2
                else:
                    fixed_chars.append('\\\\')
                    i += 1
            else:
                fixed_chars.append(json_str[i])
                i += 1
        return ''.join(fixed_chars)

    def try_parse_json(json_str: str) -> Optional[Dict]:
        try:
            obj = json.loads(json_str)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            try:
                fixed = fix_json_escapes(json_str)
                obj = json.loads(fixed)
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None

    def normalize_call(call: Dict) -> None:
        params = call.get("parameters")
        if not isinstance(params, dict):
            call["parameters"] = {}

    def append_if_tool(call: Optional[Dict]) -> None:
        if not call or not isinstance(call.get("name"), str):
            return
        if call["name"] not in KNOWN_TOOL_NAMES:
            return
        normalize_call(call)
        calls.append(call)

    def parse_multi_json(block: str) -> None:
        """从一段文本中顺序解析多个 JSON 对象（同一围栏内多工具）"""
        decoder = JSONDecoder()
        idx = 0
        n = len(block)
        while idx < n:
            while idx < n and block[idx].isspace():
                idx += 1
            if idx >= n:
                break
            try:
                obj, end = decoder.raw_decode(block, idx)
                idx = end
                if isinstance(obj, dict):
                    append_if_tool(obj)
            except json.JSONDecodeError:
                fallback = try_parse_json(block[idx:].strip())
                if fallback:
                    append_if_tool(fallback)
                break

    # 1. ```tool_call ... ```（不要求围栏结束前额外换行）
    for m in re.finditer(r'```tool_call\s*\n?([\s\S]*?)```', text, re.IGNORECASE):
        parse_multi_json(m.group(1))

    if calls:
        return calls

    # 2. ```json ... ```（仅当内含已知工具名，避免把普通 JSON 当工具）
    for m in re.finditer(r'```json\s*\n?([\s\S]*?)```', text):
        parse_multi_json(m.group(1))

    if calls:
        return calls

    # 3. 全文扫描：模型常直接输出 {"name":"write_file","parameters":{...}}，旧版正则无法匹配嵌套括号
    decoder = JSONDecoder()
    i = 0
    n = len(text)
    while i < n:
        j = text.find('{', i)
        if j == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, j)
            i = end
            if isinstance(obj, dict):
                append_if_tool(obj)
        except json.JSONDecodeError:
            i = j + 1

    return calls
