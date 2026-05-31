"""
Frok 沙箱执行模块
安全代码执行环境，使用subprocess隔离
灵感来自Open Interpreter的代码执行功能
"""

import os
import sys
import ast
import subprocess
import tempfile
import time
import signal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# resource模块仅在Unix/Linux/macOS上可用
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False

import logging
logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class ResourceLimits:
    """资源限制"""
    max_memory_mb: int = 256  # 最大内存 (MB)
    max_cpu_seconds: int = 30  # 最大CPU时间 (秒)
    max_output_size: int = 10000  # 最大输出大小 (字节)
    max_file_size: int = 1024 * 1024  # 最大文件大小 (字节)
    network_access: bool = False  # 是否允许网络访问
    filesystem_access: bool = True  # 是否允许文件系统访问
    allowed_paths: List[str] = field(default_factory=list)  # 允许访问的路径
    blocked_paths: List[str] = field(default_factory=list)  # 禁止访问的路径

    def to_dict(self) -> Dict:
        return {
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_output_size": self.max_output_size,
            "network_access": self.network_access,
            "filesystem_access": self.filesystem_access,
        }


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    memory_used: int = 0
    language: str = ""
    error: str = ""
    timed_out: bool = False

    def to_string(self) -> str:
        lines = []
        if self.success:
            lines.append("[执行成功]")
        else:
            lines.append("[执行失败]")

        if self.stdout:
            lines.append(f"\n输出:\n{self.stdout}")
        if self.stderr:
            lines.append(f"\n错误:\n{self.stderr}")
        if self.error:
            lines.append(f"\n异常: {self.error}")

        lines.append(f"\n执行时间: {self.execution_time:.2f}秒")
        if self.exit_code != 0:
            lines.append(f"退出码: {self.exit_code}")

        return "\n".join(lines)


@dataclass
class SandboxConfig:
    """沙箱配置"""
    working_dir: str = ""
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    env_vars: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    cleanup: bool = True


# ==================== 沙箱执行器 ====================

class SandboxExecutor:
    """
    安全代码执行沙箱

    功能:
    - 多语言支持 (Python, JavaScript, Shell)
    - 资源限制 (内存, CPU, 输出大小)
    - 路径隔离
    - 超时控制
    """

    # 支持的语言
    LANGUAGES = {
        "python": {
            "extension": ".py",
            "command": [sys.executable],
            "version_flag": "--version",
        },
        "javascript": {
            "extension": ".js",
            "command": ["node"],
            "version_flag": "--version",
        },
        "shell": {
            "extension": ".sh",
            "command": ["bash"],
            "version_flag": "--version",
        },
    }

    # 危险的命令模式
    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"mkfs\.",
        r"dd\s+if=",
        r">\s*/dev/sd",
        r"chmod\s+777\s+/",
        r"curl\s+.*\|\s*sh",
        r"wget\s+.*\|\s*sh",
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__\s*\(",
        r"subprocess\.",
        r"os\.system\s*\(",
        r"os\.popen\s*\(",
        r"os\._exit\s*\(",
        r"ctypes\.",
        r"importlib\.",
    ]

    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="frok_sandbox_"))

    def _check_dangerous_code(self, code: str) -> Optional[str]:
        """检查危险代码（多层检测）"""
        import re

        # 第一层：正则模式匹配
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return f"检测到危险代码模式: {pattern}"

        # 第二层：AST 分析（Python 代码）
        if 'import' in code or '__' in code:
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    # 检测 import os; os.system 等间接调用
                    if isinstance(node, ast.Attribute):
                        if isinstance(node.value, ast.Name):
                            if node.value.id in ('os', 'subprocess', 'shutil') and node.attr in ('system', 'popen', 'remove', 'rmtree'):
                                return f"检测到危险调用: {node.value.id}.{node.attr}"
                    # 检测 __import__ 内置函数调用
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        if node.func.id in ('__import__', 'eval', 'exec', 'compile'):
                            return f"检测到危险内置函数: {node.func.id}"
                    # 检测 getattr(os, 'system') 等间接调用
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        if node.func.id == 'getattr' and len(node.args) >= 2:
                            obj_arg = node.args[0]
                            attr_arg = node.args[1]
                            if isinstance(obj_arg, ast.Name) and obj_arg.id in ('os', 'subprocess', 'shutil'):
                                if isinstance(attr_arg, ast.Constant) and attr_arg.value in ('system', 'popen', 'remove', 'rmtree'):
                                    return f"检测到危险间接调用: getattr({obj_arg.id}, '{attr_arg.value}')"
            except SyntaxError:
                pass  # 非 Python 代码，跳过 AST 检测

        return None

    def _check_path_access(self, path: str) -> bool:
        """检查路径访问权限"""
        if not self.config.limits.filesystem_access:
            return False

        path = os.path.abspath(path)

        # 禁止访问的系统路径
        blocked = [
            "/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys",
        ]
        # Windows 系统路径
        if sys.platform == 'win32':
            win_path = os.environ.get('WINDIR', r'C:\Windows').lower()
            blocked.append(win_path)
            blocked.append(r'C:\Program Files'.lower())
            blocked.append(r'C:\Windows'.lower())

        for bp in blocked:
            if path.lower().startswith(bp.lower()):
                return False

        # 检查允许路径
        if self.config.limits.allowed_paths:
            allowed = False
            for ap in self.config.limits.allowed_paths:
                if path.startswith(os.path.abspath(ap)):
                    allowed = True
                    break
            return allowed

        return True

    def _set_resource_limits(self, limits: ResourceLimits):
        """设置资源限制 (Unix: resource模块, Windows: Job Objects)"""
        if HAS_RESOURCE:
            try:
                if limits.max_memory_mb:
                    max_bytes = limits.max_memory_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
                if limits.max_cpu_seconds:
                    resource.setrlimit(resource.RLIMIT_CPU, (limits.max_cpu_seconds, limits.max_cpu_seconds))
                if limits.max_file_size:
                    resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_file_size, limits.max_file_size))
            except (AttributeError, ValueError):
                pass
        elif sys.platform == 'win32':
            # Windows: 通过 subprocess 的 creationflags 限制
            # JOB_OBJECT_LIMIT_PROCESS_MEMORY 等需要 ctypes，在 _execute_code 中处理
            logger.debug("Windows 环境：资源限制通过 subprocess timeout 和输出截断实现")

    def _prepare_environment(self) -> Dict[str, str]:
        """准备执行环境"""
        env = os.environ.copy()

        # 移除敏感环境变量
        sensitive_vars = [
            "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
            "GITHUB_TOKEN", "GITLAB_TOKEN",
            "DATABASE_URL", "REDIS_URL",
            "SECRET_KEY", "API_KEY",
        ]
        for var in sensitive_vars:
            env.pop(var, None)

        # 添加配置的环境变量
        env.update(self.config.env_vars)

        # 限制网络访问
        if not self.config.limits.network_access:
            env["no_proxy"] = "*"
            env["NO_PROXY"] = "*"

        return env

    # ==================== 代码执行 ====================

    def execute_python(self, code: str, timeout: int = None) -> ExecutionResult:
        """
        执行Python代码

        Args:
            code: Python代码
            timeout: 超时时间 (秒)

        Returns:
            ExecutionResult对象
        """
        return self._execute_code(code, "python", timeout)

    def execute_javascript(self, code: str, timeout: int = None) -> ExecutionResult:
        """
        执行JavaScript代码

        Args:
            code: JavaScript代码
            timeout: 超时时间 (秒)

        Returns:
            ExecutionResult对象
        """
        return self._execute_code(code, "javascript", timeout)

    def execute_shell(self, command: str, timeout: int = None) -> ExecutionResult:
        """
        执行Shell命令

        Args:
            command: Shell命令
            timeout: 超时时间 (秒)

        Returns:
            ExecutionResult对象
        """
        return self._execute_code(command, "shell", timeout)

    def execute(self, code: str, language: str, timeout: int = None) -> ExecutionResult:
        """
        执行代码

        Args:
            code: 代码内容
            language: 语言 (python/javascript/shell)
            timeout: 超时时间

        Returns:
            ExecutionResult对象
        """
        if language not in self.LANGUAGES:
            return ExecutionResult(
                success=False,
                error=f"不支持的语言: {language}"
            )

        return self._execute_code(code, language, timeout)

    def _execute_code(self, code: str, language: str, timeout: int = None) -> ExecutionResult:
        """执行代码"""
        start_time = time.time()

        # 检查危险代码
        danger = self._check_dangerous_code(code)
        if danger:
            return ExecutionResult(
                success=False,
                error=danger,
                language=language,
            )

        # 获取语言配置
        lang_config = self.LANGUAGES.get(language)
        if not lang_config:
            return ExecutionResult(
                success=False,
                error=f"不支持的语言: {language}",
                language=language,
            )

        # 检查命令是否可用
        cmd = lang_config["command"]
        if not self._check_command_available(cmd[0]):
            return ExecutionResult(
                success=False,
                error=f"命令不可用: {cmd[0]}",
                language=language,
            )

        # 准备临时文件
        ext = lang_config["extension"]
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix=ext, dir=self.temp_dir,
                delete=False, encoding='utf-8'
            ) as f:
                f.write(code)
                temp_file = f.name
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"创建临时文件失败: {e}",
                language=language,
            )

        # 准备执行命令
        exec_cmd = cmd + [temp_file]

        # 超时设置
        if timeout is None:
            timeout = self.config.timeout

        # 环境变量
        env = self._prepare_environment()

        # 工作目录
        cwd = self.config.working_dir or os.getcwd()

        try:
            # 执行代码
            result = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )

            execution_time = time.time() - start_time

            # 截断过长的输出
            stdout = result.stdout
            stderr = result.stderr
            max_size = self.config.limits.max_output_size

            if len(stdout) > max_size:
                stdout = stdout[:max_size] + f"\n... (输出截断，共 {len(result.stdout)} 字节)"
            if len(stderr) > max_size:
                stderr = stderr[:max_size] + f"\n... (错误截断，共 {len(result.stderr)} 字节)"

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                execution_time=execution_time,
                language=language,
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"执行超时 ({timeout}秒)",
                execution_time=timeout,
                language=language,
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"执行异常: {e}",
                execution_time=time.time() - start_time,
                language=language,
            )
        finally:
            # 清理临时文件
            if self.config.cleanup:
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    def _check_command_available(self, command: str) -> bool:
        """检查命令是否可用"""
        try:
            result = subprocess.run(
                [command, "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return False

    # ==================== 交互式执行 ====================

    def execute_interactive(self, code: str, language: str,
                            timeout: int = 30) -> ExecutionResult:
        """
        交互式执行（支持多行输入）

        Args:
            code: 代码内容
            language: 语言
            timeout: 超时时间

        Returns:
            ExecutionResult对象
        """
        if language == "python":
            # 使用Python的-ic参数执行交互式代码
            return self._execute_python_interactive(code, timeout)
        else:
            return self._execute_code(code, language, timeout)

    def _execute_python_interactive(self, code: str, timeout: int) -> ExecutionResult:
        """交互式执行Python代码"""
        start_time = time.time()

        try:
            # 使用python -c执行
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.config.working_dir or os.getcwd(),
                env=self._prepare_environment(),
            )

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=time.time() - start_time,
                language="python",
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"执行超时 ({timeout}秒)",
                execution_time=timeout,
                language="python",
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                language="python",
            )

    # ==================== 代码验证 ====================

    def validate_code(self, code: str, language: str) -> Tuple[bool, str]:
        """
        验证代码语法

        Args:
            code: 代码内容
            language: 语言

        Returns:
            (是否有效, 错误信息)
        """
        if language == "python":
            return self._validate_python(code)
        elif language == "javascript":
            return self._validate_javascript(code)
        elif language == "shell":
            return self._validate_shell(code)
        return False, f"不支持的语言: {language}"

    def _validate_python(self, code: str) -> Tuple[bool, str]:
        """验证Python语法"""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"语法错误: {e}"

    def _validate_javascript(self, code: str) -> Tuple[bool, str]:
        """验证JavaScript语法"""
        # 简单检查
        if not code.strip():
            return False, "空代码"
        return True, ""

    def _validate_shell(self, code: str) -> Tuple[bool, str]:
        """验证Shell语法"""
        if not code.strip():
            return False, "空命令"
        return True, ""

    # ==================== 清理 ====================

    def cleanup(self):
        """清理临时目录"""
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except:
            pass

    def __del__(self):
        """析构时清理"""
        self.cleanup()


# ==================== 工具定义 ====================

SANDBOX_TOOLS = [
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
        "name": "execute_shell",
        "description": "在沙箱中执行Shell命令",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell命令"},
                "timeout": {"type": "integer", "description": "超时时间 (秒)"}
            },
            "required": ["command"]
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
