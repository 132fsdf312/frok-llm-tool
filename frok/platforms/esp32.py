"""
ESP32 平台适配器
支持 ESP-IDF 和 arduino-cli 两种工具链
提供 WiFi、MQTT、传感器等场景的代码生成
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from frok.embedded import CompileResult, UploadResult, EmbeddedPlatform
from frok.platforms import register_platform


# ==================== 代码模板 ====================

TEMPLATES = {
    "wifi": """\
// ESP32 WiFi 连接示例
// 自动生成功能: {description}

#include <WiFi.h>

const char* ssid = "{ssid}";
const char* password = "{password}";

void setup() {{
  Serial.begin(115200);
  delay(1000);

  Serial.printf("正在连接 WiFi: %s\\n", ssid);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {{
    delay(500);
    Serial.print(".");
    retries++;
  }}

  if (WiFi.status() == WL_CONNECTED) {{
    Serial.printf("\\nWiFi 已连接, IP: %s\\n", WiFi.localIP().toString().c_str());
  }} else {{
    Serial.println("\\nWiFi 连接失败");
  }}

  {setup_body}
}}

void loop() {{
  {loop_body}
}}
""",

    "mqtt": """\
// ESP32 MQTT 客户端示例
// 自动生成功能: {description}

#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "{ssid}";
const char* password = "{password}";
const char* mqtt_server = "{mqtt_broker}";
const int mqtt_port = {mqtt_port};
const char* mqtt_topic = "{mqtt_topic}";

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {{
  Serial.begin(115200);
  delay(1000);

  // 连接 WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {{
    delay(500);
    Serial.print(".");
  }}
  Serial.printf("\\nWiFi 已连接, IP: %s\\n", WiFi.localIP().toString().c_str());

  // 连接 MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(mqttCallback);

  {setup_body}
}}

void loop() {{
  if (!client.connected()) {{
    reconnect();
  }}
  client.loop();

  {loop_body}
}}

void reconnect() {{
  while (!client.connected()) {{
    Serial.print("正在连接 MQTT...");
    if (client.connect("esp32_client")) {{
      Serial.println("已连接");
      client.subscribe(mqtt_topic);
    }} else {{
      Serial.printf("失败, rc=%d, 5秒后重试\\n", client.state());
      delay(5000);
    }}
  }}
}}

void mqttCallback(char* topic, byte* payload, unsigned int length) {{
  String message;
  for (unsigned int i = 0; i < length; i++) {{
    message += (char)payload[i];
  }}
  Serial.printf("收到消息 [%s]: %s\\n", topic, message.c_str());
}}
""",

    "sensor": """\
// ESP32 传感器读取示例
// 自动生成功能: 读取 {sensor_name}

const int SENSOR_PIN = {sensor_pin};
const int READ_INTERVAL = {interval};  // 毫秒

void setup() {{
  Serial.begin(115200);
  {pin_setup}
  Serial.println("{sensor_name} reader started on ESP32");
}}

void loop() {{
  {read_code}

  Serial.print("{sensor_name}: ");
  Serial.println(value);

  delay(READ_INTERVAL);
}}
""",

    "ble": """\
// ESP32 BLE 示例
// 自动生成功能: {description}

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define SERVICE_UUID        "{service_uuid}"
#define CHARACTERISTIC_UUID "{char_uuid}"

BLEServer* pServer = nullptr;
BLECharacteristic* pCharacteristic = nullptr;
bool deviceConnected = false;

class MyServerCallbacks: public BLEServerCallbacks {{
  void onConnect(BLEServer* pServer) {{
    deviceConnected = true;
    Serial.println("BLE 客户端已连接");
  }}

  void onDisconnect(BLEServer* pServer) {{
    deviceConnected = false;
    Serial.println("BLE 客户端已断开");
    pServer->getAdvertising()->start();
  }}
}};

void setup() {{
  Serial.begin(115200);

  BLEDevice::init("ESP32-BLE");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService* pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_WRITE |
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->start();
  Serial.println("BLE 广播已启动");

  {setup_body}
}}

void loop() {{
  {loop_body}
}}
""",

    "default": """\
// ESP32 通用程序
// 自动生成: {description}

void setup() {{
  Serial.begin(115200);
  delay(1000);
  Serial.println("ESP32 Setup complete");
  {setup_body}
}}

void loop() {{
  {loop_body}
}}
""",
}


# ==================== 关键词到模板映射 ====================

_KEYWORD_TEMPLATES = {
    "wifi": ["wifi", "wi-fi", "wireless", "无线", "网络连接", "http", "web server", "webserver"],
    "mqtt": ["mqtt", "iot", "broker", "publish", "subscribe", "消息队列", "物联网"],
    "sensor": ["sensor", "read", "temperature", "humidity", "light", "pressure",
               "传感器", "温度", "湿度", "光照", "读取", "气压"],
    "ble": ["ble", "bluetooth", "蓝牙", "beacon"],
}


# ==================== 常见 ESP32 开发板 ====================

_DEFAULT_BOARDS = [
    {"fqbn": "esp32:esp32:esp32", "name": "ESP32 Dev Module", "description": "ESP32-WROOM-32, 4MB Flash, WiFi+BT"},
    {"fqbn": "esp32:esp32:esp32s2", "name": "ESP32-S2", "description": "ESP32-S2, 4MB Flash, WiFi, USB-OTG"},
    {"fqbn": "esp32:esp32:esp32s3", "name": "ESP32-S3", "description": "ESP32-S3, 8MB Flash, WiFi+BLE5, AI加速"},
    {"fqbn": "esp32:esp32:esp32c3", "name": "ESP32-C3", "description": "ESP32-C3, 4MB Flash, WiFi+BLE5, RISC-V"},
    {"fqbn": "esp32:esp32:esp32c2", "name": "ESP32-C2", "description": "ESP32-C2, 4MB Flash, WiFi+BLE5, 低成本"},
    {"fqbn": "esp32:esp32:nodemcu-32s", "name": "NodeMCU-32S", "description": "ESP32-WROOM-32, 4MB Flash, 开发板"},
    {"fqbn": "esp32:esp32:az-delivery-devkit-v4", "name": "AZ-Delivery DevKit V4", "description": "ESP32-WROOM-32, 4MB Flash"},
    {"fqbn": "esp32:esp32:ttgo-t7-v14-mini32", "name": "TTGO T7 Mini32", "description": "ESP32-Mini32, 4MB Flash, 小尺寸"},
    {"fqbn": "esp32:esp32:ttgo-t-oi-plus", "name": "TTGO T-OI Plus", "description": "ESP32-C3, 4MB Flash, 1.28寸LCD"},
    {"fqbn": "esp32:esp32:lolin32", "name": "LOLIN32", "description": "ESP32-WROOM-32, 4MB Flash"},
]


# ==================== 编译错误解析 ====================

def _parse_compile_errors(stderr: str) -> List[str]:
    """
    从编译输出中提取错误信息

    支持格式:
      file:line:col: error: message   (ESP-IDF / arduino-cli)
      error: message                   (通用)
    """
    errors = []

    # GCC/ESP-IDF 风格
    gcc_pattern = re.compile(
        r"^(.+?):(\d+)(?::(\d+))?:\s*(error|warning):\s*(.+)$",
        re.MULTILINE,
    )
    for match in gcc_pattern.finditer(stderr):
        file_path, line, col, level, message = match.groups()
        col_str = f":{col}" if col else ""
        errors.append(f"[{level}] {file_path}:{line}{col_str}: {message}")

    # CMake / ESP-IDF 构建错误
    cmake_pattern = re.compile(r"^CMake Error.*?:\s*(.+)$", re.MULTILINE)
    for match in cmake_pattern.finditer(stderr):
        errors.append(f"[cmake] {match.group(0)}")

    # ESP-IDF 特有错误
    idf_pattern = re.compile(r"^(?:FAILED|ERROR|fatal error):\s*(.+)$", re.MULTILINE)
    for match in idf_pattern.finditer(stderr):
        if match.group(0) not in errors:
            errors.append(match.group(0))

    return errors


# ==================== ESP32 平台 ====================

@register_platform
class ESP32Platform(EmbeddedPlatform):
    """ESP32 平台适配器，支持 ESP-IDF 和 arduino-cli"""

    @property
    def name(self) -> str:
        return "esp32"

    @property
    def display_name(self) -> str:
        return "ESP32"

    @property
    def toolchain_cmd(self) -> str:
        """返回检测到的工具链命令；优先 idf.py，其次 arduino-cli"""
        if shutil.which("idf.py"):
            return "idf.py"
        return "arduino-cli"

    def detect(self) -> bool:
        """
        检测工具链是否可用

        优先检查 ESP-IDF (idf.py)，然后检查 arduino-cli 是否已安装 ESP32 核心。
        """
        # 1. ESP-IDF
        if shutil.which("idf.py"):
            return True

        # 2. arduino-cli + ESP32 核心
        if shutil.which("arduino-cli"):
            return self._check_esp32_core()

        return False

    def generate_code(self, spec: Dict) -> str:
        """
        根据描述选择模板并生成代码

        Args:
            spec: {"board": str, "description": str, "language": str}

        Returns:
            生成的代码字符串
        """
        description = spec.get("description", "")
        dl = description.lower()
        template_name = self._select_template(dl)

        if template_name == "wifi":
            return TEMPLATES["wifi"].format(
                description=description,
                ssid=self._extract_wifi_ssid(dl, "MyWiFi"),
                password=self._extract_wifi_password(dl, "password"),
                setup_body=self._generate_wifi_setup_body(dl),
                loop_body=self._generate_wifi_loop_body(dl),
            )

        if template_name == "mqtt":
            return TEMPLATES["mqtt"].format(
                description=description,
                ssid=self._extract_wifi_ssid(dl, "MyWiFi"),
                password=self._extract_wifi_password(dl, "password"),
                mqtt_broker=self._extract_mqtt_broker(dl, "broker.emqx.io"),
                mqtt_port=self._extract_mqtt_port(dl, 1883),
                mqtt_topic=self._extract_mqtt_topic(dl, "esp32/data"),
                setup_body=self._generate_mqtt_setup_body(dl),
                loop_body=self._generate_mqtt_loop_body(dl),
            )

        if template_name == "sensor":
            sensor_name, read_code, pin_setup = self._analyze_sensor(dl)
            return TEMPLATES["sensor"].format(
                sensor_name=sensor_name,
                sensor_pin=self._extract_pin(dl, default="34"),
                interval=self._extract_interval(dl, default=2000),
                read_code=read_code,
                pin_setup=pin_setup,
            )

        if template_name == "ble":
            return TEMPLATES["ble"].format(
                description=description,
                service_uuid=self._extract_ble_uuid(dl, "12345678-1234-5678-1234-56789abcdef0"),
                char_uuid=self._extract_ble_uuid(dl, "abcdefab-1234-5678-1234-56789abcdef0", offset=1),
                setup_body="// BLE 初始化代码",
                loop_body='if (deviceConnected) {\n    pCharacteristic->setValue("Hello from ESP32");\n    pCharacteristic->notify();\n    delay(1000);\n  }',
            )

        # 默认模板
        setup_body, loop_body = self._generate_default_body(dl)
        return TEMPLATES["default"].format(
            description=description,
            setup_body=setup_body,
            loop_body=loop_body,
        )

    def compile(self, sketch_path: str, board: str = None) -> CompileResult:
        """
        编译固件

        自动选择工具链：
        - 如果项目包含 CMakeLists.txt，使用 idf.py
        - 否则使用 arduino-cli

        Args:
            sketch_path: 代码文件或项目目录
            board: 开发板 FQBN，如 esp32:esp32:esp32dev
        """
        if not self.detect():
            return CompileResult(success=False, output="ESP32 工具链未安装 (需要 idf.py 或 arduino-cli)")

        sketch = Path(sketch_path)
        fqbn = board or "esp32:esp32:esp32"

        # 判断使用哪个工具链
        use_idf = self._should_use_idf(sketch)

        if use_idf:
            return self._compile_with_idf(sketch)
        else:
            return self._compile_with_arduino_cli(sketch, fqbn)

    def upload(self, sketch_path: str, port: str = None, board: str = None) -> UploadResult:
        """
        烧录固件

        自动选择工具链，支持 idf.py 和 arduino-cli。

        Args:
            sketch_path: 代码文件或项目目录
            port: 串口设备，留空自动检测
            board: 开发板 FQBN
        """
        if not self.detect():
            return UploadResult(success=False, output="ESP32 工具链未安装")

        sketch = Path(sketch_path)
        fqbn = board or "esp32:esp32:esp32"

        # 自动检测端口
        if not port:
            port = self._auto_detect_port()
            if not port:
                return UploadResult(success=False, output="未检测到 ESP32 设备，请连接开发板")

        use_idf = self._should_use_idf(sketch)

        if use_idf:
            return self._upload_with_idf(sketch, port)
        else:
            return self._upload_with_arduino_cli(sketch, port, fqbn)

    def list_boards(self) -> List[Dict]:
        """
        列出常见 ESP32 开发板

        如果 arduino-cli 可用且已安装 ESP32 核心，优先从 CLI 获取；
        否则返回内置列表。
        """
        if shutil.which("arduino-cli"):
            args = ["arduino-cli", "board", "listall", "esp32"]
            returncode, stdout, _ = self._run_command(args, timeout=30)

            if returncode == 0 and stdout.strip():
                boards = []
                for line in stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and "esp32" in parts[0].lower():
                        boards.append({
                            "fqbn": parts[0],
                            "name": parts[1],
                            "description": parts[1],
                        })
                if boards:
                    return boards

        return _DEFAULT_BOARDS

    # ==================== 工具链选择 ====================

    def _should_use_idf(self, project_path: Path) -> bool:
        """
        判断项目是否应使用 ESP-IDF 编译

        规则：如果项目目录下存在 CMakeLists.txt 且 idf.py 可用，则使用 IDF
        """
        if not shutil.which("idf.py"):
            return False

        # 如果是目录且包含 CMakeLists.txt
        if project_path.is_dir():
            cmake = project_path / "CMakeLists.txt"
            if cmake.exists():
                return True

        # 如果是 .c/.cpp 文件的父目录有 CMakeLists.txt
        if project_path.is_file():
            cmake = project_path.parent / "CMakeLists.txt"
            if cmake.exists():
                return True

        return False

    def _check_esp32_core(self) -> bool:
        """检查 arduino-cli 是否已安装 ESP32 核心"""
        args = ["arduino-cli", "core", "list"]
        returncode, stdout, _ = self._run_command(args, timeout=15)
        if returncode == 0:
            return "esp32:esp32" in stdout
        return False

    # ==================== ESP-IDF 编译/烧录 ====================

    def _compile_with_idf(self, project_path: Path) -> CompileResult:
        """使用 ESP-IDF 编译"""
        project_dir = project_path if project_path.is_dir() else project_path.parent
        args = ["idf.py", "build"]
        returncode, stdout, stderr = self._run_command(args, cwd=str(project_dir), timeout=300)

        if returncode == 0:
            # 查找生成的固件
            firmware = self._find_idf_firmware(project_dir)
            return CompileResult(
                success=True,
                output=stdout.strip(),
                firmware_path=firmware,
            )
        else:
            errors = _parse_compile_errors(stderr)
            return CompileResult(
                success=False,
                output=stderr.strip(),
                errors=errors if errors else [stderr.strip()],
            )

    def _upload_with_idf(self, project_path: Path, port: str) -> UploadResult:
        """使用 ESP-IDF 烧录"""
        project_dir = project_path if project_path.is_dir() else project_path.parent
        args = ["idf.py", "-p", port, "flash"]
        returncode, stdout, stderr = self._run_command(args, cwd=str(project_dir), timeout=120)

        if returncode == 0:
            return UploadResult(success=True, output=stdout.strip() or f"已烧录到 {port}")
        else:
            return UploadResult(success=False, output=stderr.strip())

    def _find_idf_firmware(self, project_dir: Path) -> str:
        """查找 ESP-IDF 编译生成的固件"""
        build_dir = project_dir / "build"
        if build_dir.exists():
            for name in ("firmware.bin", "merged.bin"):
                candidate = build_dir / name
                if candidate.exists():
                    return str(candidate)
            # 默认固件名
            for ext in ("*.bin",):
                files = list(build_dir.glob(ext))
                if files:
                    return str(files[0])
        return ""

    # ==================== arduino-cli 编译/烧录 ====================

    def _compile_with_arduino_cli(self, sketch_path: Path, fqbn: str) -> CompileResult:
        """使用 arduino-cli 编译 ESP32"""
        sketch = self._resolve_sketch_path(sketch_path)
        if not sketch:
            return CompileResult(success=False, output=f"未找到代码文件: {sketch_path}")

        args = ["arduino-cli", "compile", "--fqbn", fqbn, str(sketch)]
        returncode, stdout, stderr = self._run_command(args, timeout=300)

        if returncode == 0:
            return CompileResult(
                success=True,
                output=stdout.strip(),
                firmware_path=self._find_arduino_firmware(sketch, fqbn),
            )
        else:
            errors = _parse_compile_errors(stderr)
            return CompileResult(
                success=False,
                output=stderr.strip(),
                errors=errors if errors else [stderr.strip()],
            )

    def _upload_with_arduino_cli(self, sketch_path: Path, port: str, fqbn: str) -> UploadResult:
        """使用 arduino-cli 烧录 ESP32"""
        sketch = self._resolve_sketch_path(sketch_path)
        if not sketch:
            return UploadResult(success=False, output=f"未找到代码文件: {sketch_path}")

        args = ["arduino-cli", "upload", "--fqbn", fqbn, "--port", port, str(sketch)]
        returncode, stdout, stderr = self._run_command(args, timeout=120)

        if returncode == 0:
            return UploadResult(success=True, output=stdout.strip() or f"已烧录到 {port}")
        else:
            return UploadResult(success=False, output=stderr.strip())

    # ==================== 辅助方法 ====================

    def _select_template(self, description: str) -> str:
        """根据描述关键词选择模板"""
        for template_name, keywords in _KEYWORD_TEMPLATES.items():
            for kw in keywords:
                if kw in description:
                    return template_name
        return "default"

    def _extract_pin(self, description: str, default: str = "34") -> str:
        """从描述中提取引脚号（ESP32 GPIO）"""
        # 匹配 "pin 34", "GPIO4", "IO2" 等
        match = re.search(r"(?:pin|gpio|io)\s*(\d+)", description, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            if 0 <= num <= 39:
                return str(num)
        return default

    def _extract_interval(self, description: str, default: int = 2000) -> int:
        """从描述中提取间隔时间（毫秒）"""
        match = re.search(r"(\d+(?:\.\d+)?)\s*(ms|毫秒|s|秒)", description, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()
            if unit in ("s", "秒"):
                return int(value * 1000)
            return int(value)
        return default

    def _extract_wifi_ssid(self, description: str, default: str = "MyWiFi") -> str:
        """从描述中提取 WiFi SSID"""
        # 匹配 "ssid=xxx", "WiFi: xxx", "连接 xxx"
        match = re.search(
            r"(?:ssid|wifi|wi-fi|网络)[=:\s]+[\"']?(\S+?)[\"']?(?:\s|$|,|，)",
            description, re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return default

    def _extract_wifi_password(self, description: str, default: str = "password") -> str:
        """从描述中提取 WiFi 密码"""
        match = re.search(
            r"(?:password|passwd|密码|pwd)[=:\s]+[\"']?(\S+?)[\"']?(?:\s|$|,|，)",
            description, re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return default

    def _extract_mqtt_broker(self, description: str, default: str = "broker.emqx.io") -> str:
        """从描述中提取 MQTT broker 地址"""
        match = re.search(
            r"(?:broker|server|host|服务器)[=:\s]+[\"']?(\S+?)[\"']?(?:\s|$|,|，|:)",
            description, re.IGNORECASE,
        )
        if match:
            return match.group(1)
        # 匹配 IP 地址
        ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", description)
        if ip_match:
            return ip_match.group(1)
        # 匹配域名
        domain_match = re.search(r"((?:mqtt|broker)\.[a-z0-9.-]+)", description, re.IGNORECASE)
        if domain_match:
            return domain_match.group(1)
        return default

    def _extract_mqtt_port(self, description: str, default: int = 1883) -> int:
        """从描述中提取 MQTT 端口"""
        match = re.search(r"(?:port|端口)[=:\s]*(\d{2,5})", description, re.IGNORECASE)
        if match:
            port = int(match.group(1))
            if 1 <= port <= 65535:
                return port
        return default

    def _extract_mqtt_topic(self, description: str, default: str = "esp32/data") -> str:
        """从描述中提取 MQTT topic"""
        match = re.search(
            r"(?:topic|主题|频道)[=:\s]+[\"']?([/\w.-]+)[\"']?",
            description, re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return default

    def _extract_ble_uuid(self, description: str, default: str, offset: int = 0) -> str:
        """从描述中提取 BLE UUID"""
        uuids = re.findall(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            description,
        )
        if uuids and len(uuids) > offset:
            return uuids[offset]
        return default

    def _analyze_sensor(self, description: str) -> Tuple[str, str, str]:
        """
        分析传感器描述

        Returns:
            (sensor_name, read_code, pin_setup)
        """
        if any(kw in description for kw in ("temperature", "temp", "温度")):
            return (
                "Temperature",
                "int raw = analogRead(SENSOR_PIN);\n"
                "  // ESP32 ADC 12-bit (0-4095), 3.3V 参考\n"
                "  float voltage = raw * (3.3 / 4095.0);\n"
                "  float value = (voltage - 0.5) * 100.0;  // LM35 换算",
                "analogReadResolution(12);  // ESP32 12-bit ADC",
            )

        if any(kw in description for kw in ("humidity", "湿")):
            return (
                "Humidity",
                "int raw = analogRead(SENSOR_PIN);\n"
                "  float value = raw * (100.0 / 4095.0);  // 百分比",
                "analogReadResolution(12);",
            )

        if any(kw in description for kw in ("light", "photo", "光照")):
            return (
                "Light",
                "int value = analogRead(SENSOR_PIN);",
                "analogReadResolution(12);",
            )

        if any(kw in description for kw in ("distance", "ultrasonic", "超声波", "距离")):
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

        if any(kw in description for kw in ("accel", "gyro", "imu", "mpu", "加速度", "陀螺仪")):
            return (
                "IMU",
                "// 假设 I2C 连接 MPU6050\n"
                "  Wire.beginTransmission(0x68);\n"
                "  Wire.write(0x3B);\n"
                "  Wire.endTransmission(false);\n"
                "  Wire.requestFrom(0x68, 6, true);\n"
                "  int16_t ax = Wire.read() << 8 | Wire.read();\n"
                "  int16_t ay = Wire.read() << 8 | Wire.read();\n"
                "  int16_t az = Wire.read() << 8 | Wire.read();\n"
                "  float value = sqrt(ax*ax + ay*ay + az*az) / 16384.0;",
                "#include <Wire.h>\n  Wire.begin(21, 22);  // ESP32 I2C: SDA=21, SCL=22",
            )

        # 通用模拟传感器
        return (
            "Sensor",
            "int value = analogRead(SENSOR_PIN);",
            "analogReadResolution(12);  // ESP32 12-bit ADC",
        )

    def _generate_wifi_setup_body(self, description: str) -> str:
        """生成 WiFi 模板的 setup 内容"""
        lines = []
        if any(kw in description for kw in ("server", "http", "web", "服务器")):
            lines.append("// 启动 Web 服务器")
            lines.append("// WebServer server(80);")
            lines.append("// server.begin();")
        return "\n  ".join(lines) if lines else "// WiFi setup"

    def _generate_wifi_loop_body(self, description: str) -> str:
        """生成 WiFi 模板的 loop 内容"""
        if any(kw in description for kw in ("server", "http", "web", "服务器")):
            return "// server.handleClient();\n  delay(10);"
        return 'Serial.println("WiFi connected: " + WiFi.localIP().toString());\n  delay(5000);'

    def _generate_mqtt_setup_body(self, description: str) -> str:
        """生成 MQTT 模板的 setup 内容"""
        return ""

    def _generate_mqtt_loop_body(self, description: str) -> str:
        """生成 MQTT 模板的 loop 内容"""
        lines = [
            'static unsigned long lastPublish = 0;',
            'if (millis() - lastPublish > 5000) {',
            '    lastPublish = millis();',
            '    String payload = "{\\"temp\\": 25.0, \\"humidity\\": 60}";',
            '    client.publish(mqtt_topic, payload.c_str());',
            '    Serial.println("已发布: " + payload);',
            '  }',
        ]
        return "\n    ".join(lines)

    def _generate_default_body(self, description: str) -> Tuple[str, str]:
        """为默认模板生成 setup/loop 内容"""
        setup_lines = []
        loop_lines = []

        # GPIO 控制
        if any(kw in description for kw in ("led", "light", "gpio", "输出", "灯")):
            pin = self._extract_pin(description, default="2")
            setup_lines.append(f"pinMode({pin}, OUTPUT);")
            loop_lines.extend([
                f"digitalWrite({pin}, HIGH);",
                "  delay(1000);",
                f"digitalWrite({pin}, LOW);",
                "  delay(1000);",
            ])

        # PWM
        if any(kw in description for kw in ("pwm", "dim", "brightness", "亮度", "调光")):
            setup_lines.append("ledcSetup(0, 5000, 8);  // 通道0, 5kHz, 8-bit")
            setup_lines.append("ledcAttachPin(2, 0);")
            loop_lines.extend([
                "for (int i = 0; i <= 255; i++) {",
                "    ledcWrite(0, i);",
                "    delay(10);",
                "  }",
                "  for (int i = 255; i >= 0; i--) {",
                "    ledcWrite(0, i);",
                "    delay(10);",
                "  }",
            ])

        # 蜂鸣器
        if any(kw in description for kw in ("buzzer", "beep", "tone", "蜂鸣")):
            setup_lines.append("ledcSetup(1, 2000, 8);")
            setup_lines.append("ledcAttachPin(4, 1);")
            loop_lines.extend([
                "ledcWriteTone(1, 1000);",
                "  delay(500);",
                "  ledcWriteTone(1, 0);",
                "  delay(500);",
            ])

        # 电机
        if any(kw in description for kw in ("motor", "spin", "rotate", "电机", "转动")):
            setup_lines.append("ledcSetup(2, 25000, 8);")
            setup_lines.append("ledcAttachPin(16, 2);")
            loop_lines.extend([
                "ledcWrite(2, 200);",
                "  delay(2000);",
                "  ledcWrite(2, 0);",
                "  delay(1000);",
            ])

        # Deep Sleep
        if any(kw in description for kw in ("sleep", "deep sleep", "低功耗", "休眠")):
            loop_lines.extend([
                "Serial.println(\"进入 Deep Sleep 60秒...\");",
                "  esp_deep_sleep(60 * 1000000);",
            ])

        # 兜底
        if not loop_lines:
            loop_lines.extend([
                'Serial.printf("ESP32 running, free heap: %d bytes\\n", ESP.getFreeHeap());',
                "  delay(1000);",
            ])

        return (
            "\n  ".join(setup_lines) if setup_lines else "// your setup code",
            "\n  ".join(loop_lines),
        )

    def _resolve_sketch_path(self, sketch_path) -> Path:
        """
        解析 sketch 路径

        支持:
          - 直接指向 .ino / .cpp / .c 文件
          - 指向包含代码文件的目录
          - ESP-IDF 项目目录 (包含 CMakeLists.txt)
        """
        p = Path(sketch_path) if not isinstance(sketch_path, Path) else sketch_path

        if p.is_file():
            if p.suffix in (".ino", ".cpp", ".c"):
                return p

        if p.is_dir():
            # Arduino 风格
            ino_files = list(p.glob("*.ino"))
            if ino_files:
                return ino_files[0]

            # 目录名匹配
            expected = p / f"{p.name}.ino"
            if expected.exists():
                return expected

            # ESP-IDF 项目
            if (p / "CMakeLists.txt").exists():
                main_dir = p / "main"
                if main_dir.exists():
                    for ext in ("*.cpp", "*.c"):
                        files = list(main_dir.glob(ext))
                        if files:
                            return files[0]

        return None

    def _auto_detect_port(self) -> str:
        """自动检测 ESP32 设备端口"""
        # ESP32 常见 USB 转串口芯片: CP2102, CP2104, CH340, CH9102, FTDI
        esp32_keywords = ("cp210", "cp2102", "cp2104", "ch340", "ch9102",
                          "ch9102f", "silicon labs", "esp32", "usb serial")

        # 优先用 arduino-cli
        if shutil.which("arduino-cli"):
            args = ["arduino-cli", "board", "list"]
            returncode, stdout, _ = self._run_command(args, timeout=10)
            if returncode == 0 and stdout.strip():
                for line in stdout.strip().splitlines()[1:]:
                    parts = line.split()
                    if parts and parts[0].startswith(("/dev/", "COM")):
                        line_lower = line.lower()
                        if any(kw in line_lower for kw in esp32_keywords):
                            return parts[0]

        # 回退: serial.tools.list_ports
        try:
            import serial.tools.list_ports
            for port in serial.tools.list_ports.comports():
                desc = port.description.lower()
                if any(kw in desc for kw in esp32_keywords):
                    return port.device
            # 实在没有，返回第一个端口
            ports = list(serial.tools.list_ports.comports())
            if ports:
                return ports[0].device
        except ImportError:
            pass

        return ""

    def _find_arduino_firmware(self, sketch_path: str, fqbn: str) -> str:
        """查找 arduino-cli 编译生成的固件 (.bin)"""
        sketch_dir = Path(sketch_path)
        if sketch_dir.is_file():
            sketch_dir = sketch_dir.parent

        # 构建目录
        build_dir = sketch_dir / "build"
        if build_dir.exists():
            for ext in ("*.bin", "*.elf"):
                files = list(build_dir.rglob(ext))
                if files:
                    return str(files[0])

        # arduino-cli 默认缓存
        try:
            cache_dir = Path.home() / ".cache" / "arduino" / "sketches"
            if cache_dir.exists():
                sketch_hash = sketch_dir.name
                for d in cache_dir.iterdir():
                    if d.name.startswith(sketch_hash):
                        for ext in ("*.bin", "*.elf"):
                            files = list(d.rglob(ext))
                            if files:
                                return str(files[0])
        except Exception:
            pass

        return ""
