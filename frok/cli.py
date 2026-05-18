"""
Frok CLI终端界面
Claude Code风格的彩色终端UI
"""

import os
import sys
import shutil
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


# ==================== 颜色定义 ====================

class Colors:
    """ANSI颜色代码"""
    # 基础颜色
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # 亮色
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'

    # 背景色
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'

    # 样式
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'

    @staticmethod
    def disable():
        """禁用颜色（Windows兼容）"""
        for attr in dir(Colors):
            if not attr.startswith('_') and attr.isupper():
                setattr(Colors, attr, '')


# 检测终端是否支持颜色
def supports_color() -> bool:
    """检测终端是否支持颜色"""
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('TERM') == 'dumb':
        return False
    if sys.platform == 'win32':
        # Windows 10+ 支持ANSI
        return os.environ.get('ANSICON') or os.environ.get('WT_SESSION')
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


if not supports_color():
    Colors.disable()


# ==================== 组件 ====================

class StatusLine:
    """状态栏组件"""

    def __init__(self):
        self.items: List[Tuple[str, str]] = []  # (label, value)

    def add(self, label: str, value: str):
        """添加状态项"""
        self.items.append((label, value))

    def render(self) -> str:
        """渲染状态栏"""
        if not self.items:
            return ""

        parts = []
        for label, value in self.items:
            parts.append(f"{Colors.DIM}{label}:{Colors.RESET} {value}")

        return f"{Colors.BG_BLUE}{Colors.WHITE} {' | '.join(parts)} {Colors.RESET}"


class ProgressBar:
    """进度条组件"""

    def __init__(self, total: int, width: int = 30):
        self.total = total
        self.current = 0
        self.width = width
        self.label = ""

    def update(self, current: int, label: str = ""):
        """更新进度"""
        self.current = min(current, self.total)
        self.label = label

    def render(self) -> str:
        """渲染进度条"""
        if self.total == 0:
            return ""

        percent = self.current / self.total
        filled = int(self.width * percent)
        empty = self.width - filled

        bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"
        percent_str = f"{percent * 100:.0f}%"

        result = f"  {bar} {percent_str}"
        if self.label:
            result += f" {self.label}"

        return result


class Spinner:
    """加载动画"""

    FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    def __init__(self):
        self.frame = 0
        self.message = ""

    def next(self, message: str = "") -> str:
        """获取下一帧"""
        self.message = message
        char = self.FRAMES[self.frame % len(self.FRAMES)]
        self.frame += 1
        return f"{Colors.CYAN}{char}{Colors.RESET} {self.message}"


class Box:
    """盒子组件"""

    @staticmethod
    def render(content: str, title: str = "", width: int = 60) -> str:
        """渲染盒子"""
        lines = content.split('\n')
        max_len = min(max(len(line) for line in lines), width - 4)

        result = []
        if title:
            title_line = f" {title} "
            padding = width - 2 - len(title_line)
            result.append(f"{Colors.CYAN}╭{'─' * (padding // 2)}{title_line}{'─' * (padding - padding // 2)}╮{Colors.RESET}")
        else:
            result.append(f"{Colors.CYAN}╭{'─' * (width - 2)}╮{Colors.RESET}")

        for line in lines:
            # 处理中文字符宽度
            display_len = sum(2 if ord(c) > 127 else 1 for c in line)
            padding = max_len - display_len
            result.append(f"{Colors.CYAN}│{Colors.RESET} {line}{' ' * max(0, padding)} {Colors.CYAN}│{Colors.RESET}")

        result.append(f"{Colors.CYAN}╰{'─' * (width - 2)}╯{Colors.RESET}")

        return '\n'.join(result)


class Menu:
    """交互式菜单"""

    @staticmethod
    def select(title: str, options: List[str], multi: bool = False) -> Optional[List[int]]:
        """显示选择菜单"""
        print(f"\n{Colors.BOLD}{title}{Colors.RESET}")
        print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}")

        for i, option in enumerate(options, 1):
            print(f"  {Colors.CYAN}{i}{Colors.RESET}. {option}")

        if multi:
            print(f"\n{Colors.DIM}输入序号（多个用逗号分隔，回车确认）:{Colors.RESET}")
        else:
            print(f"\n{Colors.DIM}输入序号:{Colors.RESET}")

        try:
            choice = input(f"{Colors.GREEN}>{Colors.RESET} ").strip()
            if not choice:
                return None

            if multi:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                return [i for i in indices if 0 <= i < len(options)]
            else:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return [idx]
                return None
        except (ValueError, EOFError):
            return None


class Table:
    """表格组件"""

    @staticmethod
    def render(headers: List[str], rows: List[List[str]], max_width: int = 80) -> str:
        """渲染表格"""
        if not rows:
            return "无数据"

        # 计算列宽
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # 限制总宽度
        total = sum(col_widths) + 3 * len(col_widths)
        if total > max_width:
            ratio = max_width / total
            col_widths = [int(w * ratio) for w in col_widths]

        # 渲染表头
        result = []
        header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
        result.append(f"{Colors.BOLD}{header_line}{Colors.RESET}")
        result.append(f"{Colors.DIM}{'─' * len(header_line)}{Colors.RESET}")

        # 渲染数据行
        for row in rows:
            cells = []
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    cells.append(str(cell).ljust(col_widths[i]))
            result.append(" | ".join(cells))

        return '\n'.join(result)


# ==================== 主CLI类 ====================

class FrokCLI:
    """
    Frok CLI终端界面

    功能:
    - 彩色输出
    - 状态栏
    - 进度显示
    - 语法高亮
    - 交互式菜单
    """

    def __init__(self):
        self.terminal_width = shutil.get_terminal_size().columns
        self.spinner = Spinner()
        self.history: List[str] = []

    # ==================== 输出方法 ====================

    def print(self, text: str, color: str = "", end: str = "\n"):
        """打印文本"""
        if color:
            print(f"{color}{text}{Colors.RESET}", end=end)
        else:
            print(text, end=end)

    def print_user(self, text: str):
        """打印用户输入"""
        print(f"{Colors.GREEN}{Colors.BOLD}你:{Colors.RESET} {text}")

    def print_assistant(self, text: str):
        """打印助手回复"""
        print(f"{Colors.BLUE}{Colors.BOLD}Frok:{Colors.RESET} {text}")

    def print_system(self, text: str):
        """打印系统消息"""
        print(f"{Colors.DIM}[系统] {text}{Colors.RESET}")

    def print_tool(self, name: str, params: str = ""):
        """打印工具调用"""
        print(f"{Colors.YELLOW}⚡ 调用工具:{Colors.RESET} {Colors.BOLD}{name}{Colors.RESET}")
        if params:
            print(f"{Colors.DIM}  参数: {params}{Colors.RESET}")

    def print_result(self, text: str, success: bool = True):
        """打印结果"""
        if success:
            print(f"{Colors.GREEN}✓{Colors.RESET} {text}")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} {text}")

    def print_error(self, text: str):
        """打印错误"""
        print(f"{Colors.RED}{Colors.BOLD}错误:{Colors.RESET} {text}")

    def print_warning(self, text: str):
        """打印警告"""
        print(f"{Colors.YELLOW}⚠{Colors.RESET} {text}")

    def print_info(self, text: str):
        """打印信息"""
        print(f"{Colors.CYAN}ℹ{Colors.RESET} {text}")

    def print_debug(self, text: str):
        """打印调试信息"""
        print(f"{Colors.DIM}[调试] {text}{Colors.RESET}")

    # ==================== UI组件 ====================

    def show_banner(self):
        """显示启动横幅"""
        banner = f"""
{Colors.CYAN}{Colors.BOLD}╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ███████╗██████╗  ██████╗ ██╗  ██╗                        ║
║     ██╔════╝██╔══██╗██╔═══██╗██║ ██╔╝                        ║
║     █████╗  ██████╔╝██║   ██║█████╔╝                         ║
║     ██╔══╝  ██╔══██╗██║   ██║██╔═██╗                         ║
║     ██║     ██║  ██║╚██████╔╝██║  ██╗                        ║
║     ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝                        ║
║                                                               ║
║          {Colors.WHITE}智能编程助手 v2.0{Colors.CYAN}                                   ║
║          {Colors.DIM}Powered by AI{Colors.CYAN}                                       ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝{Colors.RESET}"""
        print(banner)

    def show_status_bar(self, model: str, provider: str, messages: int = 0):
        """显示状态栏"""
        status = StatusLine()
        status.add("模型", f"{provider}/{model}")
        status.add("消息", str(messages))
        status.add("时间", datetime.now().strftime("%H:%M"))
        print(status.render())

    def show_help(self):
        """显示帮助信息"""
        help_text = f"""
{Colors.BOLD}命令列表:{Colors.RESET}

  {Colors.CYAN}基础命令{Colors.RESET}
    /help          显示此帮助
    /status        显示状态
    /clear         清空对话
    /save          保存会话
    /quit          退出程序

  {Colors.CYAN}模型管理{Colors.RESET}
    /switch        切换模型
    /models        列出可用模型

  {Colors.CYAN}功能模块{Colors.RESET}
    /skills        列出技能
    /plan          显示当前计划
    /planmode      切换Plan模式
    /hooks         列出Hook
    /agents        列出子代理
    /history       编辑历史

  {Colors.CYAN}代码工具{Colors.RESET}
    /diff          查看差异
    /blame         代码追溯
    /map           代码地图
    /sandbox       沙箱执行

  {Colors.CYAN}快捷操作{Colors.RESET}
    Tab            命令补全
    Ctrl+C         中断执行
    Ctrl+L         清屏
"""
        print(help_text)

    def show_progress(self, current: int, total: int, label: str = ""):
        """显示进度条"""
        progress = ProgressBar(total)
        progress.update(current, label)
        print(f"\r{progress.render()}", end="", flush=True)

    def show_spinner(self, message: str = "处理中..."):
        """显示加载动画"""
        return self.spinner.next(message)

    def show_box(self, content: str, title: str = ""):
        """显示盒子"""
        print(Box.render(content, title, self.terminal_width - 4))

    def show_table(self, headers: List[str], rows: List[List[str]]):
        """显示表格"""
        print(Table.render(headers, rows, self.terminal_width - 4))

    def show_menu(self, title: str, options: List[str]) -> Optional[int]:
        """显示菜单并返回选择"""
        result = Menu.select(title, options)
        if result and len(result) > 0:
            return result[0]
        return None

    # ==================== 输入方法 ====================

    def input(self, prompt: str = "") -> str:
        """获取用户输入"""
        try:
            if not prompt:
                prompt = f"{Colors.GREEN}{Colors.BOLD}>{Colors.RESET} "
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return "/quit"

    def confirm(self, message: str, default: bool = True) -> bool:
        """确认对话框"""
        suffix = " [Y/n]" if default else " [y/N]"
        try:
            response = input(f"{Colors.YELLOW}?{Colors.RESET} {message}{suffix} ").strip().lower()
            if not response:
                return default
            return response in ('y', 'yes', '是')
        except (EOFError, KeyboardInterrupt):
            return False

    # ==================== 格式化方法 ====================

    def format_code(self, code: str, language: str = "") -> str:
        """格式化代码（简单语法高亮）"""
        lines = code.split('\n')
        result = []

        for line in lines:
            # 简单的关键字高亮
            highlighted = line

            # Python关键字
            keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while',
                       'try', 'except', 'finally', 'with', 'import', 'from',
                       'return', 'yield', 'pass', 'break', 'continue', 'True',
                       'False', 'None', 'and', 'or', 'not', 'in', 'is']

            for kw in keywords:
                highlighted = highlighted.replace(f' {kw} ', f' {Colors.MAGENTA}{kw}{Colors.RESET} ')
                if highlighted.startswith(f'{kw} '):
                    highlighted = f'{Colors.MAGENTA}{kw}{Colors.RESET}' + highlighted[len(kw):]

            # 字符串高亮
            if "'" in highlighted or '"' in highlighted:
                # 简单处理
                pass

            result.append(highlighted)

        return '\n'.join(result)

    def format_diff(self, diff_text: str) -> str:
        """格式化diff输出"""
        lines = diff_text.split('\n')
        result = []

        for line in lines:
            if line.startswith('+'):
                result.append(f"{Colors.GREEN}{line}{Colors.RESET}")
            elif line.startswith('-'):
                result.append(f"{Colors.RED}{line}{Colors.RESET}")
            elif line.startswith('@@'):
                result.append(f"{Colors.CYAN}{line}{Colors.RESET}")
            else:
                result.append(line)

        return '\n'.join(result)

    def format_file_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size // 1024}KB"
        else:
            return f"{size // (1024 * 1024)}MB"

    # ==================== 清理方法 ====================

    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def clear_line(self):
        """清除当前行"""
        print(f"\r{' ' * self.terminal_width}\r", end="", flush=True)


# ==================== 全局实例 ====================

cli = FrokCLI()
