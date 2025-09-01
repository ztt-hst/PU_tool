#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SunSpec Modbus协议上位机主程序
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import json
import os
from functools import partial
import sys
from sunspec_protocol import SunSpecProtocol
from modbus_client import ModbusClient
from gui_components import ConnectionFrame, DataTableFrame
from language_manager import LanguageManager

class SunSpecGUI:
    """SunSpec协议GUI界面"""
    
    def __init__(self, parent_frame=None, language_manager=None):
        """
        初始化Modbus工具
        Args:
            parent_frame: 父框架，如果为None则创建独立窗口
            language_manager: 语言管理器
        """
        # 首先定义基本属性
        self.parent_frame = parent_frame
        self.is_embedded = parent_frame is not None
        
        if not self.is_embedded:
            self.root = tk.Tk()
            
            # 使用传入的语言管理器或创建新的
            if language_manager is None:
                self.language_manager = LanguageManager()
            else:
                self.language_manager = language_manager
            
            # 设置窗口标题（只在独立模式下）
            if not self.is_embedded:
                self.root.title(self.language_manager.get_text("window_title"))
            #self.root.geometry("1400x900")
            # 设置窗口大小和位置
            window_width = 1400
            window_height = 900
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2
            self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

            # 设置窗口图标
            self.set_window_icon()
            
            # 创建主框架
            self.main_frame = ttk.Frame(self.root)
            self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        else:
            # 嵌入模式：使用传入的父框架
            self.root = None
            self.main_frame = parent_frame
            
            # 使用传入的语言管理器或创建新的
            if language_manager is None:
                self.language_manager = LanguageManager()
            else:
                self.language_manager = LanguageManager()
        
        self.modbus_client = ModbusClient()
        self.sunspec_protocol = SunSpecProtocol()
        self.current_table = 802
        self.auto_refresh = False
        self.refresh_thread = None
        self.is_scan_base_addr = False
        self.is_scan_model_addr = False
        # 新增：日志文件相关
        self.log_file_path = self.get_default_log_file()
        self.log_file_var = None  # 将在setup_gui中设置
        
        self.setup_gui()
        self.bind_events()
    def set_window_icon(self):
        """设置窗口图标"""
        try:
            # 获取图标文件路径
            icon_path = self.get_resource_path('BQC.ico')
            
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
            else:
                print(f"图标文件不存在: {icon_path}")
        except Exception as e:
            print(f"设置窗口图标失败: {e}")

    def get_resource_path(self, filename):
        """获取资源文件路径，支持打包后的路径"""
        import sys
        import os
        
        if getattr(sys, 'frozen', False):
            # 如果是打包后的exe
            base_path = sys._MEIPASS
            return os.path.join(base_path, filename)
        else:
            # 如果是开发环境
            return filename

    def setup_gui(self):
        """设置GUI界面"""
        if self.is_embedded:
            # 嵌入模式：使用传入的父框架
            main_frame = self.main_frame
        else:
            # 独立模式：创建新的主框架
            main_frame = ttk.Frame(self.root)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 语言切换按钮（只在独立模式下显示）
        if not self.is_embedded:
            lang_frame = ttk.Frame(main_frame)
            lang_frame.pack(fill=tk.X, pady=(0, 5))
            ttk.Label(lang_frame, text="Language:").pack(side=tk.LEFT)
            lang_var = tk.StringVar(value=self.language_manager.get_current_language())
            lang_combo = ttk.Combobox(lang_frame, textvariable=lang_var, 
                                     values=self.language_manager.get_available_languages(),
                                     state="readonly", width=10)
            lang_combo.pack(side=tk.LEFT, padx=(5, 0))
            lang_combo.bind('<<ComboboxSelected>>', lambda e: self.change_language(lang_var.get()))

        # 连接设置
        self.connection_frame = ConnectionFrame(main_frame, self.language_manager)
        self.connection_frame.pack(fill=tk.X, pady=(0, 10))

        # 扫描基地址和模型地址按钮及显示
        scan_frame = ttk.Frame(main_frame)
        scan_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 保存按钮引用以便更新文本
        self.scan_base_btn = ttk.Button(scan_frame, text=self.language_manager.get_text("scan_base_address"), 
                                   command=self.scan_base_address)
        self.scan_base_btn.pack(side=tk.LEFT)
        
        self.current_base_addr_label = ttk.Label(scan_frame, text=self.language_manager.get_text("current_base_address"))
        self.current_base_addr_label.pack(side=tk.LEFT, padx=(10, 2))
        
        self.base_addr_var = tk.StringVar(value=self.language_manager.get_text("not_scanned"))
        base_addr_entry = ttk.Entry(scan_frame, textvariable=self.base_addr_var, width=10, state="readonly")
        base_addr_entry.pack(side=tk.LEFT, padx=(0, 10))

        # 扫描模型地址按钮和显示
        self.scan_model_btn = ttk.Button(scan_frame, text=self.language_manager.get_text("scan_model_address"), 
                  command=self.scan_models)
        self.scan_model_btn.pack(side=tk.LEFT, padx=(10, 0))
        

        # 总控按钮（只保留读取全部）
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        self.read_all_tables_btn = ttk.Button(btn_frame, text=self.language_manager.get_text("read_all_tables"), 
                                 command=self.read_all_tables)
        self.read_all_tables_btn.pack(side=tk.LEFT)

        # 新增：自动读取全部表格勾选框
        self.auto_read_all_var = tk.BooleanVar(value=False)
        self.auto_read_all_check = ttk.Checkbutton(
            btn_frame, text="自动读取全部表格", variable=self.auto_read_all_var, command=self.on_auto_read_all_changed
        )
        self.auto_read_all_check.pack(side=tk.LEFT, padx=(10, 0))

        # 创建标签页容器
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 数据显示区 - 使用标签页
        self.data_tables = {}
        self.table_frames = {}
        self.read_all_btns = {}  # 保存每个表格的读全部按钮

        # 初始创建默认表格页 (1，802)
        for table_id in [1, 802]:
            self.create_table_tab(table_id)

        # 日志框
        self.log_frame = ttk.LabelFrame(main_frame, text=self.language_manager.get_text("log"), padding=5)
        self.log_frame.pack(fill=tk.BOTH, expand=False, pady=(5, 0))
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=8, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 日志控制按钮
        log_btn_frame = ttk.Frame(self.log_frame)
        log_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.clear_log_btn = ttk.Button(log_btn_frame, text=self.language_manager.get_text("clear_log"), 
                                   command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT)
        
        # 自动保存日志勾选框 - 默认不勾选
        self.auto_save_log_var = tk.BooleanVar(value=False)
        self.auto_save_check = ttk.Checkbutton(log_btn_frame, text=self.language_manager.get_text("auto_save_log"), 
                                          variable=self.auto_save_log_var, command=self.on_auto_save_changed)
        self.auto_save_check.pack(side=tk.LEFT, padx=(10, 0))
        
        # 隐藏文件路径相关变量
        self.log_file_path = None
        self.log_file_var = tk.StringVar(value="未选择文件")

        # 状态栏
        self.status_var = tk.StringVar(value=self.language_manager.get_text("ready"))
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def change_language(self, language):
        """切换语言"""
        if self.language_manager.set_language(language):
            # 只更新界面文本，不重建窗口
            self.update_interface_text()
    
    def set_language(self, language):
        """外部设置语言的方法，用于统一管理器调用"""
        print(f"Modbus工具外部语言设置: {language}")
        
        # 转换语言代码
        if language == 'zh':
            modbus_language = 'zh_CN'
        elif language == 'en':
            modbus_language = 'en_US'
        else:
            modbus_language = language
            
        print(f"Modbus工具转换后的语言代码: {modbus_language}")
        
        if self.language_manager.set_language(modbus_language):
            self.update_interface_text()
            
            # 强制刷新界面
            if hasattr(self, 'root') and self.root:
                self.root.update_idletasks()
            elif hasattr(self, 'main_frame') and self.main_frame:
                self.main_frame.update_idletasks()
                
            print(f"Modbus工具语言设置完成: {language}")
        else:
            print(f"Modbus工具语言设置失败: {language}")

    def update_interface_text(self):
        """更新界面文本"""
        # 更新窗口标题（只在独立模式下）
        if not self.is_embedded and self.root:
            self.root.title(self.language_manager.get_text("window_title"))
        
        # 更新状态栏
        self.status_var.set(self.language_manager.get_text("ready"))
        
        # 更新连接设置框架
        self.update_connection_frame_text()
        
        # 更新扫描按钮文本
        self.update_scan_buttons_text()
        
        # 更新表格标题
        self.update_table_titles()
        
        # 更新日志区域文本
        self.update_log_area_text()
        
        # 更新数据表格文本
        self.update_data_tables_text()

    def update_connection_frame_text(self):
        """更新连接设置框架的文本"""
        # 更新连接框架的语言
        self.connection_frame.update_language(self.language_manager)
        
        # 更新按钮文本
        self.connection_frame.connect_rtu_btn.configure(text=self.language_manager.get_text("connect_rtu"))
        self.connection_frame.disconnect_btn.configure(text=self.language_manager.get_text("disconnect"))

    def update_scan_buttons_text(self):
        """更新扫描按钮的文本"""
        if hasattr(self, 'scan_base_btn'):
            self.scan_base_btn.configure(text=self.language_manager.get_text("scan_base_address"))
        if hasattr(self, 'scan_model_btn'):
            self.scan_model_btn.configure(text=self.language_manager.get_text("scan_model_address"))
        if hasattr(self, 'current_base_addr_label'):
            self.current_base_addr_label.configure(text=self.language_manager.get_text("current_base_address"))
        if hasattr(self, 'read_all_tables_btn'):
            self.read_all_tables_btn.configure(text=self.language_manager.get_text("read_all_tables"))
    
        # 更新基地址变量的默认值
        if hasattr(self, 'base_addr_var'):
            if self.base_addr_var.get() == "未扫描" or self.base_addr_var.get() == "Not Scanned":
                self.base_addr_var.set(self.language_manager.get_text("not_scanned"))

    def update_table_titles(self):
        """更新表格标题"""
        # 遍历所有已存在的表格页
        for i in range(self.notebook.index("end")):
            tab_text = self.notebook.tab(i, "text")
            # 从标签文本中提取表格ID
            import re
            match = re.search(r'(\d+)', tab_text)
            if match:
                table_id = int(match.group(1))
                # 获取当前地址显示
                if hasattr(self, 'model_base_addrs') and table_id in self.model_base_addrs:
                    addr_text = str(self.model_base_addrs[table_id])
                else:
                    addr_text = "-"
                self.notebook.tab(i, text=f"{self.language_manager.get_text('table')}{table_id}({self.language_manager.get_text('addr')}: {addr_text})")

    def update_log_area_text(self):
        """更新日志区域的文本"""
        # 更新日志框架标题
        if hasattr(self, 'log_frame'):
            self.log_frame.configure(text=self.language_manager.get_text("log"))
        
        # 更新按钮文本
        if hasattr(self, 'clear_log_btn'):
            self.clear_log_btn.configure(text=self.language_manager.get_text("clear_log"))
        if hasattr(self, 'auto_save_check'):
            self.auto_save_check.configure(text=self.language_manager.get_text("auto_save_log"))
        if hasattr(self, 'auto_read_all_check'):
            self.auto_read_all_check.configure(text=self.language_manager.get_text("auto_read_all_tables"))

    def update_data_tables_text(self):
        """更新数据表格的文本"""
        # 更新每个表格的读全部按钮
        for table_id, read_all_btn in self.read_all_btns.items():
            read_all_btn.configure(text=self.language_manager.get_text("read_all"))
        
        # 更新数据表格的语言
        for table_id, data_table in self.data_tables.items():
            data_table.update_language(self.language_manager)

    def bind_events(self):
        """绑定事件"""
        # 绑定连接框架的按钮事件
        self.connection_frame.connect_rtu_btn.config(command=self.connect_rtu)
        self.connection_frame.disconnect_btn.config(command=self.disconnect)
        
        # 初始化按钮状态
        self.update_connection_buttons_state()

    def update_connection_buttons_state(self):
        """更新连接按钮状态"""
        is_connected = self.modbus_client.is_connected()
        
        # 更新连接框架的按钮状态
        self.connection_frame.update_buttons_state(is_connected)

    def create_table_tab(self, table_id):
        """创建单个表格标签页"""
        if table_id in self.table_frames:
            return  # 已存在，不重复创建
        
        # 检查模型是否已加载
        if table_id not in self.sunspec_protocol.models:
            print(f"警告：尝试创建未加载的模型{table_id}的标签页")
            return
        
        # 检查模型是否有有效的字段信息
        table_info = self.sunspec_protocol.get_table_info(table_id)
        if not table_info or not table_info.get("fields"):
            print(f"警告：模型{table_id}没有有效的字段信息")
            return

        # 获取扫描到的模型长度
        scanned_model_length = None
        if hasattr(self, 'model_base_addrs') and table_id in self.model_base_addrs:
            # 从扫描结果中获取模型长度
            base_addr = self.model_base_addrs[table_id]
            # 读取模型长度寄存器（通常是基地址+1）
            try:
                length_regs = self.modbus_client.read_holding_registers(base_addr + 1, 1)
                if length_regs and len(length_regs) > 0:
                    scanned_model_length = length_regs[0]
                    self.log_message(f"模型{table_id}扫描到的长度: {scanned_model_length}")
            except Exception as e:
                self.log_message(f"读取模型{table_id}长度失败: {e}")

        # 创建标签页
        tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(tab_frame, text=f"{self.language_manager.get_text('table')}{table_id}({self.language_manager.get_text('addr')}: -)")
        self.table_frames[table_id] = tab_frame

        # 按钮区（只保留读全部）
        btn_frame = ttk.Frame(tab_frame)
        btn_frame.pack(fill=tk.X, anchor="w", pady=(5, 0))
        read_all_btn = ttk.Button(btn_frame, text=self.language_manager.get_text("read_all"), 
                         command=lambda tid=table_id: self.read_table(tid))
        read_all_btn.pack(side=tk.LEFT)
        self.read_all_btns[table_id] = read_all_btn  # 保存按钮引用

        # 内容区+滚动条
        content_frame = ttk.Frame(tab_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        canvas = tk.Canvas(content_frame)
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        canvas_window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        scrollable_frame.bind(
            "<Configure>",
            lambda e, c=canvas: c.configure(scrollregion=c.bbox("all"))
        )
        
        def on_canvas_configure(event, canvas=canvas, window_id=canvas_window_id, sf=scrollable_frame):
            canvas.itemconfig(window_id, width=event.width)
            sf.configure(width=event.width)
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        canvas.bind('<Configure>', on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 绑定鼠标滚轮事件
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _bind_mousewheel(_):
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def _unbind_mousewheel(_):
            canvas.unbind_all("<MouseWheel>")
        # 鼠标进入/离开可滚动区域时绑定/解绑（仅 Windows）
        scrollable_frame.bind("<Enter>", _bind_mousewheel)
        scrollable_frame.bind("<Leave>", _unbind_mousewheel)
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)


        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        dt = DataTableFrame(scrollable_frame, table_id, self.sunspec_protocol, 
                          self.modbus_client, main_window=self, language_manager=self.language_manager,
                          scanned_model_length=scanned_model_length)
        dt.pack(fill=tk.BOTH, expand=True)
        self.data_tables[table_id] = dt

    def get_default_log_file(self):
        """获取默认日志文件路径"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"SunSpec_Log_{timestamp}.txt"

    def on_auto_save_changed(self):
        """自动保存日志勾选框状态改变时的处理"""
        if self.auto_save_log_var.get():
            # 勾选时，直接弹出文件选择对话框
            self.select_log_file()
        else:
            # 取消勾选时，清除文件路径
            self.log_file_path = None
            self.log_file_var.set("未选择文件" if self.language_manager.get_current_language() == "zh_CN" else "No file selected")

    def select_log_file(self):
        """选择日志文件"""
        from tkinter import filedialog
        import time
        import os
        
        # 生成默认文件名
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        default_filename = f"SunSpec_Log_{timestamp}.txt"
        
        # 获取用户文档目录作为默认保存位置
        try:
            import os.path
            default_dir = os.path.expanduser("~/Documents")
            if not os.path.exists(default_dir):
                default_dir = os.getcwd()  # 如果文档目录不存在，使用当前目录
        except:
            default_dir = os.getcwd()
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="选择日志文件" if self.language_manager.get_current_language() == "zh_CN" else "Select Log File",
            initialdir=default_dir,
            initialfile=default_filename
        )
        if filename:
            self.log_file_path = filename
            self.log_file_var.set(filename)
            # 立即创建文件
            try:
                with open(self.log_file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# SunSpec Modbus Log File\n")
                    f.write(f"# Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# Language: {self.language_manager.get_current_language()}\n")
                    f.write(f"# File: {os.path.basename(filename)}\n\n")
            except Exception as e:
                messagebox.showerror("错误", f"创建日志文件失败: {str(e)}")
                # 如果创建失败，取消勾选
                self.auto_save_log_var.set(False)
        else:
            # 如果用户取消选择，取消勾选
            self.auto_save_log_var.set(False)

    def log_message(self, message):
        """添加日志消息"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # 显示在GUI中
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        # 只在独立模式下更新root
        if not self.is_embedded and self.root:
            self.root.update_idletasks()
        
        # 如果开启了自动保存且有有效的文件路径，则写入文件
        if (hasattr(self, 'auto_save_log_var') and self.auto_save_log_var.get() and 
            hasattr(self, 'log_file_path') and self.log_file_path):
            try:
                with open(self.log_file_path, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
            except Exception as e:
                # 如果写入失败，在GUI中显示错误
                error_msg = f"日志文件写入失败: {str(e)}\n"
                self.log_text.insert(tk.END, error_msg)
                self.log_text.see(tk.END)

    def clear_log(self):
        """清空日志显示区域（不清空文件）"""
        self.log_text.delete(1.0, tk.END)
        
        # 如果开启了自动保存，在日志文件中添加分隔线，但不清空文件内容
        if (hasattr(self, 'auto_save_log_var') and self.auto_save_log_var.get() and 
            hasattr(self, 'log_file_path') and self.log_file_path):
            try:
                import time
                separator = f"\n# ====== 界面日志清空时间: {time.strftime('%Y-%m-%d %H:%M:%S')} ======\n\n"
                with open(self.log_file_path, 'a', encoding='utf-8') as f:
                    f.write(separator)
            except Exception as e:
                # 如果写入分隔线失败，只在界面显示错误，不影响文件内容
                error_msg = f"添加日志分隔线失败: {str(e)}\n"
                self.log_text.insert(tk.END, error_msg)

    def connect_rtu(self):
        """连接RTU Modbus"""
        port = self.connection_frame.rtu_port_var.get()
        baudrate = int(self.connection_frame.baudrate_var.get())
        slave_id = int(self.connection_frame.slave_id_var.get())
        timeout = int(self.connection_frame.timeout_var.get())
        
        if self.modbus_client.connect_rtu(port, baudrate, timeout=timeout):
            # 设置全局slave_id
            self.modbus_client.slave_id = slave_id
            
            self.modbus_client.set_log_callback(self.log_message)
            self.status_var.set(f"RTU连接成功: {port}, 从站ID: {slave_id}")
            self.log_message(f"RTU连接成功: {port}, 从站ID: {slave_id}")
            messagebox.showinfo(self.language_manager.get_text("connection_success"), f"已连接到 {port}, 从站ID: {slave_id}")
            
            # 更新按钮状态
            self.update_connection_buttons_state()
        else:
            self.status_var.set("RTU连接失败")
            self.log_message(f"RTU连接失败: {port}")
            messagebox.showerror(self.language_manager.get_text("connection_failed"), f"无法连接到 {port}")

    def disconnect(self):
        """断开连接"""
        self.modbus_client.disconnect()
        self.status_var.set(self.language_manager.get_text("disconnected"))
        self.log_message(self.language_manager.get_text("disconnected"))
        #取消勾选自动读取
        self.auto_read_all_var.set(False)
        self.on_auto_read_all_changed()
        
        # 清除扫描到的基地址和模型地址
        self.clear_scanned_addresses()
        
        # 重新初始化表格页面
        self.reinitialize_table_pages()
        
        # 更新按钮状态
        self.update_connection_buttons_state()
    
    def clear_scanned_addresses(self):
        """清除扫描到的基地址和模型地址"""
        # 重置扫描状态标志
        self.is_scan_base_addr = False
        self.is_scan_model_addr = False
        
        # 清除基地址显示
        self.base_addr_var.set(self.language_manager.get_text("not_scanned"))
        
        # 清除协议中的基地址
        if hasattr(self.sunspec_protocol, 'base_address'):
            self.sunspec_protocol.base_address = None
            
        # 清除模型地址映射
        if hasattr(self, 'model_base_addrs'):
            self.model_base_addrs.clear()
            
        self.log_message("已清除扫描到的基地址和模型地址")
    
    def reinitialize_table_pages(self):
        """重新初始化表格页面"""
        # 清除所有现有的表格页
        for i in range(self.notebook.index("end")):
            self.notebook.forget(0)
            
        # 清除表格相关的数据结构
        self.data_tables.clear()
        self.table_frames.clear()
        self.read_all_btns.clear()
        
        # 重新创建默认表格页（1，802）
        for table_id in [1, 802]:
            self.create_table_tab(table_id)
            
        self.log_message("已重新初始化表格页面")

    def read_all_tables(self):
        if not self.modbus_client.is_connected():
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                 self.language_manager.get_text("please_connect_first"))
            return
        if self.is_scan_model_addr == False:
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                    self.language_manager.get_text("please_scan_model_addr_first"))
            return
        self.log_message(self.language_manager.get_text("start_reading_all"))
        
        # 读取所有已创建的表格页对应的表格
        for table_id in self.data_tables.keys():
            self.read_table(table_id)
            
        self.log_message(self.language_manager.get_text("all_tables_read_complete"))

    def read_table(self, table_id):
        # 检查是否已连接
        if not self.modbus_client.is_connected():
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                 self.language_manager.get_text("please_connect_first"))
            self.log_message(f"未连接")
            return
        
        if self.is_scan_model_addr == False:
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                    self.language_manager.get_text("please_scan_model_addr_first"))
            return 
        # 获取基地址
        base_addr = self.model_base_addrs[table_id]
        self.log_message(f"读取表格{table_id}，使用扫描地址: {base_addr}")
        
         # 获取扫描到的模型长度
        scanned_length = None
        try:
            length_regs = self.modbus_client.read_holding_registers(base_addr + 1, 1)
            if length_regs and len(length_regs) > 0:
                scanned_length = length_regs[0]
                self.log_message(f"模型{table_id}扫描到的长度: {scanned_length}")
        except Exception as e:
            self.log_message(f"读取模型{table_id}长度失败: {e}")
            return
        
        if not scanned_length or scanned_length <= 0:
            self.log_message(f"模型{table_id}长度无效: {scanned_length}")
            return
        
        # 使用扫描到的长度来读取数据
        if scanned_length <= 125:
            # 一次性读取
            data = self.modbus_client.read_holding_registers(base_addr, scanned_length)
        else:
            # 分段读取
            data = self.read_registers_in_chunks(base_addr, scanned_length)
            
        if data:
            parsed = self.sunspec_protocol.parse_table_data(table_id, data)
            if parsed and table_id in self.data_tables:
                self.data_tables[table_id].display_data(parsed)
                self.log_message(f"表格{table_id}读取成功")
            else:
                self.log_message(f"表格{table_id}解析失败")
        else:
            self.log_message(f"表格{table_id}读取失败")

    def read_registers_in_chunks(self, base_addr, total_length, chunk_size=125):
        """
        分段读取寄存器数据
        Args:
            base_addr: 起始地址
            total_length: 总寄存器数量
            chunk_size: 每段读取的寄存器数量，默认125
        Returns:
            完整的寄存器数据列表，失败时返回None
        """
        if chunk_size > 125:
            chunk_size = 125  # 确保不超过Modbus RTU限制
        
        all_data = []
        current_addr = base_addr
        remaining = total_length
        
        self.log_message(f"开始分段读取，总长度: {total_length}，每段最多: {chunk_size} 寄存器")
        
        chunk_num = 1
        while remaining > 0:
            # 计算本段要读取的寄存器数量
            current_chunk_size = min(chunk_size, remaining)
            
            self.log_message(f"读取第{chunk_num}段: 地址{current_addr}，长度{current_chunk_size}")
            
            # 读取当前段
            chunk_data = self.modbus_client.read_holding_registers(current_addr, current_chunk_size)
            if chunk_data is None:
                self.log_message(f"第{chunk_num}段读取失败")
                return None
            
            # 将数据添加到总数据中
            all_data.extend(chunk_data)
            
            # 更新地址和剩余长度
            current_addr += current_chunk_size
            remaining -= current_chunk_size
            chunk_num += 1
            
            # 短暂延时避免设备响应不过来
            time.sleep(0.01)
        
        self.log_message(f"分段读取完成，共读取 {len(all_data)} 个寄存器")
        return all_data

    def scan_base_address(self):
        """扫描SunSpec协议基地址"""
        if not self.modbus_client.is_connected():
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                 self.language_manager.get_text("please_connect_first"))
            return
        self.log_message(self.language_manager.get_text("start_scanning_base"))
        candidate_addrs = [0, 40000, 50000]
        found = False
        for addr in candidate_addrs:
            data = self.modbus_client.read_holding_registers(addr, 2)
            if data and len(data) == 2:
                bytes_data = ((data[0]>>8) & 0xFF).to_bytes(1, 'big') + (data[0]  & 0xFF).to_bytes(1, 'big') + \
                           ((data[1]>>8)& 0xFF).to_bytes(1, 'big') + (data[1]  & 0xFF).to_bytes(1, 'big')
                try:
                    ascii_str = bytes_data.decode('ascii')
                    hex_str = ' '.join([f"{b:02X}" for b in bytes_data])
                    self.log_message(f"地址{addr}内容: {ascii_str} (hex: {hex_str})")
                    if ascii_str == "SunS":
                        self.sunspec_protocol.base_address = addr
                        self.base_addr_var.set(str(addr))
                        self.log_message(f"发现SunSpec基地址: {addr}")
                        messagebox.showinfo(self.language_manager.get_text("scan_success"), 
                                          f"{self.language_manager.get_text('found_sunspec_base')}: {addr}")
                        found = True
                        self.scan_base_address = True
                        break
                except Exception as e:
                    self.log_message(f"地址{addr}解析失败: {e}")
        if not found:
            self.base_addr_var.set(self.language_manager.get_text("not_scanned"))
            self.log_message(self.language_manager.get_text("not_found_sunspec_base"))
            messagebox.showerror(self.language_manager.get_text("scan_failed"), 
                               self.language_manager.get_text("not_found_sunspec_base"))

    def scan_models(self):
        """扫描所有SunSpec模型，找到802/805/899的起始地址"""
        if not self.modbus_client.is_connected():
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                 self.language_manager.get_text("please_connect_first"))
            return
        if self.scan_base_address == False:
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                    self.language_manager.get_text("please_scan_base_addr_first"))
            return
        base_addr = self.sunspec_protocol.base_address
        addr = base_addr + 2  # Skip "SunS" (ID and Length of SunSpec Common Model)
        model_map = {}
        self.log_message(f"{self.language_manager.get_text('start_scanning_models')}，基地址: {base_addr}")

        while True:
            regs = self.modbus_client.read_holding_registers(addr, 2)
            if not regs or len(regs) < 2:
                self.log_message(f"读取模型ID/LEN失败，地址: {addr}")
                break
            model_id, model_len = regs[0], regs[1]
            self.log_message(f"模型ID: {model_id} LEN: {model_len} @ {addr}")

            if model_id == 0xFFFF and model_len == 0:
                self.is_scan_model_addr = True
                self.log_message("模型链表结束")
                break

            model_map[model_id] = addr
            self.sunspec_protocol.set_model_base_address(model_id, addr)

            addr = addr + 2 + model_len

        self.model_base_addrs = model_map
        self.log_message(f"{self.language_manager.get_text('scan_complete')}，找到模型: {list(model_map.keys())}")

        # 先重新加载模型，只加载扫描到的模型
        self.sunspec_protocol.load_models(available_models=list(model_map.keys()))

        # 然后为新发现的模型创建表格页（只对有JSON文件的模型）
        for model_id in model_map.keys():
            if model_id not in self.table_frames:
                # 检查模型是否成功加载（即有对应的JSON文件）
                if model_id in self.sunspec_protocol.models:
                    self.create_table_tab(model_id)
                    self.log_message(f"创建新表格页: 模型{model_id}")
                else:
                    self.log_message(f"跳过模型{model_id}：未找到对应的JSON文件")

        # 更新标签页标题显示地址
        self.update_table_titles()


    def on_auto_read_all_changed(self):
        """自动读取全部表格勾选框状态改变时的处理"""
        if self.auto_read_all_var.get():
            self.start_auto_read_all()
        else:
            self.stop_auto_read_all()

    def start_auto_read_all(self):
        """启动自动读取全部表格"""
        if self.is_scan_model_addr == False :
            #取消勾选自动读取
            self.auto_read_all_var.set(False)
            self.on_auto_read_all_changed()
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                    self.language_manager.get_text("please_scan_model_addr_first"))
            return 
        self._auto_read_all_running = True
        self.schedule_auto_read_all()

    def stop_auto_read_all(self):
        """停止自动读取全部表格"""
        self._auto_read_all_running = False

    def schedule_auto_read_all(self):
        """调度自动读取全部表格"""
        if getattr(self, "_auto_read_all_running", False):
            self.read_all_tables()
            # 5秒后再次调用（只在独立模式下）
            if not self.is_embedded and self.root:
                self.root.after(5000, self.schedule_auto_read_all)

    def run(self):
        # 只在独立模式下设置关闭事件和主循环
        if not self.is_embedded and self.root:
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.root.mainloop()

    def on_closing(self):
        self.stop_auto_read_all()
        self.modbus_client.disconnect()
        # 只在独立模式下销毁root
        if not self.is_embedded and self.root:
            self.root.destroy()

def main():
    # 独立运行模式
    app = SunSpecGUI()
    app.run()

def create_embedded_instance(parent_frame):
    """创建嵌入模式的实例，用于统一工具管理器"""
    return SunSpecGUI(parent_frame)

if __name__ == "__main__":
    main()