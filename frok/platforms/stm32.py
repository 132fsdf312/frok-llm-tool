"""
STM32 平台适配器
基于 arm-none-eabi-gcc 工具链，支持 st-flash 和 openocd 烧录
提供 GPIO、UART、传感器等场景的代码生成（基于 STM32 HAL 库）
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from frok.embedded import CompileResult, UploadResult, EmbeddedPlatform
from frok.platforms import register_platform


# ==================== 代码模板 ====================

TEMPLATES = {
    "gpio": """\
// STM32 GPIO 控制示例
// 自动生成: {description}
// 目标芯片: {chip}

#include "stm32f4xx_hal.h"

// GPIO 引脚定义
#define LED_PORT    {gpio_port}
#define LED_PIN     GPIO_PIN_{gpio_pin}

void SystemClock_Config(void);
static void MX_GPIO_Init(void);

int main(void) {{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();

  while (1) {{
    HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
    HAL_Delay({interval});
  }}
}}

static void MX_GPIO_Init(void) {{
  GPIO_InitTypeDef GPIO_InitStruct = {{0}};

  // 使能 GPIO 时钟
  __HAL_RCC_GPIOA_CLK_ENABLE();

  // 配置 GPIO 引脚
  GPIO_InitStruct.Pin = LED_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LED_PORT, &GPIO_InitStruct);
}}

void SystemClock_Config(void) {{
  // 系统时钟配置（根据实际晶振修改）
  RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};

  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = {pll_m};
  RCC_OscInitStruct.PLL.PLLN = {pll_n};
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  HAL_RCC_OscConfig(&RCC_OscInitStruct);

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                              | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
  HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2);
}}

void SysTick_Handler(void) {{
  HAL_IncTick();
}}
""",

    "uart": """\
// STM32 UART 串口通信示例
// 自动生成: {description}
// 目标芯片: {chip}

#include "stm32f4xx_hal.h"
#include <string.h>
#include <stdio.h>

UART_HandleTypeDef huart{uart_num};

void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART{uart_num}_UART_Init(void);

int main(void) {{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_USART{uart_num}_UART_Init();

  char *msg = "STM32 UART Ready\\r\\n";
  HAL_UART_Transmit(&huart{uart_num}, (uint8_t*)msg, strlen(msg), HAL_MAX_DELAY);

  uint8_t rx_buf[64];

  while (1) {{
    // 接收数据
    if (HAL_UART_Receive(&huart{uart_num}, rx_buf, 1, 100) == HAL_OK) {{
      // 回显
      HAL_UART_Transmit(&huart{uart_num}, rx_buf, 1, HAL_MAX_DELAY);
    }}

    // 定期发送数据
    char tx_buf[64];
    snprintf(tx_buf, sizeof(tx_buf), "Tick: %lu\\r\\n", HAL_GetTick());
    HAL_UART_Transmit(&huart{uart_num}, (uint8_t*)tx_buf, strlen(tx_buf), HAL_MAX_DELAY);
    HAL_Delay({interval});
  }}
}}

static void MX_USART{uart_num}_UART_Init(void) {{
  huart{uart_num}.Instance = USART{uart_num};
  huart{uart_num}.Init.BaudRate = {baudrate};
  huart{uart_num}.Init.WordLength = UART_WORDLENGTH_8B;
  huart{uart_num}.Init.StopBits = UART_STOPBITS_1;
  huart{uart_num}.Init.Parity = UART_PARITY_NONE;
  huart{uart_num}.Init.Mode = UART_MODE_TX_RX;
  huart{uart_num}.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart{uart_num}.Init.OverSampling = UART_OVERSAMPLING_16;
  HAL_UART_Init(&huart{uart_num});
}}

static void MX_GPIO_Init(void) {{
  __HAL_RCC_GPIOA_CLK_ENABLE();
}}

void SystemClock_Config(void) {{
  RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};

  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = {pll_m};
  RCC_OscInitStruct.PLL.PLLN = {pll_n};
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  HAL_RCC_OscConfig(&RCC_OscInitStruct);

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                              | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
  HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2);
}}

void SysTick_Handler(void) {{
  HAL_IncTick();
}}
""",

    "default": """\
// STM32 通用程序
// 自动生成: {description}
// 目标芯片: {chip}

#include "stm32f4xx_hal.h"
#include <string.h>

void SystemClock_Config(void);
static void MX_GPIO_Init(void);

int main(void) {{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();

  {setup_body}

  while (1) {{
    {loop_body}
  }}
}}

static void MX_GPIO_Init(void) {{
  // 使能 GPIOA 时钟
  __HAL_RCC_GPIOA_CLK_ENABLE();
}}

void SystemClock_Config(void) {{
  RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};

  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = {pll_m};
  RCC_OscInitStruct.PLL.PLLN = {pll_n};
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  HAL_RCC_OscConfig(&RCC_OscInitStruct);

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                              | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
  HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2);
}}

void SysTick_Handler(void) {{
  HAL_IncTick();
}}
""",
}


# ==================== 关键词到模板映射 ====================

_KEYWORD_TEMPLATES = {
    "gpio": ["gpio", "led", "blink", "flash", "toggle", "output",
             "gpio", "闪烁", "闪灯", "灯", "输出", "控制", "开关"],
    "uart": ["uart", "serial", "com", "rs232", "串口", "通信", "传输",
             "debug", "printf", "print", "调试", "输出"],
}


# ==================== 常见 STM32 开发板 ====================

_DEFAULT_BOARDS = [
    {
        "fqbn": "stm32f103c8",
        "name": "STM32F103C8T6 (Blue Pill)",
        "description": "Cortex-M3, 72MHz, 64KB Flash, 20KB RAM",
        "chip": "STM32F103C8",
        "family": "stm32f1",
        "pll_m": 8, "pll_n": 72, "pll_p": 2,
    },
    {
        "fqbn": "stm32f103cb",
        "name": "STM32F103CBT6",
        "description": "Cortex-M3, 72MHz, 128KB Flash, 20KB RAM",
        "chip": "STM32F103CB",
        "family": "stm32f1",
        "pll_m": 8, "pll_n": 72, "pll_p": 2,
    },
    {
        "fqbn": "stm32f401cc",
        "name": "STM32F401CCU6 (Black Pill)",
        "description": "Cortex-M4, 84MHz, 256KB Flash, 64KB RAM, FPU",
        "chip": "STM32F401CC",
        "family": "stm32f4",
        "pll_m": 25, "pll_n": 168, "pll_p": 2,
    },
    {
        "fqbn": "stm32f411ce",
        "name": "STM32F411CEU6 (Black Pill V3)",
        "description": "Cortex-M4, 100MHz, 512KB Flash, 128KB RAM, FPU",
        "chip": "STM32F411CE",
        "family": "stm32f4",
        "pll_m": 25, "pll_n": 200, "pll_p": 2,
    },
    {
        "fqbn": "stm32f407vg",
        "name": "STM32F407VG (Discovery)",
        "description": "Cortex-M4, 168MHz, 1MB Flash, 192KB RAM, FPU, DSP",
        "chip": "STM32F407VG",
        "family": "stm32f4",
        "pll_m": 8, "pll_n": 336, "pll_p": 2,
    },
    {
        "fqbn": "stm32f407zg",
        "name": "STM32F407ZGT6",
        "description": "Cortex-M4, 168MHz, 1MB Flash, 192KB RAM, FPU, 144引脚",
        "chip": "STM32F407ZG",
        "family": "stm32f4",
        "pll_m": 8, "pll_n": 336, "pll_p": 2,
    },
    {
        "fqbn": "stm32l476rg",
        "name": "STM32L476RG (Nucleo-64)",
        "description": "Cortex-M4, 80MHz, 1MB Flash, 128KB RAM, 低功耗",
        "chip": "STM32L476RG",
        "family": "stm32l4",
        "pll_m": 8, "pll_n": 160, "pll_p": 2,
    },
    {
        "fqbn": "stm32h743zi",
        "name": "STM32H743ZI (Nucleo-144)",
        "description": "Cortex-M7, 480MHz, 2MB Flash, 1MB RAM, 双精度 FPU",
        "chip": "STM32H743ZI",
        "family": "stm32h7",
        "pll_m": 4, "pll_n": 480, "pll_p": 2,
    },
    {
        "fqbn": "stm32g071rb",
        "name": "STM32G071RB (Nucleo-64)",
        "description": "Cortex-M0+, 64MHz, 128KB Flash, 36KB RAM, 低成本",
        "chip": "STM32G071RB",
        "family": "stm32g0",
        "pll_m": 4, "pll_n": 64, "pll_p": 2,
    },
    {
        "fqbn": "stm32wb55rg",
        "name": "STM32WB55RG (Nucleo)",
        "description": "Cortex-M4+M0+, 64MHz, 1MB Flash, 256KB RAM, BLE 5.0",
        "chip": "STM32WB55RG",
        "family": "stm32wb",
        "pll_m": 8, "pll_n": 64, "pll_p": 2,
    },
]


# ==================== 编译错误解析 ====================

def _parse_compile_errors(stderr: str) -> List[str]:
    """
    从 arm-none-eabi-gcc 编译输出中提取错误信息

    支持格式:
      file:line:col: error: message
      file:line: error: message
      arm-none-eabi-gcc: error: message
    """
    errors = []

    # GCC 标准格式
    gcc_pattern = re.compile(
        r"^(.+?):(\d+)(?::(\d+))?:\s*(error|warning|fatal error):\s*(.+)$",
        re.MULTILINE,
    )
    for match in gcc_pattern.finditer(stderr):
        file_path, line, col, level, message = match.groups()
        col_str = f":{col}" if col else ""
        errors.append(f"[{level}] {file_path}:{line}{col_str}: {message}")

    # linker 错误
    ld_pattern = re.compile(
        r"^(.+?):\s*(undefined reference|multiple definition|cannot find)\s*(.+)$",
        re.MULTILINE,
    )
    for match in ld_pattern.finditer(stderr):
        errors.append(f"[linker] {match.group(0)}")

    # make 错误
    make_pattern = re.compile(r"^make\[.*?\]: \*\*\* \[(.+?)\]\s*(\d+)", re.MULTILINE)
    for match in make_pattern.finditer(stderr):
        if match.group(0) not in errors:
            errors.append(f"[make] {match.group(0)}")

    return errors


# ==================== STM32 平台 ====================

@register_platform
class STM32Platform(EmbeddedPlatform):
    """STM32 平台适配器，基于 arm-none-eabi-gcc 工具链"""

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
        """
        检测工具链是否可用

        要求:
        - arm-none-eabi-gcc (编译)
        - st-flash 或 openocd (烧录，至少一个)
        """
        has_compiler = shutil.which("arm-none-eabi-gcc") is not None
        has_flasher = (
            shutil.which("st-flash") is not None
            or shutil.which("openocd") is not None
        )
        return has_compiler and has_flasher

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

        # 获取开发板参数
        board_id = spec.get("board", "")
        board_info = self._find_board(board_id)
        chip = board_info.get("chip", "STM32F401CC")
        pll_m = board_info.get("pll_m", 25)
        pll_n = board_info.get("pll_n", 168)

        if template_name == "gpio":
            return TEMPLATES["gpio"].format(
                description=description,
                chip=chip,
                gpio_port=self._extract_gpio_port(dl),
                gpio_pin=self._extract_gpio_pin(dl),
                interval=self._extract_interval(dl, default=500),
                pll_m=pll_m,
                pll_n=pll_n,
            )

        if template_name == "uart":
            return TEMPLATES["uart"].format(
                description=description,
                chip=chip,
                uart_num=self._extract_uart_num(dl),
                baudrate=self._extract_baudrate(dl),
                interval=self._extract_interval(dl, default=1000),
                pll_m=pll_m,
                pll_n=pll_n,
            )

        # 默认模板
        setup_body, loop_body = self._generate_default_body(dl)
        return TEMPLATES["default"].format(
            description=description,
            chip=chip,
            setup_body=setup_body,
            loop_body=loop_body,
            pll_m=pll_m,
            pll_n=pll_n,
        )

    def compile(self, sketch_path: str, board: str = None) -> CompileResult:
        """
        编译 STM32 固件

        优先使用 make (Makefile 项目)，否则直接调用 arm-none-eabi-gcc。

        Args:
            sketch_path: .c/.cpp 文件路径或项目目录
            board: 开发板型号，如 stm32f103c8
        """
        if not self.detect():
            missing = []
            if not shutil.which("arm-none-eabi-gcc"):
                missing.append("arm-none-eabi-gcc")
            if not shutil.which("st-flash") and not shutil.which("openocd"):
                missing.append("st-flash / openocd")
            return CompileResult(
                success=False,
                output=f"STM32 工具链未安装，缺少: {', '.join(missing)}"
            )

        project = Path(sketch_path)

        # 如果是目录且包含 Makefile，使用 make
        if project.is_dir() and (project / "Makefile").exists():
            return self._compile_with_make(project)

        # 如果是单个源文件，直接编译
        source = self._resolve_source_path(project)
        if not source:
            return CompileResult(
                success=False,
                output=f"未找到 .c/.cpp 源文件: {sketch_path}"
            )

        return self._compile_single(source, board)

    def upload(self, sketch_path: str, port: str = None, board: str = None) -> UploadResult:
        """
        烧录固件到 STM32

        优先使用 st-flash，不可用时回退到 openocd。

        Args:
            sketch_path: .bin/.hex 固件路径，或项目目录（自动查找固件）
            port: ST-Link 设备序号（多调试器时使用），一般留空
            board: 开发板型号
        """
        if not self.detect():
            return UploadResult(success=False, output="STM32 工具链未安装")

        firmware = self._resolve_firmware_path(sketch_path)
        if not firmware:
            return UploadResult(
                success=False,
                output=f"未找到固件文件 (.bin/.hex): {sketch_path}"
            )

        # 优先 st-flash
        if shutil.which("st-flash"):
            return self._upload_with_st_flash(firmware, port)

        # 回退 openocd
        if shutil.which("openocd"):
            return self._upload_with_openocd(firmware, board)

        return UploadResult(success=False, output="st-flash 和 openocd 均不可用")

    def list_boards(self) -> List[Dict]:
        """返回常见 STM32 开发板列表"""
        return _DEFAULT_BOARDS

    # ==================== 编译方法 ====================

    def _compile_with_make(self, project_dir: Path) -> CompileResult:
        """使用 Makefile 编译"""
        args = ["make", "-j4"]
        returncode, stdout, stderr = self._run_command(
            args, cwd=str(project_dir), timeout=300
        )

        if returncode == 0:
            firmware = self._find_build_output(project_dir)
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

    def _compile_single(self, source: Path, board: str = None) -> CompileResult:
        """编译单个源文件"""
        board_info = self._find_board(board or "")
        family = board_info.get("family", "stm32f4")
        chip = board_info.get("chip", "STM32F401CC")

        output = source.with_suffix(".elf")

        # 构建编译参数
        args = [
            "arm-none-eabi-gcc",
            "-mcpu=cortex-m4" if "f4" in family or "l4" in family else "-mcpu=cortex-m3",
            "-mthumb",
            "-mfloat-abi=hard" if "f4" in family else "-mfloat-abi=soft",
            "-mfpu=fpv4-sp-d16" if "f4" in family else "",
            "-Os",
            "-Wall",
            "-std=c11",
            f"-D{chip}",
            "-I.",
            "-c", str(source),
            "-o", str(source.with_suffix(".o")),
        ]
        # 清除空字符串
        args = [a for a in args if a]

        returncode, stdout, stderr = self._run_command(args, timeout=120)
        if returncode != 0:
            errors = _parse_compile_errors(stderr)
            return CompileResult(
                success=False,
                output=stderr.strip(),
                errors=errors if errors else [stderr.strip()],
            )

        # 链接
        obj_file = source.with_suffix(".o")
        link_args = [
            "arm-none-eabi-gcc",
            "-mcpu=cortex-m4" if "f4" in family or "l4" in family else "-mcpu=cortex-m3",
            "-mthumb",
            "-mfloat-abi=hard" if "f4" in family else "-mfloat-abi=soft",
            "-mfpu=fpv4-sp-d16" if "f4" in family else "",
            f"-Wl,-Map={source.with_suffix('.map')}",
            str(obj_file),
            "-o", str(output),
        ]
        link_args = [a for a in link_args if a]

        returncode, stdout, stderr = self._run_command(link_args, timeout=60)
        if returncode != 0:
            errors = _parse_compile_errors(stderr)
            return CompileResult(
                success=False,
                output=stderr.strip(),
                errors=errors if errors else [stderr.strip()],
            )

        # 生成 .bin 和 .hex
        bin_path = source.with_suffix(".bin")
        hex_path = source.with_suffix(".hex")

        self._run_command([
            "arm-none-eabi-objcopy", "-O", "binary", str(output), str(bin_path)
        ])
        self._run_command([
            "arm-none-eabi-objcopy", "-O", "ihex", str(output), str(hex_path)
        ])

        firmware = str(bin_path) if bin_path.exists() else str(hex_path)
        return CompileResult(
            success=True,
            output=f"编译成功: {output.name}",
            firmware_path=firmware,
        )

    # ==================== 烧录方法 ====================

    def _upload_with_st_flash(self, firmware: str, serial: str = None) -> UploadResult:
        """使用 st-flash 烧录"""
        fw = Path(firmware)
        args = ["st-flash"]

        if serial:
            args.extend(["--serial", serial])

        # st-flash 自动识别 .bin / .hex
        if fw.suffix == ".hex":
            args.extend(["--format", "ihex", "write", str(fw)])
        else:
            args.extend(["write", str(fw), "0x08000000"])

        returncode, stdout, stderr = self._run_command(args, timeout=60)

        if returncode == 0:
            return UploadResult(
                success=True,
                output=stdout.strip() or f"已通过 st-flash 烧录: {fw.name}",
            )
        else:
            return UploadResult(success=False, output=stderr.strip())

    def _upload_with_openocd(self, firmware: str, board: str = None) -> UploadResult:
        """使用 openocd 烧录"""
        fw = Path(firmware)
        board_info = self._find_board(board or "")
        family = board_info.get("family", "stm32f4")

        # 选择 openocd 目标配置
        target_cfg = self._openocd_target_cfg(family)

        args = [
            "openocd",
            "-f", "interface/stlink.cfg",
            "-f", f"target/{target_cfg}",
            "-c", f"program {fw} verify reset exit",
        ]

        returncode, stdout, stderr = self._run_command(args, timeout=60)

        if returncode == 0:
            return UploadResult(
                success=True,
                output=stdout.strip() or f"已通过 openocd 烧录: {fw.name}",
            )
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

    def _find_board(self, board_id: str) -> Dict:
        """查找开发板信息"""
        if not board_id:
            return _DEFAULT_BOARDS[0]  # 默认 Blue Pill

        bl = board_id.lower()
        for b in _DEFAULT_BOARDS:
            if bl in b["fqbn"] or bl in b["name"].lower() or bl in b["chip"].lower():
                return b

        return _DEFAULT_BOARDS[0]

    def _extract_gpio_port(self, description: str) -> str:
        """从描述中提取 GPIO 端口 (GPIOA-GPIOF)"""
        match = re.search(r"gpio\s*([a-f])", description, re.IGNORECASE)
        if match:
            return f"GPIO{match.group(1).upper()}"

        # 匹配 "PA0", "PB13" 等
        match = re.search(r"\bp([a-f])\d+", description, re.IGNORECASE)
        if match:
            return f"GPIO{match.group(1).upper()}"

        return "GPIOA"

    def _extract_gpio_pin(self, description: str) -> str:
        """从描述中提取 GPIO 引脚号 (0-15)"""
        # 匹配 "PA5", "PB13", "pin 13", "GPIO 5"
        match = re.search(r"\bp[a-f](\d{1,2})\b", description, re.IGNORECASE)
        if match:
            pin = int(match.group(1))
            if 0 <= pin <= 15:
                return str(pin)

        match = re.search(r"(?:pin|gpio)\s*(\d{1,2})", description, re.IGNORECASE)
        if match:
            pin = int(match.group(1))
            if 0 <= pin <= 15:
                return str(pin)

        return "5"  # 默认 PA5

    def _extract_uart_num(self, description: str) -> str:
        """从描述中提取 UART 编号"""
        match = re.search(r"uart\s*(\d+)", description, re.IGNORECASE)
        if match:
            return match.group(1)

        match = re.search(r"usart\s*(\d+)", description, re.IGNORECASE)
        if match:
            return match.group(1)

        match = re.search(r"com\s*(\d+)", description, re.IGNORECASE)
        if match:
            return match.group(1)

        return "1"  # 默认 USART1

    def _extract_baudrate(self, description: str) -> int:
        """从描述中提取波特率"""
        match = re.search(r"(\d{3,6})\s*(?:baud|bps|波特)", description, re.IGNORECASE)
        if match:
            rate = int(match.group(1))
            if rate in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
                return rate

        # 匹配裸数字如 "115200"
        match = re.search(r"\b(9600|19200|38400|57600|115200|230400|460800|921600)\b", description)
        if match:
            return int(match.group(1))

        return 115200

    def _extract_interval(self, description: str, default: int = 500) -> int:
        """从描述中提取间隔时间（毫秒）"""
        match = re.search(r"(\d+(?:\.\d+)?)\s*(ms|毫秒|s|秒)", description, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()
            if unit in ("s", "秒"):
                return int(value * 1000)
            return int(value)
        return default

    def _generate_default_body(self, description: str) -> Tuple[str, str]:
        """为默认模板生成 setup/loop 内容"""
        setup_lines = []
        loop_lines = []

        # LED 闪烁
        if any(kw in description for kw in ("led", "blink", "toggle", "闪烁", "闪灯")):
            pin = self._extract_gpio_pin(description)
            port = self._extract_gpio_port(description)
            setup_lines.extend([
                f"GPIO_InitTypeDef GPIO_InitStruct = {{0}};",
                f"GPIO_InitStruct.Pin = GPIO_PIN_{pin};",
                f"GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;",
                f"GPIO_InitStruct.Pull = GPIO_NOPULL;",
                f"GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;",
                f"HAL_GPIO_Init({port}, &GPIO_InitStruct);",
            ])
            loop_lines.extend([
                f"HAL_GPIO_TogglePin({port}, GPIO_PIN_{pin});",
                "HAL_Delay(500);",
            ])

        # 串口输出
        if any(kw in description for kw in ("print", "uart", "serial", "串口", "输出")):
            loop_lines.extend([
                '// UART 输出需要先初始化 UART 外设',
                '// HAL_UART_Transmit(&huart1, (uint8_t*)"Hello\\r\\n", 7, HAL_MAX_DELAY);',
                "HAL_Delay(1000);",
            ])

        # ADC 读取
        if any(kw in description for kw in ("adc", "analog", "read", "模拟", "读取")):
            setup_lines.extend([
                "// ADC 初始化代码",
                "// MX_ADC1_Init();",
            ])
            loop_lines.extend([
                "// HAL_ADC_Start(&hadc1);",
                "// uint32_t value = HAL_ADC_GetValue(&hadc1);",
                "HAL_Delay(100);",
            ])

        # PWM
        if any(kw in description for kw in ("pwm", "dim", "brightness", "亮度", "调光")):
            setup_lines.extend([
                "// TIM PWM 初始化代码",
                "// MX_TIM2_Init();",
                "// HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1);",
            ])
            loop_lines.extend([
                "// __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, duty);",
                "HAL_Delay(10);",
            ])

        # 兜底
        if not loop_lines:
            loop_lines.extend([
                "HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);",
                "HAL_Delay(1000);",
            ])

        return (
            "\n  ".join(setup_lines) if setup_lines else "// setup code",
            "\n  ".join(loop_lines),
        )

    def _resolve_source_path(self, path: Path) -> Path:
        """解析源文件路径"""
        if path.is_file() and path.suffix in (".c", ".cpp", ".s"):
            return path

        if path.is_dir():
            # 查找 main.c / main.cpp
            for name in ("main.c", "main.cpp"):
                candidate = path / name
                if candidate.exists():
                    return candidate

            # 查找任意 .c 文件
            c_files = list(path.glob("*.c"))
            if c_files:
                return c_files[0]

        return None

    def _resolve_firmware_path(self, path: str) -> str:
        """解析固件文件路径"""
        p = Path(path)

        if p.is_file() and p.suffix in (".bin", ".hex", ".elf"):
            return str(p)

        if p.is_dir():
            # 查找构建输出
            build_dir = p / "build"
            search_dirs = [build_dir, p] if build_dir.exists() else [p]

            for d in search_dirs:
                for ext in ("*.bin", "*.hex"):
                    files = list(d.glob(ext))
                    if files:
                        return str(files[0])

                # 查找 .elf 并转换
                elf_files = list(d.glob("*.elf"))
                if elf_files:
                    return str(elf_files[0])

        return ""

    def _find_build_output(self, project_dir: Path) -> str:
        """查找 Makefile 构建输出"""
        build_dir = project_dir / "build"
        search_dirs = [build_dir, project_dir] if build_dir.exists() else [project_dir]

        for d in search_dirs:
            for ext in ("*.bin", "*.hex", "*.elf"):
                files = list(d.glob(ext))
                if files:
                    return str(files[0])

        return ""

    def _openocd_target_cfg(self, family: str) -> str:
        """根据芯片系列返回 openocd 目标配置文件名"""
        cfg_map = {
            "stm32f0": "stm32f0x.cfg",
            "stm32f1": "stm32f1x.cfg",
            "stm32f2": "stm32f2x.cfg",
            "stm32f3": "stm32f3x.cfg",
            "stm32f4": "stm32f4x.cfg",
            "stm32f7": "stm32f7x.cfg",
            "stm32l0": "stm32l0.cfg",
            "stm32l1": "stm32l1.cfg",
            "stm32l4": "stm32l4x.cfg",
            "stm32g0": "stm32g0x.cfg",
            "stm32g4": "stm32g4x.cfg",
            "stm32h7": "stm32h7x.cfg",
            "stm32wb": "stm32wbx.cfg",
        }
        return cfg_map.get(family, "stm32f4x.cfg")
