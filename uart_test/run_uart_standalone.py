#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART工具独立启动脚本
确保在正确的目录下运行，解决配置文件路径问题
"""

import os
import sys

def main():
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 切换到UART工具目录
    os.chdir(script_dir)
    print(f"工作目录已切换到: {os.getcwd()}")
    
    # 检查配置文件是否存在
    config_files = [
        'uart_command_set.json',
        'label.json'
    ]
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"✓ 配置文件存在: {config_file}")
        else:
            print(f"✗ 配置文件不存在: {config_file}")
    
    # 导入并运行UART工具
    try:
        from uart_gui import UARTTestGUI
        import tkinter as tk
        
        # 创建主窗口
        root = tk.Tk()
        app = UARTTestGUI(root)
        
        # 设置窗口关闭事件处理
        def on_closing():
            try:
                if hasattr(app, 'uart') and app.uart:
                    app.uart.close()
            except:
                pass
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        print("UART工具启动成功！")
        root.mainloop()
        
    except ImportError as e:
        print(f"导入UART工具失败: {e}")
        print("请确保所有依赖模块都在正确的位置")
    except Exception as e:
        print(f"UART工具运行失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 