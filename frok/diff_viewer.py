"""
Frok Diff可视化模块
Aider风格的diff显示、文件变更预览、代码审查界面
"""

import os
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ==================== 颜色定义 ====================

class DiffColors:
    """Diff专用颜色"""
    ADDED = '\033[32m'      # 绿色 - 新增
    REMOVED = '\033[31m'    # 红色 - 删除
    HEADER = '\033[36m'     # 青色 - 头部
    LOCATION = '\033[33m'   # 黄色 - 位置
    CONTEXT = '\033[90m'    # 灰色 - 上下文
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


# ==================== 数据结构 ====================

@dataclass
class DiffLine:
    """Diff行"""
    line_type: str  # 'add', 'remove', 'context', 'header', 'location'
    content: str
    old_line: int = 0
    new_line: int = 0


@dataclass
class FileDiff:
    """文件差异"""
    file_path: str
    old_path: str = ""
    new_path: str = ""
    lines: List[DiffLine] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    is_binary: bool = False
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False


@dataclass
class ChangeSummary:
    """变更摘要"""
    files_changed: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    files: List[FileDiff] = field(default_factory=list)


# ==================== Diff生成器 ====================

class DiffGenerator:
    """
    Diff生成器

    功能:
    - 生成unified diff
    - 生成context diff
    - 生成side-by-side diff
    - 文件变更统计
    """

    def generate_diff(self, old_content: str, new_content: str,
                      old_path: str = "a/file", new_path: str = "b/file",
                      context_lines: int = 3) -> FileDiff:
        """
        生成unified diff

        Args:
            old_content: 旧内容
            new_content: 新内容
            old_path: 旧文件路径
            new_path: 新文件路径
            context_lines: 上下文行数

        Returns:
            FileDiff对象
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_path,
            tofile=new_path,
            n=context_lines,
        )

        file_diff = FileDiff(
            file_path=new_path,
            old_path=old_path,
            new_path=new_path,
        )

        old_line = 0
        new_line = 0

        for line in diff:
            if line.startswith('+++') or line.startswith('---'):
                file_diff.lines.append(DiffLine(
                    line_type='header',
                    content=line.rstrip()
                ))
            elif line.startswith('@@'):
                # 解析位置信息
                import re
                match = re.search(r'-(\d+)', line)
                if match:
                    old_line = int(match.group(1))
                match = re.search(r'\+(\d+)', line)
                if match:
                    new_line = int(match.group(1))

                file_diff.lines.append(DiffLine(
                    line_type='location',
                    content=line.rstrip()
                ))
            elif line.startswith('+'):
                file_diff.lines.append(DiffLine(
                    line_type='add',
                    content=line[1:].rstrip(),
                    new_line=new_line
                ))
                file_diff.additions += 1
                new_line += 1
            elif line.startswith('-'):
                file_diff.lines.append(DiffLine(
                    line_type='remove',
                    content=line[1:].rstrip(),
                    old_line=old_line
                ))
                file_diff.deletions += 1
                old_line += 1
            else:
                file_diff.lines.append(DiffLine(
                    line_type='context',
                    content=line.rstrip(),
                    old_line=old_line,
                    new_line=new_line
                ))
                old_line += 1
                new_line += 1

        return file_diff

    def generate_from_files(self, old_file: str, new_file: str,
                            context_lines: int = 3) -> Optional[FileDiff]:
        """从文件生成diff"""
        try:
            with open(old_file, 'r', encoding='utf-8', errors='ignore') as f:
                old_content = f.read()
        except FileNotFoundError:
            old_content = ""

        try:
            with open(new_file, 'r', encoding='utf-8', errors='ignore') as f:
                new_content = f.read()
        except FileNotFoundError:
            return None

        return self.generate_diff(
            old_content, new_content,
            old_file, new_file,
            context_lines
        )

    def generate_side_by_side(self, old_content: str, new_content: str,
                              width: int = 80) -> str:
        """
        生成side-by-side diff

        Args:
            old_content: 旧内容
            new_content: 新内容
            width: 总宽度

        Returns:
            格式化的side-by-side diff
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        # 使用SequenceMatcher获取匹配
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        half_width = width // 2 - 3
        result = []

        # 表头
        result.append(f"{'旧文件':<{half_width}} | {'新文件':<{half_width}}")
        result.append(f"{'─' * half_width}─┼─{'─' * half_width}")

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == 'equal':
                for i in range(i1, i2):
                    old_line = old_lines[i][:half_width].ljust(half_width)
                    new_line = new_lines[j1 + (i - i1)][:half_width]
                    result.append(f"{old_line} │ {new_line}")
            elif tag == 'replace':
                max_lines = max(i2 - i1, j2 - j1)
                for k in range(max_lines):
                    old_line = ""
                    new_line = ""
                    if k < (i2 - i1):
                        old_line = f"\033[31m{old_lines[i1 + k][:half_width]}\033[0m"
                    if k < (j2 - j1):
                        new_line = f"\033[32m{new_lines[j1 + k][:half_width]}\033[0m"
                    result.append(f"{old_line:<{half_width}} │ {new_line}")
            elif tag == 'insert':
                for j in range(j1, j2):
                    old_line = " " * half_width
                    new_line = f"\033[32m{new_lines[j][:half_width]}\033[0m"
                    result.append(f"{old_line} │ {new_line}")
            elif tag == 'delete':
                for i in range(i1, i2):
                    old_line = f"\033[31m{old_lines[i][:half_width]}\033[0m"
                    new_line = " " * half_width
                    result.append(f"{old_line} │ {new_line}")

        return '\n'.join(result)

    def generate_word_diff(self, old_content: str, new_content: str) -> str:
        """生成单词级别的diff"""
        old_words = old_content.split()
        new_words = new_content.split()

        matcher = difflib.SequenceMatcher(None, old_words, new_words)
        result = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                result.extend(old_words[i1:i2])
            elif tag == 'replace':
                result.append(f"\033[31m{' '.join(old_words[i1:i2])}\033[0m")
                result.append(f"\033[32m{' '.join(new_words[j1:j2])}\033[0m")
            elif tag == 'insert':
                result.append(f"\033[32m{' '.join(new_words[j1:j2])}\033[0m")
            elif tag == 'delete':
                result.append(f"\033[31m{' '.join(old_words[i1:i2])}\033[0m")

        return ' '.join(result)


# ==================== Diff格式化器 ====================

class DiffFormatter:
    """
    Diff格式化器

    功能:
    - 格式化unified diff
    - 格式化side-by-side diff
    - 生成变更摘要
    """

    def __init__(self, color: bool = True):
        self.color = color

    def format_diff(self, file_diff: FileDiff, show_header: bool = True) -> str:
        """格式化unified diff"""
        result = []

        if show_header:
            result.append(self._format_header(file_diff))

        for line in file_diff.lines:
            if line.line_type == 'header':
                result.append(self._color(line.content, DiffColors.HEADER))
            elif line.line_type == 'location':
                result.append(self._color(line.content, DiffColors.LOCATION))
            elif line.line_type == 'add':
                result.append(self._color(f"+{line.content}", DiffColors.ADDED))
            elif line.line_type == 'remove':
                result.append(self._color(f"-{line.content}", DiffColors.REMOVED))
            else:
                result.append(f" {line.content}")

        return '\n'.join(result)

    def format_summary(self, summary: ChangeSummary) -> str:
        """格式化变更摘要"""
        result = []

        # 总体统计
        result.append(self._color(
            f"变更统计: {summary.files_changed} 个文件, "
            f"+{summary.total_additions} -{summary.total_deletions}",
            DiffColors.BOLD
        ))

        # 文件列表
        for file_diff in summary.files:
            status = self._get_file_status(file_diff)
            result.append(f"  {status} {file_diff.file_path} "
                        f"(+{file_diff.additions} -{file_diff.deletions})")

        return '\n'.join(result)

    def format_file_list(self, files: List[FileDiff]) -> str:
        """格式化文件列表"""
        if not files:
            return "无变更文件"

        result = ["变更文件列表:"]

        for f in files:
            status = self._get_file_status(f)
            changes = f"+{f.additions} -{f.deletions}"
            result.append(f"  {status} {f.file_path} ({changes})")

        return '\n'.join(result)

    def _format_header(self, file_diff: FileDiff) -> str:
        """格式化文件头"""
        parts = []

        if file_diff.is_new:
            parts.append(self._color("[新文件]", DiffColors.ADDED))
        elif file_diff.is_deleted:
            parts.append(self._color("[已删除]", DiffColors.REMOVED))
        elif file_diff.is_renamed:
            parts.append(self._color("[已重命名]", DiffColors.LOCATION))
        else:
            parts.append(self._color("[已修改]", DiffColors.HEADER))

        parts.append(file_diff.file_path)
        parts.append(f"(+{file_diff.additions} -{file_diff.deletions})")

        return ' '.join(parts)

    def _get_file_status(self, file_diff: FileDiff) -> str:
        """获取文件状态标记"""
        if file_diff.is_new:
            return self._color("+", DiffColors.ADDED)
        elif file_diff.is_deleted:
            return self._color("-", DiffColors.REMOVED)
        elif file_diff.is_renamed:
            return self._color("→", DiffColors.LOCATION)
        else:
            return self._color("M", DiffColors.HEADER)

    def _color(self, text: str, color: str) -> str:
        """应用颜色"""
        if self.color:
            return f"{color}{text}{DiffColors.RESET}"
        return text


# ==================== 代码审查器 ====================

class CodeReviewer:
    """
    代码审查器

    功能:
    - 基于diff的代码审查
    - 生成审查意见
    - 格式化审查报告
    """

    # 审查规则
    REVIEW_RULES = [
        {
            "pattern": r"TODO|FIXME|HACK|XXX",
            "severity": "info",
            "message": "发现TODO/FIXME注释"
        },
        {
            "pattern": r"print\(|console\.log",
            "severity": "warning",
            "message": "发现调试输出语句"
        },
        {
            "pattern": r"password|secret|key|token",
            "severity": "error",
            "message": "可能包含敏感信息"
        },
        {
            "pattern": r"except\s*:",
            "severity": "warning",
            "message": "空的except子句"
        },
        {
            "pattern": r"eval\(|exec\(",
            "severity": "error",
            "message": "使用了eval/exec，存在安全风险"
        },
    ]

    def review_diff(self, file_diff: FileDiff) -> List[Dict]:
        """
        审查diff

        Args:
            file_diff: 文件差异

        Returns:
            审查意见列表
        """
        issues = []

        for line in file_diff.lines:
            if line.line_type != 'add':
                continue

            for rule in self.REVIEW_RULES:
                import re
                if re.search(rule["pattern"], line.content, re.IGNORECASE):
                    issues.append({
                        "file": file_diff.file_path,
                        "line": line.new_line,
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "content": line.content.strip(),
                    })

        return issues

    def format_review(self, issues: List[Dict]) -> str:
        """格式化审查报告"""
        if not issues:
            return "✓ 代码审查通过，未发现问题"

        result = [f"发现 {len(issues)} 个问题:"]

        for issue in issues:
            severity_icon = {
                "error": "✗",
                "warning": "⚠",
                "info": "ℹ",
            }.get(issue["severity"], "·")

            severity_color = {
                "error": DiffColors.REMOVED,
                "warning": DiffColors.LOCATION,
                "info": DiffColors.CONTEXT,
            }.get(issue["severity"], "")

            result.append(
                f"  {severity_color}{severity_icon}{DiffColors.RESET} "
                f"{issue['file']}:{issue['line']} - {issue['message']}"
            )
            result.append(f"    {DiffColors.DIM}{issue['content']}{DiffColors.RESET}")

        return '\n'.join(result)


# ==================== 工具定义 ====================

DIFF_VIEWER_TOOLS = [
    {
        "name": "show_diff",
        "description": "显示文件差异",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径"},
                "staged": {"type": "boolean", "description": "是否查看暂存区"}
            }
        }
    },
    {
        "name": "diff_files",
        "description": "比较两个文件的差异",
        "parameters": {
            "type": "object",
            "properties": {
                "old_file": {"type": "string", "description": "旧文件路径"},
                "new_file": {"type": "string", "description": "新文件路径"}
            },
            "required": ["old_file", "new_file"]
        }
    },
    {
        "name": "review_changes",
        "description": "审查代码变更",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径 (可选)"}
            }
        }
    }
]
