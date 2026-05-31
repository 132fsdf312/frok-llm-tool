"""
Frok CLI 终端界面
Claude Code 风格的紧凑、清晰终端 UI
"""

import os
import sys
import shutil
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ==================== 颜色定义 ====================

class Colors:
    """ANSI 颜色代码"""
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'

    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'

    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'

    @staticmethod
    def disable():
        for attr in dir(Colors):
            if not attr.startswith('_') and attr.isupper():
                setattr(Colors, attr, '')


def _enable_windows_ansi() -> bool:
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        if not (mode.value & 0x0004):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


def supports_color() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('TERM') == 'dumb':
        return False
    if sys.platform == 'win32':
        if os.environ.get('ANSICON') or os.environ.get('WT_SESSION'):
            return True
        if os.environ.get('ConEmuPID') or os.environ.get('TERM_PROGRAM'):
            return True
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            return _enable_windows_ansi()
        return False
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


if not supports_color():
    Colors.disable()


# ==================== 工具函数 ====================

def display_width(text: str) -> int:
    """计算文本的终端显示宽度（中文占 2 列）"""
    # 先去除 ANSI 转义序列
    clean = re.sub(r'\033\[[0-9;]*m', '', text)
    w = 0
    for ch in clean:
        if ord(ch) > 0x2E80:  # CJK 统一汉字及以上
            w += 2
        else:
            w += 1
    return w


def truncate(text: str, max_width: int, suffix: str = '...') -> str:
    """按显示宽度截断文本"""
    if display_width(text) <= max_width:
        return text
    w = 0
    for i, ch in enumerate(text):
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > max_width - len(suffix):
            return text[:i] + suffix
        w += cw
    return text


# ==================== 组件 ====================

class Box:
    """盒子组件（正确处理中文宽度）"""

    @staticmethod
    def render(content: str, title: str = "", width: int = 60) -> str:
        lines = content.split('\n')
        # 计算内容最大显示宽度
        max_content = width - 4  # 左右各 2 字符边框+空格
        c = Colors

        result = []
        if title:
            header = f" {title} "
            pad_total = width - 2 - display_width(header)
            left_pad = pad_total // 2
            right_pad = pad_total - left_pad
            result.append(f"{c.CYAN}{'─' * left_pad}{c.BOLD}{header}{c.RESET}{c.CYAN}{'─' * right_pad}{c.RESET}")
        else:
            result.append(f"{c.CYAN}{'─' * width}{c.RESET}")

        for line in lines:
            dw = display_width(line)
            pad = max_content - dw
            if pad < 0:
                line = truncate(line, max_content)
                pad = 0
            result.append(f"  {line}{' ' * pad}  ")

        result.append(f"{c.CYAN}{'─' * width}{c.RESET}")
        return '\n'.join(result)


class ProgressBar:
    """进度条组件"""

    def __init__(self, total: int, width: int = 30):
        self.total = total
        self.current = 0
        self.width = width
        self.label = ""

    def update(self, current: int, label: str = ""):
        self.current = min(current, self.total)
        self.label = label

    def render(self) -> str:
        if self.total == 0:
            return ""
        percent = self.current / self.total
        filled = int(self.width * percent)
        empty = self.width - filled
        bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"
        result = f"  {bar} {percent * 100:.0f}%"
        if self.label:
            result += f" {self.label}"
        return result


class Menu:
    """交互式菜单"""

    @staticmethod
    def select(title: str, options: List[str], multi: bool = False) -> Optional[List[int]]:
        c = Colors
        print(f"\n  {c.BOLD}{title}{c.RESET}")
        print(f"  {c.DIM}{'─' * 40}{c.RESET}")

        for i, option in enumerate(options, 1):
            print(f"    {c.CYAN}{i}{c.RESET}. {option}")

        hint = "输入序号（逗号分隔多选）" if multi else "输入序号"
        print(f"\n  {c.DIM}{hint}:{c.RESET}", end=" ")

        try:
            choice = input().strip()
            if not choice:
                return None
            if multi:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                return [i for i in indices if 0 <= i < len(options)]
            else:
                idx = int(choice) - 1
                return [idx] if 0 <= idx < len(options) else None
        except (ValueError, EOFError):
            return None


# ==================== 主 CLI 类 ====================

class FrokCLI:
    """
    Frok CLI 终端界面

    紧凑、清晰、有层次感的终端交互体验
    """

    def __init__(self):
        self.terminal_width = shutil.get_terminal_size().columns
        self._plan_mode = False

    # ==================== Banner ====================

    def show_banner(self, provider: str = "", model: str = ""):
        """显示启动横幅（精简单行风格）"""
        c = Colors
        w = min(self.terminal_width, 64)

        logo = f"{c.BOLD}{c.CYAN}Frok Code{c.RESET} {c.DIM}v2.0{c.RESET}"
        if provider and model:
            logo += f"  {c.DIM}|{c.RESET}  {c.WHITE}{provider}{c.RESET} {c.DIM}/{c.RESET} {c.DIM}{model}{c.RESET}"

        print()
        print(f"  {logo}")
        print(f"  {c.DIM}{'─' * (w - 4)}{c.RESET}")
        print(f"  {c.DIM}直接输入任务开始  /help 帮助  /setkey 配置  /quit 退出{c.RESET}")
        print()

    # ==================== 输入 ====================

    def input(self, prompt: str = "") -> str:
        """获取用户输入"""
        c = Colors
        try:
            if not prompt:
                if self._plan_mode:
                    prompt = f"{c.YELLOW}{c.BOLD}❯{c.RESET} {c.DIM}[Plan]{c.RESET} "
                else:
                    prompt = f"{c.GREEN}{c.BOLD}❯{c.RESET} "
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return "/quit"

    def confirm(self, message: str, default: bool = True) -> bool:
        """确认对话框"""
        c = Colors
        suffix = " [Y/n]" if default else " [y/N]"
        try:
            response = input(f"{c.YELLOW}?{c.RESET} {message}{suffix} ").strip().lower()
            if not response:
                return default
            return response in ('y', 'yes', '是')
        except (EOFError, KeyboardInterrupt):
            return False

    # ==================== 消息输出 ====================

    def print_assistant(self, text: str = ""):
        """打印助手回复前缀"""
        if text:
            print(f"  {text}")
        else:
            print()  # 空行作为助手回复开始的标记

    def print_system(self, text: str):
        """打印系统消息"""
        print(f"  {Colors.DIM}{text}{Colors.RESET}")

    def print_tool(self, name: str, params: str = ""):
        """打印工具调用（精简参数展示）"""
        c = Colors
        brief = self._brief_params(params)
        if brief:
            print(f"  {c.YELLOW}>{c.RESET} {c.BOLD}{name}{c.RESET} {c.DIM}{brief}{c.RESET}")
        else:
            print(f"  {c.YELLOW}>{c.RESET} {c.BOLD}{name}{c.RESET}")

    def print_result(self, text: str, success: bool = True):
        """打印工具结果"""
        c = Colors
        lines = text.split('\n')
        if len(lines) > 8:
            preview = '\n'.join(lines[:6])
            remaining = len(lines) - 6
            text = f"{preview}\n  {c.DIM}... ({remaining} more lines){c.RESET}"

        marker = f"{c.DIM}|{c.RESET}" if success else f"{c.RED}|{c.RESET}"
        for line in text.split('\n'):
            print(f"  {marker} {line}")

    def print_error(self, text: str):
        """打印错误"""
        print(f"  {Colors.RED}{Colors.BOLD}x{Colors.RESET} {Colors.RED}{text}{Colors.RESET}")

    def print_warning(self, text: str):
        """打印警告"""
        print(f"  {Colors.YELLOW}!{Colors.RESET} {text}")

    def print_info(self, text: str):
        """打印信息"""
        print(f"  {Colors.DIM}{text}{Colors.RESET}")

    def print_thinking(self):
        """打印思考中提示"""
        print(f"  {Colors.CYAN}*{Colors.RESET} {Colors.DIM}thinking...{Colors.RESET}", end="", flush=True)

    def clear_thinking(self):
        """清除思考中提示"""
        print(f"\r{' ' * 30}\r", end="", flush=True)

    # ==================== UI 组件 ====================

    def show_box(self, content: str, title: str = ""):
        """显示盒子"""
        print(Box.render(content, title, min(self.terminal_width - 2, 64)))

    def show_progress(self, current: int, total: int, label: str = ""):
        """显示进度条"""
        progress = ProgressBar(total)
        progress.update(current, label)
        print(f"\r{progress.render()}", end="", flush=True)

    def show_menu(self, title: str, options: List[str]) -> Optional[int]:
        """显示菜单并返回选择"""
        result = Menu.select(title, options)
        return result[0] if result else None

    def show_status_bar(self, provider: str, model: str,
                        tools: int = 0, messages: int = 0):
        """显示状态栏（单行紧凑）"""
        c = Colors
        parts = [
            f"{c.DIM}model{c.RESET} {c.WHITE}{provider}/{model}{c.RESET}",
            f"{c.DIM}tools{c.RESET} {tools}",
            f"{c.DIM}msgs{c.RESET} {messages}",
            f"{c.DIM}time{c.RESET} {datetime.now().strftime('%H:%M')}",
        ]
        print(f"  {c.DIM}{' | '.join(parts)}{c.RESET}")

    # ==================== 格式化 ====================

    def format_diff(self, diff_text: str) -> str:
        """格式化 diff 输出"""
        c = Colors
        lines = diff_text.split('\n')
        result = []
        for line in lines:
            if line.startswith('@@'):
                result.append(f"{c.CYAN}{line}{c.RESET}")
            elif line.startswith('+'):
                result.append(f"{c.GREEN}{line}{c.RESET}")
            elif line.startswith('-'):
                result.append(f"{c.RED}{line}{c.RESET}")
            else:
                result.append(line)
        return '\n'.join(result)

    # ==================== 辅助 ====================

    def _brief_params(self, params: str) -> str:
        """精简参数展示"""
        if not params or len(params) <= 60:
            return params
        # 截断到 60 字符
        return truncate(params, 60)

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def clear_line(self):
        print(f"\r{' ' * self.terminal_width}\r", end="", flush=True)


# ==================== 全局实例 ====================

cli = FrokCLI()
