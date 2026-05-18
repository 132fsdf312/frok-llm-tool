"""
Frok Git增强模块
深度Git集成，灵感来自Aider的Git工作流
"""

import os
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 数据结构 ====================

@dataclass
class GitStatus:
    """Git状态"""
    branch: str = ""
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    staged: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    untracked: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    conflicted: List[str] = field(default_factory=list)
    is_clean: bool = True


@dataclass
class GitCommit:
    """Git提交"""
    hash: str = ""
    short_hash: str = ""
    author: str = ""
    date: str = ""
    message: str = ""
    files_changed: int = 0


@dataclass
class GitDiff:
    """Git差异"""
    file: str = ""
    status: str = ""  # added/modified/deleted/renamed
    additions: int = 0
    deletions: int = 0
    diff_text: str = ""


@dataclass
class GitBlame:
    """Git blame信息"""
    file: str = ""
    lines: List[Dict] = field(default_factory=list)  # [{line, hash, author, date, content}]


@dataclass
class GitStash:
    """Git stash"""
    index: int = 0
    name: str = ""
    message: str = ""
    branch: str = ""


# ==================== Git增强类 ====================

class GitEnhanced:
    """
    深度Git集成

    功能:
    - 自动提交 (auto_commit)
    - 差异展示 (show_diff)
    - 代码追溯 (blame)
    - 提交图 (log_graph)
    - 暂存管理 (stash)
    - 分支管理 (branch)
    """

    def __init__(self, working_dir: str = None):
        self.working_dir = working_dir or os.getcwd()

    def _run_git(self, args: List[str], check: bool = False) -> Tuple[int, str, str]:
        """执行Git命令"""
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=check
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

    # ==================== 状态查询 ====================

    def get_status(self) -> GitStatus:
        """获取Git状态"""
        if not self._is_git_repo():
            return GitStatus()

        status = GitStatus()

        # 获取分支信息
        code, stdout, _ = self._run_git(["branch", "-vv", "--current"])
        if code == 0 and stdout:
            match = re.search(r'\*\s+(\S+)\s+(\S+)\s+\[(\S+?)(?:\s+ahead\s+(\d+))?(?:\s+behind\s+(\d+))?\]', stdout)
            if match:
                status.branch = match.group(1)
                status.upstream = match.group(3) if match.group(3) else ""
                status.ahead = int(match.group(4)) if match.group(4) else 0
                status.behind = int(match.group(5)) if match.group(5) else 0
            else:
                match = re.search(r'\*\s+(\S+)', stdout)
                if match:
                    status.branch = match.group(1)

        # 获取文件状态
        code, stdout, _ = self._run_git(["status", "--porcelain"])
        if code == 0:
            for line in stdout.strip().split('\n'):
                if not line:
                    continue
                status_code = line[:2]
                file_path = line[3:].strip()

                if status_code == '??':
                    status.untracked.append(file_path)
                elif status_code[0] in 'MADRC':
                    status.staged.append(file_path)
                elif status_code[1] == 'M':
                    status.modified.append(file_path)
                elif status_code[1] == 'D':
                    status.deleted.append(file_path)
                elif status_code[0] == 'U' or status_code[1] == 'U':
                    status.conflicted.append(file_path)

        status.is_clean = not (status.staged or status.modified or status.untracked or status.deleted)

        return status

    def format_status(self) -> str:
        """格式化显示Git状态"""
        status = self.get_status()

        if not status.branch:
            return "不是Git仓库"

        lines = []
        lines.append(f"分支: {status.branch}")

        if status.upstream:
            sync_info = ""
            if status.ahead > 0:
                sync_info += f" ↑{status.ahead}"
            if status.behind > 0:
                sync_info += f" ↓{status.behind}"
            lines.append(f"上游: {status.upstream}{sync_info}")

        if status.is_clean:
            lines.append("状态: 工作区干净")
        else:
            if status.staged:
                lines.append(f"\n已暂存 ({len(status.staged)}):")
                for f in status.staged:
                    lines.append(f"  + {f}")

            if status.modified:
                lines.append(f"\n已修改 ({len(status.modified)}):")
                for f in status.modified:
                    lines.append(f"  M {f}")

            if status.deleted:
                lines.append(f"\n已删除 ({len(status.deleted)}):")
                for f in status.deleted:
                    lines.append(f"  D {f}")

            if status.untracked:
                lines.append(f"\n未跟踪 ({len(status.untracked)}):")
                for f in status.untracked:
                    lines.append(f"  ? {f}")

            if status.conflicted:
                lines.append(f"\n冲突 ({len(status.conflicted)}):")
                for f in status.conflicted:
                    lines.append(f"  ! {f}")

        return "\n".join(lines)

    # ==================== 差异展示 ====================

    def show_diff(self, file: str = None, staged: bool = False,
                  context_lines: int = 3) -> str:
        """显示差异"""
        args = ["diff"]

        if staged:
            args.append("--staged")

        args.extend([f"-U{context_lines}"])

        if file:
            args.append(file)

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        if not stdout:
            return "无差异"

        return stdout

    def diff_stat(self, staged: bool = False) -> str:
        """显示差异统计"""
        args = ["diff", "--stat"]
        if staged:
            args.append("--staged")

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        return stdout if stdout else "无差异"

    def get_diff_summary(self, staged: bool = False) -> List[GitDiff]:
        """获取差异摘要"""
        args = ["diff", "--numstat"]
        if staged:
            args.append("--staged")

        code, stdout, _ = self._run_git(args)
        if code != 0:
            return []

        diffs = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                additions = int(parts[0]) if parts[0] != '-' else 0
                deletions = int(parts[1]) if parts[1] != '-' else 0
                file_path = parts[2]

                status = "modified"
                if additions > 0 and deletions == 0:
                    status = "added"
                elif additions == 0 and deletions > 0:
                    status = "deleted"

                diffs.append(GitDiff(
                    file=file_path,
                    status=status,
                    additions=additions,
                    deletions=deletions
                ))

        return diffs

    # ==================== 自动提交 ====================

    def auto_commit(self, message: str, files: List[str] = None,
                    add_all: bool = False) -> Tuple[bool, str]:
        """
        自动提交

        Args:
            message: 提交信息
            files: 要提交的文件列表
            add_all: 是否添加所有变更

        Returns:
            (成功, 结果信息)
        """
        if not self._is_git_repo():
            return False, "不是Git仓库"

        # 添加文件
        if add_all:
            code, _, stderr = self._run_git(["add", "-A"])
            if code != 0:
                return False, f"git add 失败: {stderr}"
        elif files:
            for f in files:
                code, _, stderr = self._run_git(["add", f])
                if code != 0:
                    return False, f"git add {f} 失败: {stderr}"

        # 检查是否有变更
        status = self.get_status()
        if not status.staged:
            return False, "没有变更可提交"

        # 提交
        code, stdout, stderr = self._run_git(["commit", "-m", message])
        if code != 0:
            return False, f"git commit 失败: {stderr}"

        return True, f"已提交: {message}"

    def generate_commit_message(self, staged: bool = False) -> str:
        """自动生成提交信息"""
        diffs = self.get_diff_summary(staged)

        if not diffs:
            return "无变更"

        # 统计变更类型
        added = [d for d in diffs if d.status == "added"]
        modified = [d for d in diffs if d.status == "modified"]
        deleted = [d for d in diffs if d.status == "deleted"]

        parts = []

        if added:
            if len(added) == 1:
                parts.append(f"添加 {Path(added[0].file).name}")
            else:
                parts.append(f"添加 {len(added)} 个文件")

        if modified:
            if len(modified) == 1:
                parts.append(f"修改 {Path(modified[0].file).name}")
            else:
                parts.append(f"修改 {len(modified)} 个文件")

        if deleted:
            if len(deleted) == 1:
                parts.append(f"删除 {Path(deleted[0].file).name}")
            else:
                parts.append(f"删除 {len(deleted)} 个文件")

        if not parts:
            return "更新代码"

        return "、".join(parts)

    # ==================== 提交历史 ====================

    def log(self, count: int = 10, oneline: bool = False) -> str:
        """查看提交历史"""
        args = ["log", f"-{count}"]
        if oneline:
            args.append("--oneline")

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        return stdout if stdout else "无提交历史"

    def log_graph(self, count: int = 20) -> str:
        """查看提交图"""
        args = ["log", f"-{count}", "--graph", "--oneline", "--decorate", "--all"]
        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        return stdout if stdout else "无提交历史"

    def get_recent_commits(self, count: int = 10) -> List[GitCommit]:
        """获取最近的提交"""
        args = ["log", f"-{count}", "--format=%H|%h|%an|%ai|%s"]
        code, stdout, _ = self._run_git(args)
        if code != 0:
            return []

        commits = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 4)
            if len(parts) >= 5:
                commits.append(GitCommit(
                    hash=parts[0],
                    short_hash=parts[1],
                    author=parts[2],
                    date=parts[3],
                    message=parts[4]
                ))

        return commits

    # ==================== 代码追溯 ====================

    def blame(self, file: str, start_line: int = None, end_line: int = None) -> str:
        """代码追溯"""
        args = ["blame", "--porcelain"]

        if start_line and end_line:
            args.extend([f"-L{start_line},{end_line}"])
        elif start_line:
            args.extend([f"-L{start_line},{start_line}"])

        args.append(file)

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        return stdout

    def blame_formatted(self, file: str, start_line: int = None, end_line: int = None) -> str:
        """格式化的代码追溯"""
        args = ["blame", "-w", "-C"]

        if start_line and end_line:
            args.extend([f"-L{start_line},{end_line}"])

        args.append(file)

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        return stdout

    # ==================== 暂存管理 ====================

    def stash_save(self, message: str = None, include_untracked: bool = True) -> Tuple[bool, str]:
        """保存暂存"""
        args = ["stash", "save"]
        if include_untracked:
            args.append("-u")
        if message:
            args.append(message)

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, stderr

        return True, stdout

    def stash_list(self) -> List[GitStash]:
        """列出暂存"""
        code, stdout, _ = self._run_git(["stash", "list"])
        if code != 0:
            return []

        stashes = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            match = re.match(r'stash@\{(\d+)\}:\s+On\s+(\S+):\s+(.*)', line)
            if match:
                stashes.append(GitStash(
                    index=int(match.group(1)),
                    name=f"stash@{{{match.group(1)}}}",
                    message=match.group(3),
                    branch=match.group(2)
                ))

        return stashes

    def stash_pop(self, index: int = 0) -> Tuple[bool, str]:
        """恢复暂存"""
        code, stdout, stderr = self._run_git(["stash", "pop", f"stash@{{{index}}}"])
        if code != 0:
            return False, stderr
        return True, stdout

    def stash_drop(self, index: int = 0) -> Tuple[bool, str]:
        """删除暂存"""
        code, stdout, stderr = self._run_git(["stash", "drop", f"stash@{{{index}}}"])
        if code != 0:
            return False, stderr
        return True, stdout

    def format_stash_list(self) -> str:
        """格式化显示暂存列表"""
        stashes = self.stash_list()
        if not stashes:
            return "无暂存"

        lines = ["暂存列表:"]
        for s in stashes:
            lines.append(f"  {s.name}: {s.message} (分支: {s.branch})")
        return "\n".join(lines)

    # ==================== 分支管理 ====================

    def branch_list(self, remote: bool = False) -> str:
        """列出分支"""
        args = ["branch"]
        if remote:
            args.append("-a")

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return f"[错误] {stderr}"

        return stdout if stdout else "无分支"

    def branch_create(self, name: str, checkout: bool = False) -> Tuple[bool, str]:
        """创建分支"""
        if checkout:
            code, stdout, stderr = self._run_git(["checkout", "-b", name])
        else:
            code, stdout, stderr = self._run_git(["branch", name])

        if code != 0:
            return False, stderr
        return True, f"已创建分支: {name}"

    def branch_delete(self, name: str, force: bool = False) -> Tuple[bool, str]:
        """删除分支"""
        args = ["branch", "-D" if force else "-d", name]
        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, stderr
        return True, f"已删除分支: {name}"

    def checkout(self, target: str) -> Tuple[bool, str]:
        """切换分支"""
        code, stdout, stderr = self._run_git(["checkout", target])
        if code != 0:
            return False, stderr
        return True, f"已切换到: {target}"

    # ==================== 远程操作 ====================

    def fetch(self, remote: str = "origin") -> Tuple[bool, str]:
        """获取远程更新"""
        code, stdout, stderr = self._run_git(["fetch", remote])
        if code != 0:
            return False, stderr
        return True, "已获取远程更新"

    def pull(self, remote: str = "origin", branch: str = None) -> Tuple[bool, str]:
        """拉取远程更新"""
        args = ["pull", remote]
        if branch:
            args.append(branch)

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, stderr
        return True, stdout

    def push(self, remote: str = "origin", branch: str = None, force: bool = False) -> Tuple[bool, str]:
        """推送到远程"""
        args = ["push", remote]
        if branch:
            args.append(branch)
        if force:
            args.append("--force")

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, stderr
        return True, stdout

    # ==================== 标签管理 ====================

    def tag_list(self) -> str:
        """列出标签"""
        code, stdout, stderr = self._run_git(["tag"])
        if code != 0:
            return f"[错误] {stderr}"
        return stdout if stdout else "无标签"

    def tag_create(self, name: str, message: str = None) -> Tuple[bool, str]:
        """创建标签"""
        args = ["tag"]
        if message:
            args.extend(["-a", name, "-m", message])
        else:
            args.append(name)

        code, stdout, stderr = self._run_git(args)
        if code != 0:
            return False, stderr
        return True, f"已创建标签: {name}"


# ==================== 工具定义 ====================

GIT_ENHANCED_TOOLS = [
    {
        "name": "git_status",
        "description": "获取详细的Git状态",
        "parameters": {
            "type": "object",
            "properties": {}
        }
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
                "message": {"type": "string", "description": "提交信息 (可选，自动生成)"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "文件列表 (可选)"},
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
    {
        "name": "git_push",
        "description": "推送到远程",
        "parameters": {
            "type": "object",
            "properties": {
                "remote": {"type": "string", "description": "远程仓库名"},
                "branch": {"type": "string", "description": "分支名"},
                "force": {"type": "boolean", "description": "是否强制推送"}
            }
        }
    },
    {
        "name": "git_pull",
        "description": "拉取远程更新",
        "parameters": {
            "type": "object",
            "properties": {
                "remote": {"type": "string", "description": "远程仓库名"},
                "branch": {"type": "string", "description": "分支名"}
            }
        }
    }
]
