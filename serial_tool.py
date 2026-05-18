#!/usr/bin/env python3
"""单片机检测、烧录和通信一体化工具"""

import serial
import serial.tools.list_ports
import subprocess
import time

class DeviceDetector:
    KNOWN_DEVICES = {
        '0x2341:0x0043': 'Arduino Uno',
        '0x2341:0x0042': 'Arduino Mega',
        '0x10C4:0xEA60': 'ESP32/ESP8266',
        '0x0483:0x5740': 'STM32',
        '0x1A86:0x7523': 'CH340',
    }
    
    @staticmethod
    def scan():
        ports = serial.tools.list_ports.comports()
        devices = []
        for p in ports:
            vid_pid = f"{hex(p.vid)}:{hex(p.pid)}" if p.vid else 'N/A'
            device_type = DeviceDetector.KNOWN_DEVICES.get(vid_pid, '未知设备')
            if 'bluetooth' in p.description.lower():
                device_type = '蓝牙串口'
            devices.append({'port': p.device, 'type': device_type, 'desc': p.description})
            print(f"  {p.device} - {device_type}: {p.description}")
        return devices


class SerialComm:
    def __init__(self, port, baud=115200):
        self.port = port
        self.baud = baud
        self.ser = None
    
    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=2)
            time.sleep(2)
            print(f"[OK] 已连接 {self.port}")
            return True
        except Exception as e:
            print(f"[ERR] {e}")
            return False
    
    def send(self, cmd):
        if self.ser:
            self.ser.write((cmd + '\n').encode())
            time.sleep(0.5)
            return self.ser.readline().decode().strip()
    
    def close(self):
        if self.ser:
            self.ser.close()


def upload_arduino(sketch, port, board='arduino:avr:uno'):
    cmd = ['arduino-cli', 'upload', '--port', port, '--fqbn', board, sketch]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print('OK' if result.returncode == 0 else f'ERR: {result.stderr}')
    return result.returncode == 0


if __name__ == '__main__':
    print('='*50)
    print('单片机检测工具')
    print('='*50)
    DeviceDetector.scan()
