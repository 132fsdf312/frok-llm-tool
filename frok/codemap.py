"""
Frok 代码地图模块
代码结构分析和符号索引
灵感来自Aider的code map功能
"""

import os
import re
import ast
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


# ==================== 数据结构 ====================

@dataclass
class Symbol:
    """代码符号"""
    name: str
    kind: str  # function/class/method/variable/import
    file: str
    line: int
    end_line: int = 0
    parent: str = ""  # 所属类/模块
    signature: str = ""  # 函数签名
    docstring: str = ""
    decorators: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "parent": self.parent,
            "signature": self.signature,
        }


@dataclass
class FileIndex:
    """文件索引"""
    path: str
    language: str
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    lines: int = 0
    size: int = 0

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "language": self.language,
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": self.imports,
            "lines": self.lines,
        }


@dataclass
class CodeMap:
    """代码地图"""
    directory: str
    files: List[FileIndex] = field(default_factory=list)
    symbol_index: Dict[str, List[Symbol]] = field(default_factory=dict)
    file_types: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "directory": self.directory,
            "files": [f.to_dict() for f in self.files],
            "file_types": self.file_types,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ==================== 语言解析器 ====================

class PythonParser:
    """Python代码解析器"""

    def parse(self, file_path: str, content: str) -> FileIndex:
        """解析Python文件"""
        index = FileIndex(
            path=file_path,
            language="python",
            lines=len(content.split('\n')),
        )

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return index

        # 提取符号
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                symbol = Symbol(
                    name=node.name,
                    kind="method" if self._is_method(node) else "function",
                    file=file_path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    parent=self._get_parent(node),
                    signature=self._get_function_signature(node),
                    docstring=ast.get_docstring(node) or "",
                    decorators=[self._get_decorator_name(d) for d in node.decorator_list],
                )
                index.symbols.append(symbol)

            elif isinstance(node, ast.ClassDef):
                symbol = Symbol(
                    name=node.name,
                    kind="class",
                    file=file_path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node) or "",
                    decorators=[self._get_decorator_name(d) for d in node.decorator_list],
                )
                index.symbols.append(symbol)

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    index.imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        index.imports.append(f"{node.module}.{alias.name}")

        return index

    def _is_method(self, node) -> bool:
        """判断是否是方法"""
        # 简单判断：检查父节点是否是类
        for parent in ast.walk(ast.parse("")):
            if isinstance(parent, ast.ClassDef):
                if node in ast.walk(parent):
                    return True
        return False

    def _get_parent(self, node) -> str:
        """获取父节点名称"""
        return ""

    def _get_function_signature(self, node) -> str:
        """获取函数签名"""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        return f"{node.name}({', '.join(args)})"

    def _get_decorator_name(self, node) -> str:
        """获取装饰器名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        return ""


class JavaScriptParser:
    """JavaScript/TypeScript代码解析器"""

    def parse(self, file_path: str, content: str) -> FileIndex:
        """解析JS/TS文件"""
        index = FileIndex(
            path=file_path,
            language="javascript",
            lines=len(content.split('\n')),
        )

        # 使用正则表达式解析
        patterns = {
            "function": r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)',
            "class": r'(?:export\s+)?class\s+(\w+)',
            "method": r'(\w+)\s*\([^)]*\)\s*\{',
            "arrow_function": r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            "import": r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
        }

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # 函数
            match = re.search(patterns["function"], line)
            if match:
                index.symbols.append(Symbol(
                    name=match.group(1),
                    kind="function",
                    file=file_path,
                    line=i,
                    signature=match.group(0),
                ))

            # 类
            match = re.search(patterns["class"], line)
            if match:
                index.symbols.append(Symbol(
                    name=match.group(1),
                    kind="class",
                    file=file_path,
                    line=i,
                ))

            # 箭头函数
            match = re.search(patterns["arrow_function"], line)
            if match:
                index.symbols.append(Symbol(
                    name=match.group(1),
                    kind="function",
                    file=file_path,
                    line=i,
                ))

            # 导入
            match = re.search(patterns["import"], line)
            if match:
                index.imports.append(match.group(1))

        return index


class GenericParser:
    """通用代码解析器"""

    def parse(self, file_path: str, content: str) -> FileIndex:
        """解析通用文件"""
        return FileIndex(
            path=file_path,
            language="unknown",
            lines=len(content.split('\n')),
        )


# ==================== 代码地图生成器 ====================

class CodeMapGenerator:
    """
    代码地图生成器

    功能:
    - 生成目录代码地图
    - 索引所有符号
    - 查找定义
    - 查找引用
    - 生成依赖图
    """

    # 支持的文件类型
    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
    }

    # 忽略的目录
    IGNORE_DIRS = {
        ".git", ".svn", ".hg",
        "node_modules", "__pycache__", ".pytest_cache",
        "venv", ".venv", "env",
        "dist", "build", ".next",
        ".idea", ".vscode",
    }

    def __init__(self, max_file_size: int = 100000):
        self.max_file_size = max_file_size
        self.parsers = {
            "python": PythonParser(),
            "javascript": JavaScriptParser(),
            "typescript": JavaScriptParser(),
        }
        self.default_parser = GenericParser()

    def generate(self, directory: str) -> CodeMap:
        """
        生成代码地图

        Args:
            directory: 目录路径

        Returns:
            CodeMap对象
        """
        directory = os.path.abspath(directory)
        code_map = CodeMap(directory=directory)

        if not os.path.isdir(directory):
            return code_map

        # 遍历目录
        for root, dirs, files in os.walk(directory):
            # 过滤忽略的目录
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for file_name in files:
                file_path = os.path.join(root, file_name)
                ext = Path(file_name).suffix.lower()

                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                # 检查文件大小
                try:
                    size = os.path.getsize(file_path)
                    if size > self.max_file_size:
                        continue
                except OSError:
                    continue

                # 解析文件
                language = self.SUPPORTED_EXTENSIONS[ext]
                file_index = self._parse_file(file_path, language, size)

                if file_index:
                    code_map.files.append(file_index)
                    code_map.file_types[ext] = code_map.file_types.get(ext, 0) + 1

                    # 索引符号
                    for symbol in file_index.symbols:
                        if symbol.name not in code_map.symbol_index:
                            code_map.symbol_index[symbol.name] = []
                        code_map.symbol_index[symbol.name].append(symbol)

        return code_map

    def _parse_file(self, file_path: str, language: str, size: int) -> Optional[FileIndex]:
        """解析单个文件"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return None

        parser = self.parsers.get(language, self.default_parser)
        file_index = parser.parse(file_path, content)
        file_index.size = size

        return file_index

    def format_map(self, code_map: CodeMap, detailed: bool = False) -> str:
        """格式化显示代码地图"""
        lines = []
        lines.append(f"# 代码地图: {code_map.directory}")
        lines.append(f"\n文件数量: {len(code_map.files)}")

        # 文件类型统计
        if code_map.file_types:
            lines.append("\n文件类型:")
            for ext, count in sorted(code_map.file_types.items(), key=lambda x: -x[1]):
                lines.append(f"  {ext}: {count}")

        # 文件列表
        lines.append("\n文件结构:")
        for file_index in sorted(code_map.files, key=lambda f: f.path):
            rel_path = os.path.relpath(file_index.path, code_map.directory)
            lines.append(f"  {rel_path} ({file_index.lines}行)")

            if detailed:
                for symbol in file_index.symbols:
                    prefix = "  "
                    if symbol.kind == "class":
                        prefix = "  [C] "
                    elif symbol.kind == "function":
                        prefix = "  [F] "
                    elif symbol.kind == "method":
                        prefix = "  [M] "
                    lines.append(f"{prefix}{symbol.name} (行{symbol.line})")

        return "\n".join(lines)

    def format_symbols(self, code_map: CodeMap, kind: str = None) -> str:
        """格式化显示符号列表"""
        symbols = []
        for file_index in code_map.files:
            for symbol in file_index.symbols:
                if kind and symbol.kind != kind:
                    continue
                symbols.append(symbol)

        if not symbols:
            return "无符号"

        lines = ["符号列表:"]
        for symbol in sorted(symbols, key=lambda s: (s.kind, s.name)):
            rel_path = os.path.relpath(symbol.file, code_map.directory)
            lines.append(f"  [{symbol.kind}] {symbol.name} - {rel_path}:{symbol.line}")

        return "\n".join(lines)

    # ==================== 符号查找 ====================

    def find_definition(self, code_map: CodeMap, symbol_name: str) -> List[Symbol]:
        """查找符号定义"""
        return code_map.symbol_index.get(symbol_name, [])

    def find_references(self, code_map: CodeMap, symbol_name: str) -> List[Tuple[str, int]]:
        """查找符号引用"""
        references = []

        pattern = re.compile(r'\b' + re.escape(symbol_name) + r'\b')

        for file_index in code_map.files:
            try:
                with open(file_index.path, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if pattern.search(line):
                            references.append((file_index.path, i))
            except Exception:
                continue

        return references

    def get_file_summary(self, file_path: str) -> str:
        """获取文件摘要"""
        ext = Path(file_path).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return f"不支持的文件类型: {ext}"

        language = self.SUPPORTED_EXTENSIONS[ext]
        parser = self.parsers.get(language, self.default_parser)

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            return f"读取失败: {e}"

        file_index = parser.parse(file_path, content)

        lines = []
        lines.append(f"文件: {file_path}")
        lines.append(f"语言: {language}")
        lines.append(f"行数: {file_index.lines}")

        if file_index.imports:
            lines.append(f"\n导入 ({len(file_index.imports)}):")
            for imp in file_index.imports[:10]:
                lines.append(f"  - {imp}")
            if len(file_index.imports) > 10:
                lines.append(f"  ... 还有 {len(file_index.imports) - 10} 个")

        classes = [s for s in file_index.symbols if s.kind == "class"]
        functions = [s for s in file_index.symbols if s.kind in ("function", "method")]

        if classes:
            lines.append(f"\n类 ({len(classes)}):")
            for cls in classes:
                lines.append(f"  - {cls.name} (行{cls.line})")

        if functions:
            lines.append(f"\n函数 ({len(functions)}):")
            for func in functions:
                lines.append(f"  - {func.signature or func.name} (行{func.line})")

        return "\n".join(lines)


# ==================== 工具定义 ====================

CODEMAP_TOOLS = [
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
    {
        "name": "list_symbols",
        "description": "列出代码符号",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "目录路径"},
                "kind": {"type": "string", "description": "符号类型 (function/class/method)"}
            },
            "required": ["directory"]
        }
    }
]
