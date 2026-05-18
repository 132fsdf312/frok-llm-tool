# 嵌入式编程能力实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Frok Code 添加 Arduino/ESP32/STM32 嵌入式编程能力，支持代码生成、编译、烧录和串口监视。

**Architecture:** 采用基类 + 平台适配器模式。`embedded.py` 定义 `EmbeddedPlatform` 基类和自动检测逻辑，`platforms/` 目录下三个平台各自实现。工具通过 `EMBEDDED_TOOLS` 列表注册到 agent。

**Tech Stack:** Python 3, pyserial, arduino-cli, esp-idf, arm-none-eabi-gcc

---

## 文件结构

```
frok/
├── embedded.py              # 基类 + 工具注册 + 自动检测 (新建)
├── platforms/
│   ├── __init__.py          # 平台自动发现 (新建)
│   ├── arduino.py           # ArduinoPlatform (新建)
│   ├── esp32.py             # ESP32Platform (新建)
│   └── stm32.py             # STM32Platform (新建)
├── skills/
│   └── embedded.json        # 嵌入式编程技能 (新建)
├── tools.py                 # 添加 EMBEDDED_TOOLS 导入 (修改)
├── agent.py                 # 导入 embedded 模块 (修改)
└── ../requirements.txt      # 添加 pyserial (修改)
```

---

### Task 1: 创建 platforms 包和基类

**Files:**
- Create: `frok/platforms/__init__.py`
- Create: `frok/embedded.py`

- [ ] **Step 1: 创建 platforms/__init__.py**

```python
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


# 延迟导入基类（避免循环导入）
def _get_base_class():
    from embedded import EmbeddedPlatform
    return EmbeddedPlatform


# 包加载时自动发现
auto_discover()
```

- [ ] **Step 2: 创建 embedded.py 基类**

```python
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
```

- [ ] **Step 3: 验证语法**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -m py_compile frok/embedded.py && python3 -m py_compile frok/platforms/__init__.py`
Expected: 无输出（语法正确）

---

### Task 2: 创建 Arduino 平台适配器

**Files:**
- Create: `frok/platforms/arduino.py`

- [ ] **Step 1: 创建 arduino.py**

```python
"""
Arduino 平台适配器
支持 arduino-cli 工具链
"""

import os
import json
from pathlib import Path
from typing import Dict, List

# 延迟导入避免循环
def _get_base():
    from embedded import EmbeddedPlatform, CompileResult, UploadResult
    return EmbeddedPlatform, CompileResult, UploadResult


# Arduino 代码模板
TEMPLATES = {
    "blink": '''\
// {description}
// Arduino {board}

const int LED_PIN = LED_BUILTIN;

void setup() {{
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    Serial.println("LED Blink Started");
}}

void loop() {{
    digitalWrite(LED_PIN, HIGH);
    Serial.println("LED ON");
    delay(1000);
    digitalWrite(LED_PIN, LOW);
    Serial.println("LED OFF");
    delay(1000);
}}
''',

    "sensor": '''\
// {description}
// Arduino {board}

void setup() {{
    Serial.begin(115200);
    // 初始化传感器引脚
}}

void loop() {{
    // 读取传感器数据
    // int value = analogRead(A0);
    // Serial.print("Sensor: ");
    // Serial.println(value);
    delay(100);
}}
''',

    "default": '''\
// {description}
// Arduino {board}

void setup() {{
    Serial.begin(115200);
    Serial.println("Setup complete");
}}

void loop() {{
    // 主循环
    delay(1000);
}}
''',
}


def _detect_template(description: str) -> str:
    """根据描述选择模板"""
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ["led", "灯", "闪烁", "blink"]):
        return "blink"
    if any(kw in desc_lower for kw in ["sensor", "传感器", "温度", "湿度", "光照"]):
        return "sensor"
    return "default"


class ArduinoPlatform:
    """Arduino 平台"""

    @property
    def name(self) -> str:
        return "arduino"

    @property
    def display_name(self) -> str:
        return "Arduino"

    @property
    def toolchain_cmd(self) -> str:
        return "arduino-cli"

    def detect(self) -> bool:
        """检测 arduino-cli 是否安装"""
        from embedded import EmbeddedPlatform
        base = EmbeddedPlatform
        returncode, stdout, stderr = base._run_command(self, ["arduino-cli", "version"])
        return returncode == 0

    def generate_code(self, spec: Dict) -> str:
        """生成 Arduino 代码"""
        description = spec.get("description", "")
        board = spec.get("board", "uno")
        language = spec.get("language", "cpp")

        template_name = _detect_template(description)
        template = TEMPLATES[template_name]

        code = template.format(
            description=description,
            board=board,
        )

        return code

    def compile(self, sketch_path: str, board: str = None) -> 'CompileResult':
        """编译 Arduino 代码"""
        from embedded import CompileResult

        board = board or "arduino:avr:uno"
        sketch_path = Path(sketch_path)

        # 如果是单个文件，创建临时目录
        if sketch_path.is_file():
            sketch_dir = sketch_path.parent
            sketch_file = sketch_path
        else:
            sketch_dir = sketch_path
            # 查找 .ino 文件
            ino_files = list(sketch_dir.glob("*.ino"))
            if not ino_files:
                return CompileResult(success=False, errors=["未找到 .ino 文件"])
            sketch_file = ino_files[0]

        # 确保目录名和文件名一致（Arduino 要求）
        expected_name = sketch_dir.name + ".ino"
        if sketch_file.name != expected_name:
            new_path = sketch_dir / expected_name
            if not new_path.exists():
                sketch_file.rename(new_path)
            sketch_file = new_path

        # 执行编译
        args = ["arduino-cli", "compile", "--fqbn", board, str(sketch_dir)]
        returncode, stdout, stderr = self._run_command(args)

        if returncode == 0:
            return CompileResult(
                success=True,
                output=stdout,
                firmware_path=str(sketch_dir)
            )
        else:
            errors = self._parse_errors(stderr)
            return CompileResult(
                success=False,
                output=stderr,
                errors=errors
            )

    def upload(self, sketch_path: str, port: str = None, board: str = None) -> 'UploadResult':
        """烧录到 Arduino"""
        from embedded import UploadResult

        board = board or "arduino:avr:uno"
        port = port or self._auto_detect_port()

        if not port:
            return UploadResult(success=False, output="未检测到串口设备")

        sketch_path = Path(sketch_path)
        if sketch_path.is_file():
            sketch_dir = sketch_path.parent
        else:
            sketch_dir = sketch_path

        # 先编译
        compile_result = self.compile(str(sketch_dir), board)
        if not compile_result.success:
            return UploadResult(success=False, output=f"编译失败:\n{compile_result.output}")

        # 烧录
        args = ["arduino-cli", "upload", "-p", port, "--fqbn", board, str(sketch_dir)]
        returncode, stdout, stderr = self._run_command(args)

        if returncode == 0:
            return UploadResult(success=True, output=f"已烧录到 {port}")
        else:
            return UploadResult(success=False, output=stderr)

    def list_boards(self) -> List[Dict]:
        """列出可用开发板"""
        args = ["arduino-cli", "board", "listall"]
        returncode, stdout, stderr = self._run_command(args)

        if returncode != 0:
            return []

        boards = []
        for line in stdout.strip().split("\n"):
            if ":" in line:
                parts = line.split()
                if parts:
                    fqbn = parts[0]
                    name = " ".join(parts[1:]) if len(parts) > 1 else fqbn
                    boards.append({"fqbn": fqbn, "description": name})

        return boards

    def _auto_detect_port(self) -> str:
        """自动检测串口"""
        from embedded import auto_detect_devices
        devices = auto_detect_devices()
        for d in devices:
            if d.platform == "arduino":
                return d.port
        if devices:
            return devices[0].port
        return ""

    def _parse_errors(self, output: str) -> List[str]:
        """解析编译错误"""
        errors = []
        for line in output.split("\n"):
            if "error:" in line.lower() or "错误" in line:
                errors.append(line.strip())
        return errors if errors else [output]

    def _run_command(self, args, cwd=None, timeout=120):
        """执行命令"""
        from embedded import EmbeddedPlatform
        return EmbeddedPlatform._run_command(self, args, cwd, timeout)


# 注册平台
from platforms import register_platform
register_platform(ArduinoPlatform)
```

- [ ] **Step 2: 验证语法**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -m py_compile frok/platforms/arduino.py`
Expected: 无输出

---

### Task 3: 创建 ESP32 平台适配器

**Files:**
- Create: `frok/platforms/esp32.py`

- [ ] **Step 1: 创建 esp32.py**

```python
"""
ESP32 平台适配器
支持 ESP-IDF 和 Arduino 框架
"""

import os
from pathlib import Path
from typing import Dict, List


# ESP32 代码模板
TEMPLATES = {
    "wifi": '''\
// {description}
// ESP32 ({board})

#include <WiFi.h>

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

void setup() {{
    Serial.begin(115200);
    delay(1000);

    Serial.println("Connecting to WiFi...");
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {{
        delay(500);
        Serial.print(".");
    }}

    Serial.println("");
    Serial.println("WiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
}}

void loop() {{
    // 主循环
    delay(1000);
}}
''',

    "mqtt": '''\
// {description}
// ESP32 ({board})

#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {{
    Serial.begin(115200);
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {{
        delay(500);
    }}

    client.setServer(mqtt_server, 1883);
    Serial.println("Ready");
}}

void loop() {{
    if (!client.connected()) {{
        reconnect();
    }}
    client.loop();
    delay(100);
}}

void reconnect() {{
    while (!client.connected()) {{
        if (client.connect("esp32client")) {{
            Serial.println("MQTT connected");
        }} else {{
            delay(5000);
        }}
    }}
}}
''',

    "sensor": '''\
// {description}
// ESP32 ({board})

void setup() {{
    Serial.begin(115200);
    delay(1000);
    Serial.println("ESP32 Sensor Ready");
}}

void loop() {{
    // 读取传感器
    // float value = analogRead(34) * 3.3 / 4095;
    // Serial.printf("Value: %.2f\\n", value);
    delay(1000);
}}
''',

    "default": '''\
// {description}
// ESP32 ({board})

void setup() {{
    Serial.begin(115200);
    delay(1000);
    Serial.println("ESP32 Ready");
}}

void loop() {{
    // 主循环
    delay(1000);
}}
''',
}


def _detect_template(description: str) -> str:
    """根据描述选择模板"""
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ["mqtt", "消息队列"]):
        return "mqtt"
    if any(kw in desc_lower for kw in ["wifi", "wi-fi", "无线", "网络"]):
        return "wifi"
    if any(kw in desc_lower for kw in ["sensor", "传感器", "dht", "温度", "湿度"]):
        return "sensor"
    return "default"


class ESP32Platform:
    """ESP32 平台"""

    @property
    def name(self) -> str:
        return "esp32"

    @property
    def display_name(self) -> str:
        return "ESP32"

    @property
    def toolchain_cmd(self) -> str:
        return "idf.py"  # 或 arduino-cli

    def detect(self) -> bool:
        """检测工具链"""
        # 先检测 ESP-IDF
        returncode, _, _ = self._run_command(["idf.py", "--version"])
        if returncode == 0:
            return True

        # 再检测 arduino-cli + ESP32 core
        returncode, stdout, _ = self._run_command(["arduino-cli", "core", "list"])
        if returncode == 0 and "esp32" in stdout:
            return True

        return False

    def generate_code(self, spec: Dict) -> str:
        """生成 ESP32 代码"""
        description = spec.get("description", "")
        board = spec.get("board", "esp32dev")

        template_name = _detect_template(description)
        template = TEMPLATES[template_name]

        return template.format(
            description=description,
            board=board,
        )

    def compile(self, sketch_path: str, board: str = None) -> 'CompileResult':
        """编译 ESP32 代码"""
        from embedded import CompileResult

        sketch_path = Path(sketch_path)

        # 检测使用哪个工具链
        if self._use_idf():
            return self._compile_idf(sketch_path)
        else:
            return self._compile_arduino(sketch_path, board or "esp32:esp32:esp32dev")

    def _use_idf(self) -> bool:
        """是否使用 ESP-IDF"""
        returncode, _, _ = self._run_command(["idf.py", "--version"])
        return returncode == 0

    def _compile_idf(self, sketch_path: Path) -> 'CompileResult':
        """使用 ESP-IDF 编译"""
        from embedded import CompileResult

        # 如果是单个文件，需要创建 CMakeLists.txt
        if sketch_path.is_file():
            project_dir = sketch_path.parent
        else:
            project_dir = sketch_path

        args = ["idf.py", "build"]
        returncode, stdout, stderr = self._run_command(args, cwd=str(project_dir))

        if returncode == 0:
            return CompileResult(success=True, output=stdout)
        else:
            return CompileResult(success=False, output=stderr, errors=[stderr])

    def _compile_arduino(self, sketch_path: Path, board: str) -> 'CompileResult':
        """使用 arduino-cli 编译"""
        from embedded import CompileResult

        if sketch_path.is_file():
            sketch_dir = sketch_path.parent
        else:
            sketch_dir = sketch_path

        args = ["arduino-cli", "compile", "--fqbn", board, str(sketch_dir)]
        returncode, stdout, stderr = self._run_command(args)

        if returncode == 0:
            return CompileResult(success=True, output=stdout)
        else:
            return CompileResult(success=False, output=stderr, errors=[stderr])

    def upload(self, sketch_path: str, port: str = None, board: str = None) -> 'UploadResult':
        """烧录 ESP32"""
        from embedded import UploadResult

        port = port or self._auto_detect_port()
        if not port:
            return UploadResult(success=False, output="未检测到设备")

        sketch_path = Path(sketch_path)

        if self._use_idf():
            return self._upload_idf(sketch_path, port)
        else:
            return self._upload_arduino(sketch_path, port, board or "esp32:esp32:esp32dev")

    def _upload_idf(self, sketch_path: Path, port: str) -> 'UploadResult':
        """使用 ESP-IDF 烧录"""
        from embedded import UploadResult

        if sketch_path.is_file():
            project_dir = sketch_path.parent
        else:
            project_dir = sketch_path

        args = ["idf.py", "-p", port, "flash"]
        returncode, stdout, stderr = self._run_command(args, cwd=str(project_dir))

        if returncode == 0:
            return UploadResult(success=True, output=f"已烧录到 {port}")
        else:
            return UploadResult(success=False, output=stderr)

    def _upload_arduino(self, sketch_path: Path, port: str, board: str) -> 'UploadResult':
        """使用 arduino-cli 烧录"""
        from embedded import UploadResult

        if sketch_path.is_file():
            sketch_dir = sketch_path.parent
        else:
            sketch_dir = sketch_path

        # 先编译
        compile_result = self._compile_arduino(sketch_dir, board)
        if not compile_result.success:
            return UploadResult(success=False, output=f"编译失败:\n{compile_result.output}")

        args = ["arduino-cli", "upload", "-p", port, "--fqbn", board, str(sketch_dir)]
        returncode, stdout, stderr = self._run_command(args)

        if returncode == 0:
            return UploadResult(success=True, output=f"已烧录到 {port}")
        else:
            return UploadResult(success=False, output=stderr)

    def list_boards(self) -> List[Dict]:
        """列出可用开发板"""
        # ESP32 常见开发板
        return [
            {"fqbn": "esp32:esp32:esp32dev", "description": "ESP32 Dev Module"},
            {"fqbn": "esp32:esp32:esp32s2", "description": "ESP32-S2"},
            {"fqbn": "esp32:esp32:esp32s3", "description": "ESP32-S3"},
            {"fqbn": "esp32:esp32:esp32c3", "description": "ESP32-C3"},
            {"fqbn": "esp32:esp32:esp32c6", "description": "ESP32-C6"},
            {"fqbn": "esp32:esp32:nodemcu-32s", "description": "NodeMCU-32S"},
        ]

    def _auto_detect_port(self) -> str:
        """自动检测串口"""
        from embedded import auto_detect_devices
        devices = auto_detect_devices()
        for d in devices:
            if d.platform == "esp32":
                return d.port
        if devices:
            return devices[0].port
        return ""

    def _run_command(self, args, cwd=None, timeout=120):
        """执行命令"""
        from embedded import EmbeddedPlatform
        return EmbeddedPlatform._run_command(self, args, cwd, timeout)


# 注册平台
from platforms import register_platform
register_platform(ESP32Platform)
```

- [ ] **Step 2: 验证语法**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -m py_compile frok/platforms/esp32.py`
Expected: 无输出

---

### Task 4: 创建 STM32 平台适配器

**Files:**
- Create: `frok/platforms/stm32.py`

- [ ] **Step 1: 创建 stm32.py**

```python
"""
STM32 平台适配器
支持 arm-none-eabi-gcc + st-flash/openocd
"""

import os
from pathlib import Path
from typing import Dict, List


# STM32 代码模板
TEMPLATES = {
    "gpio": '''\
// {description}
// STM32 ({board})

#include "stm32f4xx_hal.h"

// LED 引脚定义
#define LED_PIN GPIO_PIN_13
#define LED_GPIO_PORT GPIOC
#define LED_GPIO_CLK_ENABLE() __HAL_RCC_GPIOC_CLK_ENABLE()

void SystemClock_Config(void);

int main(void) {{
    HAL_Init();
    SystemClock_Config();

    // 配置 LED 引脚
    LED_GPIO_CLK_ENABLE();
    GPIO_InitTypeDef GPIO_InitStruct = {{0}};
    GPIO_InitStruct.Pin = LED_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(LED_GPIO_PORT, &GPIO_InitStruct);

    while (1) {{
        HAL_GPIO_TogglePin(LED_GPIO_PORT, LED_PIN);
        HAL_Delay(500);
    }}
}}

void SystemClock_Config(void) {{
    RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};

    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM = 8;
    RCC_OscInitStruct.PLL.PLLN = 336;
    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ = 7;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                                |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
    HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5);
}}
''',

    "uart": '''\
// {description}
// STM32 ({board})

#include "stm32f4xx_hal.h"

UART_HandleTypeDef huart2;

void SystemClock_Config(void);
void MX_USART2_UART_Init(void);

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART2_UART_Init();

    char *msg = "STM32 Ready\\r\\n";
    HAL_UART_Transmit(&huart2, (uint8_t*)msg, strlen(msg), HAL_MAX_DELAY);

    while (1) {{
        // 主循环
        HAL_Delay(1000);
    }}
}}

void MX_USART2_UART_Init(void) {{
    huart2.Instance = USART2;
    huart2.Init.BaudRate = 115200;
    huart2.Init.WordLength = UART_WORDLENGTH_8B;
    huart2.Init.StopBits = UART_STOPBITS_1;
    huart2.Init.Parity = UART_PARITY_NONE;
    huart2.Init.Mode = UART_MODE_TX_RX;
    huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart2.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart2);
}}

void SystemClock_Config(void) {{
    // 系统时钟配置（根据具体芯片调整）
}}
''',

    "default": '''\
// {description}
// STM32 ({board})

#include "stm32f4xx_hal.h"

void SystemClock_Config(void);

int main(void) {{
    HAL_Init();
    SystemClock_Config();

    while (1) {{
        // 主循环
        HAL_Delay(1000);
    }}
}}

void SystemClock_Config(void) {{
    // 系统时钟配置
}}
''',
}


def _detect_template(description: str) -> str:
    """根据描述选择模板"""
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ["uart", "串口", "serial", "通信"]):
        return "uart"
    if any(kw in desc_lower for kw in ["led", "灯", "gpio", "闪烁"]):
        return "gpio"
    return "default"


class STM32Platform:
    """STM32 平台"""

    @property
    def name(self) -> str:
        return "stm32"

    @property
    def display_name(self) -> str:
        return "STM32"

    @property
    def toolchain_cmd(self) -> str:
        return "arm-none-eabi-gcc"

    def detect(self) -> bool:
        """检测工具链"""
        # 检测编译器
        returncode, _, _ = self._run_command(["arm-none-eabi-gcc", "--version"])
        if returncode != 0:
            return False

        # 检测烧录工具
        returncode1, _, _ = self._run_command(["st-flash", "--version"])
        returncode2, _, _ = self._run_command(["openocd", "--version"])

        return returncode1 == 0 or returncode2 == 0

    def generate_code(self, spec: Dict) -> str:
        """生成 STM32 代码"""
        description = spec.get("description", "")
        board = spec.get("board", "stm32f4")

        template_name = _detect_template(description)
        template = TEMPLATES[template_name]

        return template.format(
            description=description,
            board=board,
        )

    def compile(self, sketch_path: str, board: str = None) -> 'CompileResult':
        """编译 STM32 代码"""
        from embedded import CompileResult

        sketch_path = Path(sketch_path)

        # 如果是单个文件，编译为 .o 文件
        if sketch_path.is_file():
            output = sketch_path.with_suffix(".elf")
            args = [
                "arm-none-eabi-gcc",
                "-mcpu=cortex-m4",
                "-mthumb",
                "-o", str(output),
                str(sketch_path),
            ]
        else:
            # 项目目录，尝试 make
            args = ["make"]
            output = sketch_path / "build" / "firmware.elf"

        returncode, stdout, stderr = self._run_command(args, cwd=str(sketch_path.parent if sketch_path.is_file() else sketch_path))

        if returncode == 0:
            return CompileResult(
                success=True,
                output=stdout,
                firmware_path=str(output)
            )
        else:
            return CompileResult(
                success=False,
                output=stderr,
                errors=[stderr]
            )

    def upload(self, sketch_path: str, port: str = None, board: str = None) -> 'UploadResult':
        """烧录 STM32"""
        from embedded import UploadResult

        sketch_path = Path(sketch_path)

        # 先编译
        compile_result = self.compile(sketch_path)
        if not compile_result.success:
            return UploadResult(success=False, output=f"编译失败:\n{compile_result.output}")

        firmware_path = compile_result.firmware_path
        if not firmware_path:
            return UploadResult(success=False, output="未找到固件文件")

        # 尝试 st-flash
        returncode, stdout, stderr = self._run_command([
            "st-flash", "write", firmware_path, "0x08000000"
        ])

        if returncode == 0:
            return UploadResult(success=True, output="已通过 st-flash 烧录")

        # 尝试 openocd
        returncode, stdout, stderr = self._run_command([
            "openocd",
            "-f", "interface/stlink.cfg",
            "-f", "target/stm32f4x.cfg",
            "-c", f"program {firmware_path} verify reset exit"
        ])

        if returncode == 0:
            return UploadResult(success=True, output="已通过 openocd 烧录")

        return UploadResult(success=False, output=f"烧录失败:\nst-flash: {stderr}\nopenocd: {stderr}")

    def list_boards(self) -> List[Dict]:
        """列出可用开发板"""
        return [
            {"fqbn": "stm32f401re", "description": "STM32F401RE (Nucleo)"},
            {"fqbn": "stm32f411re", "description": "STM32F411RE (Nucleo)"},
            {"fqbn": "stm32f407vg", "description": "STM32F407VG (Discovery)"},
            {"fqbn": "stm32f103c8", "description": "STM32F103C8 (Blue Pill)"},
            {"fqbn": "stm32l476rg", "description": "STM32L476RG (Nucleo)"},
            {"fqbn": "stm32h743zi", "description": "STM32H743ZI (Nucleo)"},
        ]

    def _run_command(self, args, cwd=None, timeout=120):
        """执行命令"""
        from embedded import EmbeddedPlatform
        return EmbeddedPlatform._run_command(self, args, cwd, timeout)


# 注册平台
from platforms import register_platform
register_platform(STM32Platform)
```

- [ ] **Step 2: 验证语法**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -m py_compile frok/platforms/stm32.py`
Expected: 无输出

---

### Task 5: 创建嵌入式编程技能

**Files:**
- Create: `frok/skills/embedded.json`

- [ ] **Step 1: 创建技能文件**

```json
{
  "name": "embedded",
  "description": "嵌入式编程 - Arduino/ESP32/STM32 开发",
  "trigger": "嵌入式 / Arduino / ESP32 / STM32 / 单片机 / 开发板 / IoT / 传感器 / 串口 / 烧录 / 固件",
  "system_prompt": "你是嵌入式编程专家。根据用户需求：\n1. 选择合适的平台和开发板\n2. 生成符合平台规范的代码\n3. 处理硬件外设（GPIO、I2C、SPI、UART等）\n4. 添加必要的库依赖\n5. 编译烧录并验证\n\n可用工具：\n- embedded_detect: 检测工具链和设备\n- embedded_generate: 生成代码\n- embedded_compile: 编译固件\n- embedded_upload: 烧录固件\n- embedded_monitor: 串口监视\n- embedded_list_boards: 列出开发板\n- embedded_list_ports: 列出串口\n- embedded_stop_monitor: 停止监视",
  "steps": [
    "确认硬件平台和开发板型号",
    "分析外设需求（传感器、显示屏、通信模块等）",
    "使用 embedded_generate 生成代码",
    "使用 embedded_compile 编译检查语法错误",
    "使用 embedded_upload 烧录到开发板",
    "使用 embedded_monitor 查看串口输出验证"
  ]
}
```

- [ ] **Step 2: 验证 JSON 格式**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -c "import json; json.load(open('frok/skills/embedded.json'))" && echo "JSON OK"`
Expected: `JSON OK`

---

### Task 6: 修改 tools.py 添加嵌入式工具

**Files:**
- Modify: `frok/tools.py`

- [ ] **Step 1: 在 tools.py 末尾添加 EMBEDDED_TOOLS 导入**

在文件开头的导入部分之后，添加：

```python
# 嵌入式工具（延迟导入避免循环依赖）
def _get_embedded_tools():
    from embedded import EMBEDDED_TOOLS
    return EMBEDDED_TOOLS
```

- [ ] **Step 2: 在 TOOLS_SCHEMA 之后添加合并逻辑**

找到 `TOOLS_SCHEMA` 列表定义的末尾，在其后添加：

```python
# 获取所有工具（包括嵌入式工具）
def get_all_tools():
    """获取所有可用工具"""
    all_tools = TOOLS_SCHEMA.copy()
    try:
        all_tools.extend(_get_embedded_tools())
    except ImportError:
        pass  # 嵌入式模块不可用时忽略
    return all_tools
```

- [ ] **Step 3: 验证语法**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -m py_compile frok/tools.py`
Expected: 无输出

---

### Task 7: 修改 agent.py 集成嵌入式工具

**Files:**
- Modify: `frok/agent.py`

- [ ] **Step 1: 添加导入**

在 agent.py 的导入部分添加：

```python
try:
    from embedded import EMBEDDED_TOOLS, get_executor as get_embedded_executor
    HAS_EMBEDDED = True
except ImportError:
    HAS_EMBEDDED = False
```

- [ ] **Step 2: 在 FrokAgent.__init__ 中初始化嵌入式执行器**

在 `__init__` 方法的组件初始化部分添加：

```python
        # 嵌入式工具
        if HAS_EMBEDDED:
            self.embedded_executor = get_embedded_executor()
```

- [ ] **Step 3: 在 _execute_tool_call 中添加嵌入式工具处理**

在 `_execute_tool_call` 方法的末尾（`# 代码补全工具` 之后）添加：

```python
        # 嵌入式工具
        elif name.startswith("embedded_"):
            if HAS_EMBEDDED:
                result = self.embedded_executor.execute(name, params)
            else:
                result = "[错误] 嵌入式模块未加载，请检查依赖"
```

- [ ] **Step 4: 在系统提示词中添加嵌入式工具说明**

在 `SYSTEM_PROMPT` 的工具列表中，在 `## 沙箱执行` 之后添加：

```
## 嵌入式编程 (Arduino/ESP32/STM32)
- embedded_detect(platform): 检测工具链和设备
- embedded_generate(platform, board, description, language): 生成嵌入式代码
- embedded_compile(platform, sketch_path, board): 编译固件
- embedded_upload(platform, sketch_path, port, board): 烧录固件
- embedded_monitor(port, baud, duration): 串口监视
- embedded_list_boards(platform): 列出开发板
- embedded_list_ports(platform): 列出串口设备
- embedded_stop_monitor(): 停止串口监视
```

- [ ] **Step 5: 验证语法**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -m py_compile frok/agent.py`
Expected: 无输出

---

### Task 8: 更新 requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 添加 pyserial 依赖**

在 requirements.txt 中添加：

```
pyserial>=3.5
```

- [ ] **Step 2: 验证依赖文件**

Run: `cat "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code/requirements.txt"`
Expected: 显示包含 pyserial 的依赖列表

---

### Task 9: 集成测试

**Files:**
- Test: 运行 Frok Code 验证嵌入式工具可用

- [ ] **Step 1: 测试模块导入**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -c "from frok.embedded import EMBEDDED_TOOLS, get_executor; print(f'加载 {len(EMBEDDED_TOOLS)} 个嵌入式工具'); e = get_executor(); print('执行器初始化成功')"`
Expected: 显示加载 8 个工具，执行器初始化成功

- [ ] **Step 2: 测试平台发现**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -c "from frok.platforms import get_all_platforms; platforms = get_all_platforms(); print(f'发现 {len(platforms)} 个平台: {list(platforms.keys())}')"`
Expected: 显示发现 3 个平台: ['arduino', 'esp32', 'stm32']

- [ ] **Step 3: 测试设备检测**

Run: `cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code" && python3 -c "from frok.embedded import auto_detect_devices; devices = auto_detect_devices(); print(f'检测到 {len(devices)} 个设备')"`
Expected: 显示检测到的设备数量

- [ ] **Step 4: 测试完整流程（可选）**

如果有连接的开发板：
```bash
cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code"
python3 -c "
from frok.embedded import get_executor
e = get_executor()

# 检测
print(e.execute('embedded_detect', {}))

# 列出端口
print(e.execute('embedded_list_ports', {}))
"
```

- [ ] **Step 5: 提交代码**

```bash
cd "/mnt/d/10临时工作室/1海峡两岸暨港澳地区大学生计算机创新选拔赛/Frok code"
git init  # 如果还没有 git
git add frok/embedded.py frok/platforms/ frok/skills/embedded.json frok/tools.py frok/agent.py requirements.txt
git commit -m "feat: 添加嵌入式编程能力 (Arduino/ESP32/STM32)"
```

---

## 完成

实现计划完成。所有文件已创建，工具已注册，技能已定义。

**使用方式：**
```
用户: 帮我写个 Arduino LED 闪烁
Frok: [自动生成代码 → 检测设备 → 编译 → 烧录 → 串口监视]

用户: ESP32 温湿度监测
Frok: [自动生成代码 → 检测设备 → 编译 → 烧录 → 串口监视]
```
