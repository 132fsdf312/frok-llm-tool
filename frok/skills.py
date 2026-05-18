"""
Frok Skill系统
管理和执行预定义的技能
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

class SkillManager:
    def __init__(self, skills_dir: str = None):
        self.skills_dir = Path(skills_dir or os.path.join(os.path.dirname(__file__), "skills"))
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.skills: Dict[str, Dict] = {}
        self._load_skills()

    def _load_skills(self):
        """加载所有技能"""
        for skill_file in self.skills_dir.glob("*.json"):
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    skill = json.load(f)
                    if "name" in skill and "description" in skill:
                        self.skills[skill["name"]] = skill
            except Exception as e:
                print(f"[技能加载失败] {skill_file}: {e}")

        # 创建默认技能（如果不存在）
        self._create_default_skills()

    def _create_default_skills(self):
        """创建默认技能"""
        default_skills = [
            {
                "name": "code_review",
                "description": "代码审查",
                "trigger": "审查代码 / review code / 检查代码质量",
                "system_prompt": "你是一个专业的代码审查专家。请从以下维度审查代码：\n1. 代码质量和可读性\n2. 潜在bug和错误\n3. 性能问题\n4. 安全漏洞\n5. 最佳实践\n\n给出具体的改进建议。",
                "steps": [
                    "读取目标文件",
                    "分析代码结构",
                    "检查潜在问题",
                    "给出改进建议"
                ]
            },
            {
                "name": "debug_helper",
                "description": "调试助手",
                "trigger": "调试 / debug / 排查问题 / 修复bug",
                "system_prompt": "你是一个调试专家。请系统性地排查问题：\n1. 理解问题现象\n2. 分析可能原因\n3. 设计验证方案\n4. 提供修复方案",
                "steps": [
                    "了解问题现象",
                    "查看相关代码和日志",
                    "分析可能原因",
                    "提供修复方案"
                ]
            },
            {
                "name": "refactor_code",
                "description": "代码重构",
                "trigger": "重构 / refactor / 优化代码结构",
                "system_prompt": "你是一个代码重构专家。请在保持功能不变的前提下优化代码：\n1. 提取重复代码\n2. 简化复杂逻辑\n3. 改善命名和结构\n4. 提高可维护性",
                "steps": [
                    "分析现有代码",
                    "识别重构机会",
                    "设计新结构",
                    "执行重构并验证"
                ]
            },
            {
                "name": "write_docs",
                "description": "编写文档",
                "trigger": "写文档 / 文档生成 / API文档",
                "system_prompt": "你是一个技术文档专家。请编写清晰、完整的文档：\n1. 功能说明\n2. 使用示例\n3. API参考\n4. 注意事项",
                "steps": [
                    "分析代码功能",
                    "提取关键信息",
                    "编写文档",
                    "添加示例"
                ]
            },
            {
                "name": "explain_code",
                "description": "代码解释",
                "trigger": "解释代码 / 这段代码什么意思 / explain",
                "system_prompt": "请用清晰易懂的方式解释代码：\n1. 整体功能\n2. 核心逻辑\n3. 关键实现细节\n4. 使用场景",
                "steps": [
                    "阅读代码",
                    "分析逻辑",
                    "用通俗语言解释"
                ]
            },
            {
                "name": "generate_tests",
                "description": "生成测试",
                "trigger": "写测试 / 生成测试用例 / test",
                "system_prompt": "你是一个测试专家。请生成全面的测试用例：\n1. 正常流程测试\n2. 边界条件测试\n3. 异常情况测试\n4. 性能测试（如需要）",
                "steps": [
                    "分析待测代码",
                    "识别测试场景",
                    "生成测试用例",
                    "添加断言和验证"
                ]
            },
            {
                "name": "project_setup",
                "description": "项目初始化",
                "trigger": "初始化项目 / 创建项目 / setup",
                "system_prompt": "你是一个项目初始化专家。请帮助搭建项目结构：\n1. 创建目录结构\n2. 配置文件\n3. 依赖管理\n4. 基础代码",
                "steps": [
                    "了解项目需求",
                    "设计目录结构",
                    "创建配置文件",
                    "生成基础代码"
                ]
            },
            {
                "name": "learning_guide",
                "description": "学习指南",
                "trigger": "学习 / 教我 / 怎么学 / tutorial",
                "system_prompt": "你是一个耐心的导师。请根据用户的基础和目标，提供个性化的学习路径：\n1. 评估当前水平\n2. 设定学习目标\n3. 推荐学习资源\n4. 设计练习项目",
                "steps": [
                    "了解学习目标",
                    "评估当前水平",
                    "设计学习路径",
                    "推荐资源和练习"
                ]
            },
            {
                "name": "game_development",
                "description": "游戏开发",
                "trigger": "游戏 / game / 贪吃蛇 / 俄罗斯方块 / 打砖块",
                "system_prompt": "你是一个游戏开发专家。请帮助开发游戏：\n1. 设计游戏规则\n2. 实现核心逻辑\n3. 添加图形界面\n4. 优化游戏体验\n\n使用HTML5 Canvas或Python Pygame，确保游戏可直接运行。",
                "steps": [
                    "确定游戏类型和规则",
                    "设计游戏架构",
                    "实现核心游戏逻辑",
                    "添加图形和音效",
                    "测试和优化"
                ]
            },
            {
                "name": "web_development",
                "description": "网页开发",
                "trigger": "网页 / website / HTML / CSS / 前端",
                "system_prompt": "你是一个网页开发专家。请帮助开发网页：\n1. 设计页面结构\n2. 实现响应式布局\n3. 添加交互效果\n4. 优化性能\n\n使用现代HTML5、CSS3和JavaScript。",
                "steps": [
                    "分析需求",
                    "设计页面结构",
                    "编写HTML/CSS",
                    "添加JavaScript交互",
                    "测试和优化"
                ]
            },
            {
                "name": "api_integration",
                "description": "API集成",
                "trigger": "API / 接口 / 调用 / 请求",
                "system_prompt": "你是一个API集成专家。请帮助集成API：\n1. 分析API文档\n2. 设计调用方案\n3. 实现请求和响应处理\n4. 添加错误处理\n\n确保代码健壮、可维护。",
                "steps": [
                    "阅读API文档",
                    "设计调用架构",
                    "实现API调用",
                    "添加错误处理",
                    "测试和优化"
                ]
            },
            {
                "name": "data_processing",
                "description": "数据处理",
                "trigger": "数据 / data / CSV / JSON / 清洗 / 分析",
                "system_prompt": "你是一个数据处理专家。请帮助处理数据：\n1. 读取数据源\n2. 清洗和转换\n3. 分析和统计\n4. 可视化展示\n\n使用Pandas、NumPy等库。",
                "steps": [
                    "了解数据源",
                    "设计处理流程",
                    "实现数据清洗",
                    "分析和统计",
                    "生成报告"
                ]
            },
            {
                "name": "automation",
                "description": "自动化脚本",
                "trigger": "自动化 / 脚本 / 批量 / 定时 / auto",
                "system_prompt": "你是一个自动化专家。请帮助编写自动化脚本：\n1. 分析重复任务\n2. 设计自动化流程\n3. 实现脚本\n4. 添加日志和监控\n\n确保脚本可靠、可维护。",
                "steps": [
                    "了解任务需求",
                    "设计自动化流程",
                    "编写脚本",
                    "添加错误处理",
                    "测试和部署"
                ]
            }
        ]

        for skill in default_skills:
            # 只创建不存在的技能
            if skill["name"] not in self.skills:
                self.save_skill(skill)

    def save_skill(self, skill: Dict):
        """保存技能"""
        name = skill["name"]
        self.skills[name] = skill
        skill_file = self.skills_dir / f"{name}.json"
        with open(skill_file, "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)

    def get_skill(self, name: str) -> Optional[Dict]:
        """获取技能"""
        return self.skills.get(name)

    def list_skills(self) -> str:
        """列出所有技能"""
        if not self.skills:
            return "暂无技能"

        lines = ["可用技能:\n"]
        for name, skill in self.skills.items():
            lines.append(f"  /{name} - {skill['description']}")
        return "\n".join(lines)

    def find_skill_by_trigger(self, text: str) -> Optional[Dict]:
        """根据触发词查找技能"""
        text_lower = text.lower()
        for skill in self.skills.values():
            trigger = skill.get("trigger", "").lower()
            if any(t in text_lower for t in trigger.split(" / ")):
                return skill
        return None

    def get_skill_prompt(self, name: str) -> str:
        """获取技能的提示词"""
        skill = self.get_skill(name)
        if not skill:
            return f"[错误] 未找到技能: {name}"

        prompt = f"## 当前技能: {skill['description']}\n\n"
        prompt += f"{skill.get('system_prompt', '')}\n\n"

        if "steps" in skill:
            prompt += "执行步骤:\n"
            for i, step in enumerate(skill["steps"], 1):
                prompt += f"{i}. {step}\n"

        return prompt

# ==================== Skill工具 ====================

SKILL_TOOLS = [
    {
        "name": "list_skills",
        "description": "列出所有可用技能",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "use_skill",
        "description": "使用指定技能",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "技能名称"},
                "task": {"type": "string", "description": "具体任务描述"}
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "create_skill",
        "description": "创建新技能",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "技能名称"},
                "description": {"type": "string", "description": "技能描述"},
                "trigger": {"type": "string", "description": "触发词"},
                "system_prompt": {"type": "string", "description": "系统提示词"},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "执行步骤"}
            },
            "required": ["name", "description", "system_prompt"]
        }
    }
]
