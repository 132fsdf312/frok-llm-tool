#!/usr/bin/env python3
"""串口通信示例 - 与单片机通信的原理"""

import serial
import serial.tools.list_ports
import time

def list_serial_ports():
    """列出所有可用的串口设备"""
    ports = serial.tools.list_ports.comports()
    print("可用串口设备:")
    print("-" * 50)
    for port in ports:
        print(f"  设备: {port.device}")
        print(f"  描述: {port.description}")
        print(f"  硬件ID: {port.hwid}")
        print("-" * 50)
    return ports

def send_command(port, baudrate=115200, command="LED_ON"):
    """向单片机发送命令"""
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"已连接到 {port}, 波特率: {baudrate}")
        
        # 发送命令
        ser.write((command + "\n").encode())
        print(f"发送命令: {command}")
        
        # 等待响应
        time.sleep(0.1)
        response = ser.readline().decode().strip()
        print(f"收到响应: {response}")
        
        ser.close()
        return response
    except Exception as e:
        print(f"通信错误: {e}")
        return None

# 串口通信参数说明
SERIAL_CONFIG = {
    "波特率": [9600, 19200, 38400, 57600, 115200],
    "数据位": [5, 6, 7, 8],
    "停止位": [1, 1.5, 2],
    "校验位": ["None", "Even", "Odd"]
}

if __name__ == "__main__":
    print("=" * 60)
    print("单片机串口通信演示")
    print("=" * 60)
    
    print("\n【通信原理】")
    print("1. 通过 USB 转 TTL 模块连接电脑和单片机")
    print("2. 使用 pyserial 库进行串口通信")
    print("3. 发送 ASCII 命令，接收单片机响应")
    
    print("\n【常用通信协议】")
    print("- UART (串口): 最简单，2线(TX/RX)")
    print("- SPI: 高速，4线(MOSI/MISO/SCK/CS)")
    print("- I2C: 多设备，2线(SDA/SCL)")
    
    print("\n【串口配置参数】")
    for key, values in SERIAL_CONFIG.items():
        print(f"  {key}: {values}")
    
    print("\n正在扫描串口设备...")
    list_serial_ports()
