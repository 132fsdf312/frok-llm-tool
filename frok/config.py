"""
Frok Code 项目常量和配置加载
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
ENV_PATH = PROJECT_ROOT / ".env"


def load_config() -> dict:
    """加载 config.json"""
    if not CONFIG_PATH.exists():
        logger.warning(f"配置文件不存在: {CONFIG_PATH}")
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"配置文件加载失败: {e}")
        return {}
