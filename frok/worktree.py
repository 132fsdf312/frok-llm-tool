"""
Frok Worktree管理模块
Git Worktree隔离工作空间
灵感来自Claude Code的Worktree功能
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 数据结构 ====================

@dataclass
class WorktreeInfo:
    """Worktree信息"""
    path: str = ""
    branch: str = ""
    head: str = ""
    is_bare: bool = False
    is_detached: bool = False
    is_locked: bool = False
    is_main: bool = False  # 是否是主工作树

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "branch": self.branch,
            "head": self.head,
            "is_bare": self.is_bare,
            "is_detached": self.is_detached,
            "is_locked": self.is_locked,
            "is_main": self.is_main,
        }


@dataclass
class WorktreeConfig:
    """Worktree配置"""
    base_dir: str = ".worktrees"  # 工作树存放目录
    auto_branch: bool = True  # 自动创建分支
    prefix: str = "frok-"  # 工作树名称前缀


# ==================== Worktree管理器 ====================

class WorktreeManager:
    """
    Git Worktree管理器

    功能:
    - 创建隔离工作空间
    - 管理多个工作树
    - 在工作树间切换
    - 合并工作树变更
    """

    def __init__(self, working_dir: str = None, config: WorktreeConfig = None):
        self.working_dir = working_dir or os.getcwd()
        self.config = config or WorktreeConfig()

        # 确保工作树目录存在
        self.worktrees_dir = Path(self.working_dir) / self.config.base_dir
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def _run_git(self, args: List[str], cwd: str = None) -> Tuple[int, str, str]:
        """执行Git命令"""
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.working_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "命令超时"
        except Exception as e:
            return -1, "", str(e)

    def _is_git_repo(self) -> bool:
        """检查是否是Git仓库"""
        code, _, _ = self._run_git(["rev-parse", "--git-dir"])
        return code == 0

    def _get_main_worktree_path(self) -> str:
        """获取主工作树路径"""
        code, stdout, _ = self._run_git(["rev-parse", "--show-toplevel"])
        return stdout.strip() if code == 0 else ""

    # ==================== 工作树管理 ====================

    def list(self) -> List[WorktreeInfo]:
        """列出所有工作树"""
        if not self._is_git_repo():
            return []

        code, stdout, _ = self._run_git(["worktree", "list", "--porcelain"])
        if code != 0:
            return []

        worktrees = []
        current = WorktreeInfo()

        for line in stdout.strip().split('\n'):
            if not line:
                if current.path:
                    worktrees.append(current)
                    current = WorktreeInfo()
                continue

            if line.startswith("worktree "):
                current.path = line[9:].strip()
                # 检查是否是主工作树
                main_path = self._get_main_worktree_path()
                if current.path == main_path:
                    current.is_main = True
            elif line.startswith("HEAD "):
                current.head = line[5:].strip()
            elif line.startswith("branch "):
                current.branch = line[7:].strip()
            elif line == "bare":
                current.is_bare = True
            elif line == "detached":
                current.is_detached = True
            elif line == "locked":
                current.is_locked = True

        if current.path:
            worktrees.append(current)

        return worktrees

    def format_list(self) -> str:
        """格式化显示工作树列表"""
        worktrees = self.list()
        if not worktrees:
            return "无工作树"

        lines = ["工作树列表:"]
        for wt in worktrees:
            marker = " *" if wt.is_main else ""
            status = []
            if wt.is_detached:
                status.append("detached")
            if wt.is_locked:
                status.append("locked")
            status_str = f" [{', '.join(status)}]" if status else ""

            lines.append(f"  {wt.path}{marker}{status_str}")
            if wt.branch:
                lines.append(f"    分支: {wt.branch}")
            if wt.head:
                lines.append(f"    HEAD: {wt.head[:8]}")

        return "\n".join(lines)

    # ==================== 工作树操作 ====================

    def create(self, name: str, branch: str = None,
               new_branch: bool = True) -> Tuple[bool, str]:
        """
        创建新的工作树

        Args:
            name: 工作树名称
            branch: 分支名 (可选)
            new_branch: 是否创建新分支

        Returns:
            (成功, 结果信息)
        """
        if not self._is_git_repo():
            return False, "不是Git仓库"

        # 生成路径
        if not branch:
            branch = f"{self.config.prefix}{name}"

        worktree_path = self.worktrees_dir / name

        # 检查是否已存在
        if worktree_path.exists():
            return False, f"工作树已存在: {worktree_path}"

        # 创建工作树
        args = ["worktree", "add"]
        if new_branch:
            args.extend(["-b", branch])
        args.extend([str(worktree_path), branch])

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, f"创建失败: {stderr}"

        return True, f"已创建工作树: {worktree_path} (分支: {branch})"

    def create_from_commit(self, name: str, commit: str,
                           branch: str = None) -> Tuple[bool, str]:
        """从指定提交创建工作树"""
        if not self._is_git_repo():
            return False, "不是Git仓库"

        worktree_path = self.worktrees_dir / name

        if worktree_path.exists():
            return False, f"工作树已存在: {worktree_path}"

        args = ["worktree", "add"]
        if branch:
            args.extend(["-b", branch])
        args.extend([str(worktree_path), commit])

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, f"创建失败: {stderr}"

        return True, f"已创建工作树: {worktree_path}"

    def remove(self, name: str, force: bool = False) -> Tuple[bool, str]:
        """
        删除工作树

        Args:
            name: 工作树名称
            force: 是否强制删除

        Returns:
            (成功, 结果信息)
        """
        worktree_path = self.worktrees_dir / name

        if not worktree_path.exists():
            return False, f"工作树不存在: {name}"

        # 使用git worktree remove
        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            # 尝试手动删除
            if force:
                try:
                    shutil.rmtree(worktree_path)
                    # 清理git配置
                    self._run_git(["worktree", "prune"])
                    return True, f"已强制删除工作树: {name}"
                except Exception as e:
                    return False, f"删除失败: {e}"
            return False, f"删除失败: {stderr}"

        return True, f"已删除工作树: {name}"

    def lock(self, name: str) -> Tuple[bool, str]:
        """锁定工作树"""
        worktree_path = self.worktrees_dir / name

        code, stdout, stderr = self._run_git(["worktree", "lock", str(worktree_path)])
        if code != 0:
            return False, stderr
        return True, f"已锁定工作树: {name}"

    def unlock(self, name: str) -> Tuple[bool, str]:
        """解锁工作树"""
        worktree_path = self.worktrees_dir / name

        code, stdout, stderr = self._run_git(["worktree", "unlock", str(worktree_path)])
        if code != 0:
            return False, stderr
        return True, f"已解锁工作树: {name}"

    def prune(self) -> Tuple[bool, str]:
        """清理无效工作树引用"""
        code, stdout, stderr = self._run_git(["worktree", "prune"])
        if code != 0:
            return False, stderr
        return True, "已清理无效工作树引用"

    # ==================== 工作树切换 ====================

    def get_path(self, name: str) -> Optional[str]:
        """获取工作树路径"""
        worktree_path = self.worktrees_dir / name
        return str(worktree_path) if worktree_path.exists() else None

    def get_current(self) -> Optional[str]:
        """获取当前工作树名称"""
        current_path = Path(self.working_dir).resolve()

        # 检查是否在主工作树
        main_path = Path(self._get_main_worktree_path()).resolve()
        if current_path == main_path:
            return "main"

        # 检查是否在某个子工作树
        for wt in self.list():
            wt_path = Path(wt.path).resolve()
            if current_path == wt_path or current_path.is_relative_to(wt_path):
                return Path(wt.path).name

        return None

    def switch(self, name: str) -> Tuple[bool, str]:
        """
        切换到指定工作树

        注意: 这只是返回路径，实际切换需要用户cd到该目录
        """
        worktree_path = self.worktrees_dir / name

        if not worktree_path.exists():
            return False, f"工作树不存在: {name}"

        return True, str(worktree_path)

    # ==================== 工作树合并 ====================

    def merge(self, source: str, target: str = None,
              message: str = None) -> Tuple[bool, str]:
        """
        合并工作树的变更

        Args:
            source: 源工作树名称
            target: 目标分支 (默认当前分支)
            message: 合并信息

        Returns:
            (成功, 结果信息)
        """
        source_path = self.worktrees_dir / source

        if not source_path.exists():
            return False, f"源工作树不存在: {source}"

        # 获取源工作树的分支
        source_branch = None
        for wt in self.list():
            if wt.path == str(source_path):
                source_branch = wt.branch.replace("refs/heads/", "")
                break

        if not source_branch:
            return False, f"无法获取源工作树的分支"

        # 在主工作树执行合并
        main_path = self._get_main_worktree_path()

        args = ["merge", source_branch]
        if message:
            args.extend(["-m", message])

        code, stdout, stderr = self._run_git(args, cwd=main_path)
        if code != 0:
            return False, f"合并失败: {stderr}"

        return True, f"已合并 {source_branch} 到当前分支"

    def cherry_pick(self, commit: str) -> Tuple[bool, str]:
        """Cherry-pick提交"""
        code, stdout, stderr = self._run_git(["cherry-pick", commit])
        if code != 0:
            return False, stderr
        return True, f"已cherry-pick: {commit[:8]}"

    # ==================== 工作树信息 ====================

    def get_info(self, name: str) -> Optional[WorktreeInfo]:
        """获取工作树详细信息"""
        worktree_path = self.worktrees_dir / name

        for wt in self.list():
            if wt.path == str(worktree_path):
                return wt
        return None

    def get_status(self, name: str) -> str:
        """获取工作树的Git状态"""
        worktree_path = self.worktrees_dir / name

        if not worktree_path.exists():
            return f"工作树不存在: {name}"

        code, stdout, stderr = self._run_git(["status"], cwd=str(worktree_path))
        if code != 0:
            return f"[错误] {stderr}"

        return stdout

    def get_diff(self, name: str, staged: bool = False) -> str:
        """获取工作树的差异"""
        worktree_path = self.worktrees_dir / name

        if not worktree_path.exists():
            return f"工作树不存在: {name}"

        args = ["diff"]
        if staged:
            args.append("--staged")

        code, stdout, stderr = self._run_git(args, cwd=str(worktree_path))
        if code != 0:
            return f"[错误] {stderr}"

        return stdout if stdout else "无差异"

    # ==================== 快照与恢复 ====================

    def snapshot(self, name: str, message: str = None) -> Tuple[bool, str]:
        """
        创建工作树快照 (提交所有变更)

        Args:
            name: 工作树名称
            message: 提交信息

        Returns:
            (成功, 结果信息)
        """
        worktree_path = self.worktrees_dir / name

        if not worktree_path.exists():
            return False, f"工作树不存在: {name}"

        # 添加所有变更
        self._run_git(["add", "-A"], cwd=str(worktree_path))

        # 检查是否有变更
        code, stdout, _ = self._run_git(["status", "--porcelain"], cwd=str(worktree_path))
        if not stdout.strip():
            return True, "无变更需要快照"

        # 提交
        if not message:
            message = f"快照: {name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        code, stdout, stderr = self._run_git(["commit", "-m", message], cwd=str(worktree_path))
        if code != 0:
            return False, f"快照失败: {stderr}"

        return True, f"已创建快照: {message}"


# ==================== 工具定义 ====================

WORKTREE_TOOLS = [
    {
        "name": "worktree_list",
        "description": "列出所有工作树",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "worktree_create",
        "description": "创建新的工作树",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工作树名称"},
                "branch": {"type": "string", "description": "分支名 (可选)"},
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
        "name": "worktree_switch",
        "description": "切换工作树",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工作树名称"}
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
    {
        "name": "worktree_snapshot",
        "description": "创建工作树快照",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工作树名称"},
                "message": {"type": "string", "description": "快照信息"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "worktree_status",
        "description": "获取工作树状态",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工作树名称"}
            },
            "required": ["name"]
        }
    }
]
