"""
Frok 嵌入式编程模块
提供 Arduino/ESP32/STM32 的代码生成、编译、烧录、串口监视功能
"""

import os
import subprocess
import threading
import time
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


# ==================== 数据结构 ====================

@dataclass
class DeviceInfo:
    """设备信息"""
    port: str
    description: str
    platform: str = ""
    board: str = ""
    vid: int = 0
    pid: int = 0
    manufacturer: str = ""

    def to_dict(self) -> Dict:
        return {
            "port": self.port,
            "description": self.description,
            "platform": self.platform,
            "board": self.board,
            "vid": f"0x{self.vid:04X}" if self.vid else "",
            "pid": f"0x{self.pid:04X}" if self.pid else "",
            "manufacturer": self.manufacturer,
        }


@dataclass
class CompileResult:
    """编译结果"""
    success: bool
    output: str = ""
    errors: List[str] = None
    firmware_path: str = ""

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "output": self.output,
            "errors": self.errors,
            "firmware_path": self.firmware_path,
        }


@dataclass
class UploadResult:
    """烧录结果"""
    success: bool
    output: str = ""

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "output": self.output,
        }


# ==================== 平台基类 ====================

class EmbeddedPlatform(ABC):
    """嵌入式平台基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """平台名称：arduino/esp32/stm32"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称"""
        ...

    @property
    @abstractmethod
    def toolchain_cmd(self) -> str:
        """工具链主命令"""
        ...

    @abstractmethod
    def detect(self) -> bool:
        """检测工具链是否安装"""
        ...

    @abstractmethod
    def generate_code(self, spec: Dict) -> str:
        """
        生成嵌入式代码

        Args:
            spec: {"board": str, "description": str, "language": str}

        Returns:
            生成的代码字符串
        """
        ...

    @abstractmethod
    def compile(self, sketch_path: str, board: str = None) -> CompileResult:
        """编译固件"""
        ...

    @abstractmethod
    def upload(self, sketch_path: str, port: str = None, board: str = None) -> UploadResult:
        """烧录固件"""
        ...

    @abstractmethod
    def list_boards(self) -> List[Dict]:
        """列出可用开发板"""
        ...

    def list_ports(self) -> List[DeviceInfo]:
        """列出串口设备（通用实现）"""
        try:
            import serial.tools.list_ports
            ports = []
            for port in serial.tools.list_ports.comports():
                device = DeviceInfo(
                    port=port.device,
                    description=port.description,
                    vid=port.vid or 0,
                    pid=port.pid or 0,
                    manufacturer=port.manufacturer or "",
                )
                device.platform = self._infer_platform(device)
                device.board = self._infer_board(device)
                ports.append(device)
            return ports
        except ImportError:
            return []

    def _infer_platform(self, device: DeviceInfo) -> str:
        """通过 VID/PID 推断平台"""
        vid = device.vid
        pid = device.pid

        # Arduino 官方板
        if vid == 0x2341:
            return "arduino"

        # CH340 串口
        if vid == 0x1A86 and pid == 0x7523:
            return "arduino"  # 兼容板

        # CP2102 (ESP32 常见)
        if vid == 0x10C4 and pid == 0xEA60:
            return "esp32"

        # FTDI
        if vid == 0x0403:
            return "arduino"

        return ""

    def _infer_board(self, device: DeviceInfo) -> str:
        """推断开发板型号"""
        # 默认返回，子类可覆盖
        return ""

    def _run_command(self, args: List[str], cwd: str = None, timeout: int = 120) -> tuple:
        """
        执行命令

        Returns:
            (returncode, stdout, stderr)
        """
        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "命令超时"
        except FileNotFoundError:
            return -1, "", f"命令未找到: {args[0]}"
        except Exception as e:
            return -1, "", str(e)


# ==================== 串口监视器 ====================

class SerialMonitor:
    """串口监视器"""

    def __init__(self):
        self._running = False
        self._thread = None
        self._serial = None

    def start(self, port: str, baud: int = 115200, callback=None):
        """开始监视"""
        try:
            import serial
            self._serial = serial.Serial(port, baud, timeout=1)
            self._running = True
            self._thread = threading.Thread(target=self._read_loop, args=(callback,), daemon=True)
            self._thread.start()
            return True, f"已打开串口 {port} @ {baud}"
        except Exception as e:
            return False, f"打开串口失败: {e}"

    def stop(self):
        """停止监视"""
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        return "串口监视已停止"

    def _read_loop(self, callback=None):
        """读取循环"""
        while self._running:
            try:
                if self._serial and self._serial.in_waiting:
                    data = self._serial.readline().decode('utf-8', errors='replace').strip()
                    if data:
                        if callback:
                            callback(data)
                        else:
                            print(f"[串口] {data}")
                else:
                    time.sleep(0.05)
            except Exception:
                if self._running:
                    time.sleep(0.1)


# 全局监视器实例
_monitor = SerialMonitor()


# ==================== 自动检测 ====================

def auto_detect_devices() -> List[DeviceInfo]:
    """自动检测所有连接的嵌入式设备"""
    try:
        import serial.tools.list_ports
        devices = []
        for port in serial.tools.list_ports.comports():
            device = DeviceInfo(
                port=port.device,
                description=port.description,
                vid=port.vid or 0,
                pid=port.pid or 0,
                manufacturer=port.manufacturer or "",
            )
            # 推断平台
            device.platform = _infer_device_platform(device)
            device.board = _infer_device_board(device)
            devices.append(device)
        return devices
    except ImportError:
        return []


def _infer_device_platform(device: DeviceInfo) -> str:
    """推断设备平台"""
    vid = device.vid
    pid = device.pid

    if vid == 0x2341:
        return "arduino"
    if vid == 0x1A86 and pid == 0x7523:
        return "arduino"
    if vid == 0x10C4 and pid == 0xEA60:
        return "esp32"
    if vid == 0x0403:
        return "arduino"
    if vid == 0x0483:
        return "stm32"

    return ""


def _infer_device_board(device: DeviceInfo) -> str:
    """推断开发板型号"""
    vid = device.vid
    pid = device.pid

    # Arduino Uno
    if vid == 0x2341 and pid in (0x0043, 0x0001):
        return "uno"

    # Arduino Mega
    if vid == 0x2341 and pid in (0x0042, 0x0010):
        return "mega2560"

    # Arduino Nano
    if vid == 0x2341 and pid == 0x0044:
        return "nano"

    return ""


def smart_select_device(devices: List[DeviceInfo], platform_hint: str = "") -> Optional[DeviceInfo]:
    """
    智能选择设备

    Args:
        devices: 检测到的设备列表
        platform_hint: 用户指定的平台提示

    Returns:
        选中的设备，或 None（需要用户确认）
    """
    if not devices:
        return None

    # 只有一个设备，直接选
    if len(devices) == 1:
        return devices[0]

    # 用户指定了平台，过滤匹配的
    if platform_hint:
        matched = [d for d in devices if d.platform == platform_hint]
        if len(matched) == 1:
            return matched[0]
        if matched:
            return matched[0]  # 多个匹配，选第一个

    # 无法确定
    return None


# ==================== 工具定义 ====================

EMBEDDED_TOOLS = [
    {
        "name": "embedded_detect",
        "description": "检测嵌入式工具链安装状态和连接的设备",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "平台名称：arduino/esp32/stm32，留空检测所有"
                }
            }
        }
    },
    {
        "name": "embedded_generate",
        "description": "生成嵌入式代码",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "目标平台：arduino/esp32/stm32"
                },
                "board": {
                    "type": "string",
                    "description": "开发板型号，如 esp32dev、uno、nucleo_f401re"
                },
                "description": {
                    "type": "string",
                    "description": "功能描述，自然语言"
                },
                "language": {
                    "type": "string",
                    "description": "编程语言：c/cpp/micropython"
                }
            },
            "required": ["platform", "description"]
        }
    },
    {
        "name": "embedded_compile",
        "description": "编译嵌入式固件",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "目标平台"
                },
                "sketch_path": {
                    "type": "string",
                    "description": "代码文件或项目目录路径"
                },
                "board": {
                    "type": "string",
                    "description": "开发板型号"
                }
            },
            "required": ["platform", "sketch_path"]
        }
    },
    {
        "name": "embedded_upload",
        "description": "烧录固件到开发板",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "目标平台"
                },
                "sketch_path": {
                    "type": "string",
                    "description": "代码文件或项目目录路径"
                },
                "port": {
                    "type": "string",
                    "description": "串口设备，留空自动检测"
                },
                "board": {
                    "type": "string",
                    "description": "开发板型号"
                }
            },
            "required": ["platform", "sketch_path"]
        }
    },
    {
        "name": "embedded_monitor",
        "description": "打开串口监视器",
        "parameters": {
            "type": "object",
            "properties": {
                "port": {
                    "type": "string",
                    "description": "串口设备"
                },
                "baud": {
                    "type": "integer",
                    "description": "波特率，默认 115200"
                },
                "duration": {
                    "type": "integer",
                    "description": "监视时长（秒），留空持续监视"
                }
            }
        }
    },
    {
        "name": "embedded_list_boards",
        "description": "列出可用的开发板",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "目标平台"
                }
            },
            "required": ["platform"]
        }
    },
    {
        "name": "embedded_list_ports",
        "description": "列出连接的串口设备",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "目标平台，留空检测所有"
                }
            }
        }
    },
    {
        "name": "embedded_stop_monitor",
        "description": "停止串口监视器",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
]


# ==================== 工具执行器 ====================

class EmbeddedToolExecutor:
    """嵌入式工具执行器"""

    def __init__(self):
        self._platforms = {}
        self._load_platforms()

    def _load_platforms(self):
        """加载平台"""
        from platforms import get_all_platforms
        self._platforms = get_all_platforms()

    def _get_platform(self, name: str) -> Optional[EmbeddedPlatform]:
        """获取平台实例"""
        return self._platforms.get(name)

    def execute(self, tool_name: str, params: Dict) -> str:
        """执行工具调用"""
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler:
            return handler(params)
        return f"[错误] 未知工具: {tool_name}"

    def _handle_embedded_detect(self, params: Dict) -> str:
        """检测工具链"""
        platform_name = params.get("platform", "")

        if platform_name:
            platform = self._get_platform(platform_name)
            if not platform:
                return f"[错误] 未知平台: {platform_name}"

            installed = platform.detect()
            devices = platform.list_ports()

            lines = [f"## {platform.display_name} 状态"]
            lines.append(f"工具链: {'✓ 已安装' if installed else '✗ 未安装'}")
            lines.append(f"命令: {platform.toolchain_cmd}")

            if devices:
                lines.append(f"\n检测到 {len(devices)} 个设备:")
                for d in devices:
                    lines.append(f"  - {d.port}: {d.description} [{d.platform or '未知'}]")
            else:
                lines.append("\n未检测到设备")

            return "\n".join(lines)

        # 检测所有平台
        lines = ["## 嵌入式环境检测\n"]

        for name, platform in self._platforms.items():
            installed = platform.detect()
            status = "✓" if installed else "✗"
            lines.append(f"- {status} {platform.display_name} ({platform.toolchain_cmd})")

        # 检测设备
        devices = auto_detect_devices()
        if devices:
            lines.append(f"\n检测到 {len(devices)} 个设备:")
            for d in devices:
                lines.append(f"  - {d.port}: {d.description} [{d.platform or '未知'}]")
        else:
            lines.append("\n未检测到设备")

        return "\n".join(lines)

    def _handle_embedded_generate(self, params: Dict) -> str:
        """生成代码"""
        platform_name = params["platform"]
        platform = self._get_platform(platform_name)
        if not platform:
            return f"[错误] 未知平台: {platform_name}"

        if not platform.detect():
            return f"[错误] {platform.display_name} 工具链未安装，请先安装 {platform.toolchain_cmd}"

        code = platform.generate_code(params)
        return f"[已生成代码]\n\n```cpp\n{code}\n```\n\n请使用 embedded_compile 编译，或 embedded_upload 直接烧录。"

    def _handle_embedded_compile(self, params: Dict) -> str:
        """编译"""
        platform_name = params["platform"]
        platform = self._get_platform(platform_name)
        if not platform:
            return f"[错误] 未知平台: {platform_name}"

        if not platform.detect():
            return f"[错误] {platform.display_name} 工具链未安装"

        result = platform.compile(
            sketch_path=params["sketch_path"],
            board=params.get("board")
        )

        if result.success:
            return f"[编译成功]\n{result.output}"
        else:
            error_str = "\n".join(result.errors) if result.errors else result.output
            return f"[编译失败]\n{error_str}"

    def _handle_embedded_upload(self, params: Dict) -> str:
        """烧录"""
        platform_name = params["platform"]
        platform = self._get_platform(platform_name)
        if not platform:
            return f"[错误] 未知平台: {platform_name}"

        if not platform.detect():
            return f"[错误] {platform.display_name} 工具链未安装"

        port = params.get("port")
        if not port:
            # 自动检测设备
            devices = platform.list_ports()
            if not devices:
                return "[错误] 未检测到设备，请连接开发板后重试"
            if len(devices) == 1:
                port = devices[0].port
            else:
                # 尝试智能选择
                selected = smart_select_device(devices, platform_name)
                if selected:
                    port = selected.port
                else:
                    device_list = "\n".join([f"  - {d.port}: {d.description}" for d in devices])
                    return f"[错误] 检测到多个设备，请指定端口:\n{device_list}"

        result = platform.upload(
            sketch_path=params["sketch_path"],
            port=port,
            board=params.get("board")
        )

        if result.success:
            return f"[烧录成功] {port}\n{result.output}"
        else:
            return f"[烧录失败]\n{result.output}"

    def _handle_embedded_monitor(self, params: Dict) -> str:
        """串口监视"""
        port = params.get("port")
        baud = params.get("baud", 115200)

        if not port:
            # 自动检测
            devices = auto_detect_devices()
            if not devices:
                return "[错误] 未检测到设备"
            if len(devices) == 1:
                port = devices[0].port
            else:
                device_list = "\n".join([f"  - {d.port}: {d.description}" for d in devices])
                return f"[错误] 检测到多个设备，请指定端口:\n{device_list}"

        success, msg = _monitor.start(port, baud)
        if success:
            return f"[串口监视已启动] {port} @ {baud}\n输出将实时显示。使用 embedded_stop_monitor 停止。"
        else:
            return f"[错误] {msg}"

    def _handle_embedded_list_boards(self, params: Dict) -> str:
        """列出开发板"""
        platform_name = params["platform"]
        platform = self._get_platform(platform_name)
        if not platform:
            return f"[错误] 未知平台: {platform_name}"

        boards = platform.list_boards()
        if not boards:
            return f"[{platform.display_name}] 未找到可用开发板，请检查工具链安装"

        lines = [f"## {platform.display_name} 可用开发板\n"]
        for b in boards:
            lines.append(f"- {b.get('fqbn', b.get('name', ''))}: {b.get('description', '')}")

        return "\n".join(lines)

    def _handle_embedded_list_ports(self, params: Dict) -> str:
        """列出串口"""
        devices = auto_detect_devices()
        if not devices:
            return "未检测到串口设备"

        lines = ["## 检测到的串口设备\n"]
        for d in devices:
            platform_str = f" [{d.platform}]" if d.platform else ""
            lines.append(f"- {d.port}: {d.description}{platform_str}")

        return "\n".join(lines)

    def _handle_embedded_stop_monitor(self, params: Dict) -> str:
        """停止串口监视"""
        return _monitor.stop()


# 全局执行器实例
_executor = None


def get_executor() -> EmbeddedToolExecutor:
    """获取工具执行器单例"""
    global _executor
    if _executor is None:
        _executor = EmbeddedToolExecutor()
    return _executor
