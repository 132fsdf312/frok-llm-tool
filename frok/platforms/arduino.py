"""
Arduino 平台适配器
基于 arduino-cli 实现代码生成、编译、烧录、开发板管理
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List

from frok.embedded import CompileResult, UploadResult, EmbeddedPlatform
from frok.platforms import register_platform


# ==================== 代码模板 ====================

TEMPLATES = {
    "blink": """\
// Blink - Arduino 入门示例
// 自动生成功能: LED 闪烁

const int LED_PIN = {led_pin};
const int INTERVAL = {interval};  // 毫秒

void setup() {{
  pinMode(LED_PIN, OUTPUT);
  Serial.begin(115200);
  Serial.println("Blink started");
}}

void loop() {{
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED ON");
  delay(INTERVAL);

  digitalWrite(LED_PIN, LOW);
  Serial.println("LED OFF");
  delay(INTERVAL);
}}
""",

    "sensor": """\
// Sensor Reader - 传感器读取示例
// 自动生成功能: 读取 {sensor_name} 并通过串口输出

const int SENSOR_PIN = {sensor_pin};
const int READ_INTERVAL = {interval};  // 毫秒

void setup() {{
  Serial.begin(115200);
  {pin_setup}
  Serial.println("{sensor_name} reader started");
}}

void loop() {{
  {read_code}

  Serial.print("{sensor_name}: ");
  Serial.println(value);

  delay(READ_INTERVAL);
}}
""",

    "default": """\
// Arduino Sketch
// 自动生成: {description}

void setup() {{
  Serial.begin(115200);
  Serial.println("Setup complete");
  {setup_body}
}}

void loop() {{
  {loop_body}
}}
""",
}

# 关键词到模板的映射
_KEYWORD_TEMPLATES = {
    "blink": ["blink", "led", "flash", "闪烁", "闪灯"],
    "sensor": ["sensor", "read", "temperature", "humidity", "light",
               "sensor", "传感器", "温度", "湿度", "光照", "读取"],
}


# ==================== 默认开发板 FQBN ====================

_DEFAULT_BOARDS = [
    {"fqbn": "arduino:avr:uno", "name": "Arduino Uno", "description": "ATmega328P, 32KB Flash"},
    {"fqbn": "arduino:avr:mega:cpu=atmega2560", "name": "Arduino Mega 2560", "description": "ATmega2560, 256KB Flash"},
    {"fqbn": "arduino:avr:nano:cpu=atmega328", "name": "Arduino Nano", "description": "ATmega328P, 32KB Flash (old bootloader)"},
    {"fqbn": "arduino:avr:leonardo", "name": "Arduino Leonardo", "description": "ATmega32U4, 32KB Flash"},
    {"fqbn": "arduino:avr:micro", "name": "Arduino Micro", "description": "ATmega32U4, 32KB Flash"},
    {"fqbn": "arduino:sam:arduino_due_x_dbg", "name": "Arduino Due", "description": "SAM3X8E, 512KB Flash"},
    {"fqbn": "arduino:mbed_nano:nanorp2040connect", "name": "Arduino Nano RP2040 Connect", "description": "RP2040, 16MB Flash"},
    {"fqbn": "arduino:mbed_nano:nano33ble", "name": "Arduino Nano 33 BLE", "description": "nRF52840, 1MB Flash"},
    {"fqbn": "arduino:mbed_rp2040:pico", "name": "Arduino Nano RP2040", "description": "RP2040, 2MB Flash"},
]


# ==================== 编译错误解析 ====================

def _parse_compile_errors(stderr: str) -> List[str]:
    """
    从 arduino-cli 编译输出中提取错误信息

    匹配格式:
      file:line:col: error: message
      file:line: error: message
    """
    errors = []
    pattern = re.compile(r"^(.+?):(\d+)(?::(\d+))?:\s*(error|warning):\s*(.+)$", re.MULTILINE)

    for match in pattern.finditer(stderr):
        file_path, line, col, level, message = match.groups()
        col_str = f":{col}" if col else ""
        errors.append(f"[{level}] {file_path}:{line}{col_str}: {message}")

    return errors


# ==================== Arduino 平台 ====================

@register_platform
class ArduinoPlatform(EmbeddedPlatform):
    """Arduino 平台适配器"""

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
        """检测 arduino-cli 是否可用"""
        return shutil.which("arduino-cli") is not None

    def generate_code(self, spec: Dict) -> str:
        """
        根据描述选择模板并生成代码

        Args:
            spec: {"board": str, "description": str, "language": str}

        Returns:
            生成的代码字符串
        """
        description = spec.get("description", "").lower()
        template_name = self._select_template(description)

        if template_name == "blink":
            return TEMPLATES["blink"].format(
                led_pin=self._extract_pin(description, default="LED_BUILTIN"),
                interval=self._extract_interval(description, default=1000),
            )

        if template_name == "sensor":
            sensor_name, read_code, pin_setup = self._analyze_sensor(description)
            return TEMPLATES["sensor"].format(
                sensor_name=sensor_name,
                sensor_pin=self._extract_pin(description, default="A0"),
                interval=self._extract_interval(description, default=2000),
                read_code=read_code,
                pin_setup=pin_setup,
            )

        # 默认模板
        setup_body, loop_body = self._generate_default_body(description)
        return TEMPLATES["default"].format(
            description=spec.get("description", ""),
            setup_body=setup_body,
            loop_body=loop_body,
        )

    def compile(self, sketch_path: str, board: str = None) -> CompileResult:
        """
        调用 arduino-cli compile 编译固件

        Args:
            sketch_path: .ino 文件路径或目录
            board: FQBN，如 arduino:avr:uno
        """
        if not self.detect():
            return CompileResult(success=False, output="arduino-cli 未安装")

        fqbn = board or "arduino:avr:uno"
        sketch = self._resolve_sketch_path(sketch_path)

        if not sketch:
            return CompileResult(success=False, output=f"未找到 .ino 文件: {sketch_path}")

        args = ["arduino-cli", "compile", "--fqbn", fqbn, str(sketch)]
        returncode, stdout, stderr = self._run_command(args, timeout=180)

        if returncode == 0:
            return CompileResult(
                success=True,
                output=stdout.strip(),
                firmware_path=self._find_firmware(sketch, fqbn),
            )
        else:
            errors = _parse_compile_errors(stderr)
            return CompileResult(
                success=False,
                output=stderr.strip(),
                errors=errors if errors else [stderr.strip()],
            )

    def upload(self, sketch_path: str, port: str = None, board: str = None) -> UploadResult:
        """
        调用 arduino-cli upload 烧录固件

        Args:
            sketch_path: .ino 文件路径或目录
            port: 串口设备路径，留空自动检测
            board: FQBN
        """
        if not self.detect():
            return UploadResult(success=False, output="arduino-cli 未安装")

        fqbn = board or "arduino:avr:uno"
        sketch = self._resolve_sketch_path(sketch_path)

        if not sketch:
            return UploadResult(success=False, output=f"未找到 .ino 文件: {sketch_path}")

        # 自动检测端口
        if not port:
            port = self._auto_detect_port()
            if not port:
                return UploadResult(success=False, output="未检测到串口设备，请连接开发板")

        args = ["arduino-cli", "upload", "--fqbn", fqbn, "--port", port, str(sketch)]
        returncode, stdout, stderr = self._run_command(args, timeout=120)

        if returncode == 0:
            return UploadResult(success=True, output=stdout.strip() or f"已烧录到 {port}")
        else:
            return UploadResult(success=False, output=stderr.strip())

    def list_boards(self) -> List[Dict]:
        """
        列出可用开发板

        优先使用 arduino-cli board listall，失败时返回内置列表
        """
        if not self.detect():
            return _DEFAULT_BOARDS

        args = ["arduino-cli", "board", "listall"]
        returncode, stdout, stderr = self._run_command(args, timeout=30)

        if returncode != 0 or not stdout.strip():
            return _DEFAULT_BOARDS

        boards = []
        for line in stdout.strip().splitlines():
            # 格式: FQBN    Board Name
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                boards.append({
                    "fqbn": parts[0],
                    "name": parts[1],
                    "description": parts[1],
                })

        return boards if boards else _DEFAULT_BOARDS

    # ==================== 辅助方法 ====================

    def _select_template(self, description: str) -> str:
        """根据描述关键词选择模板"""
        for template_name, keywords in _KEYWORD_TEMPLATES.items():
            for kw in keywords:
                if kw in description:
                    return template_name
        return "default"

    def _extract_pin(self, description: str, default: str = "LED_BUILTIN") -> str:
        """从描述中提取引脚号"""
        # 匹配 "pin 13", "D13", "GPIO2" 等
        match = re.search(r"(?:pin|gpio|d)\s*(\d+)", description, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            # 数字引脚 vs 模拟引脚
            if description.lower().find("a") >= 0 and num < 16:
                return f"A{num}"
            return str(num)
        return default

    def _extract_interval(self, description: str, default: int = 1000) -> int:
        """从描述中提取间隔时间（毫秒）"""
        # 匹配 "500ms", "0.5s", "2 秒"
        match = re.search(r"(\d+(?:\.\d+)?)\s*(ms|毫秒|s|秒)", description, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()
            if unit in ("s", "秒"):
                return int(value * 1000)
            return int(value)
        return default

    def _analyze_sensor(self, description: str):
        """
        分析传感器描述，返回 (名称, 读取代码, 引脚配置)

        Returns:
            (sensor_name, read_code, pin_setup)
        """
        dl = description.lower()

        if any(kw in dl for kw in ("temperature", "temp", "温度")):
            return (
                "Temperature",
                "int raw = analogRead(SENSOR_PIN);\n"
                "  float value = raw * (5.0 / 1023.0) * 100.0;  // 换算为摄氏度",
                "pinMode(SENSOR_PIN, INPUT);",
            )

        if any(kw in dl for kw in ("humidity", "湿")):
            return (
                "Humidity",
                "int raw = analogRead(SENSOR_PIN);\n"
                "  float value = raw * (100.0 / 1023.0);  // 百分比",
                "pinMode(SENSOR_PIN, INPUT);",
            )

        if any(kw in dl for kw in ("light", "photo", "光照")):
            return (
                "Light",
                "int value = analogRead(SENSOR_PIN);",
                "pinMode(SENSOR_PIN, INPUT);",
            )

        if any(kw in dl for kw in ("distance", "ultrasonic", "超声波", "距离")):
            return (
                "Distance",
                "digitalWrite(SENSOR_PIN, LOW);\n"
                "  delayMicroseconds(2);\n"
                "  digitalWrite(SENSOR_PIN, HIGH);\n"
                "  delayMicroseconds(10);\n"
                "  digitalWrite(SENSOR_PIN, LOW);\n"
                "  long duration = pulseIn(SENSOR_PIN + 1, HIGH);\n"
                "  float value = duration * 0.034 / 2.0;  // 厘米",
                "pinMode(SENSOR_PIN, OUTPUT);",
            )

        # 通用模拟传感器
        return (
            "Sensor",
            "int value = analogRead(SENSOR_PIN);",
            "pinMode(SENSOR_PIN, INPUT);",
        )

    def _generate_default_body(self, description: str):
        """为默认模板生成 setup/loop 内容"""
        dl = description.lower()

        setup_lines = []
        loop_lines = []

        # 串口输出
        if any(kw in dl for kw in ("print", "serial", "monitor", "输出", "监视")):
            loop_lines.append('Serial.println("Hello from Arduino");')

        # PWM
        if any(kw in dl for kw in ("pwm", "dim", "brightness", "亮度", "调光")):
            setup_lines.append("pinMode(9, OUTPUT);")
            loop_lines.extend([
                "for (int i = 0; i <= 255; i++) {",
                "    analogWrite(9, i);",
                "    delay(10);",
                "  }",
                "  for (int i = 255; i >= 0; i--) {",
                "    analogWrite(9, i);",
                "    delay(10);",
                "  }",
            ])

        # 蜂鸣器
        if any(kw in dl for kw in ("buzzer", "beep", "tone", "蜂鸣")):
            setup_lines.append("pinMode(8, OUTPUT);")
            loop_lines.extend([
                "tone(8, 1000, 500);",
                "  delay(1000);",
            ])

        # 电机
        if any(kw in dl for kw in ("motor", "spin", "rotate", "电机", "转动")):
            setup_lines.append("pinMode(9, OUTPUT);")
            loop_lines.extend([
                "analogWrite(9, 200);",
                "  delay(2000);",
                "  analogWrite(9, 0);",
                "  delay(1000);",
            ])

        # 兜底
        if not loop_lines:
            loop_lines.append('Serial.println("Running...");')
            loop_lines.append("  delay(1000);")

        return "\n  ".join(setup_lines) or "// your setup code", "\n  ".join(loop_lines)

    def _resolve_sketch_path(self, sketch_path: str) -> str:
        """
        解析 sketch 路径

        支持:
          - 直接指向 .ino 文件
          - 指向包含 .ino 的目录
          - 目录名与 .ino 文件名不一致时自动查找
        """
        p = Path(sketch_path)

        if p.is_file() and p.suffix == ".ino":
            return str(p)

        if p.is_dir():
            # 在目录中查找 .ino 文件
            ino_files = list(p.glob("*.ino"))
            if ino_files:
                return str(ino_files[0])

            # 目录名匹配：sketch_path/sketch_path.ino
            expected = p / f"{p.name}.ino"
            if expected.exists():
                return str(expected)

        return ""

    def _auto_detect_port(self) -> str:
        """自动检测 Arduino 设备端口"""
        # 优先用 arduino-cli board list
        if self.detect():
            args = ["arduino-cli", "board", "list"]
            returncode, stdout, _ = self._run_command(args, timeout=10)
            if returncode == 0 and stdout.strip():
                for line in stdout.strip().splitlines()[1:]:  # 跳过表头
                    parts = line.split()
                    if parts and parts[0].startswith(("/dev/", "COM")):
                        return parts[0]

        # 回退: 用 serial.tools.list_ports
        try:
            import serial.tools.list_ports
            for port in serial.tools.list_ports.comports():
                desc = port.description.lower()
                if any(kw in desc for kw in ("arduino", "ch340", "cp210", "ftdi", "usb serial")):
                    return port.device
            # 实在没有，返回第一个端口
            ports = list(serial.tools.list_ports.comports())
            if ports:
                return ports[0].device
        except ImportError:
            pass

        return ""

    def _find_firmware(self, sketch_path: str, fqbn: str) -> str:
        """查找编译生成的固件文件 (.hex / .bin)"""
        sketch_dir = Path(sketch_path)
        if sketch_dir.is_file():
            sketch_dir = sketch_dir.parent

        build_dir = sketch_dir / "build"
        if build_dir.exists():
            for ext in ("*.hex", "*.bin", "*.elf"):
                files = list(build_dir.rglob(ext))
                if files:
                    return str(files[0])

        # arduino-cli 默认输出位置
        try:
            cache_dir = Path.home() / ".cache" / "arduino" / "sketches"
            if cache_dir.exists():
                sketch_hash = sketch_dir.name
                for d in cache_dir.iterdir():
                    if d.name.startswith(sketch_hash):
                        for ext in ("*.hex", "*.bin", "*.elf"):
                            files = list(d.rglob(ext))
                            if files:
                                return str(files[0])
        except Exception:
            pass

        return ""
