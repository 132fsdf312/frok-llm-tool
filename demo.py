#!/usr/bin/env python3
# Frok Code 示例文件

import datetime
import sys

def main():
    print("="*50)
    print("欢迎使用 Frok Code 智能编程助手")
    print("="*50)
    
    # 显示当前时间
    now = datetime.datetime.now()
    print(f"\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 显示系统信息
    print(f"\nPython 版本: {sys.version}")
    print(f"操作系统: {sys.platform}")
    
    # 简单计算示例
    print("\n" + "="*50)
    print("示例计算:")
    print("="*50)
    
    a = 10
    b = 20
    print(f"{a} + {b} = {a + b}")
    print(f"{a} * {b} = {a * b}")
    print(f"{a} / {b} = {a / b:.2f}")
    
    # 列表操作示例
    fruits = ["苹果", "香蕉", "橙子", "葡萄", "西瓜"]
    print(f"\n水果列表: {fruits}")
    print(f"水果数量: {len(fruits)}")
    print(f"第一种水果: {fruits[0]}")
    
    # 函数示例
    print("\n" + "="*50)
    print("函数示例:")
    print("="*50)
    
    def calculate_average(numbers):
        """计算平均值"""
        if not numbers:
            return 0
        return sum(numbers) / len(numbers)
    
    scores = [85, 92, 78, 90, 88]
    average = calculate_average(scores)
    print(f"分数列表: {scores}")
    print(f"平均分: {average:.2f}")
    
    print("\n" + "="*50)
    print("演示完成！")
    print("="*50)

if __name__ == "__main__":
    main()
