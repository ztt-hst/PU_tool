#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SunSpec协议解析模块 - 支持model_xxx.json格式
"""

import json
import os

class SunSpecProtocol:
    """SunSpec协议解析类"""

    def __init__(self, model_dir='.'):
        self.model_dir = model_dir
        self.models = {}
        self.base_address = 0  # 默认0，可被扫描覆盖
        self.model_base_addrs = {}  # 新增：保存扫描到的模型地址
        self.load_models()

    def load_models(self, available_models=None):
        """
        加载模型定义。
        available_models: 可用模型ID列表（如[ 802, 805]），为None时加载全部支持的。
        """
        # 支持的模型及其文件名
        default_model_files = {
            1: 'model_1.json',
            802: 'model_802.json',
            #805: 'model_805.json',
            #899: 'model_899.json'
        }
        
        # 如果传入了扫描到的模型，动态构建文件映射
        if available_models is not None:
            model_files = {}
            for model_id in available_models:
                if model_id in default_model_files:
                    model_files[model_id] = default_model_files[model_id]
                else:
                    # 动态生成文件名
                    model_files[model_id] = f'model_{model_id}.json'
        else:
            model_files = default_model_files

        for table_id, filename in model_files.items():
            try:
                filepath = self.get_resource_path(filename)
                if not os.path.exists(filepath):
                    print(f"模型文件 {filename} 不存在，跳过。")
                    continue
                with open(filepath, 'r', encoding='utf-8') as f:
                    model_data = json.load(f)
                    self.models[table_id] = model_data
            except Exception as e:
                print(f"加载模型文件 {filename} 失败: {e}")

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

    def parse_table_data(self, table_id, data):
        """解析表格数据，支持model_xxx.json格式"""
        if table_id not in self.models:
            return None
            
        model_data = self.models[table_id]
        points = model_data['group']['points']
        groups = model_data['group'].get('groups', [])
        parsed_data = {}

        # 解析固定points部分
        current_offset = 0
        for point in points:
            name = point['name']
            field_type = point['type'].lower()
            size = point.get('size', 1)
            offset = point.get('offset', current_offset)
            raw_value = None
            value = None

            # 取出对应寄存器
            if offset + size <= len(data):
                regs = data[offset:offset+size]
                # 解析类型
                if field_type in ['uint16', 'sunssf']:
                    raw_value = regs[0]
                    if field_type == 'sunssf' or field_type == 'int16':
                        # 有符号
                        if raw_value > 32767:
                            raw_value = raw_value - 65536
                    value = raw_value
                elif field_type == 'int16':
                    raw_value = regs[0]
                    if raw_value > 32767:
                        raw_value = raw_value - 65536
                    value = raw_value
                elif field_type == 'uint32':
                    raw_value = (regs[0] << 16) | regs[1]
                    value = raw_value
                elif field_type == 'int32':
                    raw_value = (regs[0] << 16) | regs[1]
                    if raw_value > 0x7FFFFFFF:
                        raw_value = raw_value - 0x100000000
                    value = raw_value
                elif field_type == 'enum16':
                    # enum16 使用1个寄存器，按uint16解析
                    raw_value = regs[0]
                    value = raw_value
                elif field_type == 'bitfield32':
                    # bitfield32 使用2个寄存器，按uint32解析
                    raw_value = (regs[0] << 16) | regs[1]
                    value = raw_value
                elif field_type == 'string':
                    # 每个寄存器2字节，拼接为字符串
                    chars = []
                    for reg in regs:
                        chars.append(chr((reg >> 8) & 0xFF))
                        chars.append(chr(reg & 0xFF))
                    value = ''.join(chars).rstrip('\x00').strip()
                    raw_value = value
                elif field_type == "hex":
                    # hex类型：直接显示16进制数据
                    hex_values = []
                    for reg in regs:
                        hex_values.append(f"{reg:04X}")
                    value = ' '.join(hex_values)  # 用空格分隔多个寄存器
                    raw_value = value
                else:
                    # 其他类型直接显示原始
                    value = regs[0]
                    raw_value = regs[0]
            else:
                value = None
                raw_value = None

            # 移除缩放因子处理，统一显示原始值
            parsed_data[name] = {
                'value': value,
                'raw': raw_value,
                'unit': point.get('units', ''),
                'type': field_type,
                'label': point.get('label', name),
                'description': point.get('desc', ''),
                'access': 'rw' if 'access' in point and point['access'] == 'RW' else 'r'
            }
            
            current_offset = offset + size
# 解析子groups部分（动态重复）
        if groups:
            # 计算固定points部分的长度
            fixed_points_length = 0
            for point in points:
                if 'offset' in point:
                    fixed_points_length = max(fixed_points_length, point['offset'] + point.get('size', 1))
                else:
                    fixed_points_length += point.get('size', 1)
            
            # 计算剩余数据长度
            remaining_length = len(data) - fixed_points_length
            
            # 计算子groups的重复次数
            for group in groups:
                group_name = group['name']
                group_points = group['points']
                
                # 计算单个group的寄存器长度
                single_group_length = 0
                for gp in group_points:
                    single_group_length += gp.get('size', 1)
                
                if single_group_length > 0 and remaining_length > 0:
                    # 计算重复次数
                    repeat_count = remaining_length // single_group_length
                    
                    # 解析重复的groups
                    for i in range(repeat_count):
                        group_data = {}
                        group_offset = fixed_points_length + (i * single_group_length)
                        
                        # 解析group中的每个point
                        current_group_offset = 0
                        for gp in group_points:
                            gp_name = gp['name']
                            gp_type = gp['type'].lower()
                            gp_size = gp.get('size', 1)
                            
                            # 计算在data中的实际偏移
                            data_offset = group_offset + current_group_offset
                            
                            if data_offset + gp_size <= len(data):
                                regs = data[data_offset:data_offset + gp_size]
                                
                                # 解析类型（复用相同的解析逻辑）
                                if gp_type in ['uint16', 'sunssf']:
                                    raw_value = regs[0]
                                    if gp_type == 'sunssf':
                                        if raw_value > 32767:
                                            raw_value = raw_value - 65536
                                    value = raw_value
                                elif gp_type == 'int16':
                                    raw_value = regs[0]
                                    if raw_value > 32767:
                                        raw_value = raw_value - 65536
                                    value = raw_value
                                elif gp_type == 'uint32':
                                    raw_value = (regs[0] << 16) | regs[1]
                                    value = raw_value
                                elif gp_type == 'int32':
                                    raw_value = (regs[0] << 16) | regs[1]
                                    if raw_value > 0x7FFFFFFF:
                                        raw_value = raw_value - 0x100000000
                                    value = raw_value
                                elif gp_type == 'enum16':
                                    raw_value = regs[0]
                                    value = raw_value
                                elif gp_type == 'bitfield32':
                                    raw_value = (regs[0] << 16) | regs[1]
                                    value = raw_value
                                elif gp_type == 'string':
                                    chars = []
                                    for reg in regs:
                                        chars.append(chr((reg >> 8) & 0xFF))
                                        chars.append(chr(reg & 0xFF))
                                    value = ''.join(chars).rstrip('\x00').strip()
                                    raw_value = value
                                elif gp_type == "hex":
                                    hex_values = []
                                    for reg in regs:
                                        hex_values.append(f"{reg:04X}")
                                    value = ' '.join(hex_values)
                                    raw_value = value
                                else:
                                    value = regs[0]
                                    raw_value = regs[0]
                            else:
                                value = None
                                raw_value = None
                            
                            # 添加到group数据中，使用索引区分重复的groups
                            field_name = f"{group_name}_{i+1}_{gp_name}"
                            group_data[field_name] = {
                                'value': value,
                                'raw': raw_value,
                                'unit': gp.get('units', ''),
                                'type': gp_type,
                                'label': f"{gp.get('label', gp_name)} (Group {i+1})",
                                'description': gp.get('desc', ''),
                                'access': 'rw' if 'access' in gp and gp['access'] == 'RW' else 'r',
                                'group_index': i + 1,
                                'group_name': group_name
                            }
                            
                            current_group_offset += gp_size
                        
                        # 将group数据合并到主数据中
                        parsed_data.update(group_data)

        return parsed_data

    def parse_single_field(self, table_id, field_name, data):
        """解析单个字段，根据type和size解析"""
        if table_id not in self.models:
            return None
            
        model_data = self.models[table_id]
        points = model_data['group']['points']
        
        # 找到指定字段
        for point in points:
            if point['name'] == field_name:
                field_type = point['type'].lower()
                size = point.get('size', 1)
                
                # 检查数据长度是否足够
                if len(data) < size:
                    return None
                
                # 根据类型解析
                if field_type in ['uint16', 'sunssf']:
                    raw_value = data[0]
                    if field_type == 'sunssf':
                        # sunssf是有符号的
                        if raw_value > 32767:
                            raw_value = raw_value - 65536
                    value = raw_value
                    
                elif field_type == 'int16':
                    raw_value = data[0]
                    if raw_value > 32767:
                        raw_value = raw_value - 65536
                    value = raw_value
                    
                elif field_type == 'uint32':
                    if size >= 2:
                        raw_value = (data[0] << 16) | data[1]
                        value = raw_value
                    else:
                        return None
                        
                elif field_type == 'int32':
                    if size >= 2:
                        raw_value = (data[0] << 16) | data[1]
                        if raw_value > 0x7FFFFFFF:
                            raw_value = raw_value - 0x100000000
                        value = raw_value
                    else:
                        return None
                        
                elif field_type == 'enum16':
                    # enum16 使用1个寄存器，按uint16解析
                    raw_value = data[0]
                    value = raw_value
                    
                elif field_type == 'bitfield32':
                    # bitfield32 使用2个寄存器，按uint32解析
                    if size >= 2:
                        raw_value = (data[0] << 16) | data[1]
                        value = raw_value
                    else:
                        return None
                        
                elif field_type == 'string':
                    # 字符串解析：每个寄存器2字节
                    chars = []
                    for reg in data:                      
                        chars.append(chr((reg >> 8) & 0xFF))
                        chars.append(chr(reg & 0xFF))
                    value = ''.join(chars).rstrip('\x00').strip()
                    raw_value = value
                    
                elif field_type == "hex":
                    # hex类型：直接显示16进制数据
                    hex_values = []
                    for reg in data:
                        hex_values.append(f"{reg:04X}")
                    value = ' '.join(hex_values)  # 用空格分隔多个寄存器
                    raw_value = value
                    
                else:
                    # 其他类型直接显示原始
                    value = data[0]
                    raw_value = data[0]
                
                # 移除缩放因子处理，统一显示原始值
                return {
                    'value': value,
                    'raw': raw_value,
                    'unit': point.get('units', ''),
                    'type': field_type,
                    'label': point.get('label', field_name),
                    'description': point.get('desc', ''),
                    'access': 'rw' if 'access' in point and point['access'] == 'RW' else 'r'
                }
        
        return None

    def set_model_base_address(self, model_id, address):
        """设置特定模型的基地址"""
        self.model_base_addrs[model_id] = address

    def get_table_info(self, table_id):
        """获取表格信息，转换为兼容格式"""
        if table_id not in self.models:
            return None
            
        model_data = self.models[table_id]
        points = model_data['group']['points']
        groups = model_data['group'].get('groups', [])
        # 转换为兼容格式，计算正确的offset
        fields = {}
        current_offset = 0
        total_registers = 0  # 新增：计算总寄存器数
        # 计算固定points部分的寄存器数
        for point in points:
            # 如果没有显式定义offset，则按顺序计算
            if 'offset' in point:
                offset = point['offset']
            else:
                offset = current_offset
                current_offset += point.get('size', 1)  # 累加字段大小
            
            # 累加寄存器数量
            total_registers += point.get('size', 1)
            
            fields[point['name']] = {
                'offset': offset,
                'size': point.get('size', 1),
                'type': point['type'],
                'scale': point.get('sf', 1),
                'unit': point.get('units', ''),
                'access': 'rw' if 'access' in point and point['access'] == 'RW' else 'r',
                'label': point.get('label', point['name']),
                'description': point.get('desc', '')
            }
        # 计算子groups部分的寄存器数
        for group in groups:
            group_points = group['points']
            single_group_length = 0
            for gp in group_points:
                single_group_length += gp.get('size', 1)
            
            # 注意：这里不直接累加到total_registers，因为子groups是动态重复的
            # 实际长度需要在运行时根据扫描到的数据长度动态计算
        
        # 使用扫描到的模型地址，如果没有则使用默认基地址
        base_addr = self.model_base_addrs.get(table_id, self.base_address)
        
        return {
            'name': model_data['group'].get('label', f'Model {table_id}'),
            'description': model_data['group'].get('label', f'Model {table_id}'),
            'base_address': base_addr,
            'length': total_registers,  # 修改：使用总寄存器数
            'fields': fields,
            'has_groups': len(groups) > 0,  # 新增：标识是否有子groups
            'groups_info': groups  # 新增：子groups信息
        }

    def get_available_tables(self):
        """获取可用的表格列表"""
        return list(self.models.keys()) 