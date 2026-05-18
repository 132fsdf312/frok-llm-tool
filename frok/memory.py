"""
Frok 记忆系统
管理持久化记忆，包括用户偏好、项目信息、对话历史等
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class MemoryManager:
    def __init__(self, memory_dir: str = None):
        self.memory_dir = Path(memory_dir or os.path.join(os.path.dirname(__file__), "memory"))
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 记忆文件路径
        self.user_memory_file = self.memory_dir / "user.json"
        self.project_memory_file = self.memory_dir / "project.json"
        self.feedback_memory_file = self.memory_dir / "feedback.json"
        self.session_file = self.memory_dir / "sessions" / f"{datetime.now().strftime('%Y%m%d')}.json"

        # 确保目录存在
        self.session_file.parent.mkdir(exist_ok=True)

        # 加载记忆
        self.user_memory = self._load_json(self.user_memory_file) or {}
        self.project_memory = self._load_json(self.project_memory_file) or {}
        self.feedback_memory = self._load_json(self.feedback_memory_file) or {}

    def _load_json(self, path: Path) -> Optional[Dict]:
        """加载JSON文件"""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return None

    def _save_json(self, path: Path, data: Dict):
        """保存JSON文件"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[记忆保存失败] {e}")

    # ==================== 用户记忆 ====================

    def update_user_memory(self, key: str, value: str):
        """更新用户记忆"""
        self.user_memory[key] = {
            "value": value,
            "updated_at": datetime.now().isoformat()
        }
        self._save_json(self.user_memory_file, self.user_memory)

    def get_user_memory(self, key: str = None) -> str:
        """获取用户记忆"""
        if key:
            entry = self.user_memory.get(key)
            return entry["value"] if entry else None
        else:
            if not self.user_memory:
                return "暂无用户记忆"
            lines = []
            for k, v in self.user_memory.items():
                lines.append(f"- {k}: {v['value']}")
            return "\n".join(lines)

    def delete_user_memory(self, key: str) -> bool:
        """删除用户记忆"""
        if key in self.user_memory:
            del self.user_memory[key]
            self._save_json(self.user_memory_file, self.user_memory)
            return True
        return False

    # ==================== 项目记忆 ====================

    def update_project_memory(self, key: str, value: str):
        """更新项目记忆"""
        self.project_memory[key] = {
            "value": value,
            "updated_at": datetime.now().isoformat()
        }
        self._save_json(self.project_memory_file, self.project_memory)

    def get_project_memory(self, key: str = None) -> str:
        """获取项目记忆"""
        if key:
            entry = self.project_memory.get(key)
            return entry["value"] if entry else None
        else:
            if not self.project_memory:
                return "暂无项目记忆"
            lines = []
            for k, v in self.project_memory.items():
                lines.append(f"- {k}: {v['value']}")
            return "\n".join(lines)

    # ==================== 反馈记忆 ====================

    def add_feedback(self, feedback: str, category: str = "general"):
        """添加反馈记忆"""
        if category not in self.feedback_memory:
            self.feedback_memory[category] = []

        self.feedback_memory[category].append({
            "content": feedback,
            "timestamp": datetime.now().isoformat()
        })

        # 只保留最近50条
        if len(self.feedback_memory[category]) > 50:
            self.feedback_memory[category] = self.feedback_memory[category][-50:]

        self._save_json(self.feedback_memory_file, self.feedback_memory)

    def get_feedback(self, category: str = None) -> str:
        """获取反馈记忆"""
        if category:
            feedbacks = self.feedback_memory.get(category, [])
            if not feedbacks:
                return f"暂无 {category} 类型的反馈"
            return "\n".join(f"- {f['content']}" for f in feedbacks[-10:])
        else:
            if not self.feedback_memory:
                return "暂无反馈记忆"
            lines = []
            for cat, feedbacks in self.feedback_memory.items():
                lines.append(f"### {cat}")
                for f in feedbacks[-3:]:
                    lines.append(f"- {f['content']}")
            return "\n".join(lines)

    # ==================== 会话历史 ====================

    def save_session(self, messages: List[Dict], summary: str = ""):
        """保存会话"""
        sessions = self._load_json(self.session_file) or []
        sessions.append({
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "message_count": len(messages),
            "messages": messages[-20:]  # 只保存最后20条
        })
        self._save_json(self.session_file, sessions)

    def get_recent_sessions(self, count: int = 5) -> str:
        """获取最近的会话"""
        sessions = self._load_json(self.session_file) or []
        if not sessions:
            return "暂无会话历史"

        lines = []
        for s in sessions[-count:]:
            time = s["timestamp"][:19].replace("T", " ")
            summary = s.get("summary", "无摘要")
            lines.append(f"[{time}] {summary} ({s['message_count']}条消息)")
        return "\n".join(lines)

    # ==================== 记忆导出 ====================

    def export_all(self) -> str:
        """导出所有记忆"""
        output = []
        output.append("# Frok 记忆导出\n")
        output.append(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        output.append("## 用户记忆\n")
        output.append(self.get_user_memory() or "暂无")

        output.append("\n## 项目记忆\n")
        output.append(self.get_project_memory() or "暂无")

        output.append("\n## 反馈记忆\n")
        output.append(self.get_feedback() or "暂无")

        return "\n".join(output)

    def get_context_summary(self) -> str:
        """获取记忆上下文摘要（用于提示词）"""
        parts = []

        # 用户信息
        user_info = []
        for k, v in self.user_memory.items():
            user_info.append(f"{k}: {v['value']}")
        if user_info:
            parts.append("用户信息:\n" + "\n".join(user_info))

        # 项目信息
        project_info = []
        for k, v in self.project_memory.items():
            project_info.append(f"{k}: {v['value']}")
        if project_info:
            parts.append("项目信息:\n" + "\n".join(project_info))

        # 重要反馈
        important_feedback = self.feedback_memory.get("important", [])
        if important_feedback:
            parts.append("重要反馈:\n" + "\n".join(f"- {f['content']}" for f in important_feedback[-5:]))

        return "\n\n".join(parts) if parts else ""

# ==================== 记忆工具 ====================

MEMORY_TOOLS = [
    {
        "name": "remember_user",
        "description": "记住用户相关信息（偏好、角色、技能等）",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "value": {"type": "string", "description": "记忆内容"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "remember_project",
        "description": "记住项目相关信息（目标、进度、决策等）",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "value": {"type": "string", "description": "记忆内容"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "remember_feedback",
        "description": "记住用户反馈（纠正、确认、偏好等）",
        "parameters": {
            "type": "object",
            "properties": {
                "feedback": {"type": "string", "description": "反馈内容"},
                "category": {"type": "string", "description": "类别（correction/confirmation/preference）"}
            },
            "required": ["feedback"]
        }
    },
    {
        "name": "recall_memory",
        "description": "回忆记忆内容",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "记忆类型（user/project/feedback）"},
                "key": {"type": "string", "description": "特定键名（可选）"}
            },
            "required": ["type"]
        }
    }
]
