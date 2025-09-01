#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一工具管理器 - 集成CAN、Modbus、UART三个工具
使用标签页方式，每个工具占用一个标签页
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
import threading
import traceback

# 导入三个工具的主类
can_tool_available = False
modbus_tool_available = False
uart_tool_available = False

# 添加工具目录到Python路径
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))

# 添加各个工具目录到Python路径
tool_dirs = [
    os.path.join(current_dir, 'can_tool'),
    os.path.join(current_dir, 'mobus_tool'),
    os.path.join(current_dir, 'uart_test')
]

for tool_dir in tool_dirs:
    if tool_dir not in sys.path:
        sys.path.insert(0, tool_dir)
        print(f"添加路径: {tool_dir}")

try:
    # 尝试导入完整版CAN工具
    import can_tool.can_host_computer as can_host_computer
    from can_tool.can_host_computer import CANHostComputer, create_embedded_instance as create_can_embedded
    can_tool_available = True
    print("完整版CAN工具导入成功")
except ImportError as e:
    print(f"CAN工具导入失败: {e}")

try:
    import mobus_tool.main as modbus_main
    from mobus_tool.main import SunSpecGUI, create_embedded_instance as create_modbus_embedded
    modbus_tool_available = True
    print("Modbus工具导入成功")
except ImportError as e:
    print(f"Modbus工具导入失败: {e}")

try:
    import uart_test.uart_gui as uart_gui
    from uart_test.uart_gui import UARTTestGUI, create_embedded_instance as create_uart_embedded
    uart_tool_available = True
    print("UART工具导入成功")
except ImportError as e:
    print(f"UART工具导入失败: {e}")

if not any([can_tool_available, modbus_tool_available, uart_tool_available]):
    print("警告：没有可用的工具模块")
    print("请确保三个工具目录都在当前路径下")

class UnifiedToolManager:
    """统一工具管理器"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PU工具集 - 统一管理界面")
        
        # 设置窗口大小和位置
        window_width = 1600
        window_height = 1000
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(1200, 800)
        
        # 设置窗口图标
        self.set_window_icon()
        
        # 工具实例字典
        self.tools = {}
        
        # 创建主界面
        self.create_main_interface()
        
        # 初始化工具
        self.initialize_tools()
        
        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def set_window_icon(self):
        """设置窗口图标"""
        try:
            # 尝试从各个工具目录获取图标
            icon_paths = [
                'can_tool/BQC.ico',
                'mobus_tool/BQC.ico', 
                'uart_test/BQC.ico'
            ]
            
            for icon_path in icon_paths:
                if os.path.exists(icon_path):
                    self.root.iconbitmap(icon_path)
                    break
        except Exception as e:
            print(f"设置窗口图标失败: {e}")
    
    def create_main_interface(self):
        """创建主界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题标签
        title_label = ttk.Label(main_frame, text="PU工具集 - 统一管理界面", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 10))
        
        # 创建标签页容器
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪 - 请选择工具标签页")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 工具状态指示器
        self.create_tool_status_indicator(main_frame)
        
        # 统一的语言切换控件
        self.create_unified_language_control(main_frame)
    
    def create_tool_status_indicator(self, parent_frame):
        """创建工具状态指示器"""
        status_frame = ttk.LabelFrame(parent_frame, text="工具状态", padding="5")
        status_frame.pack(fill="x", pady=(0, 10))
        
        # 创建状态标签
        self.can_status_label = ttk.Label(status_frame, text="CAN工具: 未初始化", foreground="orange")
        self.can_status_label.pack(side="left", padx=10)
        
        self.modbus_status_label = ttk.Label(status_frame, text="Modbus工具: 未初始化", foreground="orange")
        self.modbus_status_label.pack(side="left", padx=10)
        
        self.uart_status_label = ttk.Label(status_frame, text="UART工具: 未初始化", foreground="orange")
        self.uart_status_label.pack(side="left", padx=10)
    
    def create_disabled_tab(self, tab_name, message):
        """创建禁用的标签页"""
        try:
            # 创建标签页
            disabled_frame = ttk.Frame(self.notebook)
            self.notebook.add(disabled_frame, text=tab_name)
            
            # 显示禁用信息
            info_label = ttk.Label(disabled_frame, text=message, 
                                  font=("Arial", 12), foreground="red")
            info_label.pack(expand=True)
            
            # 添加说明
            desc_label = ttk.Label(disabled_frame, 
                                  text="请检查模块依赖和配置文件",
                                  font=("Arial", 10))
            desc_label.pack(pady=(10, 0))
            
        except Exception as e:
            print(f"创建禁用标签页失败: {e}")
    
    def create_unified_language_control(self, parent_frame):
        """创建统一的语言切换控件"""
        lang_frame = ttk.LabelFrame(parent_frame, text="语言设置", padding="5")
        lang_frame.pack(fill="x", pady=(0, 10))
        
        # 语言选择
        ttk.Label(lang_frame, text="语言/Language:").pack(side=tk.LEFT, padx=(0, 5))
        self.lang_var = tk.StringVar(value="zh")
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.lang_var, 
                                 values=["zh", "en"], state="readonly", width=8)
        lang_combo.pack(side=tk.LEFT, padx=(0, 5))
        lang_combo.bind("<<ComboboxSelected>>", self.on_language_change)
        
        # 语言切换按钮
        self.lang_btn = ttk.Button(lang_frame, text="切换语言", command=self.toggle_language)
        self.lang_btn.pack(side=tk.LEFT, padx=(10, 0))
    
    def on_language_change(self, event=None):
        """语言选择改变事件"""
        selected_lang = self.lang_var.get()
        self.change_all_tools_language(selected_lang)
    
    def toggle_language(self):
        """切换语言"""
        current_lang = self.lang_var.get()
        new_lang = "en" if current_lang == "zh" else "zh"
        self.lang_var.set(new_lang)
        self.change_all_tools_language(new_lang)
    
    def change_all_tools_language(self, language):
        """改变所有工具的语言"""
        try:
            print(f"开始切换语言到: {language}")
            
            # 改变CAN工具语言
            if 'can' in self.tools and self.tools['can'].can_tool:
                print("正在切换CAN工具语言...")
                if hasattr(self.tools['can'].can_tool, 'set_language'):
                    # 使用新的set_language方法
                    self.tools['can'].can_tool.set_language(language)
                    print("CAN工具语言切换完成")
                elif hasattr(self.tools['can'].can_tool, 'lang_var'):
                    # 备用方法
                    self.tools['can'].can_tool.lang_var.set(language)
                    if hasattr(self.tools['can'].can_tool, 'refresh_ui_language'):
                        self.tools['can'].can_tool.refresh_ui_language()
                        print("CAN工具语言切换完成（备用方法）")
                    else:
                        print("CAN工具没有refresh_ui_language方法")
                else:
                    print("CAN工具没有语言设置方法")
            
            # 改变Modbus工具语言
            if 'modbus' in self.tools and self.tools['modbus'].modbus_tool:
                print("正在切换Modbus工具语言...")
                if hasattr(self.tools['modbus'].modbus_tool, 'set_language'):
                    # 使用新的set_language方法
                    self.tools['modbus'].modbus_tool.set_language(language)
                    print("Modbus工具语言切换完成")
                elif hasattr(self.tools['modbus'].modbus_tool, 'language_manager'):
                    # 备用方法
                    self.tools['modbus'].modbus_tool.language_manager.set_language(language)
                    if hasattr(self.tools['modbus'].modbus_tool, 'update_interface_text'):
                        self.tools['modbus'].modbus_tool.update_interface_text()
                        print("Modbus工具语言切换完成（备用方法）")
                    else:
                        print("Modbus工具没有update_interface_text方法")
                else:
                    print("Modbus工具没有语言设置方法")
            
            # 改变UART工具语言
            if 'uart' in self.tools and self.tools['uart'].uart_tool:
                print("正在切换UART工具语言...")
                if hasattr(self.tools['uart'].uart_tool, 'set_language'):
                    # 使用新的set_language方法
                    self.tools['uart'].uart_tool.set_language(language)
                    print("UART工具语言切换完成")
                elif hasattr(self.tools['uart'].uart_tool, 'label_manager'):
                    # 备用方法
                    self.tools['uart'].uart_tool.label_manager.set_language(language)
                    if hasattr(self.tools['uart'].uart_tool, 'update_interface_language'):
                        self.tools['uart'].uart_tool.update_interface_language()
                        print("UART工具语言切换完成（备用方法）")
                    elif hasattr(self.tools['uart'].uart_tool, 'recreate_items'):
                        # 如果UART工具没有update_interface_language方法，尝试重新创建项目
                        self.tools['uart'].uart_tool.recreate_items()
                        print("UART工具通过recreate_items切换语言完成")
                    else:
                        print("UART工具没有语言更新方法")
                else:
                    print("UART工具没有语言设置方法")
            
            # 强制刷新界面
            self.root.update_idletasks()
            
            self.status_var.set(f"语言已切换到: {language}")
            print(f"所有工具语言切换完成: {language}")
            
        except Exception as e:
            print(f"改变语言时出错: {e}")
            import traceback
            traceback.print_exc()
            self.status_var.set(f"语言切换失败: {str(e)}")
    
    def initialize_tools(self):
        """初始化三个工具"""
        try:
            tools_initialized = 0
            
            # 初始化CAN工具
            if can_tool_available:
                self.init_can_tool()
                tools_initialized += 1
                self.can_status_label.config(text="CAN工具: 已加载", foreground="green")
            else:
                self.create_disabled_tab("CAN工具", "CAN工具模块不可用")
                self.can_status_label.config(text="CAN工具: 不可用", foreground="red")
            
            # 初始化Modbus工具
            if modbus_tool_available:
                self.init_modbus_tool()
                tools_initialized += 1
                self.modbus_status_label.config(text="Modbus工具: 已加载", foreground="green")
            else:
                self.create_disabled_tab("Modbus工具", "Modbus工具模块不可用")
                self.modbus_status_label.config(text="Modbus工具: 不可用", foreground="red")
            
            # 初始化UART工具
            if uart_tool_available:
                self.init_uart_tool()
                tools_initialized += 1
                self.uart_status_label.config(text="UART工具: 已加载", foreground="green")
            else:
                self.create_disabled_tab("UART工具", "UART工具模块不可用")
                self.uart_status_label.config(text="UART工具: 不可用", foreground="red")
            
            if tools_initialized > 0:
                self.status_var.set(f"{tools_initialized}个工具初始化完成")
            else:
                self.status_var.set("没有可用的工具")
                messagebox.showwarning("警告", "没有可用的工具模块")
            
        except Exception as e:
            error_msg = f"工具初始化失败: {str(e)}"
            self.status_var.set(error_msg)
            messagebox.showerror("初始化错误", error_msg)
            print(traceback.format_exc())
    
    def init_can_tool(self):
        """初始化CAN工具"""
        try:
            # 创建CAN工具的标签页
            can_frame = ttk.Frame(self.notebook)
            self.notebook.add(can_frame, text="CAN工具")
            
            # 创建CAN工具实例（使用嵌入模式）
            can_tool = CANToolWrapper(can_frame)
            self.tools['can'] = can_tool
            
            self.status_var.set("CAN工具初始化完成")
            
        except Exception as e:
            error_msg = f"CAN工具初始化失败: {str(e)}"
            self.status_var.set(error_msg)
            print(f"CAN工具错误: {error_msg}")
            print(traceback.format_exc())
    
    def init_modbus_tool(self):
        """初始化Modbus工具"""
        try:
            # 创建Modbus工具的标签页
            modbus_frame = ttk.Frame(self.notebook)
            self.notebook.add(modbus_frame, text="Modbus工具")
            
            # 创建Modbus工具实例
            modbus_tool = ModbusToolWrapper(modbus_frame, self)
            self.tools['modbus'] = modbus_tool
            
            self.status_var.set("Modbus工具初始化完成")
            
        except Exception as e:
            error_msg = f"Modbus工具初始化失败: {str(e)}"
            self.status_var.set(error_msg)
            print(f"Modbus工具错误: {error_msg}")
            print(traceback.format_exc())
            # 添加错误显示到界面
            self.create_disabled_tab("Modbus工具", f"Modbus工具初始化失败:\n{str(e)}")
    
    def init_uart_tool(self):
        """初始化UART工具"""
        try:
            # 创建UART工具的标签页
            uart_frame = ttk.Frame(self.notebook)
            self.notebook.add(uart_frame, text="UART工具")
            
            # 创建UART工具实例
            uart_tool = UARTToolWrapper(uart_frame, self)
            self.tools['uart'] = uart_tool
            
            self.status_var.set("UART工具初始化完成")
            
        except Exception as e:
            error_msg = f"UART工具初始化失败: {str(e)}"
            self.status_var.set(error_msg)
            print(f"UART工具错误: {error_msg}")
            print(traceback.format_exc())
    
    def on_closing(self):
        """窗口关闭事件处理"""
        try:
            # 关闭所有工具
            for tool_name, tool in self.tools.items():
                try:
                    if hasattr(tool, 'cleanup'):
                        tool.cleanup()
                    elif hasattr(tool, 'disconnect'):
                        tool.disconnect()
                except Exception as e:
                    print(f"关闭{tool_name}工具时出错: {e}")
            
            # 销毁主窗口
            self.root.destroy()
            
        except Exception as e:
            print(f"关闭程序时出错: {e}")
            self.root.destroy()
    
    def run(self):
        """运行主程序"""
        try:
            self.root.mainloop()
        except Exception as e:
            print(f"主程序运行错误: {e}")
            print(traceback.format_exc())


class CANToolWrapper:
    """CAN工具包装器"""
    
    def __init__(self, parent_frame):
        self.parent_frame = parent_frame
        self.can_tool = None
        self.init_can_tool()
    
    def init_can_tool(self):
        """初始化CAN工具"""
        try:
            # 创建CAN工具实例（使用嵌入模式）
            self.can_tool = create_can_embedded(self.parent_frame)
            print("CAN工具实例创建成功")
            
            # 检查工具是否成功创建
            if self.can_tool and hasattr(self.can_tool, 'main_frame'):
                print("CAN工具界面创建成功")
                # 工具已经直接使用传入的父框架，无需重新打包
            else:
                print("CAN工具界面创建失败，使用简化界面")
                self.create_simple_can_interface()
                
        except Exception as e:
            # 如果初始化失败，显示错误信息
            error_label = ttk.Label(self.parent_frame, 
                                  text=f"CAN工具初始化失败:\n{str(e)}",
                                  foreground="red")
            error_label.pack(expand=True)
            print(f"CAN工具初始化错误: {e}")
    
    def create_simple_can_interface(self):
        """创建简化的CAN工具界面"""
        try:
            # 创建标题
            title_label = ttk.Label(self.parent_frame, text="CAN工具", 
                                   font=("Arial", 14, "bold"))
            title_label.pack(pady=(10, 20))
            
            # 创建说明标签
            info_label = ttk.Label(self.parent_frame, 
                                  text="CAN工具已加载成功！\n\n由于界面嵌入技术限制，建议使用独立模式运行此工具以获得完整功能。\n\n点击下方按钮启动独立CAN工具。",
                                  font=("Arial", 10), justify="center")
            info_label.pack(expand=True, pady=20)
            
            # 创建启动按钮
            launch_btn = ttk.Button(self.parent_frame, text="启动独立CAN工具", 
                                   command=self.launch_standalone_can)
            launch_btn.pack(pady=20)
            
        except Exception as e:
            print(f"创建简化CAN界面失败: {e}")
    
    def launch_standalone_can(self):
        """启动独立的CAN工具"""
        try:
            import subprocess
            import os
            can_path = os.path.join(os.path.dirname(__file__), 'can_tool', 'can_host_computer.py')
            subprocess.Popen([sys.executable, can_path])
        except Exception as e:
            print(f"启动独立CAN工具失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.can_tool and hasattr(self.can_tool, 'disconnect_can'):
                self.can_tool.disconnect_can()
        except Exception as e:
            print(f"CAN工具清理错误: {e}")


class ModbusToolWrapper:
    """Modbus工具包装器"""
    
    def __init__(self, parent_frame, main_window):
        self.parent_frame = parent_frame
        self.main_window = main_window
        self.modbus_tool = None
        self.init_modbus_tool()
    
    def init_modbus_tool(self):
        """初始化Modbus工具"""
        try:
            # 创建Modbus工具实例（使用嵌入模式）
            self.modbus_tool = create_modbus_embedded(self.parent_frame)
            
            # 检查工具是否成功创建
            if self.modbus_tool and hasattr(self.modbus_tool, 'main_frame'):
                print("Modbus工具界面创建成功")
                # 工具已经直接使用传入的父框架，无需重新打包
            else:
                print("Modbus工具界面创建失败，使用简化界面")
                self.create_simple_modbus_interface()
                
        except Exception as e:
            # 如果初始化失败，显示错误信息
            error_label = ttk.Label(self.parent_frame, 
                                  text=f"Modbus工具初始化失败:\n{str(e)}",
                                  foreground="red")
            error_label.pack(expand=True)
            print(f"Modbus工具初始化错误: {e}")
    
    def create_simple_modbus_interface(self):
        """创建简化的Modbus工具界面"""
        try:
            # 创建标题
            title_label = ttk.Label(self.parent_frame, text="Modbus工具", 
                                   font=("Arial", 14, "bold"))
            title_label.pack(pady=(10, 20))
            
            # 创建说明标签
            info_label = ttk.Label(self.parent_frame, 
                                  text="Modbus工具已加载成功！\n\n由于界面嵌入技术限制，建议使用独立模式运行此工具以获得完整功能。\n\n点击下方按钮启动独立Modbus工具。",
                                  font=("Arial", 10), justify="center")
            info_label.pack(expand=True, pady=20)
            
            # 创建启动按钮
            launch_btn = ttk.Button(self.parent_frame, text="启动独立Modbus工具", 
                                   command=self.launch_standalone_modbus)
            launch_btn.pack(pady=20)
            
        except Exception as e:
            print(f"创建简化界面失败: {e}")
    
    def launch_standalone_modbus(self):
        """启动独立的Modbus工具"""
        try:
            import subprocess
            import os
            modbus_path = os.path.join(os.path.dirname(__file__), 'mobus_tool', 'main.py')
            subprocess.Popen([sys.executable, modbus_path])
        except Exception as e:
            print(f"启动独立Modbus工具失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.modbus_tool and hasattr(self.modbus_tool, 'on_closing'):
                self.modbus_tool.on_closing()
        except Exception as e:
            print(f"Modbus工具清理错误: {e}")


class UARTToolWrapper:
    """UART工具包装器"""
    
    def __init__(self, parent_frame, main_window):
        self.parent_frame = parent_frame
        self.main_window = main_window
        self.uart_tool = None
        self.init_uart_tool()
    
    def init_uart_tool(self):
        """初始化UART工具"""
        try:
            # 创建UART工具实例（使用嵌入模式）
            self.uart_tool = create_uart_embedded(self.parent_frame)
            
            # 检查工具是否成功创建
            if self.uart_tool and hasattr(self.uart_tool, 'main_frame'):
                print("UART工具界面创建成功")
                # 工具已经直接使用传入的父框架，无需重新打包
            else:
                print("UART工具界面创建失败，使用简化界面")
                self.create_simple_uart_interface()
                
        except Exception as e:
            # 如果初始化失败，显示错误信息
            error_label = ttk.Label(self.parent_frame, 
                                  text=f"UART工具初始化失败:\n{str(e)}",
                                  foreground="red")
            error_label.pack(expand=True)
            print(f"UART工具初始化错误: {e}")
    
    def create_simple_uart_interface(self):
        """创建简化的UART工具界面"""
        try:
            # 创建标题
            title_label = ttk.Label(self.parent_frame, text="UART工具", 
                                   font=("Arial", 14, "bold"))
            title_label.pack(pady=(10, 20))
            
            # 创建说明标签
            info_label = ttk.Label(self.parent_frame, 
                                  text="UART工具已加载成功！\n\n由于界面嵌入技术限制，建议使用独立模式运行此工具以获得完整功能。\n\n点击下方按钮启动独立UART工具。",
                                  font=("Arial", 10), justify="center")
            info_label.pack(expand=True, pady=20)
            
            # 创建启动按钮
            launch_btn = ttk.Button(self.parent_frame, text="启动独立UART工具", 
                                   command=self.launch_standalone_uart)
            launch_btn.pack(pady=20)
            
        except Exception as e:
            print(f"创建简化界面失败: {e}")
    
    def launch_standalone_uart(self):
        """启动独立的UART工具"""
        try:
            import subprocess
            import os
            # 使用专门的启动脚本
            uart_path = os.path.join(os.path.dirname(__file__), 'uart_test', 'run_uart_standalone.py')
            if os.path.exists(uart_path):
                subprocess.Popen([sys.executable, uart_path])
            else:
                # 如果启动脚本不存在，使用原来的main.py
                uart_path = os.path.join(os.path.dirname(__file__), 'uart_test', 'main.py')
                subprocess.Popen([sys.executable, uart_path])
        except Exception as e:
            print(f"启动独立UART工具失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.uart_tool and hasattr(self.uart_tool, 'uart'):
                self.uart_tool.uart.close()
        except Exception as e:
            print(f"UART工具清理错误: {e}")


def main():
    """主函数"""
    try:
        app = UnifiedToolManager()
        app.run()
    except Exception as e:
        print(f"程序启动失败: {e}")
        print(traceback.format_exc())
        messagebox.showerror("启动错误", f"程序启动失败:\n{str(e)}")


if __name__ == "__main__":
    main() 