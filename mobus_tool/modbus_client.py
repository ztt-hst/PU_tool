#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modbus客户端模块
"""

import serial
import time

class ModbusClient:
    def __init__(self):
        self.ser = None
        self.connected = False
        self.slave_id = 1
        self.timeout = 1  # 秒
        self.log_callback = None

    def set_log_callback(self, callback):
        self.log_callback = callback

    def connect_rtu(self, port, baudrate=9600, timeout=1):
        try:
            self.ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8, parity='N', stopbits=1, timeout=timeout)
            self.connected = self.ser.is_open
            self.timeout = timeout
            return self.connected
        except Exception as e:
            print(f"串口连接失败: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.connected = False

    def is_connected(self):
        return self.connected and self.ser and self.ser.is_open

    def calculate_crc16(self, data: bytes):
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

    def send_and_recv(self, request: bytes, resp_len: int):
        if not self.is_connected():
            return None
        self.ser.reset_input_buffer()
        self.ser.write(request)
        if self.log_callback:
            self.log_callback("发送：" + " ".join(f"{b:02X}" for b in request))
        time.sleep(0.05)
        response = self.ser.read(resp_len)
        if self.log_callback:
            self.log_callback("接收：" + " ".join(f"{b:02X}" for b in response))
        return response

    def parse_modbus_data(self, data_bytes, data_types=None):
        """
        根据数据类型解析Modbus数据
        data_bytes: 原始字节数据
        data_types: 数据类型列表，如 ['uint16', 'int16', 'uint32', 'string[4]']
        """
        if not data_types:
            # 默认按uint16处理
            return [data_bytes[i] << 8 | data_bytes[i+1] for i in range(0, len(data_bytes), 2)]
        
        result = []
        byte_index = 0
        
        for data_type in data_types:
            if byte_index >= len(data_bytes):
                break
                
            if data_type == 'uint16':
                if byte_index + 1 < len(data_bytes):
                    value = data_bytes[byte_index] << 8 | data_bytes[byte_index + 1]
                    result.append(value)
                    byte_index += 2
            elif data_type == 'int16':
                if byte_index + 1 < len(data_bytes):
                    value = data_bytes[byte_index] << 8 | data_bytes[byte_index + 1]
                    if value > 32767:
                        value = value - 65536
                    result.append(value)
                    byte_index += 2
            elif data_type == 'uint32':
                if byte_index + 3 < len(data_bytes):
                    value = (data_bytes[byte_index] << 24 | 
                            data_bytes[byte_index + 1] << 16 | 
                            data_bytes[byte_index + 2] << 8 | 
                            data_bytes[byte_index + 3])
                    result.append(value)
                    byte_index += 4
            elif data_type == 'int32':
                if byte_index + 3 < len(data_bytes):
                    value = (data_bytes[byte_index] << 24 | 
                            data_bytes[byte_index + 1] << 16 | 
                            data_bytes[byte_index + 2] << 8 | 
                            data_bytes[byte_index + 3])
                    if value > 0x7FFFFFFF:
                        value = value - 0x100000000
                    result.append(value)
                    byte_index += 4
            elif data_type.startswith('string['):
                # 修正字符串解析
                try:
                    str_len = int(data_type[7:-1])
                    if byte_index + str_len - 1 < len(data_bytes):
                        # 字符串解析：每个寄存器包含2个字符
                        chars = []
                        for i in range(0, str_len, 2):
                            if byte_index + i + 1 < len(data_bytes):
                                # 每个寄存器16位，包含2个8位字符
                                reg_val = data_bytes[byte_index + i] << 8 | data_bytes[byte_index + i + 1]
                                # 高字节在前，低字节在后
                                char1 = chr((reg_val >> 8) & 0xFF)
                                char2 = chr(reg_val & 0xFF)
                                chars.append(char1)
                                chars.append(char2)
                        
                        # 移除null字符和空格
                        result_str = ''.join(chars).rstrip('\x00').strip()
                        result.append(result_str)
                        byte_index += str_len
                    else:
                        result.append("")
                        byte_index += str_len
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"字符串解析错误: {e}")
                    result.append("")
                    byte_index += 2
            elif data_type == 'enum16':
                # enum16 按 uint16 处理
                if byte_index + 1 < len(data_bytes):
                    value = data_bytes[byte_index] << 8 | data_bytes[byte_index + 1]
                    result.append(value)
                    byte_index += 2
            elif data_type == 'bitfield32':
                # bitfield32 按 uint32 处理
                if byte_index + 3 < len(data_bytes):
                    value = (data_bytes[byte_index] << 24 | 
                            data_bytes[byte_index + 1] << 16 | 
                            data_bytes[byte_index + 2] << 8 | 
                            data_bytes[byte_index + 3])
                    result.append(value)
                    byte_index += 4
            else:
                # 未知类型，按uint16处理
                if byte_index + 1 < len(data_bytes):
                    value = data_bytes[byte_index] << 8 | data_bytes[byte_index + 1]
                    result.append(value)
                    byte_index += 2
        
        return result

    def read_holding_registers(self, address, count, data_types=None):
        # 组帧: [slave][0x03][addr_hi][addr_lo][cnt_hi][cnt_lo][crc_lo][crc_hi]
        slave = self.slave_id
        req = bytes([
            slave,
            0x03,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])
        crc = self.calculate_crc16(req)
        req += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        # 响应长度: 1+1+1+count*2+2
        resp_len = 5 + count * 2
        resp = self.send_and_recv(req, resp_len)
        if not resp or len(resp) < resp_len:
            return None
        # 校验CRC
        crc_calc = self.calculate_crc16(resp[:-2])
        crc_recv = resp[-2] | (resp[-1] << 8)
        if crc_calc != crc_recv:
            if self.log_callback:
                self.log_callback("CRC校验失败")
            return None
        # 解析数据
        if resp[1] != 0x03:
            return None
        reg_bytes = resp[3:-2]
        
        # 使用新的解析方法
        if data_types:
            return self.parse_modbus_data(reg_bytes, data_types)
        else:
            # 默认按uint16处理
            return [reg_bytes[i] << 8 | reg_bytes[i+1] for i in range(0, len(reg_bytes), 2)]

    def write_holding_register(self, address, value):
        slave = self.slave_id
        req = bytes([
            slave,
            0x06,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF
        ])
        crc = self.calculate_crc16(req)
        req += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        resp_len = 8  # 固定长度
        resp = self.send_and_recv(req, resp_len)
        if not resp or len(resp) < resp_len:
            return False
        crc_calc = self.calculate_crc16(resp[:-2])
        crc_recv = resp[-2] | (resp[-1] << 8)
        if crc_calc != crc_recv:
            if self.log_callback:
                self.log_callback("CRC校验失败")
            return False
        return resp[1] == 0x06

    def write_holding_registers(self, address, values):
        # 批量写入功能码0x10
        slave = self.slave_id
        count = len(values)
        byte_count = count * 2
        req = bytes([
            slave,
            0x10,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
            byte_count
        ])
        for v in values:
            req += bytes([(v >> 8) & 0xFF, v & 0xFF])
        crc = self.calculate_crc16(req)
        req += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        resp_len = 8
        resp = self.send_and_recv(req, resp_len)
        if not resp or len(resp) < resp_len:
            return False
        crc_calc = self.calculate_crc16(resp[:-2])
        crc_recv = resp[-2] | (resp[-1] << 8)
        if crc_calc != crc_recv:
            if self.log_callback:
                self.log_callback("CRC校验失败")
            return False
        return resp[1] == 0x10

    def read_input_registers(self, address, count):
        # 组帧: [slave][0x04][addr_hi][addr_lo][cnt_hi][cnt_lo][crc_lo][crc_hi]
        slave = self.slave_id
        req = bytes([
            slave,
            0x04,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])
        crc = self.calculate_crc16(req)
        req += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        resp_len = 5 + count * 2
        resp = self.send_and_recv(req, resp_len)
        if not resp or len(resp) < resp_len:
            return None
        crc_calc = self.calculate_crc16(resp[:-2])
        crc_recv = resp[-2] | (resp[-1] << 8)
        if crc_calc != crc_recv:
            if self.log_callback:
                self.log_callback("CRC校验失败")
            return None
        if resp[1] != 0x04:
            return None
        reg_bytes = resp[3:-2]
        regs = self.parse_modbus_data(reg_bytes, ['uint16'] * count)
        return regs 