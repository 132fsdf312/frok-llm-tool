"""
Frok 工具系统
基础工具执行器（文件操作、搜索、命令执行）+ 工具调用解析
"""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from json import JSONDecoder
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ==================== 基础工具 Schema ====================

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
]

# ==================== 危险命令检测 ====================

DANGEROUS_COMMANDS = [
    r"rm\s+-rf\s+/",
    r"mkfs\.",
    r"dd\s+if=",
    r">\s*/dev/sd",
    r"chmod\s+777\s+/",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r":(){ :\|:& };:",  # fork bomb
    r"mv\s+/\s",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r"format\s+[a-zA-Z]:",
    r"del\s+/[sS]\s+/[qQ]\s+[a-zA-Z]:\\",
]


def _check_command_safety(command: str) -> Optional[str]:
    """检查命令是否危险，返回警告信息或 None"""
    for pattern in DANGEROUS_COMMANDS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"检测到危险命令模式: {pattern}"
    return None


# ==================== 工具执行器 ====================

class ToolExecutor:
    def __init__(self, working_dir: str = None):
        self.working_dir = working_dir or os.getcwd()

    @staticmethod
    def _is_wsl() -> bool:
        """检测是否在 WSL 环境中"""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False

    def _normalize_path(self, path: str) -> str:
        """标准化路径：仅在 WSL 中将 Windows 路径转为 /mnt/ 格式"""
        if '\\' in path and ':' in path and self._is_wsl():
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

    # ===== 文件操作 =====

    def read_file(self, path: str, start_line: int = None, end_line: int = None) -> str:
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
        try:
            path = self._normalize_path(path)
            dir_path = Path(path).expanduser().resolve()
            dir_path.mkdir(parents=True, exist_ok=True)
            return f"[已创建目录] {dir_path}"
        except Exception as e:
            return f"[错误] {e}"

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
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
        try:
            file_path = Path(path).expanduser().resolve()
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"[已追加] {file_path}"
        except Exception as e:
            return f"[错误] {e}"

    def delete_file(self, path: str) -> str:
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return f"[错误] 文件不存在: {path}"
            file_path.unlink()
            return f"[已删除] {file_path}"
        except Exception as e:
            return f"[错误] {e}"

    def copy_file(self, source: str, destination: str) -> str:
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
        try:
            src = Path(source).expanduser().resolve()
            dst = Path(destination).expanduser().resolve()
            if not src.exists():
                return f"[错误] 源文件不存在: {source}"
            shutil.move(str(src), str(dst))
            return f"[已移动] {src} -> {dst}"
        except Exception as e:
            return f"[错误] {e}"

    # ===== 目录操作 =====

    def list_directory(self, path: str = ".", show_hidden: bool = False) -> str:
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
                    output.append(f"  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024*1024:
                        size_str = f"{size//1024}KB"
                    else:
                        size_str = f"{size//(1024*1024)}MB"
                    output.append(f"  {entry.name} ({size_str})")

            return "\n".join(output) if output else "空目录"
        except Exception as e:
            return f"[错误] {e}"

    def get_tree(self, path: str = ".", max_depth: int = 3) -> str:
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

    # ===== 搜索 =====

    def search_files(self, directory: str, pattern: str, glob: str = "*") -> str:
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
                    except Exception:
                        continue
                if len(results) >= 50:
                    break

            return "\n".join(results) if results else "未找到匹配内容"
        except Exception as e:
            return f"[错误] {e}"

    def find_files(self, directory: str, pattern: str) -> str:
        try:
            dir_path = Path(directory).expanduser().resolve()
            if not dir_path.exists():
                return f"[错误] 目录不存在: {directory}"

            files = list(dir_path.rglob(pattern))
            return "\n".join(str(f) for f in files[:50]) if files else "未找到匹配文件"
        except Exception as e:
            return f"[错误] {e}"

    # ===== 命令执行（安全加固） =====

    def execute_command(self, command: str, working_directory: str = None) -> str:
        # 安全检查
        danger = _check_command_safety(command)
        if danger:
            logger.warning(f"危险命令被拦截: {command} ({danger})")
            return f"[安全拦截] {danger}\n命令: {command}\n如需执行此命令，请用户手动操作。"

        logger.info(f"执行命令: {command}")
        try:
            cwd = working_directory or self.working_dir
            # Windows 上 cmd.exe 内置命令（如 dir、type）需要 shell=True
            # 其他情况使用 shlex.split 避免命令注入
            if sys.platform == 'win32':
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=cwd
                )
            else:
                args = shlex.split(command)
                result = subprocess.run(
                    args,
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
        cmd = f"git {subcommand}"
        if args:
            cmd += f" {args}"
        return self.execute_command(cmd)

    def ask_user(self, question: str) -> str:
        return f"[需要用户回答] {question}"

    def finish(self, result: str) -> str:
        return f"[任务完成] {result}"


# ==================== 工具调用解析 ====================

def parse_tool_calls(text: str, known_tool_names: set = None) -> List[Dict]:
    """
    从AI响应中解析工具调用

    支持:
    1. ```tool_call ... ``` 围栏格式
    2. ```json ... ``` 围栏格式（含已知工具名时）
    3. 全文裸 JSON 扫描

    Args:
        text: AI 响应文本
        known_tool_names: 已知工具名集合，用于过滤非工具 JSON

    Returns:
        解析到的工具调用列表
    """
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
        if known_tool_names and call["name"] not in known_tool_names:
            return
        normalize_call(call)
        calls.append(call)

    def parse_multi_json(block: str) -> None:
        """从一段文本中顺序解析多个 JSON 对象"""
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

    # 1. ```tool_call ... ```
    for m in re.finditer(r'```tool_call\s*\n?([\s\S]*?)```', text, re.IGNORECASE):
        parse_multi_json(m.group(1))

    if calls:
        return calls

    # 2. ```json ... ```
    for m in re.finditer(r'```json\s*\n?([\s\S]*?)```', text):
        parse_multi_json(m.group(1))

    if calls:
        return calls

    # 3. XML-style tool_call (some models use this format)
    def parse_xml_calls(text):
        results = []
        tag = chr(60) + "tool_call" + chr(62)  # build tag without literal
        close_tag = chr(60) + "/tool_call" + chr(62)
        func_open = chr(60) + "function" + chr(62)
        func_close = chr(60) + "/function" + chr(62)
        pattern = re.escape(tag) + r"([\s\S]*?)" + re.escape(close_tag)
        for m in re.finditer(pattern, text):
            block = m.group(0)
            fn_pattern = re.escape(func_open) + r"(\w+)" + re.escape(func_close)
            fn_match = re.search(fn_pattern, block)
            if fn_match:
                call = {"name": fn_match.group(1), "parameters": {}}
                # Only match parameter tags (skip tool_call and function)
                for pm in re.finditer(r"<(?!tool_call|function|/)(\w+)>([\s\S]*?)</\1>", block):
                    pname = pm.group(1)
                    pval = pm.group(2).strip()
                    try:
                        call["parameters"][pname] = json.loads(pval)
                    except json.JSONDecodeError:
                        call["parameters"][pname] = pval
                results.append(call)
        return results

    for call in parse_xml_calls(text):
        append_if_tool(call)

    if calls:
        return calls

    # 4. Full text scan (bare JSON)
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
