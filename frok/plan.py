"""
Frok Plan模式
先规划后执行的工作模式
灵感来自Claude Code的Plan模式
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


# ==================== 数据结构 ====================

class PlanStatus(Enum):
    """计划状态"""
    DRAFT = "draft"          # 草稿
    APPROVED = "approved"    # 已批准
    EXECUTING = "executing"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class PlanStep:
    """计划步骤"""
    id: str
    description: str
    tool: str = ""  # 需要使用的工具
    params: Dict = field(default_factory=dict)
    status: str = "pending"  # pending/executing/completed/failed/skipped
    result: str = ""
    error: str = ""
    depends_on: List[str] = field(default_factory=list)  # 依赖的步骤ID


@dataclass
class Plan:
    """执行计划"""
    id: str
    task: str
    description: str
    steps: List[PlanStep]
    status: PlanStatus
    created_at: str
    updated_at: str
    context: Dict = field(default_factory=dict)
    result: str = ""
    error: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "task": self.task,
            "description": self.description,
            "steps": [asdict(s) for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Plan':
        """从字典创建"""
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return cls(
            id=data["id"],
            task=data["task"],
            description=data.get("description", ""),
            steps=steps,
            status=PlanStatus(data.get("status", "draft")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            context=data.get("context", {}),
            result=data.get("result", ""),
            error=data.get("error", ""),
            metadata=data.get("metadata", {}),
        )


# ==================== Plan管理器 ====================

class PlanManager:
    """
    规划模式管理器

    工作流程:
    1. 用户提出任务
    2. AI生成计划
    3. 用户审核计划
    4. 批准后执行
    5. 跟踪执行状态
    """

    def __init__(self, plans_dir: str = None):
        self.plans_dir = Path(plans_dir or os.path.join(os.path.dirname(__file__), "plans"))
        self.plans_dir.mkdir(parents=True, exist_ok=True)

        self.current_plan: Optional[Plan] = None
        self.plans_history: Dict[str, Plan] = {}

        # 加载历史计划
        self._load_history()

    def _load_history(self):
        """加载历史计划"""
        for plan_file in self.plans_dir.glob("*.json"):
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                plan = Plan.from_dict(data)
                self.plans_history[plan.id] = plan
            except Exception:
                continue

    def _save_plan(self, plan: Plan):
        """保存计划到文件"""
        plan_file = self.plans_dir / f"{plan.id}.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)

    # ==================== 计划创建 ====================

    def create_plan(self, task: str, description: str = "",
                    steps: List[Dict] = None, context: Dict = None) -> Plan:
        """
        创建新计划

        Args:
            task: 任务描述
            description: 详细说明
            steps: 步骤列表，每个步骤包含 description, tool, params
            context: 上下文信息

        Returns:
            新创建的Plan对象
        """
        now = datetime.now().isoformat()
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"

        plan_steps = []
        if steps:
            for i, step_data in enumerate(steps):
                step = PlanStep(
                    id=f"{plan_id}_step_{i}",
                    description=step_data.get("description", f"步骤 {i+1}"),
                    tool=step_data.get("tool", ""),
                    params=step_data.get("params", {}),
                    depends_on=step_data.get("depends_on", []),
                )
                plan_steps.append(step)

        plan = Plan(
            id=plan_id,
            task=task,
            description=description or task,
            steps=plan_steps,
            status=PlanStatus.DRAFT,
            created_at=now,
            updated_at=now,
            context=context or {},
        )

        self.current_plan = plan
        self.plans_history[plan_id] = plan
        self._save_plan(plan)

        return plan

    def add_step(self, plan_id: str, description: str, tool: str = "",
                 params: Dict = None, depends_on: List[str] = None) -> PlanStep:
        """向计划添加步骤"""
        plan = self._get_plan(plan_id)
        if not plan:
            raise ValueError(f"计划不存在: {plan_id}")

        step = PlanStep(
            id=f"{plan_id}_step_{len(plan.steps)}",
            description=description,
            tool=tool,
            params=params or {},
            depends_on=depends_on or [],
        )
        plan.steps.append(step)
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return step

    def remove_step(self, plan_id: str, step_id: str) -> bool:
        """从计划中移除步骤"""
        plan = self._get_plan(plan_id)
        if not plan:
            return False

        plan.steps = [s for s in plan.steps if s.id != step_id]
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    # ==================== 计划审核 ====================

    def approve_plan(self, plan_id: str) -> bool:
        """批准计划"""
        plan = self._get_plan(plan_id)
        if not plan or plan.status != PlanStatus.DRAFT:
            return False

        plan.status = PlanStatus.APPROVED
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    def reject_plan(self, plan_id: str, reason: str = "") -> bool:
        """拒绝计划"""
        plan = self._get_plan(plan_id)
        if not plan:
            return False

        plan.status = PlanStatus.CANCELLED
        plan.error = reason
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    # ==================== 计划执行 ====================

    def start_execution(self, plan_id: str) -> bool:
        """开始执行计划"""
        plan = self._get_plan(plan_id)
        if not plan or plan.status != PlanStatus.APPROVED:
            return False

        plan.status = PlanStatus.EXECUTING
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    def update_step_status(self, plan_id: str, step_id: str,
                           status: str, result: str = "", error: str = "") -> bool:
        """更新步骤状态"""
        plan = self._get_plan(plan_id)
        if not plan:
            return False

        for step in plan.steps:
            if step.id == step_id:
                step.status = status
                step.result = result
                step.error = error
                plan.updated_at = datetime.now().isoformat()
                self._save_plan(plan)
                return True
        return False

    def complete_plan(self, plan_id: str, result: str = "") -> bool:
        """完成计划"""
        plan = self._get_plan(plan_id)
        if not plan:
            return False

        plan.status = PlanStatus.COMPLETED
        plan.result = result
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    def fail_plan(self, plan_id: str, error: str) -> bool:
        """标记计划失败"""
        plan = self._get_plan(plan_id)
        if not plan:
            return False

        plan.status = PlanStatus.FAILED
        plan.error = error
        plan.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    # ==================== 计划查询 ====================

    def _get_plan(self, plan_id: str) -> Optional[Plan]:
        """获取计划"""
        if self.current_plan and self.current_plan.id == plan_id:
            return self.current_plan
        return self.plans_history.get(plan_id)

    def get_current_plan(self) -> Optional[Plan]:
        """获取当前计划"""
        return self.current_plan

    def get_next_step(self, plan_id: str) -> Optional[PlanStep]:
        """获取下一个待执行的步骤"""
        plan = self._get_plan(plan_id)
        if not plan:
            return None

        for step in plan.steps:
            if step.status == "pending":
                # 检查依赖是否都已完成
                if step.depends_on:
                    deps_met = all(
                        any(s.id == dep and s.status == "completed"
                            for s in plan.steps)
                        for dep in step.depends_on
                    )
                    if not deps_met:
                        continue
                return step
        return None

    def get_plan_progress(self, plan_id: str) -> Dict:
        """获取计划进度"""
        plan = self._get_plan(plan_id)
        if not plan:
            return {}

        total = len(plan.steps)
        completed = sum(1 for s in plan.steps if s.status == "completed")
        failed = sum(1 for s in plan.steps if s.status == "failed")
        pending = sum(1 for s in plan.steps if s.status == "pending")

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "progress": f"{completed}/{total}" if total > 0 else "0/0",
            "percentage": round(completed / total * 100) if total > 0 else 0,
        }

    # ==================== 计划展示 ====================

    def format_plan(self, plan_id: str = None) -> str:
        """格式化显示计划"""
        plan = self._get_plan(plan_id) if plan_id else self.current_plan
        if not plan:
            return "暂无计划"

        lines = []
        lines.append(f"## 计划: {plan.task}")
        lines.append(f"ID: {plan.id}")
        lines.append(f"状态: {plan.status.value}")
        lines.append(f"创建时间: {plan.created_at[:19]}")
        lines.append("")

        if plan.description and plan.description != plan.task:
            lines.append(f"说明: {plan.description}")
            lines.append("")

        lines.append("### 执行步骤:")
        for i, step in enumerate(plan.steps, 1):
            status_icon = {
                "pending": "○",
                "executing": "◉",
                "completed": "●",
                "failed": "✗",
                "skipped": "⊘",
            }.get(step.status, "?")

            lines.append(f"{i}. [{status_icon}] {step.description}")
            if step.tool:
                lines.append(f"   工具: {step.tool}")
            if step.result:
                lines.append(f"   结果: {step.result[:100]}")
            if step.error:
                lines.append(f"   错误: {step.error}")

        # 进度
        progress = self.get_plan_progress(plan.id)
        lines.append("")
        lines.append(f"进度: {progress['progress']} ({progress['percentage']}%)")

        return "\n".join(lines)

    def list_plans(self, status: PlanStatus = None) -> str:
        """列出所有计划"""
        plans = []
        for plan in self.plans_history.values():
            if status and plan.status != status:
                continue
            plans.append(
                f"  [{plan.status.value}] {plan.id}: {plan.task[:50]}"
            )

        if not plans:
            return "暂无历史计划"

        return "历史计划:\n" + "\n".join(plans)


# ==================== 工具定义 ====================

PLAN_TOOLS = [
    {
        "name": "create_plan",
        "description": "创建执行计划。在执行复杂任务前，先创建计划供用户审核。",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "任务描述"
                },
                "description": {
                    "type": "string",
                    "description": "详细说明"
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "tool": {"type": "string"},
                            "params": {"type": "object"}
                        }
                    },
                    "description": "执行步骤列表"
                }
            },
            "required": ["task", "steps"]
        }
    },
    {
        "name": "approve_plan",
        "description": "批准执行计划",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "计划ID"
                }
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "execute_plan",
        "description": "执行已批准的计划",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "计划ID"
                }
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "show_plan",
        "description": "显示当前计划",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "计划ID (可选，默认显示当前计划)"
                }
            }
        }
    },
    {
        "name": "list_plans",
        "description": "列出所有计划",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "按状态筛选 (可选)"
                }
            }
        }
    },
    {
        "name": "update_step",
        "description": "更新计划步骤状态",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "计划ID"
                },
                "step_id": {
                    "type": "string",
                    "description": "步骤ID"
                },
                "status": {
                    "type": "string",
                    "description": "新状态 (completed/failed/skipped)"
                },
                "result": {
                    "type": "string",
                    "description": "执行结果"
                }
            },
            "required": ["plan_id", "step_id", "status"]
        }
    }
]
