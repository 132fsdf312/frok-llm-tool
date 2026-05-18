"""
Frok 多文件编辑模块
批量编辑多个文件，支持预览、撤销、重做
灵感来自Cursor的Composer功能
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 数据结构 ====================

@dataclass
class FileEdit:
    """单个文件编辑"""
    file_path: str
    old_content: str = ""  # 原始内容（用于撤销）
    new_content: str = ""  # 新内容
    edit_type: str = "modify"  # create/modify/delete
    diff_text: str = ""  # 差异文本

    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "edit_type": self.edit_type,
            "diff_text": self.diff_text,
        }


@dataclass
class EditOperation:
    """编辑操作（支持撤销/重做）"""
    id: str
    timestamp: str
    edits: List[FileEdit]
    description: str = ""
    is_applied: bool = False


@dataclass
class EditResult:
    """编辑结果"""
    success: bool
    files_modified: int = 0
    files_created: int = 0
    files_deleted: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_string(self) -> str:
        lines = []
        if self.success:
            lines.append("编辑完成:")
        else:
            lines.append("编辑失败:")

        if self.files_modified:
            lines.append(f"  修改: {self.files_modified} 个文件")
        if self.files_created:
            lines.append(f"  创建: {self.files_created} 个文件")
        if self.files_deleted:
            lines.append(f"  删除: {self.files_deleted} 个文件")
        if self.errors:
            lines.append("\n错误:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("\n警告:")
            for w in self.warnings:
                lines.append(f"  - {w}")

        return "\n".join(lines)


# ==================== 多文件编辑器 ====================

class MultiFileEditor:
    """
    多文件批量编辑器

    功能:
    - 批量编辑多个文件
    - 预览变更
    - 撤销/重做操作
    - 冲突检测
    """

    def __init__(self, working_dir: str = None, backup_dir: str = None):
        self.working_dir = working_dir or os.getcwd()
        self.backup_dir = Path(backup_dir or os.path.join(self.working_dir, ".frok_edits"))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # 操作历史
        self.history: List[EditOperation] = []
        self.current_index: int = -1
        self.max_history: int = 50

    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        if not os.path.isabs(path):
            path = os.path.join(self.working_dir, path)
        return os.path.normpath(path)

    def _generate_id(self) -> str:
        """生成操作ID"""
        return f"edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.history)}"

    # ==================== 编辑操作 ====================

    def edit_multiple(self, edits: List[Dict], description: str = "") -> EditResult:
        """
        批量编辑多个文件

        Args:
            edits: 编辑列表，每个编辑包含:
                - file_path: 文件路径
                - content: 新内容 (用于create/modify)
                - old_string: 要替换的旧内容 (用于精确编辑)
                - new_string: 替换后的新内容
                - action: create/modify/delete/replace
            description: 操作描述

        Returns:
            EditResult对象
        """
        result = EditResult(success=True)
        file_edits = []

        # 预处理所有编辑
        for edit in edits:
            file_path = self._normalize_path(edit.get("file_path", ""))
            action = edit.get("action", "modify")

            file_edit = FileEdit(
                file_path=file_path,
                edit_type=action,
            )

            try:
                if action == "create":
                    # 创建新文件
                    if os.path.exists(file_path):
                        result.warnings.append(f"文件已存在，将覆盖: {file_path}")
                        with open(file_path, "r", encoding="utf-8") as f:
                            file_edit.old_content = f.read()
                    file_edit.new_content = edit.get("content", "")

                elif action == "modify":
                    # 修改文件
                    if not os.path.exists(file_path):
                        result.errors.append(f"文件不存在: {file_path}")
                        result.success = False
                        continue

                    with open(file_path, "r", encoding="utf-8") as f:
                        file_edit.old_content = f.read()

                    if "content" in edit:
                        # 完全替换
                        file_edit.new_content = edit["content"]
                    elif "old_string" in edit and "new_string" in edit:
                        # 精确替换
                        old_string = edit["old_string"]
                        new_string = edit["new_string"]

                        if old_string not in file_edit.old_content:
                            result.errors.append(f"未找到匹配内容: {file_path}")
                            result.success = False
                            continue

                        count = file_edit.old_content.count(old_string)
                        if count > 1:
                            result.warnings.append(f"找到 {count} 处匹配，将全部替换: {file_path}")

                        file_edit.new_content = file_edit.old_content.replace(old_string, new_string)
                    else:
                        result.errors.append(f"缺少编辑内容: {file_path}")
                        result.success = False
                        continue

                elif action == "delete":
                    # 删除文件
                    if not os.path.exists(file_path):
                        result.warnings.append(f"文件不存在，跳过: {file_path}")
                        continue

                    with open(file_path, "r", encoding="utf-8") as f:
                        file_edit.old_content = f.read()
                    file_edit.new_content = ""

                elif action == "replace":
                    # 正则替换
                    import re
                    if not os.path.exists(file_path):
                        result.errors.append(f"文件不存在: {file_path}")
                        result.success = False
                        continue

                    with open(file_path, "r", encoding="utf-8") as f:
                        file_edit.old_content = f.read()

                    pattern = edit.get("pattern", "")
                    replacement = edit.get("replacement", "")

                    try:
                        file_edit.new_content = re.sub(pattern, replacement, file_edit.old_content)
                    except re.error as e:
                        result.errors.append(f"正则表达式错误: {e}")
                        result.success = False
                        continue

                file_edits.append(file_edit)

            except Exception as e:
                result.errors.append(f"处理 {file_path} 时出错: {e}")
                result.success = False

        # 如果有错误，不执行
        if not result.success:
            return result

        # 执行编辑
        return self._apply_edits(file_edits, description, result)

    def _apply_edits(self, file_edits: List[FileEdit], description: str,
                     result: EditResult) -> EditResult:
        """应用编辑"""
        # 创建备份
        backup_files = []
        for edit in file_edits:
            if edit.old_content and os.path.exists(edit.file_path):
                backup_path = self._create_backup(edit.file_path)
                if backup_path:
                    backup_files.append((edit.file_path, backup_path))

        # 执行编辑
        applied_edits = []
        for edit in file_edits:
            try:
                if edit.edit_type == "delete":
                    if os.path.exists(edit.file_path):
                        os.remove(edit.file_path)
                        result.files_deleted += 1
                else:
                    # 确保目录存在
                    os.makedirs(os.path.dirname(edit.file_path), exist_ok=True)

                    with open(edit.file_path, "w", encoding="utf-8") as f:
                        f.write(edit.new_content)

                    if edit.edit_type == "create":
                        result.files_created += 1
                    else:
                        result.files_modified += 1

                applied_edits.append(edit)

            except Exception as e:
                result.errors.append(f"写入 {edit.file_path} 失败: {e}")
                result.success = False

        # 记录操作历史
        if applied_edits:
            operation = EditOperation(
                id=self._generate_id(),
                timestamp=datetime.now().isoformat(),
                edits=applied_edits,
                description=description,
                is_applied=True,
            )
            self._add_to_history(operation)

        return result

    def _create_backup(self, file_path: str) -> Optional[str]:
        """创建文件备份"""
        try:
            backup_name = f"{Path(file_path).name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            backup_path = self.backup_dir / backup_name
            shutil.copy2(file_path, backup_path)
            return str(backup_path)
        except Exception:
            return None

    # ==================== 预览 ====================

    def preview(self, edits: List[Dict]) -> str:
        """
        预览编辑结果

        Args:
            edits: 编辑列表

        Returns:
            预览文本
        """
        lines = ["预览编辑结果:\n"]

        for edit in edits:
            file_path = self._normalize_path(edit.get("file_path", ""))
            action = edit.get("action", "modify")

            lines.append(f"## {file_path}")
            lines.append(f"操作: {action}")

            try:
                if action == "create":
                    content = edit.get("content", "")
                    lines.append(f"新建文件 ({len(content)} 字节)")
                    lines.append("```")
                    lines.append(content[:500])
                    if len(content) > 500:
                        lines.append("... (截断)")
                    lines.append("```")

                elif action == "modify":
                    if not os.path.exists(file_path):
                        lines.append("[错误] 文件不存在")
                        continue

                    with open(file_path, "r", encoding="utf-8") as f:
                        old_content = f.read()

                    if "content" in edit:
                        new_content = edit["content"]
                        lines.append(f"完全替换 ({len(old_content)} -> {len(new_content)} 字节)")
                    elif "old_string" in edit and "new_string" in edit:
                        old_string = edit["old_string"]
                        new_string = edit["new_string"]
                        count = old_content.count(old_string)
                        lines.append(f"替换 {count} 处匹配")
                        lines.append(f"- 旧: {old_string[:50]}...")
                        lines.append(f"+ 新: {new_string[:50]}...")
                    else:
                        lines.append("[警告] 缺少编辑内容")

                elif action == "delete":
                    if os.path.exists(file_path):
                        size = os.path.getsize(file_path)
                        lines.append(f"删除文件 ({size} 字节)")
                    else:
                        lines.append("[警告] 文件不存在")

            except Exception as e:
                lines.append(f"[错误] {e}")

            lines.append("")

        return "\n".join(lines)

    # ==================== 撤销/重做 ====================

    def _add_to_history(self, operation: EditOperation):
        """添加到历史记录"""
        # 清除当前索引之后的历史
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]

        self.history.append(operation)
        self.current_index = len(self.history) - 1

        # 限制历史大小
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
            self.current_index = len(self.history) - 1

    def undo(self, operation_id: str = None) -> Tuple[bool, str]:
        """
        撤销操作

        Args:
            operation_id: 操作ID（默认撤销最后一个）

        Returns:
            (成功, 结果信息)
        """
        if not self.history:
            return False, "无可撤销的操作"

        if operation_id:
            # 查找指定操作
            target_index = None
            for i, op in enumerate(self.history):
                if op.id == operation_id:
                    target_index = i
                    break
            if target_index is None:
                return False, f"未找到操作: {operation_id}"
        else:
            target_index = self.current_index

        if target_index < 0:
            return False, "无可撤销的操作"

        operation = self.history[target_index]
        if not operation.is_applied:
            return False, "操作未应用"

        # 执行撤销
        errors = []
        for edit in operation.edits:
            try:
                if edit.edit_type == "create":
                    # 创建的文件，删除
                    if os.path.exists(edit.file_path):
                        os.remove(edit.file_path)
                elif edit.edit_type == "delete":
                    # 删除的文件，恢复
                    with open(edit.file_path, "w", encoding="utf-8") as f:
                        f.write(edit.old_content)
                else:
                    # 修改的文件，恢复原内容
                    with open(edit.file_path, "w", encoding="utf-8") as f:
                        f.write(edit.old_content)
            except Exception as e:
                errors.append(f"撤销 {edit.file_path} 失败: {e}")

        operation.is_applied = False
        self.current_index = target_index - 1

        if errors:
            return False, f"撤销部分失败: {'; '.join(errors)}"
        return True, f"已撤销: {operation.description or operation.id}"

    def redo(self, operation_id: str = None) -> Tuple[bool, str]:
        """
        重做操作

        Args:
            operation_id: 操作ID（默认重做下一个）

        Returns:
            (成功, 结果信息)
        """
        if not self.history:
            return False, "无可重做的操作"

        if operation_id:
            target_index = None
            for i, op in enumerate(self.history):
                if op.id == operation_id:
                    target_index = i
                    break
            if target_index is None:
                return False, f"未找到操作: {operation_id}"
        else:
            target_index = self.current_index + 1

        if target_index >= len(self.history):
            return False, "无可重做的操作"

        operation = self.history[target_index]
        if operation.is_applied:
            return False, "操作已应用"

        # 执行重做
        errors = []
        for edit in operation.edits:
            try:
                if edit.edit_type == "delete":
                    if os.path.exists(edit.file_path):
                        os.remove(edit.file_path)
                else:
                    os.makedirs(os.path.dirname(edit.file_path), exist_ok=True)
                    with open(edit.file_path, "w", encoding="utf-8") as f:
                        f.write(edit.new_content)
            except Exception as e:
                errors.append(f"重做 {edit.file_path} 失败: {e}")

        operation.is_applied = True
        self.current_index = target_index

        if errors:
            return False, f"重做部分失败: {'; '.join(errors)}"
        return True, f"已重做: {operation.description or operation.id}"

    def get_history(self) -> str:
        """获取操作历史"""
        if not self.history:
            return "无操作历史"

        lines = ["操作历史:"]
        for i, op in enumerate(self.history):
            marker = "-> " if i == self.current_index else "   "
            status = "✓" if op.is_applied else "✗"
            files = ", ".join(Path(e.file_path).name for e in op.edits[:3])
            if len(op.edits) > 3:
                files += f" ... ({len(op.edits)} 个文件)"

            lines.append(f"{marker}[{status}] {op.id}: {op.description or files}")

        return "\n".join(lines)

    # ==================== 冲突检测 ====================

    def check_conflicts(self, edits: List[Dict]) -> List[str]:
        """检测编辑冲突"""
        conflicts = []
        file_paths = [self._normalize_path(e.get("file_path", "")) for e in edits]

        # 检查重复编辑
        seen = set()
        for path in file_paths:
            if path in seen:
                conflicts.append(f"重复编辑同一文件: {path}")
            seen.add(path)

        # 检查文件锁定
        for path in file_paths:
            lock_file = Path(path + ".lock")
            if lock_file.exists():
                conflicts.append(f"文件被锁定: {path}")

        return conflicts


# ==================== 工具定义 ====================

MULTI_EDIT_TOOLS = [
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
                            "action": {"type": "string", "description": "操作 (create/modify/delete/replace)"},
                            "content": {"type": "string", "description": "新内容"},
                            "old_string": {"type": "string", "description": "要替换的旧内容"},
                            "new_string": {"type": "string", "description": "替换后的新内容"},
                            "pattern": {"type": "string", "description": "正则表达式"},
                            "replacement": {"type": "string", "description": "替换内容"}
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
                    },
                    "description": "编辑列表"
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
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]
