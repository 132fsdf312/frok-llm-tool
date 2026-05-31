"""
Frok 工具注册表
统一的工具注册、查找、分发机制
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册表

    每个子系统注册自己的工具 schema 和 handler。
    agent 通过 registry.execute(name, params) 统一分发。
    """

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._schemas: List[Dict] = []
        self._tool_names: set = set()

    def register(self, schema: Dict, handler: Callable) -> None:
        name = schema["name"]
        self._handlers[name] = handler
        self._schemas.append(schema)
        self._tool_names.add(name)

    def register_batch(self, schemas: List[Dict], handler_map: Dict[str, Callable]) -> None:
        for schema in schemas:
            name = schema["name"]
            handler = handler_map.get(name)
            if handler:
                self.register(schema, handler)
            else:
                logger.warning(f"工具 {name} 没有对应的 handler，跳过注册")

    def execute(self, name: str, params: Dict[str, Any]) -> str:
        handler = self._handlers.get(name)
        if not handler:
            return f"[错误] 未知工具: {name}"
        try:
            result = handler(**params)
            return result if isinstance(result, str) else str(result)
        except TypeError as e:
            return f"[错误] 工具 {name} 参数错误: {e}"
        except Exception as e:
            logger.exception(f"工具 {name} 执行异常")
            return f"[错误] {name} 执行失败: {e}"

    def get_schemas(self) -> List[Dict]:
        return self._schemas.copy()

    def get_tool_names(self) -> set:
        return self._tool_names.copy()

    def has_tool(self, name: str) -> bool:
        return name in self._handlers

    def get_handler(self, name: str) -> Optional[Callable]:
        return self._handlers.get(name)

    def format_tools_for_prompt(self) -> str:
        """生成工具描述文本（用于系统提示词）"""
        lines = ["你可以使用以下工具:\n"]
        for schema in self._schemas:
            params = []
            for pname, info in schema.get("parameters", {}).get("properties", {}).items():
                required = pname in schema.get("parameters", {}).get("required", [])
                param_str = f"{pname}" + (" (必填)" if required else " (可选)")
                params.append(param_str)

            lines.append(f"### {schema['name']}")
            lines.append(f"{schema.get('description', '')}")
            if params:
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
