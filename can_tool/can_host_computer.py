import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import time
from datetime import datetime
import json
import struct
import ctypes
from ctypes import *
from can_protocol_config import *  # 导入配置文件
from lang_config import LANGUAGES
import sys
import os

# 创芯科技CAN API常量
VCI_USBCAN2 = 4
STATUS_OK = 1

def get_resource_path(filename):
    """
    获取资源文件路径，兼容开发环境和PyInstaller打包后的环境
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后的exe
        base_path = sys._MEIPASS
    else:
        # 源码运行
        base_path = os.path.abspath(".")
    return os.path.join(base_path, filename)


class VCI_INIT_CONFIG(Structure):  
    _fields_ = [("AccCode", c_uint),
                ("AccMask", c_uint),
                ("Reserved", c_uint),
                ("Filter", c_ubyte),
                ("Timing0", c_ubyte),
                ("Timing1", c_ubyte),
                ("Mode", c_ubyte)
                ]  

class VCI_CAN_OBJ(Structure):  
    _fields_ = [("ID", c_uint),
                ("TimeStamp", c_uint),
                ("TimeFlag", c_ubyte),
                ("SendType", c_ubyte),
                ("RemoteFlag", c_ubyte),
                ("ExternFlag", c_ubyte),
                ("DataLen", c_ubyte),
                ("Data", c_ubyte*8),
                ("Reserved", c_ubyte*3)
                ] 

class VCI_CAN_OBJ_ARRAY(Structure):
    _fields_ = [('SIZE', ctypes.c_uint16), ('STRUCT_ARRAY', ctypes.POINTER(VCI_CAN_OBJ))]

    def __init__(self, num_of_structs):
        self.STRUCT_ARRAY = ctypes.cast((VCI_CAN_OBJ * num_of_structs)(), ctypes.POINTER(VCI_CAN_OBJ))
        self.SIZE = num_of_structs
        self.ADDR = self.STRUCT_ARRAY[0]

class CANalystCANBus:
    """创芯科技CAN总线类"""
    def __init__(self, device_type=VCI_USBCAN2, device_index=0, can_index=0):
        self.device_type = device_type
        self.device_index = device_index
        self.can_index = can_index
        self.can_dll = None
        self.is_connected = False
        
    def connect(self, baudrate=500000):
        """连接CAN设备"""
        try:
            # 加载DLL
            self.can_dll = windll.LoadLibrary('./ControlCAN.dll')
            
            # 打开设备
            ret = self.can_dll.VCI_OpenDevice(self.device_type, self.device_index, 0)
            if ret != STATUS_OK:
                raise Exception("打开设备失败")
                
            # 设置波特率
            timing0, timing1 = self.get_timing(baudrate)
            
            # 初始化CAN
            vci_initconfig = VCI_INIT_CONFIG(0x80000008, 0xFFFFFFFF, 0,
                                           0, timing0, timing1, 0)
            ret = self.can_dll.VCI_InitCAN(self.device_type, self.device_index, 
                                          self.can_index, byref(vci_initconfig))
            if ret != STATUS_OK:
                raise Exception("初始化CAN失败")
                
            # 启动CAN
            ret = self.can_dll.VCI_StartCAN(self.device_type, self.device_index, self.can_index)
            if ret != STATUS_OK:
                raise Exception("启动CAN失败")
                
            self.is_connected = True
            return True
            
        except Exception as e:
            raise Exception(f"连接CAN设备失败: {str(e)}")
            
    def get_timing(self, baudrate):
        """根据波特率获取定时参数"""
        timing_map = {
            250000: (0x03, 0x1C),  # 250kbps
            500000: (0x00, 0x1C),  # 500kbps
        }
        return timing_map.get(baudrate, (0x00, 0x1C))
        
    def send(self, can_id, data):
        """发送CAN报文"""
        if not self.is_connected:
            raise Exception("CAN设备未连接")
            
        # 创建数据数组
        ubyte_array = c_ubyte * 8
        can_data = ubyte_array(*data[:8])
        
        # 创建CAN对象
        ubyte_3array = c_ubyte * 3
        reserved = ubyte_3array(0, 0, 0)
        vci_can_obj = VCI_CAN_OBJ(can_id, 0, 0, 1, 0, 0, len(data), can_data, reserved)
        
        # 发送数据
        ret = self.can_dll.VCI_Transmit(self.device_type, self.device_index, 
                                       self.can_index, byref(vci_can_obj), 1)
        if ret != STATUS_OK:
            raise Exception("发送CAN报文失败")
            
    def receive(self, timeout=100):
        """接收CAN报文"""
        if not self.is_connected:
            return None
            
        try:
            # 创建接收缓冲区
            rx_vci_can_obj = VCI_CAN_OBJ_ARRAY(2500)
            
            # 接收数据
            ret = self.can_dll.VCI_Receive(self.device_type, self.device_index, 
                                          self.can_index, byref(rx_vci_can_obj.ADDR), 2500, timeout)
            
            if ret > 0:
                messages = []
                for i in range(ret):
                    msg = rx_vci_can_obj.STRUCT_ARRAY[i]
                    data = list(msg.Data[:msg.DataLen])
                    messages.append({
                        'id': msg.ID,
                        'data': data,
                        'length': msg.DataLen,
                        'timestamp': msg.TimeStamp
                    })
                return messages
            elif ret == 0:
                # 超时，没有接收到数据
                return None
            else:
                # 接收错误
                print(f"VCI_Receive返回错误: {ret}")
                return None
                
        except Exception as e:
            print(f"接收CAN报文错误: {str(e)}")
            return None
        
    def disconnect(self):
        """断开连接"""
        if self.can_dll and self.is_connected:
            self.can_dll.VCI_CloseDevice(self.device_type, self.device_index)
            self.is_connected = False

class CANHostComputer:
    def __init__(self, parent_frame=None):
        """
        初始化CAN工具
        Args:
            parent_frame: 父框架，如果为None则创建独立窗口
        """
        self.parent_frame = parent_frame
        self.is_embedded = parent_frame is not None
        
        if not self.is_embedded:
            # 独立模式：创建自己的root窗口
            self.root = tk.Tk()
            self.root.title("CAN协议上位机 - 创芯科技CANalyst-II")
            
            # 设置窗口初始大小和最小尺寸
            window_width = 1400
            window_height = 800
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2
            self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
            self.root.minsize(1000, 700)
            
            # 设置窗口图标
            self.set_window_icon()
            
            # 创建主框架
            self.main_frame = ttk.Frame(self.root)
            self.main_frame.pack(fill=tk.BOTH, expand=True)
        else:
            # 嵌入模式：使用传入的父框架
            self.root = None
            self.main_frame = parent_frame
        
        # CAN相关变量
        self.can_bus = None
        self.is_connected = False
        self.is_running = False
        self.is_receiving = False  # 新增接收状态
        self.last_heartbeat_time = None
        self.heartbeat_monitor_thread = None
        
        # 统计变量
        self.sent_count = 0
        self.received_count = 0
        self.heartbeat_count = 0  # 新增心跳计数器
        
        # 发送统计变量
        self.sent_305_count = 0
        self.sent_307_count = 0
        
        # 语言设置
        self.lang = 'zh' # 默认中文
        self.lang_var = tk.StringVar(value=self.lang)
        
        # 创建界面
        self.create_widgets()
    def set_window_icon(self):
        """设置窗口图标"""
        try:
            # 获取图标文件路径
            icon_path = get_resource_path('BQC.ico')        
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
            else:
                print(f"图标文件不存在: {icon_path}")
        except Exception as e:
            print(f"设置窗口图标失败: {e}")

    def create_widgets(self):
        # 主框架
        if self.is_embedded:
            # 嵌入模式：使用传入的父框架
            main_frame = self.main_frame
        else:
            # 独立模式：创建新的主框架
            main_frame = ttk.Frame(self.root)
            main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 语言选择（只在独立模式下显示）
        if not self.is_embedded:
            lang_frame = ttk.Frame(self.root)
            lang_frame.pack(fill="x", padx=10, pady=2)
            ttk.Label(lang_frame, text=LANGUAGES[self.lang]['language']).pack(side="left")
            self.lang_var = tk.StringVar(value=self.lang)
            lang_combo = ttk.Combobox(lang_frame, textvariable=self.lang_var, values=['zh', 'en'], width=8, state="readonly")
            lang_combo.pack(side="left")
            lang_combo.bind("<<ComboboxSelected>>", self.on_language_change)
        
        # 连接设置框架
        self.connection_frame = ttk.LabelFrame(main_frame, text="连接设置", padding="10")
        connection_frame = self.connection_frame
        connection_frame.pack(fill="x", pady=5)
        
        # 第一行：设备设置
        row1 = ttk.Frame(connection_frame)
        row1.pack(fill="x", pady=2)
        
        ttk.Label(row1, text="设备类型:").pack(side="left", padx=5)
        self.device_type_var = tk.StringVar(value="VCI_USBCAN2")
        device_type_combo = ttk.Combobox(row1, textvariable=self.device_type_var, 
                                       values=["VCI_USBCAN2"], width=15, state="readonly")
        device_type_combo.pack(side="left", padx=5)
        
        ttk.Label(row1, text="设备索引:").pack(side="left", padx=5)
        self.device_index_var = tk.StringVar(value="0")
        device_index_combo = ttk.Combobox(row1, textvariable=self.device_index_var, 
                                        values=["0", "1"], width=5)
        device_index_combo.pack(side="left", padx=5)
        
        ttk.Label(row1, text="CAN通道:").pack(side="left", padx=5)
        self.can_index_var = tk.StringVar(value="0")
        can_index_combo = ttk.Combobox(row1, textvariable=self.can_index_var, 
                                      values=["0", "1"], width=5)
        can_index_combo.pack(side="left", padx=5)
        
        # 第二行：波特率设置
        row2 = ttk.Frame(connection_frame)
        row2.pack(fill="x", pady=2)
        
        ttk.Label(row2, text="波特率:").pack(side="left", padx=5)
        self.baudrate_var = tk.StringVar(value="500000")
        baudrate_combo = ttk.Combobox(row2, textvariable=self.baudrate_var,
                                     values=["250000", "500000"], width=10)
        baudrate_combo.pack(side="left", padx=5)
        
        # 连接按钮
        self.connect_btn = ttk.Button(row2, text="连接", command=self.connect_can)
        self.connect_btn.pack(side="left", padx=10)
        
        self.disconnect_btn = ttk.Button(row2, text="断开", command=self.disconnect_can, state="disabled")
        self.disconnect_btn.pack(side="left", padx=5)
        
        # 控制框架
        self.control_frame = ttk.LabelFrame(main_frame, text="控制", padding="10")
        control_frame = self.control_frame
        control_frame.pack(fill="x", pady=5)
        
        # 控制按钮
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill="x")
        
        # 发送控制
        send_frame = ttk.Frame(btn_frame)
        send_frame.pack(side="left", padx=10)
        
        ttk.Label(send_frame, text="发送控制:").pack(side="left")
        self.start_btn = ttk.Button(send_frame, text="启动发送", command=self.start_sending, state="disabled")
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(send_frame, text="停止发送", command=self.stop_sending, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        
        # 接收控制
        receive_frame = ttk.Frame(btn_frame)
        receive_frame.pack(side="left", padx=10)
        
        ttk.Label(receive_frame, text="接收控制:").pack(side="left")
        self.receive_var = tk.BooleanVar(value=False)
        self.receive_check = ttk.Checkbutton(receive_frame, text="开启接收", 
                                           variable=self.receive_var, 
                                           command=self.toggle_receive, 
                                           state="disabled")
        self.receive_check.pack(side="left", padx=5)
        
        # 状态显示
        lang = LANGUAGES[self.lang]
        self.status_var = tk.StringVar(value=lang['disconnected'])
        status_label = ttk.Label(btn_frame, textvariable=self.status_var)
        status_label.pack(side="right", padx=5)
        
        # 统计信息框架
        self.stats_frame = ttk.LabelFrame(main_frame, text="统计信息", padding="10")
        stats_frame = self.stats_frame
        stats_frame.pack(fill="x", pady=5)
        
        stats_inner = ttk.Frame(stats_frame)
        stats_inner.pack(fill="x")
        
        # 发送统计
        ttk.Label(stats_inner, text="发送:").grid(row=0, column=0, sticky="w", padx=5)
        self.sent_count_var = tk.StringVar(value="0")
        ttk.Label(stats_inner, textvariable=self.sent_count_var).grid(row=0, column=1, padx=5)
        
        # 接收统计
        ttk.Label(stats_inner, text="接收:").grid(row=0, column=2, sticky="w", padx=5)
        self.received_count_var = tk.StringVar(value="0")
        ttk.Label(stats_inner, textvariable=self.received_count_var).grid(row=0, column=3, padx=5)
        
        # 心跳状态
        ttk.Label(stats_inner, text="心跳状态:").grid(row=0, column=4, sticky="w", padx=5)
        lang = LANGUAGES[self.lang]
        self.heartbeat_status_var = tk.StringVar(value=lang['normal'])
        self.heartbeat_status_label = ttk.Label(stats_inner, textvariable=self.heartbeat_status_var)
        self.heartbeat_status_label.grid(row=0, column=5, padx=5)
        
        # 创建左右分栏布局
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True, pady=5)
        
        # 左侧：发送数据和实时数据
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # 发送数据显示框架
        self.send_data_frame = ttk.LabelFrame(left_frame, text="发送数据", padding="10")
        send_data_frame = self.send_data_frame
        send_data_frame.pack(fill="x", pady=5)
        
        # 创建发送数据表格
        self.create_send_data_table(send_data_frame)
        
        # 实时数据表格显示框架
        self.data_frame = ttk.LabelFrame(left_frame, text="实时数据", padding="10")
        data_frame = self.data_frame
        data_frame.pack(fill="both", expand=True, pady=5)
        
        # 创建表格
        self.create_data_table(data_frame)
        
        # 右侧：日志框架
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        # 日志框架
        self.log_frame = ttk.LabelFrame(right_frame, text="通信日志", padding="10")
        log_frame = self.log_frame
        log_frame.pack(fill="both", expand=True)
        
        # 日志控制按钮 - 移到日志文本框上方
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill="x", pady=(0, 5))
        
        clear_btn = ttk.Button(log_btn_frame, text="清空日志", command=self.clear_log)
        clear_btn.pack(side="left")
        
        # 将保存日志按钮改为勾选框 - 默认不勾选
        self.auto_save_var = tk.BooleanVar(value=False)  # 默认不勾选
        self.auto_save_check = ttk.Checkbutton(log_btn_frame, text="自动保存日志", 
                                             variable=self.auto_save_var, 
                                             command=self.toggle_auto_save)
        self.auto_save_check.pack(side="left", padx=5)
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill="both", expand=True)
        
        # 配置文本标签颜色
        self.log_text.tag_configure("heartbeat_red", foreground="red")
        
        # 初始化日志文件相关变量
        self.log_file = None
        self.log_filename = None
        
        # 程序启动时自动开始保存日志（只在独立模式下）
        if not self.is_embedded and self.root:
            self.root.after(100, self.start_auto_save_on_startup)
    
    def toggle_auto_save(self):
        """切换自动保存日志功能"""
        if self.auto_save_var.get():
            self.start_auto_save()
        else:
            self.stop_auto_save()
    
    def start_auto_save(self):
        """开始自动保存日志"""
        try:
            # 弹出文件保存对话框
            filetypes = [("日志文件", "*.txt"), ("所有文件", "*.*")]
            filename = filedialog.asksaveasfilename(
                title="选择日志保存路径",
                defaultextension=".txt",
                filetypes=filetypes,
                initialfile=f"can_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            if not filename:
                # 用户取消选择，自动保存不生效
                self.auto_save_var.set(False)
                return

            self.log_filename = filename
            self.log_file = open(self.log_filename, 'w', encoding='utf-8')

            # 写入日志文件头部信息
            header = f"CAN协议上位机日志文件\n"
            header += f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            header += f"设备类型: 创芯科技CANalyst-II\n"
            header += "=" * 50 + "\n\n"
            self.log_file.write(header)
            self.log_file.flush()

            self.log_message(f"自动保存日志已开启，日志文件: {self.log_filename}")

        except Exception as e:
            messagebox.showerror("错误", f"无法创建日志文件: {str(e)}")
            self.auto_save_var.set(False)
    
    def stop_auto_save(self):
        """停止自动保存日志"""
        if self.log_file:
            try:
                # 写入日志文件尾部信息
                footer = f"\n" + "=" * 50 + "\n"
                footer += f"日志结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                footer += f"总日志条数: {self.get_log_line_count()}\n"
                
                self.log_file.write(footer)
                self.log_file.close()
                
                self.log_message(f"自动保存日志已停止，日志文件: {self.log_filename}")
                
            except Exception as e:
                self.log_message(f"关闭日志文件时出错: {str(e)}")
            
            self.log_file = None
            self.log_filename = None
    
    def get_log_line_count(self):
        """获取日志行数"""
        try:
            content = self.log_text.get(1.0, tk.END)
            return len(content.split('\n')) - 1  # 减去最后一行空行
        except:
            return 0
    
    def log_message(self, message, color="black"):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # 构建完整的日志消息
        log_entry = f"[{timestamp}] {message}\n"
        
        # 插入到界面文本框
        self.log_text.insert(tk.END, log_entry)
        
        # 检查是否包含"心跳状态"并设置颜色
        if "心跳状态" in message:
            # 获取刚插入的行的起始和结束位置
            last_line_start = self.log_text.index("end-2l linestart")
            last_line_end = self.log_text.index("end-1c")
            
            # 为整行设置红色标签
            self.log_text.tag_add("heartbeat_red", last_line_start, last_line_end)
        
        self.log_text.see(tk.END)
        
        # 如果开启了自动保存，同时写入文件
        if self.auto_save_var.get() and self.log_file:
            try:
                self.log_file.write(log_entry)
                self.log_file.flush()  # 立即写入文件，确保数据不丢失
            except Exception as e:
                # 如果写入文件失败，在界面上显示错误
                error_msg = f"[{timestamp}] 写入日志文件失败: {str(e)}\n"
                self.log_text.insert(tk.END, error_msg)
                self.log_text.see(tk.END)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
        
        # 如果开启了自动保存，在日志文件中记录清空操作
        if self.auto_save_var.get() and self.log_file:
            try:
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                clear_msg = f"[{timestamp}] 用户手动清空日志\n"
                self.log_file.write(clear_msg)
                self.log_file.flush()
            except Exception as e:
                pass  # 忽略清空时的文件写入错误
    
    def save_log(self):
        """手动保存日志到文件（保留原有功能作为备用）"""
        try:
            filename = f"can_log_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.get(1.0, tk.END))
            messagebox.showinfo("保存成功", f"日志已保存到: {filename}")
        except Exception as e:
            messagebox.showerror("保存失败", f"无法保存日志: {str(e)}")
    
    def __del__(self):
        """析构函数，确保程序退出时关闭日志文件"""
        if hasattr(self, 'log_file') and self.log_file:
            try:
                self.log_file.close()
            except:
                pass
        
    def connect_can(self):
        """连接CAN总线"""
        try:
            device_type = VCI_USBCAN2
            device_index = int(self.device_index_var.get())
            can_index = int(self.can_index_var.get())
            baudrate = int(self.baudrate_var.get())
            
            self.log_message(f"正在连接CAN设备...")
            self.log_message(f"设备类型: VCI_USBCAN2, 设备索引: {device_index}, CAN通道: {can_index}, 波特率: {baudrate}")
            
            # 创建CAN总线对象
            self.can_bus = CANalystCANBus(device_type, device_index, can_index)
            self.can_bus.connect(baudrate)
            
            self.is_connected = True
            
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            self.start_btn.config(state="normal")
            self.receive_check.config(state="normal")  # 确保复选框可用
            
            lang = LANGUAGES[self.lang]
            self.status_var.set(lang['connected'])
            lang = LANGUAGES[self.lang]
            self.heartbeat_status_var.set(lang['waiting'])  # 初始状态为等待
            self.heartbeat_count = 0  # 重置心跳计数
            
            # 重置表格中的心跳状态
            current_time = datetime.now().strftime("%H:%M:%S")
            lang = LANGUAGES[self.lang]
            self.update_table_item('0x351', lang['table_351'][0][0], '0', '', lang['waiting'], current_time)
            
            # 重置发送数据表格状态
            lang = LANGUAGES[self.lang]
            self.update_send_data_table(0x305, lang['stop_send'], 0, current_time)
            self.update_send_data_table(0x307, lang['stop_send'], 0, current_time)
            
            self.log_message("CAN设备连接成功")
            
        except Exception as e:
            messagebox.showerror("连接错误", f"无法连接CAN设备: {str(e)}")
            self.log_message(f"连接失败: {str(e)}")
    
    def _initial_receive_test(self):
        """连接后立即测试接收"""
        try:
            # 测试接收3秒
            start_time = time.time()
            received_count = 0
            
            while time.time() - start_time < 3:
                messages = self.can_bus.receive(timeout=100)
                if messages:
                    received_count += len(messages)
                    for msg in messages:
                        self.log_message(f"初始测试接收: ID=0x{msg['id']:03X}, 数据: {bytes(msg['data']).hex()}")
                time.sleep(0.1)
            
            if received_count > 0:
                self.log_message(f"初始测试成功，接收到 {received_count} 个报文")
            else:
                self.log_message("初始测试未接收到报文，请检查通道设置")
                
        except Exception as e:
            self.log_message(f"初始测试错误: {str(e)}")
            
    def disconnect_can(self):
        """断开CAN连接"""
        if self.can_bus:
            self.stop_sending()
            self.stop_receiving()
            self.can_bus.disconnect()
            self.can_bus = None
            
        self.is_connected = False
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")
        self.receive_check.config(state="disabled")  # 禁用接收复选框
        self.receive_var.set(False)  # 取消勾选
        self.toggle_receive()

        lang = LANGUAGES[self.lang]
        self.status_var.set(lang['disconnected'])
        self.heartbeat_count = 0  # 重置心跳计数
        
        # 重置表格中的心跳状态
        current_time = datetime.now().strftime("%H:%M:%S")
        lang = LANGUAGES[self.lang]
        self.update_table_item('0x351', lang['table_351'][0][0], '0', '', lang['stop'], current_time)
        
        # 重置发送数据表格状态
        lang = LANGUAGES[self.lang]
        self.update_send_data_table(0x305, lang['stop_send'], 0, current_time)
        self.update_send_data_table(0x307, lang['stop_send'], 0, current_time)
        
        self.log_message("CAN设备已断开")
    
    def start_sending(self):
        """开始发送CAN报文"""
        if not self.is_connected:
            return
            
        self.is_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        
        # 重置发送计数
        self.sent_305_count = 0
        self.sent_307_count = 0
        
        # 更新发送数据表格初始状态 - 改为"正在发送"
        current_time = datetime.now().strftime("%H:%M:%S")
        lang = LANGUAGES[self.lang]
        self.update_send_data_table(0x305, lang['start_send_status'], 0, current_time)
        self.update_send_data_table(0x307, lang['start_send_status'], 0, current_time)
        
        # 启动发送线程
        self.send_thread = threading.Thread(target=self.send_messages, daemon=True)
        self.send_thread.start()
        
        self.log_message("开始发送CAN报文")
    
    def stop_sending(self):
        """停止发送CAN报文"""
        self.is_running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        
        # 更新发送数据表格停止状态 - 改为"已停止"
        current_time = datetime.now().strftime("%H:%M:%S")
        lang = LANGUAGES[self.lang]
        self.update_send_data_table(0x305, lang['stopped'], self.sent_305_count, current_time)
        self.update_send_data_table(0x307, lang['stopped'], self.sent_307_count, current_time)
        
        self.log_message("停止发送CAN报文")
        
    def send_messages(self):
        """发送CAN报文的线程函数"""
        while self.is_running and self.is_connected:
            try:
                # 发送ID为0x305的报文
                msg_305_data = self.create_305_message()
                self.can_bus.send(0x305, msg_305_data)
                self.sent_count += 1
                self.sent_305_count += 1
                self.sent_count_var.set(str(self.sent_count))
                
                # 更新发送数据表格 - 保持"正在发送"状态
                current_time = datetime.now().strftime("%H:%M:%S")
                lang = LANGUAGES[self.lang]
                self.update_send_data_table(0x305, lang['start_send_status'], self.sent_305_count, current_time)
                
                self.log_message(f"发送: ID=0x305, 数据: {msg_305_data.hex()}")
                
                # 发送ID为0x307的报文
                msg_307_data = self.create_307_message()
                self.can_bus.send(0x307, msg_307_data)
                self.sent_count += 1
                self.sent_307_count += 1
                self.sent_count_var.set(str(self.sent_count))
                
                # 更新发送数据表格 - 保持"正在发送"状态
                current_time = datetime.now().strftime("%H:%M:%S")
                lang = LANGUAGES[self.lang]
                self.update_send_data_table(0x307, lang['start_send_status'], self.sent_307_count, current_time)
                
                self.log_message(f"发送: ID=0x307, 数据: {msg_307_data.hex()}")
                
                time.sleep(1)  # 每秒发送一次
                
            except Exception as e:
                self.log_message(f"发送错误: {str(e)}")
                break
                
    def create_305_message(self):
        """创建0x305报文数据 - Keepalive from inverter to BMS"""
        # 根据协议文档：8个字节都是0
        data = bytearray(8)
        # 所有字节都是0，不需要额外设置，bytearray默认就是0
        return data
        
    def create_307_message(self):
        """创建0x307报文数据 - Inverter identification from inverter to BMS"""
        # 根据协议文档：0x12 0x34 0x56 0x78 V I C 0x00
        data = bytearray(8)
        data[0] = 0x12  # Byte 0
        data[1] = 0x34  # Byte 1
        data[2] = 0x56  # Byte 2
        data[3] = 0x78  # Byte 3
        data[4] = ord('V')  # Byte 4: ASCII 'V'
        data[5] = ord('I')  # Byte 5: ASCII 'I'
        data[6] = ord('C')  # Byte 6: ASCII 'C'
        data[7] = 0x00  # Byte 7: reserved for future use
        return data
                
    def parse_heartbeat_message(self, msg):
        """解析0x351报文 - 充放电信息（用作心跳标志）"""
        try:
            data = msg['data']
            parsed_data = parse_351_message(data)
            
            if parsed_data:
                # 更新表格
                self.update_table_data(0x351, parsed_data)
                
                self.log_message(f"充放电信息 - 充电电压限制: {parsed_data['charge_voltage_limit']:.1f}V, 最大充电电流: {parsed_data['max_charge_current']:.1f}A, 最大放电电流: {parsed_data['max_discharge_current']:.1f}A, 放电电压: {parsed_data['discharge_voltage']:.1f}V")
            else:
                self.log_message(f"0x351报文数据长度不足: {len(data)} 字节")
                
        except Exception as e:
            self.log_message(f"解析0x351报文错误: {str(e)}")
    
    def parse_bms_status_message(self, msg):
        """解析BMS状态报文 (0x355)"""
        try:
            data = msg['data']
            parsed_data = parse_355_message(data)
            
            if parsed_data:
                # 更新表格
                self.update_table_data(0x355, parsed_data)
                
                self.log_message(f"BMS状态 - SOC: {parsed_data['soc_value']}%, SOH: {parsed_data['soh_value']}%, 高精度SOC: {parsed_data['high_res_soc']:.2f}%")
            else:
                self.log_message(f"0x355报文数据长度不足: {len(data)} 字节")
                
        except Exception as e:
            self.log_message(f"解析BMS状态报文错误: {str(e)}")
    
    def parse_battery_info_message(self, msg):
        """解析电池信息报文 (0x356)"""
        try:
            data = msg['data']
            parsed_data = parse_356_message(data)
            
            if parsed_data:
                # 更新表格
                self.update_table_data(0x356, parsed_data)
                
                self.log_message(f"电池信息 - 电压: {parsed_data['battery_voltage']:.2f}V, 电流: {parsed_data['battery_current']:.1f}A, 温度: {parsed_data['battery_temperature']:.1f}°C")
            else:
                self.log_message(f"0x356报文数据长度不足: {len(data)} 字节")
                
        except Exception as e:
            self.log_message(f"解析电池信息报文错误: {str(e)}")
    
    def parse_error_message(self, msg):
        """解析错误报文 (0x35A)"""
        try:
            data = msg['data']
            parsed_data = parse_35A_message(data)
            
            if parsed_data:
                # 更新表格
                self.update_table_data(0x35A, parsed_data)
                
                # 记录警告信息
                warnings = parsed_data['warnings']
                active_warnings = [name for name, active in warnings.items() if active]
                if active_warnings:
                    self.log_message(f"检测到警告: {', '.join(active_warnings)}")
                else:
                    self.log_message("无警告信息")
            else:
                self.log_message(f"0x35A报文数据长度不足: {len(data)} 字节")
                
        except Exception as e:
            self.log_message(f"解析错误报文错误: {str(e)}")
    
    def parse_new_message(self, msg):
        """解析新的CAN报文"""
        msg_id = msg['id']
        data = msg['data']
        
        try:
            # 使用通用解析函数
            parsed_data = parse_can_message(msg_id, data)
            if parsed_data:
                # 统一使用现有的update_table_data方法
                self.update_table_data(msg_id, parsed_data)
                self.log_message(f"成功解析 0x{msg_id:03X}: {parsed_data}")
            else:
                self.log_message(f"无法解析报文: ID=0x{msg_id:03X}")
        except Exception as e:
            self.log_message(f"解析报文 0x{msg_id:03X} 出错: {str(e)}")
    
    def monitor_heartbeat(self):
        """监控心跳的线程函数"""
        self.log_message("心跳监控线程已启动")
        heartbeat_timeout_reported = False  # 添加标志，避免重复报告超时
        
        while self.is_receiving and self.is_connected:
            try:
                # 缩短接收超时时间，提高响应速度
                messages = self.can_bus.receive(timeout=10)
                
                if messages:
                    self.log_message(f"接收到 {len(messages)} 个报文")
                    for msg in messages:
                        # 在处理每个消息前检查停止标志
                        if not self.is_receiving:
                            break
                            
                        self.received_count += 1
                        self.received_count_var.set(str(self.received_count))
                        self.process_received_message(msg)
                        
                        # 检查心跳报文（0x351作为心跳标志）
                        if msg['id'] == 0x351:
                            self.last_heartbeat_time = time.time()
                            self.heartbeat_count += 1  # 增加心跳计数
                            lang = LANGUAGES[self.lang]
                            self.heartbeat_status_var.set(lang['normal'])
                            self.heartbeat_status_label.config(foreground="black") # 恢复黑色
                            
                            # 重置超时报告标志
                            heartbeat_timeout_reported = False
                            
                            # 更新表格中的心跳状态
                            current_time = datetime.now().strftime("%H:%M:%S")
                            lang = LANGUAGES[self.lang]
                            self.update_table_item('0x351', lang['table_351'][0][0], str(self.heartbeat_count), '', lang['normal'], current_time)
                            self.set_table_item_color('0x351', lang['table_351'][0][0], 'black')
                            
                            self.log_message(f"收到心跳标志: ID=0x351, 数据: {bytes(msg['data']).hex()}")
                            
            except Exception as e:
                if self.is_receiving:  # 只在仍在运行时报告错误
                    self.log_message(f"接收线程错误: {str(e)}")
                break  # 出错时退出循环
                
            # 在每次循环结束时检查停止标志
            if not self.is_receiving:
                break
                
            # 检查心跳超时（3秒未收到0x351）
            if self.last_heartbeat_time and (time.time() - self.last_heartbeat_time) > 3:
                if not heartbeat_timeout_reported:  # 只在第一次超时时报告
                    if not self.is_embedded and self.root:
                        self.root.after(0, self.handle_heartbeat_timeout)
                    heartbeat_timeout_reported = True
        
        self.log_message("心跳监控线程已退出")
    
    def process_received_message(self, msg):
        """处理接收到的CAN报文"""
        msg_id = msg['id']
        
        # 扩展支持的CAN ID列表
        supported_ids = [0x351, 0x355, 0x356, 0x35A]
        
        # 添加新的0x2nn系列ID支持
        for i in range(16):  # 支持电池地址0-15
            supported_ids.extend([
                0x200 + i, 0x210 + i, 0x220 + i, 0x230 + i, 0x240 + i, 0x250 + i, 0x260 + i,
                0x400 + i, 0x410 + i, 0x420 + i, 0x430 + i, 0x440 + i, 0x450 + i, 0x460 + i,
                0x470 + i, 0x480 + i, 0x490 + i, 0x4A0 + i
            ])
        
        if msg_id in supported_ids:
            self.log_message(f"解析报文: ID=0x{msg_id:03X}, 数据: {bytes(msg['data']).hex()}")
            
            # 根据协议解析具体内容
            if msg_id == 0x351:
                self.parse_heartbeat_message(msg)
            elif msg_id == 0x355:
                self.parse_bms_status_message(msg)
            elif msg_id == 0x356:
                self.parse_battery_info_message(msg)
            elif msg_id == 0x35A:
                self.parse_error_message(msg)
            else:
                # 处理新的CAN ID
                self.parse_new_message(msg)
                
    def handle_heartbeat_timeout(self):
        """处理心跳超时"""
        lang = LANGUAGES[self.lang]
        self.heartbeat_status_var.set(lang['stop'])
        # 设置统计信息区域为红色
        self.heartbeat_status_label.config(foreground="red")
        # 更新表格中的心跳状态
        current_time = datetime.now().strftime("%H:%M:%S")
        self.update_table_item('0x351', lang['table_351'][0][0], str(self.heartbeat_count), '', lang['stop'], current_time)
        # 设置表格中“停止”为红色
        self.set_table_item_color('0x351', lang['table_351'][0][0], 'red')
        # 日志记录
        self.log_message("警告: BMS心跳终止，3秒未收到0x351报文", color="red")

    def test_receive(self):
        """手动测试接收功能"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先连接CAN设备")
            return
            
        self.log_message("开始测试接收功能...")
        
        # 在单独的线程中测试接收
        test_thread = threading.Thread(target=self._test_receive_thread, daemon=True)
        test_thread.start()
    
    def _test_receive_thread(self):
        """测试接收线程"""
        try:
            # 测试接收5秒
            start_time = time.time()
            while time.time() - start_time < 5:
                messages = self.can_bus.receive(timeout=100)
                if messages:
                    for msg in messages:
                        self.log_message(f"测试接收: ID=0x{msg['id']:03X}, 数据: {bytes(msg['data']).hex()}")
                time.sleep(0.1)
            
            self.log_message("接收测试完成")
            
        except Exception as e:
            self.log_message(f"接收测试错误: {str(e)}")

    def diagnose_connection(self):
        """诊断连接问题"""
        if not self.is_connected:
            self.log_message("设备未连接，无法诊断")
            return
            
        self.log_message("开始连接诊断...")
        
        # 检查设备状态
        try:
            # 这里可以添加更多的诊断代码
            self.log_message("设备连接正常")
            self.log_message("建议检查：")
            self.log_message("1. CAN总线连接是否正确")
            self.log_message("2. 波特率是否匹配")
            self.log_message("3. 目标设备是否发送数据")
            self.log_message("4. CAN通道选择是否正确")
            
        except Exception as e:
            self.log_message(f"诊断错误: {str(e)}")

    def switch_channel(self):
        """切换CAN通道"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先连接CAN设备")
            return
            
        current_channel = int(self.can_index_var.get())
        new_channel = 1 if current_channel == 0 else 0
        
        self.log_message(f"切换CAN通道: {current_channel} -> {new_channel}")
        
        # 断开当前连接
        self.disconnect_can()
        
        # 更新通道设置
        self.can_index_var.set(str(new_channel))
        
        # 重新连接
        self.connect_can()

    def force_receive_test(self):
        """强制接收测试"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先连接CAN设备")
            return
            
        self.log_message("开始强制接收测试...")
        
        # 在单独的线程中测试接收
        test_thread = threading.Thread(target=self._force_receive_thread, daemon=True)
        test_thread.start()
    
    def _force_receive_thread(self):
        """强制接收测试线程"""
        try:
            # 测试接收10秒
            start_time = time.time()
            total_received = 0
            
            while time.time() - start_time < 10:
                messages = self.can_bus.receive(timeout=50)
                if messages:
                    total_received += len(messages)
                    for msg in messages:
                        self.log_message(f"强制测试接收: ID=0x{msg['id']:03X}, 数据: {bytes(msg['data']).hex()}")
                time.sleep(0.05)  # 更频繁的检查
            
            self.log_message(f"强制接收测试完成，总共接收: {total_received} 个报文")
            
            if total_received == 0:
                self.log_message("未接收到任何报文，建议：")
                self.log_message("1. 检查CAN通道设置（尝试切换通道）")
                self.log_message("2. 确认波特率设置正确")
                self.log_message("3. 检查CAN总线连接")
            
        except Exception as e:
            self.log_message(f"强制接收测试错误: {str(e)}")

    def toggle_receive(self):
        """切换接收状态"""
        if self.receive_var.get():
            self.start_receiving()
        else:
            self.stop_receiving()

    def start_receiving(self):
        """启动接收CAN报文的线程"""
        if not self.is_connected:
            self.log_message("请先连接CAN总线。", color="orange")
            self.receive_check.config(state="disabled")
            return
        
        if self.is_receiving:
            self.log_message("接收线程已在运行。", color="orange")
            return
        
        self.is_receiving = True
        
        # 重置心跳状态
        lang = LANGUAGES[self.lang]
        self.heartbeat_status_var.set(lang['waiting'])
        self.heartbeat_count = 0
        self.last_heartbeat_time = None
        
        # 重置表格中的心跳状态
        current_time = datetime.now().strftime("%H:%M:%S")
        self.update_table_item('0x351', lang['table_351'][0][0], '0', '', lang['waiting'], current_time)
        
        self.receive_thread = threading.Thread(target=self.monitor_heartbeat, daemon=True)
        self.receive_thread.start()
        self.log_message("已开启接收CAN报文。", color="green")
    
    def stop_receiving(self):
        """停止接收CAN报文的线程"""
        if not self.is_receiving:
            self.log_message("接收线程未运行。", color="orange")
            return
        
        self.is_receiving = False
        # 增加等待时间，确保线程有足够时间停止
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=3) # 给线程3秒时间停止
            if self.receive_thread.is_alive():
                self.log_message("警告：接收线程可能未完全停止", color="orange")
        
        # 重置心跳状态
        lang = LANGUAGES[self.lang]
        self.heartbeat_status_var.set(lang['stop'])
        self.heartbeat_count = 0
        self.last_heartbeat_time = None
        
        # 重置表格中的心跳状态
        current_time = datetime.now().strftime("%H:%M:%S")
        self.update_table_item('0x351', lang['table_351'][0][0], '0', '', lang['stop'], current_time)
        
        self.log_message("停止接收CAN报文。", color="green")

    def create_data_table(self, parent):
        """创建数据表格"""
        # 创建表格框架
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="both", expand=True)
        
        # 创建Treeview表格 - 调整高度
        lang = LANGUAGES[self.lang]
        columns = ('CAN ID', 'parameter', 'value', 'unit', 'status', 'refresh_time')
        column_texts = (lang['can_id'], lang['parameter'], lang['value'], lang['unit'], lang['status_col'], lang['refresh_time'])
        self.data_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)  # 增加高度
        
        # 设置列标题
        for i, col in enumerate(columns):
            self.data_tree.heading(col, text=column_texts[i])
            # 调整列宽
            if col == 'CAN ID':
                self.data_tree.column(col, width=80, anchor='center')
            elif col == 'parameter':
                self.data_tree.column(col, width=150, anchor='w')
            elif col == 'value':
                self.data_tree.column(col, width=100, anchor='center')
            elif col == 'unit':
                self.data_tree.column(col, width=60, anchor='center')
            elif col == 'status':
                self.data_tree.column(col, width=80, anchor='center')
            elif col == 'refresh_time':
                self.data_tree.column(col, width=120, anchor='center')
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.data_tree.yview)
        self.data_tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.data_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 初始化表格数据
        self.initialize_table_data()
    
    def initialize_table_data(self):
        """初始化表格数据"""
        lang = LANGUAGES[self.lang]
        for item in self.data_tree.get_children():
            self.data_tree.delete(item)
        
        # 0x351 - 心跳状态特殊处理
        self.data_tree.insert('', 'end', values=('0x351', lang['table_351'][0][0], '0', '', lang['waiting'], '--'))
        
        # 0x351 - 其他参数
        for label, key in lang['table_351'][1:]:  # 跳过第一个心跳状态
            unit = ''
            if 'voltage' in key or '电压' in label:
                unit = 'V'
            elif 'current' in key or '电流' in label:
                unit = 'A'
            self.data_tree.insert('', 'end', values=('0x351', label, '--', unit, lang['waiting'], '--'))
        
        # 0x355
        for label, key in lang.get('table_355', []):
            unit = '%' if 'soc' in key.lower() or 'soh' in key.lower() else ''
            self.data_tree.insert('', 'end', values=('0x355', label, '--', unit, lang['waiting'], '--'))
        
        # 0x356
        for label, key in lang.get('table_356', []):
            unit = ''
            if 'voltage' in key or '电压' in label:
                unit = 'V'
            elif 'current' in key or '电流' in label:
                unit = 'A'
            elif 'temperature' in key or '温度' in label:
                unit = '°C'
            self.data_tree.insert('', 'end', values=('0x356', label, '--', unit, lang['waiting'], '--'))
        
        # 0x35A - Alarm信息
        for label, key in lang['table_35A_alarm']:
            self.data_tree.insert('', 'end', values=('0x35A', label, '--', '', lang['waiting'], '--'))

        # 0x35A - Warning信息
        for label, key in lang['table_35A_warning']:
            self.data_tree.insert('', 'end', values=('0x35A', label, '--', '', lang['waiting'], '--'))
    
    def update_table_data(self, can_id, parsed_data):
        """更新表格数据"""
        lang = LANGUAGES[self.lang]
        current_time = datetime.now().strftime("%H:%M:%S")

        # ---------- 小工具：格式化标量 ----------
        def fmt_scalar(key, val):
            unit = ''
            if key == 'operation_mode':
                op = {
                    1: "Standby Mode", 2: "Run Mode", 3: "Charge Disabled !",
                    4: "Charge DC/DC !", 5: "Discharge Disabled !", 6: "Emergency !"
                }
                return op.get(val, f"模式{val}"), unit
            if key in ('state_of_charge', 'state_of_health'):
                return f"{float(val):.1f}", '%'
            if 'voltage' in key:
                return f"{float(val):.3f}", 'V'
            if 'current' in key:
                return f"{float(val):.1f}", 'A'
            if ('temperature' in key) or ('temp' in key):
                return f"{float(val):.1f}", '°C'
            if 'uptime' in key:
                return f"{val}", 's'
            if 'accelerometer' in key:
                return f"{val}", 'milli-g'
            if key == 'esp32_free_heap_size_byte':
                return f"{val}", 'B'
            if key in ('cycle_count', 'lifetime_hour', 'cell_balance_state', 'module_id'):
                u = 'h' if key == 'lifetime_hour' else ('次' if key == 'cycle_count' else '')
                return f"{val}", u
            if isinstance(val, bool):
                return str(int(val)), ''
            return str(val), ''

        # ---------- 各类报文专用处理 ----------
        if can_id == 0x351:
            self.update_table_item('0x351', lang['table_351'][1][0],
                                f"{parsed_data.get('charge_voltage_limit', 0):.1f}", 'V', lang['normal'], current_time)
            self.update_table_item('0x351', lang['table_351'][2][0],
                                f"{parsed_data.get('max_charge_current', 0):.1f}", 'A', lang['normal'], current_time)
            self.update_table_item('0x351', lang['table_351'][3][0],
                                f"{parsed_data.get('max_discharge_current', 0):.1f}", 'A', lang['normal'], current_time)
            self.update_table_item('0x351', lang['table_351'][4][0],
                                f"{parsed_data.get('discharge_voltage', 0):.1f}", 'V', lang['normal'], current_time)

        elif can_id == 0x355:
            self.update_table_item('0x355', lang['table_355'][0][0],
                                f"{parsed_data.get('soc_value', 0)}", '%', lang['normal'], current_time)
            self.update_table_item('0x355', lang['table_355'][1][0],
                                f"{parsed_data.get('soh_value', 0)}", '%', lang['normal'], current_time)
            self.update_table_item('0x355', lang['table_355'][2][0],
                                f"{parsed_data.get('high_res_soc', 0):.2f}", '%', lang['normal'], current_time)

        elif can_id == 0x356:
            self.update_table_item('0x356', lang['table_356'][0][0],
                                f"{parsed_data.get('battery_voltage', 0):.2f}", 'V', lang['normal'], current_time)
            self.update_table_item('0x356', lang['table_356'][1][0],
                                f"{parsed_data.get('battery_current', 0):.1f}", 'A', lang['normal'], current_time)
            self.update_table_item('0x356', lang['table_356'][2][0],
                                f"{parsed_data.get('battery_temperature', 0):.1f}", '°C', lang['normal'], current_time)

        elif can_id == 0x35A:
            alarms = parsed_data.get('alarms', {})
            warnings = parsed_data.get('warnings', {})
            for label, key in lang['table_35A_alarm']:
                self.update_table_item('0x35A', label, int(alarms.get(key, False)), '', lang['normal'], current_time)
            for label, key in lang['table_35A_warning']:
                self.update_table_item('0x35A', label, int(warnings.get(key, False)), '', lang['normal'], current_time)

        else:
            battery_addr = parsed_data.get('battery_address', 1)
            can_id_key = can_id
            if 0x200 <= can_id <= 0x2FF:
                can_id_key = can_id & 0xFF0
            elif 0x400 <= can_id <= 0x4FF:
                can_id_key = can_id & 0xFF0

            table_key = f'table_{can_id_key:X}'
            can_id_display = f"0x{can_id:03X}"
            if battery_addr != 1 or (can_id >= 0x200):
                can_id_display = f"0x{can_id:03X}(电池{battery_addr})"

            # ---------- 0x200 专用分段 ----------
            if can_id_key == 0x200:
                base_tbl = lang.get('table_200_base', [])
                status_tbl = lang.get('table_200_status', [])
                alarm_tbl = lang.get('table_200_alarms', [])

                if base_tbl or status_tbl or alarm_tbl:
                    for label, data_key in base_tbl:
                        if data_key not in parsed_data:
                            continue
                        val, unit = fmt_scalar(data_key, parsed_data[data_key])
                        self.update_table_item(can_id_display, label, val, unit, lang['normal'], current_time)

                    st = parsed_data.get('status', {})
                    for label, key in status_tbl:
                        self.update_table_item(can_id_display, label, int(st.get(key, False)), '', lang['normal'], current_time)

                    al = parsed_data.get('alarms', {})
                    for label, key in alarm_tbl:
                        self.update_table_item(can_id_display, label, int(al.get(key, False)), '', lang['normal'], current_time)
                    return
                else:
                    # 旧版 table_200 回退
                    for label, data_key in lang.get('table_200', []):
                        if data_key in parsed_data:
                            val, unit = fmt_scalar(data_key, parsed_data[data_key])
                        elif data_key in ('status', 'alarms'):
                            d = parsed_data.get(data_key, {})
                            if isinstance(d, dict):
                                on = [k for k, v in d.items() if v]
                                val = '、'.join(on) if on else '正常'
                                unit = ''
                            else:
                                val = str(d)
                                unit = ''
                        else:
                            continue
                        self.update_table_item(can_id_display, label, val, unit, lang['normal'], current_time)
                    return

            # ---------- 其它 CAN ID ----------
            if table_key not in lang:
                return
            for label, data_key in lang[table_key]:
                if data_key not in parsed_data:
                    continue
                val, unit = fmt_scalar(data_key, parsed_data[data_key])
                self.update_table_item(can_id_display, label, val, unit, lang['normal'], current_time)

    def update_table_item(self, can_id, parameter, value, unit, status, update_time):
        """更新表格中的单个项目，如果不存在则创建"""
        # 先检查是否已存在该项目
        for item in self.data_tree.get_children():
            values = self.data_tree.item(item)['values']
            if values[0] == can_id and values[1] == parameter:
                self.data_tree.item(item, values=(can_id, parameter, value, unit, status, update_time))
                return
        
        # 如果不存在，创建新条目
        self.data_tree.insert('', 'end', values=(can_id, parameter, value, unit, status, update_time))

    def create_send_data_table(self, parent):
        """创建发送数据表格"""
        # 创建表格框架
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="x")
        
        # 创建Treeview表格 - 调整高度
        lang = LANGUAGES[self.lang]
        columns = ('CAN ID', 'send_status', 'send_count', 'status', 'send_time')
        column_texts = (lang['can_id'], lang['send_status'], lang['send_count'], lang['status_col'], lang['send_time'])
        self.send_data_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=3)  # 减少高度
        
        # 设置列标题
        for i, col in enumerate(columns):
            self.send_data_tree.heading(col, text=column_texts[i])
            # 调整列宽
            if col == 'CAN ID':
                self.send_data_tree.column(col, width=80, anchor='center')
            elif col == 'send_status':
                self.send_data_tree.column(col, width=150, anchor='w')
            elif col == 'send_count':
                self.send_data_tree.column(col, width=100, anchor='center')
            elif col == 'status':
                self.send_data_tree.column(col, width=80, anchor='center')
            elif col == 'send_time':
                self.send_data_tree.column(col, width=120, anchor='center')
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.send_data_tree.yview)
        self.send_data_tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.send_data_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 初始化发送数据表格
        self.initialize_send_data_table()
    
    def initialize_send_data_table(self):
        """初始化发送数据表格"""
        lang = LANGUAGES[self.lang]
        
        # 清空现有数据
        for item in self.send_data_tree.get_children():
            self.send_data_tree.delete(item)
        
        # 添加0x305数据项 - 初始状态为"停止发送"
        self.send_data_tree.insert('', 'end', values=('0x305', lang['stop_send'], '0', lang['stop'], '--'))
        
        # 添加0x307数据项 - 初始状态为"停止发送"
        self.send_data_tree.insert('', 'end', values=('0x307', lang['stop_send'], '0', lang['stop'], '--'))
    
    def update_send_data_table(self, can_id, status, count, send_time):
        """更新发送数据表格"""
        lang = LANGUAGES[self.lang]
        if can_id == 0x305:
            self.update_send_table_item('0x305', status, str(count), lang['normal'], send_time)
        elif can_id == 0x307:
            self.update_send_table_item('0x307', status, str(count), lang['normal'], send_time)
    
    def update_send_table_item(self, can_id, send_status, count, status, send_time):
        """更新发送表格中的单个项目"""
        for item in self.send_data_tree.get_children():
            values = self.send_data_tree.item(item)['values']
            if values[0] == can_id:
                self.send_data_tree.item(item, values=(can_id, send_status, count, status, send_time))
                break

    def start_auto_save_on_startup(self):
        """程序启动时自动开始保存日志"""
        if self.auto_save_var.get():
            self.start_auto_save()

    def on_language_change(self, event=None):
        self.lang = self.lang_var.get()
        print(f"CAN工具语言切换: {self.lang}")
        self.refresh_ui_language()
    
    def set_language(self, language):
        """外部设置语言的方法，用于统一管理器调用"""
        if language in LANGUAGES:
            self.lang = language
            if hasattr(self, 'lang_var'):
                self.lang_var.set(language)
            print(f"CAN工具外部语言设置: {language}")
            self.refresh_ui_language()
            
            # 强制刷新界面
            if hasattr(self, 'root') and self.root:
                self.root.update_idletasks()
            elif hasattr(self, 'main_frame') and self.main_frame:
                self.main_frame.update_idletasks()
                
            print(f"CAN工具语言设置完成: {language}")
        else:
            print(f"CAN工具不支持的语言: {language}")

    def refresh_ui_language(self):
        """刷新UI语言显示"""
        lang = LANGUAGES[self.lang]
        
        # 更新窗口标题（只在独立模式下）
        if not self.is_embedded and self.root:
            self.root.title(lang['title'])
        
        # 更新按钮文本
        self.connect_btn.config(text=lang['connect'])
        self.disconnect_btn.config(text=lang['disconnect'])
        self.start_btn.config(text=lang['start_send'])
        self.stop_btn.config(text=lang['stop_send'])
        self.receive_check.config(text=lang['open_receive'])
        
        # 更新LabelFrame标题
        self.connection_frame.config(text=lang['connection_settings'])
        self.control_frame.config(text=lang['control'])
        self.stats_frame.config(text=lang['stat_info'])
        self.send_data_frame.config(text=lang['send_data'])
        self.data_frame.config(text=lang['realtime_data'])
        self.log_frame.config(text=lang['log'])
        
        # 更新连接状态显示
        current_status = self.status_var.get()
        if current_status in ['未连接', 'Disconnected']:
            self.status_var.set(lang['disconnected'])
        elif current_status in ['已连接', 'Connected']:
            self.status_var.set(lang['connected'])
        
        # 更新心跳状态显示
        current_heartbeat_status = self.heartbeat_status_var.get()
        if current_heartbeat_status in ['正常', 'Normal']:
            self.heartbeat_status_var.set(lang['normal'])
            self.heartbeat_status_label.config(foreground="black") # 恢复黑色
            self.set_table_item_color('0x351', lang['table_351'][0][0], 'black')
        elif current_heartbeat_status in ['等待', 'Waiting']:
            self.heartbeat_status_var.set(lang['waiting'])
            self.heartbeat_status_var.set(lang['waiting'])
            self.heartbeat_status_label.config(foreground="black") # 恢复黑色
            self.set_table_item_color('0x351', lang['table_351'][0][0], 'black')
        elif current_heartbeat_status in ['停止', 'Stop']:
            self.heartbeat_status_var.set(lang['stop'])
            self.heartbeat_status_var.set(lang['stop'])
            self.heartbeat_status_label.config(foreground="red") # 设置统计信息区域为红色
            self.set_table_item_color('0x351', lang['table_351'][0][0], 'red')
        
        # 更新标签文本
        self.update_label_texts(lang)
        
        # 重新初始化表格数据以更新列标题和内容
        self.refresh_table_headers()
        self.initialize_table_data()
        self.initialize_send_data_table()
    
    def update_label_texts(self, lang):
        """更新所有标签的文本"""
        # 这个方法会递归遍历所有控件并更新文本
        def update_widget_texts(widget):
            try:
                if isinstance(widget, ttk.Label):
                    text = widget.cget('text')
                    # 更新特定的标签文本
                    if '语言/Language:' in text or 'Language:' in text:
                        widget.config(text=lang['language'])
                    elif '设备类型:' in text or 'Device Type:' in text:
                        widget.config(text=lang.get('device_type', '设备类型:' if self.lang == 'zh' else 'Device Type:'))
                    elif '设备索引:' in text or 'Device Index:' in text:
                        widget.config(text=lang.get('device_index', '设备索引:' if self.lang == 'zh' else 'Device Index:'))
                    elif 'CAN通道:' in text or 'CAN Channel:' in text:
                        widget.config(text=lang.get('can_channel', 'CAN通道:' if self.lang == 'zh' else 'CAN Channel:'))
                    elif '波特率:' in text or 'Baud Rate:' in text:
                        widget.config(text=lang.get('baud_rate', '波特率:' if self.lang == 'zh' else 'Baud Rate:'))
                    elif '发送控制:' in text or 'Send Control:' in text:
                        widget.config(text=lang['send_control'])
                    elif '接收控制:' in text or 'Receive Control:' in text:
                        widget.config(text=lang['receive_control'])
                    elif '发送:' in text or 'Send:' in text:
                        widget.config(text=lang['send'] + ':')
                    elif '接收:' in text or 'Receive:' in text:
                        widget.config(text=lang['receive'] + ':')
                    elif '心跳状态:' in text or 'Heartbeat:' in text:
                        widget.config(text=lang['heartbeat_status'] + ':')
                elif isinstance(widget, ttk.Button):
                    text = widget.cget('text')
                    if '清空日志' in text or 'Clear Log' in text:
                        widget.config(text=lang['clear_log'])
                elif isinstance(widget, ttk.Checkbutton):
                    text = widget.cget('text')
                    if '自动保存日志' in text or 'Auto Save Log' in text:
                        widget.config(text=lang['auto_save_log'])
                
                # 递归更新所有子控件
                for child in widget.winfo_children():
                    update_widget_texts(child)
                    
            except Exception as e:
                print(f"更新控件文本时出错: {e}")
        
        # 从主框架开始递归更新
        if hasattr(self, 'main_frame'):
            update_widget_texts(self.main_frame)
        elif hasattr(self, 'root') and self.root:
            update_widget_texts(self.root)
    
    def refresh_table_headers(self):
        """刷新表格表头语言"""
        lang = LANGUAGES[self.lang]
        
        # 更新实时数据表格表头
        if hasattr(self, 'data_tree'):
            columns = ('CAN ID', 'parameter', 'value', 'unit', 'status', 'refresh_time')
            column_texts = (lang['can_id'], lang['parameter'], lang['value'], 
                           lang['unit'], lang['status_col'], lang['refresh_time'])
            for i, col in enumerate(columns):
                self.data_tree.heading(col, text=column_texts[i])
        
        # 更新发送数据表格表头
        if hasattr(self, 'send_data_tree'):
            columns = ('CAN ID', 'send_status', 'send_count', 'status', 'send_time')
            column_texts = (lang['can_id'], lang['send_status'], lang['send_count'], 
                           lang['status_col'], lang['send_time'])
            for i, col in enumerate(columns):
                self.send_data_tree.heading(col, text=column_texts[i])

    def set_table_item_color(self, can_id, parameter, color):
        """设置表格中特定行的字体颜色"""
        for item in self.data_tree.get_children():
            values = self.data_tree.item(item)['values']
            if values[0] == can_id and values[1] == parameter:
                self.data_tree.tag_configure('heartbeat_stop', foreground=color)
                self.data_tree.item(item, tags=('heartbeat_stop',))
                break

def main():
    # 独立运行模式
    app = CANHostComputer() 
    
    # 设置窗口关闭事件处理
    def on_closing():
        if app.auto_save_var.get():
            app.stop_auto_save()
        app.root.destroy()
    
    app.root.protocol("WM_DELETE_WINDOW", on_closing)
    app.root.mainloop()

def create_embedded_instance(parent_frame):
    """创建嵌入模式的实例，用于统一工具管理器"""
    return CANHostComputer(parent_frame)

if __name__ == "__main__":
    main()