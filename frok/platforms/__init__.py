"""
嵌入式平台适配器包
自动发现并加载所有平台实现
"""

from pathlib import Path
from typing import Dict, Type
import importlib
import inspect

# 平台注册表
_platforms: Dict[str, 'EmbeddedPlatform'] = {}


def register_platform(platform_class: Type['EmbeddedPlatform']):
    """注册平台类"""
    instance = platform_class()
    _platforms[instance.name] = instance
    return platform_class


def get_platform(name: str) -> 'EmbeddedPlatform':
    """获取平台实例"""
    return _platforms.get(name)


def get_all_platforms() -> Dict[str, 'EmbeddedPlatform']:
    """获取所有已注册平台"""
    return _platforms.copy()


def auto_discover():
    """自动发现并加载平台模块"""
    package_dir = Path(__file__).parent
    for py_file in package_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = f".{py_file.stem}"
        try:
            importlib.import_module(module_name, package=__name__)
        except Exception as e:
            print(f"[平台加载失败] {py_file.name}: {e}")


# 包加载时自动发现
auto_discover()
