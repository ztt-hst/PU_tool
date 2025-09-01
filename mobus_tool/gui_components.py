#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI组件模块
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial.tools.list_ports
import datetime

# 添加语言管理器导入
try:
    from language_manager import LanguageManager
except ImportError:
    # 如果导入失败，创建一个简单的默认类
    class LanguageManager:
        def get_text(self, key, default=None):
            return default or key

class DataTableFrame(ttk.Frame):
    def __init__(self, parent, table_id, protocol, modbus_client, main_window=None, language_manager=None,scanned_model_length=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.table_id = table_id
        self.protocol = protocol
        self.modbus_client = modbus_client
        self.main_window = main_window
        self.language_manager = language_manager or LanguageManager()
        self.scanned_model_length = scanned_model_length  # 新增：扫描到的模型长度
        
        # 获取字段信息，支持动态长度
        if scanned_model_length:
            # 如果有扫描到的长度，动态生成字段信息
            self.fields = self.generate_dynamic_fields(scanned_model_length)
        else:
            # 否则使用固定字段信息
            table_info = protocol.get_table_info(table_id)
            self.fields = table_info["fields"]
        
        self.entries = {}
        self.headers = []  # 保存表头引用
        self.setup_table()
    def generate_dynamic_fields(self, scanned_length):
            """根据扫描到的模型长度动态生成字段信息"""
            # 获取基础模型信息
            table_info = self.protocol.get_table_info(self.table_id)
            if not table_info:
                return {}
            
            fields = {}
            
            # 添加固定points部分
            for field_name, field_info in table_info["fields"].items():
                fields[field_name] = field_info.copy()
            
            # 检查是否有子groups
            if table_info.get("has_groups") and table_info.get("groups_info"):
                groups_info = table_info["groups_info"]
                fixed_length = table_info["length"]  # 固定points部分的长度
                
                # 计算剩余长度和子groups重复次数
                remaining_length = scanned_length - fixed_length
                
                for group in groups_info:
                    group_name = group['name']
                    group_points = group['points']
                    
                    # 计算单个group的寄存器长度
                    single_group_length = sum(gp.get('size', 1) for gp in group_points)
                    
                    if single_group_length > 0 and remaining_length > 0:
                        # 计算重复次数
                        repeat_count = remaining_length // single_group_length
                        
                        # 为每个重复的group生成字段
                        for i in range(repeat_count):
                            current_offset = fixed_length + (i * single_group_length)
                            
                            for gp in group_points:
                                gp_name = gp['name']
                                gp_size = gp.get('size', 1)
                                
                                # 生成字段名
                                field_name = f"{group_name}_{i+1}_{gp_name}"
                                
                                # 计算在扫描数据中的实际偏移
                                data_offset = current_offset
                                
                                fields[field_name] = {
                                    'offset': data_offset,
                                    'size': gp_size,
                                    'type': gp['type'],
                                    'scale': gp.get('sf', 1),
                                    'unit': gp.get('units', ''),
                                    'access': 'rw' if 'access' in gp and gp['access'] == 'RW' else 'r',
                                    'label': f"{gp.get('label', gp_name)} (Group {i+1})",
                                    'description': gp.get('desc', ''),
                                    'group_index': i + 1,
                                    'group_name': group_name,
                                    'is_dynamic_group': True  # 标识这是动态生成的group字段
                                }
                                
                                current_offset += gp_size
            
            return fields
    def setup_table(self):
        headers = [
            self.language_manager.get_text("field_name"),
            self.language_manager.get_text("value"),
            self.language_manager.get_text("update_time"),
            self.language_manager.get_text("unit"),
            self.language_manager.get_text("type"),
            self.language_manager.get_text("description"),
            self.language_manager.get_text("access_rights"),
            self.language_manager.get_text("read"),
            self.language_manager.get_text("write_value"),
            self.language_manager.get_text("write"),
            self.language_manager.get_text("write_status")
        ]
        
        col_widths = [120, 80, 80, 60, 70, 200, 60, 40, 80, 40, 80]
        self.headers = []  # 保存表头引用以便更新
        
        for col, h in enumerate(headers):
            header_label = ttk.Label(self, text=h, anchor='center', borderwidth=1, relief='solid')
            header_label.grid(row=0, column=col, sticky='nsew', padx=1, pady=1)
            self.headers.append(header_label)  # 保存引用
            self.grid_columnconfigure(col, weight=1, minsize=col_widths[col])
        
        for row, (field_name, field_info) in enumerate(self.fields.items(), start=1):
            value_var = tk.StringVar(value='-')
            update_time_var = tk.StringVar(value='-')
            write_var = tk.StringVar(value='')
            write_status_var = tk.StringVar(value='')
            
            # 使用 label 作为显示名
            display_name = field_info.get('label', field_name)
            ttk.Label(self, text=display_name).grid(row=row, column=0, sticky='nsew')
            
            ttk.Label(self, textvariable=value_var).grid(row=row, column=1, sticky='nsew')
            ttk.Label(self, textvariable=update_time_var).grid(row=row, column=2, sticky='nsew')
            ttk.Label(self, text=field_info.get('unit', '')).grid(row=row, column=3, sticky='nsew')
            ttk.Label(self, text=field_info.get('type', '')).grid(row=row, column=4, sticky='nsew')
            ttk.Label(self, text=field_info.get('description', '')).grid(row=row, column=5, sticky='nsew')
            ttk.Label(self, text=field_info.get('access', 'r')).grid(row=row, column=6, sticky='nsew')
            
            btn_read = ttk.Button(self, text=self.language_manager.get_text("read"), width=4, 
                                 command=lambda fn=field_name: self.read_field(fn))
            btn_read.grid(row=row, column=7, sticky='nsew')
            
            # 根据访问权限决定是否显示写值输入框
            if field_info.get('access', 'r') == 'rw':
                # 有写入权限，显示输入框
                entry_write = ttk.Entry(self, textvariable=write_var, width=8)
                entry_write.grid(row=row, column=8, sticky='nsew')
                
                # 显示写按钮
                btn_write = ttk.Button(self, text=self.language_manager.get_text("write"), width=4, 
                                     command=lambda fn=field_name: self.write_field(fn))
                btn_write.grid(row=row, column=9, sticky='nsew')
            else:
                # 只读字段，隐藏输入框和写按钮
                ttk.Label(self, text='').grid(row=row, column=8, sticky='nsew')  # 空的写值列
                ttk.Label(self, text='').grid(row=row, column=9, sticky='nsew')  # 空的写按钮列
            
            ttk.Label(self, textvariable=write_status_var).grid(row=row, column=10, sticky='nsew')
            self.entries[field_name] = (value_var, update_time_var, write_var, write_status_var)

    def read_field(self, field_name):
        # 检查是否已连接
        if not self.modbus_client.is_connected():
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                 self.language_manager.get_text("please_connect_first"))
            return
        
        # 检查模型是否扫描
        if self.main_window and not getattr(self.main_window, 'is_scan_model_addr', False):
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                self.language_manager.get_text("please_scan_model_addr_first"))
            return     
        base_addr = self.main_window.model_base_addrs[self.table_id]     
        offset = self.fields[field_name]["offset"]
        addr = base_addr + offset
        length = self.fields[field_name]["size"]
        
        # 读取数据
        data = self.modbus_client.read_holding_registers(addr, length)
        if data:
            # 使用专门的单字段解析方法
            field_data = self.protocol.parse_single_field(self.table_id, field_name, data)
            if field_data:
                self.entries[field_name][0].set(str(field_data['value']))
                now = datetime.datetime.now().strftime("%H:%M:%S")
                self.entries[field_name][1].set(str(now))
            else:
                self.entries[field_name][0].set("Err")
                self.entries[field_name][1].set("-")
        else:
            self.entries[field_name][0].set("Err")
            self.entries[field_name][1].set("-")

    def write_field(self, field_name):
        # 检查是否已连接
        if not self.modbus_client.is_connected():
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                 self.language_manager.get_text("please_connect_first"))
            return
        
        # 检查模型是否扫描
        if self.main_window and not getattr(self.main_window, 'is_scan_model_addr', False):
            messagebox.showwarning(self.language_manager.get_text("warning"), 
                                self.language_manager.get_text("please_scan_model_addr_first"))
            return  
        base_addr = self.main_window.model_base_addrs[self.table_id]   
        offset = self.fields[field_name]["offset"]
        addr = base_addr + offset
        value_str = self.entries[field_name][2].get()
        try:
            value = int(value_str)
        except Exception:
            self.entries[field_name][3].set(self.language_manager.get_text("format_error"))
            return
        ok = self.modbus_client.write_holding_register(addr, value)
        self.entries[field_name][3].set(self.language_manager.get_text("success") if ok else self.language_manager.get_text("failed"))

    def display_data(self, data):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        for field_name, v in data.items():
            if field_name in self.entries:
                self.entries[field_name][0].set(str(v['value']))
                self.entries[field_name][1].set(str(now))

    def clear_data(self):
        for field_name, (value_var, update_time_var, _, write_status_var) in self.entries.items():
            value_var.set('-')
            update_time_var.set('-')
            write_status_var.set('')

    def update_language(self, language_manager):
        """更新语言"""
        self.language_manager = language_manager
        
        # 更新表头
        new_headers = [
            self.language_manager.get_text("field_name"),
            self.language_manager.get_text("value"),
            self.language_manager.get_text("update_time"),
            self.language_manager.get_text("unit"),
            self.language_manager.get_text("type"),
            self.language_manager.get_text("description"),
            self.language_manager.get_text("access_rights"),
            self.language_manager.get_text("read"),
            self.language_manager.get_text("write_value"),
            self.language_manager.get_text("write"),
            self.language_manager.get_text("write_status")
        ]
        
        for i, header_label in enumerate(self.headers):
            if i < len(new_headers):
                header_label.configure(text=new_headers[i])
        
        # 更新按钮文本
        for row in range(1, len(self.fields) + 1):
            # 更新读按钮
            read_btn = self.grid_slaves(row=row, column=7)[0]
            if isinstance(read_btn, ttk.Button):
                read_btn.configure(text=self.language_manager.get_text("read"))
            
            # 更新写按钮
            write_btn = self.grid_slaves(row=row, column=9)[0]
            if isinstance(write_btn, ttk.Button):
                write_btn.configure(text=self.language_manager.get_text("write"))

class ConnectionFrame(ttk.LabelFrame):
    """连接设置框架"""
    def __init__(self, parent, language_manager=None, **kwargs):
        # 获取语言管理器
        if language_manager is None:
            from language_manager import LanguageManager
            language_manager = LanguageManager()
        
        # 使用语言管理器获取文本
        frame_text = language_manager.get_text("connection_settings")
        super().__init__(parent, text=frame_text, padding=10, **kwargs)
        
        self.language_manager = language_manager
        self.setup_connection_controls()

    def setup_connection_controls(self):
        # 只保留RTU连接设置
        rtu_frame = ttk.Frame(self)
        rtu_frame.pack(fill=tk.X)
        
        # 第一行：COM口和波特率
        self.rtu_connection_label = ttk.Label(rtu_frame, text=self.language_manager.get_text("rtu_connection"))
        self.rtu_connection_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        
        # 自动识别COM口
        self.rtu_port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(rtu_frame, textvariable=self.rtu_port_var, width=12)
        self.port_combo.grid(row=0, column=1, padx=(0, 5))
        
        # 刷新COM口按钮
        self.refresh_btn = ttk.Button(rtu_frame, text=self.language_manager.get_text("refresh"), 
                                     command=self.refresh_ports, width=6)
        self.refresh_btn.grid(row=0, column=2, padx=(0, 5))
        
        self.baud_rate_label = ttk.Label(rtu_frame, text=self.language_manager.get_text("baud_rate"))
        self.baud_rate_label.grid(row=0, column=3, sticky=tk.W, padx=(0, 5))
        self.baudrate_var = tk.StringVar(value="9600")
        ttk.Combobox(rtu_frame, textvariable=self.baudrate_var, 
                     values=["9600", "19200", "38400", "57600", "115200"], 
                     width=8).grid(row=0, column=4, padx=(0, 10))
        
        # 第二行：从站ID和其他设置
        self.slave_id_label = ttk.Label(rtu_frame, text=self.language_manager.get_text("slave_id"))
        self.slave_id_label.grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        self.slave_id_var = tk.StringVar(value="1")
        slave_id_spinbox = ttk.Spinbox(rtu_frame, textvariable=self.slave_id_var, 
                                       from_=1, to=247, width=8)
        slave_id_spinbox.grid(row=1, column=1, padx=(0, 5))
        
        self.timeout_label = ttk.Label(rtu_frame, text=self.language_manager.get_text("timeout_seconds"))
        self.timeout_label.grid(row=1, column=2, sticky=tk.W, padx=(0, 5))
        self.timeout_var = tk.StringVar(value="10")
        timeout_spinbox = ttk.Spinbox(rtu_frame, textvariable=self.timeout_var, 
                                     from_=1, to=60, width=8)
        timeout_spinbox.grid(row=1, column=3, padx=(0, 10))
        
        # 连接按钮
        self.connect_rtu_btn = ttk.Button(rtu_frame, text=self.language_manager.get_text("connect_rtu"))
        self.connect_rtu_btn.grid(row=1, column=4, padx=(0, 5))
        
        self.disconnect_btn = ttk.Button(rtu_frame, text=self.language_manager.get_text("disconnect"))
        self.disconnect_btn.grid(row=1, column=5)
        
        # 初始化COM口列表
        self.refresh_ports()

    def update_buttons_state(self, is_connected):
        """更新按钮状态"""
        if is_connected:
            # 已连接：禁用连接按钮，启用断开按钮
            self.connect_rtu_btn.configure(state="disabled")
            self.disconnect_btn.configure(state="normal")
        else:
            # 未连接：启用连接按钮，禁用断开按钮
            self.connect_rtu_btn.configure(state="normal")
            self.disconnect_btn.configure(state="disabled")

    def update_language(self, language_manager):
        """更新语言"""
        self.language_manager = language_manager
        
        # 更新框架标题
        self.configure(text=self.language_manager.get_text("connection_settings"))
        
        # 更新标签文本
        self.rtu_connection_label.configure(text=self.language_manager.get_text("rtu_connection"))
        self.refresh_btn.configure(text=self.language_manager.get_text("refresh"))
        self.baud_rate_label.configure(text=self.language_manager.get_text("baud_rate"))
        self.slave_id_label.configure(text=self.language_manager.get_text("slave_id"))
        self.timeout_label.configure(text=self.language_manager.get_text("timeout_seconds"))
        
        # 更新按钮文本
        self.connect_rtu_btn.configure(text=self.language_manager.get_text("connect_rtu"))
        self.disconnect_btn.configure(text=self.language_manager.get_text("disconnect"))

    def refresh_ports(self):
        """刷新可用COM口列表"""
        try:
            # 获取系统所有可用串口
            ports = [port.device for port in serial.tools.list_ports.comports()]
            
            if ports:
                self.port_combo['values'] = ports
                # 如果有COM口，默认选择第一个
                if not self.rtu_port_var.get() or self.rtu_port_var.get() not in ports:
                    self.rtu_port_var.set(ports[0])
            else:
                self.port_combo['values'] = ['无可用串口']
                self.rtu_port_var.set('')
                
        except Exception as e:
            # 如果无法获取串口列表，提供默认选项
            default_ports = ['COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8']
            self.port_combo['values'] = default_ports
            if not self.rtu_port_var.get():
                self.rtu_port_var.set('COM1')

class TableControlFrame(ttk.LabelFrame):
    """表格控制框架"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, text="表格选择", padding=10, **kwargs)
        self.setup_table_controls()
    
    def setup_table_controls(self):
        """设置表格控制控件"""
        ttk.Label(self, text="选择表格:").pack(side=tk.LEFT, padx=(0, 5))
        self.table_var = tk.IntVar(value=802)
        table_combo = ttk.Combobox(self, textvariable=self.table_var, 
                                   values=[802, 805, 899], state="readonly", width=10)
        table_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(self, text="起始地址:").pack(side=tk.LEFT, padx=(0, 5))
        self.start_address_var = tk.StringVar(value="40000")
        ttk.Entry(self, textvariable=self.start_address_var, width=10).pack(side=tk.LEFT, padx=(0, 10))
        
        self.read_btn = ttk.Button(self, text="读取数据")
        self.read_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.write_btn = ttk.Button(self, text="写入数据")
        self.write_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 自动刷新设置
        self.auto_refresh_var = tk.BooleanVar()
        ttk.Checkbutton(self, text="自动刷新", variable=self.auto_refresh_var).pack(side=tk.LEFT, padx=(20, 0))
        
        ttk.Label(self, text="刷新间隔(秒):").pack(side=tk.LEFT, padx=(10, 5))
        self.refresh_interval_var = tk.StringVar(value="5")
        ttk.Entry(self, textvariable=self.refresh_interval_var, width=5).pack(side=tk.LEFT)