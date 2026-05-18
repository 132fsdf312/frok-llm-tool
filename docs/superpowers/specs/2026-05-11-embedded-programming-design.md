# 嵌入式编程能力设计文档

**日期：** 2026-05-11
**状态：** 已批准
**作者：** 聪音

## 概述

为 Frok Code 添加嵌入式编程能力，支持 Arduino、ESP32、STM32 三个平台的代码生成、编译、烧录和调试监控。采用完全自动化设计，用户只需自然语言输入，系统自动检测设备并完成整个开发流程。

## 设计目标

1. **多平台支持**：Arduino (AVR)、ESP32、STM32 (ARM Cortex-M)
2. **全流程覆盖**：代码生成 → 编译 → 烧录 → 串口监视
3. **完全自动化**：自动检测设备、推断平台、选择串口
4. **自然语言交互**：用户只需描述需求，无需关心技术细节

## 架构设计

### 目录结构

```
frok/
├── embedded.py              # 基类 EmbeddedPlatform + 工具注册 + 自动检测
├── platforms/
│   ├── __init__.py          # 自动发现所有平台
│   ├── arduino.py           # ArduinoPlatform
│   ├── esp32.py             # ESP32Platform
│   └── stm32.py             # STM32Platform
└── skills/
    └── embedded.json        # 嵌入式编程技能
```

### 核心接口

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class EmbeddedPlatform(ABC):
    """嵌入式平台基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """平台名称"""
        ...
    
    @property
    @abstractmethod
    def toolchain_cmd(self) -> str:
        """工具链命令"""
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
            spec: 包含 board, description, language 等信息
            
        Returns:
            生成的代码字符串
        """
        ...
    
    @abstractmethod
    def compile(self, sketch_path: str, board: str = None) -> Dict:
        """
        编译固件
        
        Returns:
            {"success": bool, "output": str, "errors": List[str]}
        """
        ...
    
    @abstractmethod
    def upload(self, sketch_path: str, port: str = None, board: str = None) -> Dict:
        """
        烧录固件
        
        Returns:
            {"success": bool, "output": str}
        """
        ...
    
    @abstractmethod
    def monitor(self, port: str, baud: int = 115200, duration: int = None) -> None:
        """串口监视"""
        ...
    
    @abstractmethod
    def list_boards(self) -> List[Dict]:
        """列出可用开发板"""
        ...
    
    @abstractmethod
    def list_ports(self) -> List[Dict]:
        """
        列出串口设备
        
        Returns:
            [{"port": "COM3", "description": "Arduino Uno", "vid": "0x2341", "pid": "0x0043"}]
        """
        ...
```

## 工具定义

新增 8 个工具到 TOOLS_SCHEMA：

### embedded_detect

```json
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
}
```

### embedded_generate

```json
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
}
```

### embedded_compile

```json
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
            },
            "options": {
                "type": "object",
                "description": "编译选项"
            }
        },
        "required": ["platform", "sketch_path"]
    }
}
```

### embedded_upload

```json
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
}
```

### embedded_monitor

```json
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
}
```

### embedded_list_boards

```json
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
}
```

### embedded_list_ports

```json
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
}
```

### embedded_stop_monitor

```json
{
    "name": "embedded_stop_monitor",
    "description": "停止串口监视器",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}
```

## 平台实现

### Arduino 平台

**工具链：** `arduino-cli`

**代码模板：**
```cpp
// {description}
// 生成时间: {timestamp}

void setup() {
    Serial.begin(115200);
    // 初始化代码
}

void loop() {
    // 主循环代码
}
```

**关键命令：**
- 检测：`arduino-cli version`
- 编译：`arduino-cli compile --fqbn {board} {sketch_path}`
- 烧录：`arduino-cli upload -p {port} --fqbn {board} {sketch_path}`
- 列出板子：`arduino-cli board list`
- 列出开发板：`arduino-cli board listall`

### ESP32 平台

**工具链：** `idf.py`（ESP-IDF）或 `arduino-cli`（Arduino 框架）

**代码模板（Arduino 风格）：**
```cpp
// {description}
// ESP32 开发板

#include <WiFi.h>

void setup() {
    Serial.begin(115200);
    // 初始化代码
}

void loop() {
    // 主循环代码
}
```

**代码模板（ESP-IDF 风格）：**
```c
// {description}
// ESP-IDF 项目

#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"

void app_main() {
    // 主函数
}
```

**关键命令：**
- 检测：`idf.py --version` 或 `arduino-cli board list`
- 编译：`idf.py build` 或 `arduino-cli compile --fqbn esp32:esp32:{board}`
- 烧录：`idf.py -p {port} flash` 或 `arduino-cli upload -p {port} --fqbn esp32:esp32:{board}`

### STM32 平台

**工具链：** `arm-none-eabi-gcc` + `st-flash` 或 `openocd`

**代码模板（HAL 库）：**
```c
// {description}
// STM32 开发板

#include "stm32f4xx_hal.h"

int main(void) {
    HAL_Init();
    SystemClock_Config();
    
    // 初始化代码
    
    while (1) {
        // 主循环代码
    }
}
```

**关键命令：**
- 检测：`arm-none-eabi-gcc --version`
- 编译：`make` 或 `arm-none-eabi-gcc -o firmware.elf ...`
- 烧录：`st-flash write firmware.bin 0x08000000` 或 `openocd -f ...`

## 自动检测策略

### 设备检测流程

```python
def auto_detect_devices() -> List[Dict]:
    """自动检测所有连接的嵌入式设备"""
    devices = []
    
    # 1. 扫描串口
    for port in serial.tools.list_ports.comports():
        device = {
            "port": port.device,
            "description": port.description,
            "vid": port.vid,
            "pid": port.pid,
            "manufacturer": port.manufacturer
        }
        
        # 2. 通过 VID/PID 推断板子类型
        device["platform"] = infer_platform(device)
        device["board"] = infer_board(device)
        
        devices.append(device)
    
    # 3. 扫描调试器（ST-Link, J-Link 等）
    debuggers = detect_debuggers()
    devices.extend(debuggers)
    
    return devices
```

### 平台推断规则

| VID:PID | 推断结果 |
|---------|----------|
| 0x2341:* | Arduino 官方板 |
| 0x1A86:0x7523 | CH340 串口（可能是 ESP32/Arduino 兼容板） |
| 0x10C4:0xEA60 | CP2102 串口（ESP32 开发板常见） |
| 0x0483:0x374B | ST-Link V2（STM32） |

### 智能推断策略

1. **用户明确指定**：用户说"Arduino"/"ESP32"/"STM32" → 直接匹配
2. **代码分析**：代码包含 `WiFi.h` → 推断 ESP32
3. **设备信息**：USB VID/PID → 推断板子类型
4. **单一设备**：只连接一个设备 → 自动选择
5. **多设备歧义**：多个设备且无法推断 → 询问用户

## 技能定义

```json
{
    "name": "embedded",
    "description": "嵌入式编程 - Arduino/ESP32/STM32 开发",
    "trigger": "嵌入式 / Arduino / ESP32 / STM32 / 单片机 / 开发板 / IoT / 传感器 / 串口",
    "system_prompt": "你是嵌入式编程专家。根据用户需求：\n1. 选择合适的平台和开发板\n2. 生成符合平台规范的代码\n3. 处理硬件外设（GPIO、I2C、SPI、UART等）\n4. 添加必要的库依赖\n5. 编译烧录并验证",
    "steps": [
        "确认硬件平台和开发板型号",
        "分析外设需求（传感器、显示屏、通信模块等）",
        "生成代码并添加注释",
        "编译检查语法错误",
        "烧录并打开串口监视验证"
    ]
}
```

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| 工具链未安装 | 提示安装命令，给出下载链接 |
| 编译失败 | 解析错误信息，定位到具体行号 |
| 烧录失败 | 检查串口权限、板子连接、boot 模式 |
| 串口占用 | 提示关闭占用进程，或切换串口 |
| 板子不匹配 | 提示正确的 board 参数 |
| 多设备歧义 | 列出设备列表，询问用户选择 |

## 依赖要求

### Python 依赖

```
# requirements.txt 新增
pyserial>=3.5        # 串口通信
```

### 外部工具（用户自行安装）

| 平台 | 工具 | 安装命令 |
|------|------|----------|
| Arduino | `arduino-cli` | `curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \| sh` |
| ESP32 | `esp-idf` | https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/ |
| STM32 | `arm-none-eabi-gcc` | https://developer.arm.com/downloads/-/gnu-rm |
| STM32 | `st-link` | https://github.com/stlink-org/stlink |

## 工作流示例

### 示例 1：ESP32 温湿度监测

```
用户: 帮我做一个 ESP32 的温湿度监测，DHT22 接 GPIO4，数据发到 MQTT

Frok:
1. [代码生成] 生成 ESP32 + DHT22 + MQTT 代码
2. [自动检测] 扫描串口 → 发现 COM3 (CH340, 推断 ESP32)
3. [自动编译] 调用 idf.py 编译
4. [自动烧录] 烧录到 COM3
5. [自动监视] 打开串口 115200，实时显示温湿度数据
```

### 示例 2：Arduino LED 闪烁

```
用户: 帮我写个 LED 闪烁

Frok:
1. [代码生成] 生成 Arduino LED Blink
2. [自动检测] 扫描串口 → 发现 COM5 (Arduino Uno)
3. [自动编译] arduino-cli compile
4. [自动烧录] 烧录到 COM5
5. [自动监视] 串口输出 "LED ON/OFF"
```

### 示例 3：STM32 按键中断

```
用户: STM32 按键中断控制 LED

Frok:
1. [代码生成] 生成 STM32 HAL 库按键中断代码
2. [自动检测] 扫描调试器 → 发现 ST-Link
3. [自动编译] arm-none-eabi-gcc 编译
4. [自动烧录] st-flash 烧录
5. [完成] 提示用户按下按键测试
```

## 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frok/embedded.py` | 新增 | 基类 + 工具注册 + 自动检测 |
| `frok/platforms/__init__.py` | 新增 | 平台自动发现 |
| `frok/platforms/arduino.py` | 新增 | Arduino 适配器 |
| `frok/platforms/esp32.py` | 新增 | ESP32 适配器 |
| `frok/platforms/stm32.py` | 新增 | STM32 适配器 |
| `frok/skills/embedded.json` | 新增 | 嵌入式编程技能 |
| `frok/tools.py` | 修改 | 添加 8 个嵌入式工具到 TOOLS_SCHEMA |
| `frok/agent.py` | 修改 | 导入 embedded 模块，注册工具 |
| `requirements.txt` | 修改 | 添加 pyserial |
