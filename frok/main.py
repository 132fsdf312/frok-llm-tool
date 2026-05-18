#!/usr/bin/env python3
"""
Frok - 智能编程助手
自动调用工具，像智能体一样工作
"""

import sys
import os
import subprocess
from pathlib import Path

# ==================== 环境检测与自动配置 ====================

SETUP_MARKER = Path(__file__).parent.parent / ".setup_complete"

REQUIRED_PACKAGES = [
    ("openai", "openai>=1.0.0"),
    ("anthropic", "anthropic>=0.18.0"),
    ("requests", "requests>=2.28.0"),
]


def check_and_install_packages():
    """检测依赖，缺少的自动安装，完成后写入标记文件跳过后续检测"""
    if SETUP_MARKER.exists():
        return

    missing = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            __import__(import_name)
        except ImportError:
            missing.append((import_name, pip_name))

    if not missing:
        SETUP_MARKER.write_text("setup complete", encoding="utf-8")
        return

    print("╔═══════════════════════════════════════════════╗")
    print("║             环境检测 - 依赖检查中             ║")
    print("╚═══════════════════════════════════════════════╝")

    for _, pip_name in missing:
        print(f"  [必需] {pip_name} ... 缺失")

    print()
    to_install = [pip_name for _, pip_name in missing]
    print(f"正在自动安装: {', '.join(to_install)}")
    print()

    install_ok = False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *to_install],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print("  依赖安装成功！\n")
            install_ok = True
        else:
            print("  自动安装失败。")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if "error" in line.lower() or "denied" in line.lower():
                        print(f"  {line.strip()}")
    except subprocess.TimeoutExpired:
        print("  安装超时，请检查网络连接。")
    except Exception as e:
        print(f"  安装失败: {e}")

    if not install_ok:
        print()
        print("─" * 50)
        print("  请手动安装依赖，打开终端执行：")
        print()
        print(f"  pip install {' '.join(to_install)}")
        print()
        print("  或者进入项目目录执行：")
        print(f"  cd \"{Path(__file__).parent.parent}\"")
        print("  pip install -r requirements.txt")
        print("─" * 50)
        print()

        input("安装完成后按回车键继续...")
        still_missing = []
        for import_name, pip_name in missing:
            try:
                __import__(import_name)
            except ImportError:
                still_missing.append(pip_name)
        if still_missing:
            print(f"\n  仍然缺少: {', '.join(still_missing)}")
            print("  请安装后重新运行程序。")
            input("\n按回车键退出...")
            sys.exit(1)
        print("  依赖已就绪，继续启动...\n")

    SETUP_MARKER.write_text("setup complete", encoding="utf-8")


check_and_install_packages()

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import main

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[错误] {e}")
        input("\n按回车键退出...")
