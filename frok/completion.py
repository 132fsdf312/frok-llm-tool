"""
Frok 代码补全模块
代码补全引擎，支持补全建议和内联建议
灵感来自Cursor的Tab补全功能
"""

import os
import re
import ast
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


# ==================== 数据结构 ====================

@dataclass
class Position:
    """光标位置"""
    line: int
    column: int

    def to_dict(self) -> Dict:
        return {"line": self.line, "column": self.column}


@dataclass
class CompletionItem:
    """补全项"""
    label: str
    kind: str  # function/class/variable/keyword/snippet
    detail: str = ""
    documentation: str = ""
    insert_text: str = ""
    sort_text: str = ""
    score: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
            "insert_text": self.insert_text,
        }


@dataclass
class InlineSuggestion:
    """内联建议"""
    text: str
    range_start: Position
    range_end: Position
    confidence: float = 0.0


@dataclass
class CompletionContext:
    """补全上下文"""
    file_path: str
    language: str
    position: Position
    current_line: str
    prefix: str  # 光标前的内容
    suffix: str  # 光标后的内容
    lines_before: List[str] = field(default_factory=list)
    lines_after: List[str] = field(default_factory=list)


# ==================== 语言支持 ====================

# Python关键字
PYTHON_KEYWORDS = [
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return",
    "try", "while", "with", "yield",
]

# Python内置函数
PYTHON_BUILTINS = [
    "abs", "all", "any", "bin", "bool", "bytearray", "bytes", "callable",
    "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir",
    "divmod", "enumerate", "eval", "exec", "filter", "float", "format",
    "frozenset", "getattr", "globals", "hasattr", "hash", "help", "hex",
    "id", "input", "int", "isinstance", "issubclass", "iter", "len",
    "list", "locals", "map", "max", "memoryview", "min", "next",
    "object", "oct", "open", "ord", "pow", "print", "property",
    "range", "repr", "reversed", "round", "set", "setattr", "slice",
    "sorted", "staticmethod", "str", "sum", "super", "tuple", "type",
    "vars", "zip",
]

# JavaScript关键字
JS_KEYWORDS = [
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "export", "extends", "finally",
    "for", "function", "if", "import", "in", "instanceof", "let", "new",
    "return", "super", "switch", "this", "throw", "try", "typeof",
    "var", "void", "while", "with", "yield", "async", "await",
]

# 代码片段
SNIPPETS = {
    "python": {
        "def": "def ${1:function_name}(${2:args}):\n    ${3:pass}",
        "class": "class ${1:ClassName}:\n    def __init__(self${2:, args}):\n        ${3:pass}",
        "if": "if ${1:condition}:\n    ${2:pass}",
        "for": "for ${1:item} in ${2:iterable}:\n    ${3:pass}",
        "while": "while ${1:condition}:\n    ${2:pass}",
        "try": "try:\n    ${1:pass}\nexcept ${2:Exception} as e:\n    ${3:print(e)}",
        "with": "with ${1:expression} as ${2:var}:\n    ${3:pass}",
        "list": "[${1:expression} for ${2:item} in ${3:iterable}]",
        "dict": "{${1:key}: ${2:value} for ${3:item} in ${4:iterable}}",
        "lambda": "lambda ${1:args}: ${2:expression}",
    },
    "javascript": {
        "function": "function ${1:name}(${2:args}) {\n    ${3}\n}",
        "arrow": "const ${1:name} = (${2:args}) => {\n    ${3}\n}",
        "class": "class ${1:Name} {\n    constructor(${2:args}) {\n        ${3}\n    }\n}",
        "if": "if (${1:condition}) {\n    ${2}\n}",
        "for": "for (let ${1:i} = 0; ${1:i} < ${2:length}; ${1:i}++) {\n    ${3}\n}",
        "foreach": "${1:array}.forEach((${2:item}) => {\n    ${3}\n})",
        "try": "try {\n    ${1}\n} catch (${2:error}) {\n    ${3}\n}",
        "import": "import ${1:module} from '${2:path}'",
        "export": "export default ${1:module}",
        "promise": "new Promise((resolve, reject) => {\n    ${1}\n})",
    }
}


# ==================== 补全引擎 ====================

class CodeCompletion:
    """
    代码补全引擎

    功能:
    - 上下文感知补全
    - 符号补全
    - 关键字补全
    - 代码片段
    - 内联建议
    """

    # 支持的语言
    SUPPORTED_LANGUAGES = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
    }

    def __init__(self, working_dir: str = None):
        self.working_dir = working_dir or os.getcwd()
        self.symbol_cache: Dict[str, List[str]] = {}

    def _detect_language(self, file_path: str) -> str:
        """检测文件语言"""
        ext = Path(file_path).suffix.lower()
        return self.SUPPORTED_LANGUAGES.get(ext, "unknown")

    def _build_context(self, file_path: str, position: Position,
                       content: str = None) -> CompletionContext:
        """构建补全上下文"""
        if content is None:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = ""

        lines = content.split("\n")

        # 获取当前行
        current_line = ""
        if 0 <= position.line - 1 < len(lines):
            current_line = lines[position.line - 1]

        # 获取前缀和后缀
        prefix = current_line[:position.column] if position.column <= len(current_line) else current_line
        suffix = current_line[position.column:] if position.column <= len(current_line) else ""

        # 获取上下文行
        lines_before = lines[max(0, position.line - 10):position.line - 1]
        lines_after = lines[position.line:min(len(lines), position.line + 10)]

        return CompletionContext(
            file_path=file_path,
            language=self._detect_language(file_path),
            position=position,
            current_line=current_line,
            prefix=prefix,
            suffix=suffix,
            lines_before=lines_before,
            lines_after=lines_after,
        )

    # ==================== 补全建议 ====================

    def get_completions(self, file_path: str, position: Position,
                        content: str = None) -> List[CompletionItem]:
        """
        获取补全建议

        Args:
            file_path: 文件路径
            position: 光标位置
            content: 文件内容（可选）

        Returns:
            补全项列表
        """
        context = self._build_context(file_path, position, content)
        completions = []

        # 1. 关键字补全
        completions.extend(self._keyword_completions(context))

        # 2. 符号补全
        completions.extend(self._symbol_completions(context))

        # 3. 代码片段补全
        completions.extend(self._snippet_completions(context))

        # 4. 内置函数补全
        completions.extend(self._builtin_completions(context))

        # 5. 上下文补全
        completions.extend(self._context_completions(context))

        # 去重和排序
        completions = self._deduplicate(completions)
        completions.sort(key=lambda c: -c.score)

        return completions[:50]  # 限制返回数量

    def _keyword_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """关键字补全"""
        completions = []

        # 获取当前输入的前缀
        prefix = self._get_current_prefix(context)

        if not prefix:
            return completions

        keywords = PYTHON_KEYWORDS if context.language == "python" else JS_KEYWORDS

        for keyword in keywords:
            if keyword.startswith(prefix):
                completions.append(CompletionItem(
                    label=keyword,
                    kind="keyword",
                    insert_text=keyword,
                    score=0.8,
                ))

        return completions

    def _symbol_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """符号补全"""
        completions = []
        prefix = self._get_current_prefix(context)

        if not prefix or len(prefix) < 2:
            return completions

        # 从当前文件中提取符号
        try:
            with open(context.file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 提取函数名
            for match in re.finditer(r'def\s+(\w+)', content):
                name = match.group(1)
                if name.startswith(prefix):
                    completions.append(CompletionItem(
                        label=name,
                        kind="function",
                        insert_text=name,
                        score=0.9,
                    ))

            # 提取类名
            for match in re.finditer(r'class\s+(\w+)', content):
                name = match.group(1)
                if name.startswith(prefix):
                    completions.append(CompletionItem(
                        label=name,
                        kind="class",
                        insert_text=name,
                        score=0.9,
                    ))

            # 提取变量名
            for match in re.finditer(r'(\w+)\s*=', content):
                name = match.group(1)
                if name.startswith(prefix) and not name.startswith("_"):
                    completions.append(CompletionItem(
                        label=name,
                        kind="variable",
                        insert_text=name,
                        score=0.7,
                    ))

        except Exception:
            pass

        return completions

    def _snippet_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """代码片段补全"""
        completions = []
        prefix = self._get_current_prefix(context)

        if not prefix:
            return completions

        snippets = SNIPPETS.get(context.language, {})

        for trigger, snippet in snippets.items():
            if trigger.startswith(prefix):
                completions.append(CompletionItem(
                    label=trigger,
                    kind="snippet",
                    detail="代码片段",
                    insert_text=snippet,
                    score=0.85,
                ))

        return completions

    def _builtin_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """内置函数补全"""
        completions = []
        prefix = self._get_current_prefix(context)

        if not prefix or context.language != "python":
            return completions

        for builtin in PYTHON_BUILTINS:
            if builtin.startswith(prefix):
                completions.append(CompletionItem(
                    label=builtin,
                    kind="function",
                    detail="内置函数",
                    insert_text=builtin,
                    score=0.75,
                ))

        return completions

    def _context_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """上下文补全"""
        completions = []

        # 检查是否在字符串中
        if self._is_in_string(context):
            return completions

        # 检查是否在注释中
        if self._is_in_comment(context):
            return completions

        return completions

    # ==================== 内联建议 ====================

    def get_inline_suggestion(self, file_path: str, position: Position,
                              content: str = None) -> Optional[InlineSuggestion]:
        """
        获取内联建议

        Args:
            file_path: 文件路径
            position: 光标位置
            content: 文件内容

        Returns:
            内联建议或None
        """
        context = self._build_context(file_path, position, content)

        # 分析上下文，生成内联建议
        suggestion = self._analyze_for_inline(context)

        return suggestion

    def _analyze_for_inline(self, context: CompletionContext) -> Optional[InlineSuggestion]:
        """分析上下文生成内联建议"""
        # 简单的模式匹配建议

        # 模式1: 函数定义后自动补全
        if context.language == "python":
            if context.current_line.strip().endswith(":"):
                # 检查是否是def语句
                if "def " in context.current_line:
                    indent = len(context.current_line) - len(context.current_line.lstrip())
                    return InlineSuggestion(
                        text=f"\n{' ' * (indent + 4)}pass",
                        range_start=Position(context.position.line, len(context.current_line)),
                        range_end=Position(context.position.line, len(context.current_line)),
                        confidence=0.8,
                    )

        # 模式2: 括号匹配
        if context.current_line.rstrip().endswith("("):
            return InlineSuggestion(
                text=")",
                range_start=Position(context.position.line, len(context.current_line)),
                range_end=Position(context.position.line, len(context.current_line)),
                confidence=0.9,
            )

        # 模式3: 引号匹配
        if context.current_line.rstrip().endswith('"'):
            return InlineSuggestion(
                text='"',
                range_start=Position(context.position.line, len(context.current_line)),
                range_end=Position(context.position.line, len(context.current_line)),
                confidence=0.9,
            )

        return None

    # ==================== 辅助方法 ====================

    def _get_current_prefix(self, context: CompletionContext) -> str:
        """获取当前输入的前缀"""
        # 查找光标前的标识符
        match = re.search(r'(\w+)$', context.prefix)
        return match.group(1) if match else ""

    def _is_in_string(self, context: CompletionContext) -> bool:
        """检查是否在字符串中"""
        prefix = context.prefix
        single_quotes = prefix.count("'") - prefix.count("\\'")
        double_quotes = prefix.count('"') - prefix.count('\\"')
        return (single_quotes % 2 == 1) or (double_quotes % 2 == 1)

    def _is_in_comment(self, context: CompletionContext) -> bool:
        """检查是否在注释中"""
        prefix = context.prefix
        if context.language == "python":
            return "#" in prefix
        elif context.language in ("javascript", "typescript"):
            return "//" in prefix
        return False

    def _deduplicate(self, completions: List[CompletionItem]) -> List[CompletionItem]:
        """去重"""
        seen = set()
        unique = []
        for c in completions:
            if c.label not in seen:
                seen.add(c.label)
                unique.append(c)
        return unique

    # ==================== 格式化 ====================

    def format_completions(self, completions: List[CompletionItem]) -> str:
        """格式化显示补全建议"""
        if not completions:
            return "无补全建议"

        lines = ["补全建议:"]
        for i, c in enumerate(completions[:20], 1):
            kind_icon = {
                "function": "ƒ",
                "class": "C",
                "variable": "v",
                "keyword": "K",
                "snippet": "S",
            }.get(c.kind, "·")

            detail = f" - {c.detail}" if c.detail else ""
            lines.append(f"  {i}. [{kind_icon}] {c.label}{detail}")

        return "\n".join(lines)


# ==================== 工具定义 ====================

COMPLETION_TOOLS = [
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
    }
]
