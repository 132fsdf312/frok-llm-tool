"""
Frok Subagent系统
子代理并行执行，允许同时处理多个独立任务
灵感来自Claude Code的Subagent机制
"""

import json
import os
import uuid
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum


# ==================== 数据结构 ====================

class AgentStatus(Enum):
    """子代理状态"""
    IDLE = "idle"              # 空闲
    RUNNING = "running"        # 运行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消


@dataclass
class AgentMessage:
    """代理消息"""
    role: str  # user/assistant/system
    content: str
    timestamp: str = ""
    tool_calls: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class SubagentResult:
    """子代理执行结果"""
    agent_id: str
    task: str
    status: AgentStatus
    result: str = ""
    error: str = ""
    messages: List[AgentMessage] = field(default_factory=list)
    tool_calls: List[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "task": self.task,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class SubagentConfig:
    """子代理配置"""
    max_iterations: int = 10
    timeout_seconds: int = 300
    tools: List[str] = field(default_factory=list)  # 允许使用的工具，空=全部
    system_prompt: str = ""
    model_override: str = ""  # 覆盖默认模型


# ==================== 子代理实例 ====================

class Subagent:
    """
    子代理实例

    每个子代理是一个独立的智能体，可以：
    - 接收任务
    - 调用工具
    - 返回结果
    """

    def __init__(self, agent_id: str, task: str, config: SubagentConfig,
                 tool_executor=None, llm_caller=None):
        self.agent_id = agent_id
        self.task = task
        self.config = config
        self.tool_executor = tool_executor
        self.llm_caller = llm_caller

        self.status = AgentStatus.IDLE
        self.messages: List[AgentMessage] = []
        self.result: str = ""
        self.error: str = ""
        self.tool_calls: List[str] = []
        self.started_at: str = ""
        self.completed_at: str = ""

        self._cancel_flag = threading.Event()

    def run(self) -> SubagentResult:
        """执行子代理任务"""
        self.status = AgentStatus.RUNNING
        self.started_at = datetime.now().isoformat()

        try:
            # 构建系统提示
            system_prompt = self._build_system_prompt()

            # 初始化消息
            self.messages.append(AgentMessage(
                role="system",
                content=system_prompt
            ))
            self.messages.append(AgentMessage(
                role="user",
                content=self.task
            ))

            # 执行循环
            iteration = 0
            while iteration < self.config.max_iterations:
                if self._cancel_flag.is_set():
                    self.status = AgentStatus.CANCELLED
                    self.error = "任务被取消"
                    break

                iteration += 1

                # 调用LLM
                if self.llm_caller:
                    response, _ = self.llm_caller(
                        [{"role": m.role, "content": m.content} for m in self.messages],
                        stream=False
                    )
                else:
                    response = self._mock_llm_response()

                if not response:
                    self.error = "LLM未返回响应"
                    break

                self.messages.append(AgentMessage(
                    role="assistant",
                    content=response
                ))

                # 解析工具调用
                tool_calls = self._parse_tool_calls(response)

                if not tool_calls:
                    # 没有工具调用，认为任务完成
                    self.result = response
                    self.status = AgentStatus.COMPLETED
                    break

                # 执行工具
                for call in tool_calls:
                    if self._cancel_flag.is_set():
                        break

                    tool_name = call.get("name", "")
                    tool_params = call.get("parameters", {})

                    # 检查工具是否允许
                    if self.config.tools and tool_name not in self.config.tools:
                        tool_result = f"[错误] 工具 {tool_name} 不在允许列表中"
                    elif self.tool_executor:
                        tool_result = self.tool_executor.execute(tool_name, tool_params)
                    else:
                        tool_result = f"[模拟] 执行 {tool_name}"

                    self.tool_calls.append(tool_name)
                    self.messages.append(AgentMessage(
                        role="user",
                        content=f"工具结果 ({tool_name}):\n{tool_result}"
                    ))

                    # 检查是否是finish调用
                    if tool_name == "finish":
                        self.result = tool_params.get("result", "任务完成")
                        self.status = AgentStatus.COMPLETED
                        break

                if self.status == AgentStatus.COMPLETED:
                    break

            else:
                # 达到最大迭代次数
                self.result = "达到最大迭代次数"
                self.status = AgentStatus.COMPLETED

        except Exception as e:
            self.error = str(e)
            self.status = AgentStatus.FAILED

        self.completed_at = datetime.now().isoformat()

        return SubagentResult(
            agent_id=self.agent_id,
            task=self.task,
            status=self.status,
            result=self.result,
            error=self.error,
            messages=self.messages,
            tool_calls=self.tool_calls,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )

    def cancel(self):
        """取消任务"""
        self._cancel_flag.set()

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        prompt = self.config.system_prompt or "你是一个编程助手，负责执行指定任务。"
        prompt += f"\n\n你的任务: {self.task}"

        if self.config.tools:
            prompt += f"\n\n你可以使用的工具: {', '.join(self.config.tools)}"

        prompt += """

工具调用格式:
```tool_call
{"name": "工具名", "parameters": {"参数名": "值"}}
```

任务完成时调用:
```tool_call
{"name": "finish", "parameters": {"result": "任务结果"}}
```
"""
        return prompt

    def _parse_tool_calls(self, text: str) -> List[Dict]:
        """解析工具调用"""
        import re
        calls = []

        # 匹配 ```tool_call ... ```
        pattern = r'```tool_call\s*\n?([\s\S]*?)```'
        for match in re.finditer(pattern, text):
            try:
                call = json.loads(match.group(1).strip())
                if isinstance(call, dict) and "name" in call:
                    calls.append(call)
            except json.JSONDecodeError:
                continue

        # 匹配裸JSON
        if not calls:
            pattern = r'\{"name"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:\s*\{[^}]*\}\s*\}'
            for match in re.finditer(pattern, text):
                try:
                    call = json.loads(match.group())
                    if isinstance(call, dict) and "name" in call:
                        calls.append(call)
                except json.JSONDecodeError:
                    continue

        return calls

    def _mock_llm_response(self) -> str:
        """模拟LLM响应（用于测试）"""
        return f"[模拟响应] 正在处理任务: {self.task}"


# ==================== Subagent管理器 ====================

class SubagentManager:
    """
    子代理管理器

    功能:
    - 创建和管理子代理
    - 并行执行多个任务
    - 收集执行结果
    """

    def __init__(self, max_workers: int = 3, tool_executor=None, llm_caller=None):
        self.max_workers = max_workers
        self.tool_executor = tool_executor
        self.llm_caller = llm_caller

        self.agents: Dict[str, Subagent] = {}
        self.results: Dict[str, SubagentResult] = {}
        self.futures: Dict[str, Future] = {}

        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def spawn(self, task: str, config: SubagentConfig = None) -> str:
        """
        创建子代理

        Args:
            task: 任务描述
            config: 子代理配置

        Returns:
            子代理ID
        """
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        config = config or SubagentConfig()

        agent = Subagent(
            agent_id=agent_id,
            task=task,
            config=config,
            tool_executor=self.tool_executor,
            llm_caller=self.llm_caller,
        )

        self.agents[agent_id] = agent
        return agent_id

    def run_agent(self, agent_id: str) -> SubagentResult:
        """运行子代理（同步）"""
        agent = self.agents.get(agent_id)
        if not agent:
            return SubagentResult(
                agent_id=agent_id,
                task="",
                status=AgentStatus.FAILED,
                error=f"子代理不存在: {agent_id}"
            )

        result = agent.run()
        self.results[agent_id] = result
        return result

    def run_agent_async(self, agent_id: str) -> Future:
        """运行子代理（异步）"""
        agent = self.agents.get(agent_id)
        if not agent:
            future = Future()
            future.set_result(SubagentResult(
                agent_id=agent_id,
                task="",
                status=AgentStatus.FAILED,
                error=f"子代理不存在: {agent_id}"
            ))
            return future

        future = self.executor.submit(agent.run)
        self.futures[agent_id] = future

        # 设置回调
        def on_complete(f):
            result = f.result()
            self.results[agent_id] = result

        future.add_done_callback(on_complete)
        return future

    def parallel(self, tasks: List[str], configs: List[SubagentConfig] = None) -> List[SubagentResult]:
        """
        并行执行多个任务

        Args:
            tasks: 任务列表
            configs: 配置列表（可选）

        Returns:
            结果列表
        """
        if configs is None:
            configs = [SubagentConfig() for _ in tasks]
        elif len(configs) < len(tasks):
            configs.extend([SubagentConfig() for _ in range(len(tasks) - len(configs))])

        # 创建子代理
        agent_ids = []
        for task, config in zip(tasks, configs):
            agent_id = self.spawn(task, config)
            agent_ids.append(agent_id)

        # 并行执行
        futures = [self.run_agent_async(aid) for aid in agent_ids]

        # 等待所有完成
        results = []
        for future in futures:
            try:
                result = future.result(timeout=300)
                results.append(result)
            except Exception as e:
                results.append(SubagentResult(
                    agent_id="unknown",
                    task="",
                    status=AgentStatus.FAILED,
                    error=str(e)
                ))

        return results

    def collect(self, agent_id: str, timeout: int = 300) -> Optional[SubagentResult]:
        """收集子代理结果"""
        # 如果已有结果
        if agent_id in self.results:
            return self.results[agent_id]

        # 如果有future，等待完成
        if agent_id in self.futures:
            try:
                result = self.futures[agent_id].result(timeout=timeout)
                return result
            except Exception:
                return None

        return None

    def cancel(self, agent_id: str) -> bool:
        """取消子代理"""
        agent = self.agents.get(agent_id)
        if agent:
            agent.cancel()
            return True
        return False

    def cancel_all(self):
        """取消所有子代理"""
        for agent in self.agents.values():
            agent.cancel()

    def get_status(self, agent_id: str) -> AgentStatus:
        """获取子代理状态"""
        agent = self.agents.get(agent_id)
        return agent.status if agent else AgentStatus.IDLE

    def list_agents(self) -> str:
        """列出所有子代理"""
        if not self.agents:
            return "暂无子代理"

        lines = ["子代理列表:"]
        for agent_id, agent in self.agents.items():
            status_icon = {
                AgentStatus.IDLE: "○",
                AgentStatus.RUNNING: "◉",
                AgentStatus.COMPLETED: "●",
                AgentStatus.FAILED: "✗",
                AgentStatus.CANCELLED: "⊘",
            }.get(agent.status, "?")

            task_preview = agent.task[:40] + "..." if len(agent.task) > 40 else agent.task
            lines.append(f"  [{status_icon}] {agent_id}: {task_preview}")

        return "\n".join(lines)

    def format_result(self, agent_id: str) -> str:
        """格式化显示结果"""
        result = self.results.get(agent_id)
        if not result:
            return f"暂无结果: {agent_id}"

        lines = []
        lines.append(f"## 子代理结果: {agent_id}")
        lines.append(f"任务: {result.task}")
        lines.append(f"状态: {result.status.value}")
        lines.append(f"工具调用: {len(result.tool_calls)} 次")

        if result.started_at and result.completed_at:
            lines.append(f"时间: {result.started_at[:19]} -> {result.completed_at[:19]}")

        if result.result:
            lines.append(f"\n### 结果:\n{result.result}")

        if result.error:
            lines.append(f"\n### 错误:\n{result.error}")

        return "\n".join(lines)

    def shutdown(self):
        """关闭管理器"""
        self.cancel_all()
        self.executor.shutdown(wait=False)


# ==================== 工具定义 ====================

SUBAGENT_TOOLS = [
    {
        "name": "spawn_agent",
        "description": "创建子代理执行独立任务",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "任务描述"
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "允许使用的工具列表 (可选，空=全部)"
                },
                "system_prompt": {
                    "type": "string",
                    "description": "自定义系统提示 (可选)"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "run_agent",
        "description": "运行子代理并等待结果",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "子代理ID"
                }
            },
            "required": ["agent_id"]
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
        "name": "collect_result",
        "description": "收集子代理执行结果",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "子代理ID"
                }
            },
            "required": ["agent_id"]
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
    {
        "name": "cancel_agent",
        "description": "取消子代理",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "子代理ID"
                }
            },
            "required": ["agent_id"]
        }
    }
]
