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
            # 如果是开发环境：使用模块目录
            module_dir = os.path.dirname(__file__)
            return os.path.join(module_dir, filename)

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
                # 调试输出
                # if field_type == 'string' and size <= 8:
                #     print(f"DEBUG {name}: offset={offset}, size={size}, data_len={len(data)}")
                #     print(f"DEBUG {name}: regs={[hex(r) for r in regs]}")
                
                # 使用统一的数据类型解析器
                value, raw_value = self._parse_data_by_type(regs, field_type, size)
            else:
                # print(f"DEBUG {name}: 数据长度不足 - offset={offset}, size={size}, data_len={len(data)}")
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
                                
                                # 使用统一的数据类型解析器
                                value, raw_value = self._parse_data_by_type(regs, gp_type, gp_size)
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
        #print(f"DEBUG: parse_single_field called with table_id={table_id}, field_name={field_name}, data={data}")
        
        if table_id not in self.models:
            #print(f"DEBUG: table_id {table_id} not found in models")
            return None
            
        model_data = self.models[table_id]
        points = model_data['group']['points']
        
        # 首先检查是否是动态group字段
        if '_' in field_name and field_name.count('_') >= 2:
            #print(f"DEBUG: Checking dynamic group field: {field_name}")
            # 动态group字段格式：GroupName_index_fieldName
            parts = field_name.split('_')
            if len(parts) >= 3:
                group_name = parts[0]
                try:
                    group_index = int(parts[1])
                    original_field_name = '_'.join(parts[2:])  # 处理field_name中包含下划线的情况
                    #print(f"DEBUG: Parsed group: {group_name}, index: {group_index}, field: {original_field_name}")
                    
                    # 在groups中查找对应的group定义
                    groups = model_data['group'].get('groups', [])
                    #print(f"DEBUG: Available groups: {[g.get('name', 'unnamed') for g in groups]}")
                    
                    for group in groups:
                        if group['name'] == group_name:
                            #print(f"DEBUG: Found matching group: {group_name}")
                            group_points = group['points']
                            for gp in group_points:
                                if gp['name'] == original_field_name:
                                    #print(f"DEBUG: Found matching field: {original_field_name}")
                                    field_type = gp['type'].lower()
                                    size = gp.get('size', 1)
                                    
                                    # 检查数据长度是否足够
                                    if len(data) < size:
                                        #print(f"DEBUG: Data length {len(data)} insufficient for size {size}")
                                        return None
                                    
                                    # 解析数据（复用下面的解析逻辑）
                                    result = self._parse_field_data(data, field_type, size, gp, original_field_name)
                                    #print(f"DEBUG: Parse result: {result}")
                                    return result
                            #print(f"DEBUG: Field {original_field_name} not found in group {group_name}")
                    #print(f"DEBUG: Group {group_name} not found")
                except ValueError:
                    #print(f"DEBUG: ValueError parsing group index from {parts[1]}")
                    pass  # 如果无法解析索引，继续尝试普通字段解析
        
        # 普通字段解析
        #print(f"DEBUG: Trying normal field parsing for {field_name}")
        for point in points:
            if point['name'] == field_name:
                #print(f"DEBUG: Found normal field: {field_name}")
                field_type = point['type'].lower()
                size = point.get('size', 1)
                
                # 检查数据长度是否足够
                if len(data) < size:
                    ##print(f"DEBUG: Data length {len(data)} insufficient for size {size}")
                    return None
                
                # 解析数据
                result = self._parse_field_data(data, field_type, size, point, field_name)
                ##print(f"DEBUG: Parse result: {result}")
                return result
        
        ##print(f"DEBUG: Field {field_name} not found anywhere")
        return None

    def _parse_field_data(self, data, field_type, size, point, field_name):
        """解析字段数据的通用方法"""
        # 使用统一的数据类型解析器
        value, raw_value = self._parse_data_by_type(data, field_type, size)
        
        if value is None:
            return None
        
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

    def _parse_data_by_type(self, data, field_type, size):
        """
        统一的数据类型解析方法
        返回 (value, raw_value) 元组，解析失败时返回 (None, None)
        """
        if not data or len(data) == 0:
            return None, None
            
        field_type = field_type.lower()
        
        if field_type in ['uint16', 'sunssf']:
            raw_value = data[0]
            if field_type == 'sunssf':
                # sunssf是有符号的
                if raw_value > 32767:
                    raw_value = raw_value - 65536
            return raw_value, raw_value
            
        elif field_type == 'int16':
            raw_value = data[0]
            if raw_value > 32767:
                raw_value = raw_value - 65536
            return raw_value, raw_value
            
        elif field_type == 'uint32':
            if size >= 2 and len(data) >= 2:
                raw_value = (data[0] << 16) | data[1]
                return raw_value, raw_value
            else:
                return None, None
                
        elif field_type == 'int32':
            if size >= 2 and len(data) >= 2:
                raw_value = (data[0] << 16) | data[1]
                if raw_value > 0x7FFFFFFF:
                    raw_value = raw_value - 0x100000000
                return raw_value, raw_value
            else:
                return None, None
                
        elif field_type == 'enum16':
            # enum16 使用1个寄存器，按uint16解析
            raw_value = data[0]
            return raw_value, raw_value
            
        elif field_type == 'bitfield32':
            # bitfield32 使用2个寄存器，按uint32解析，显示为十六进制
            if size >= 2 and len(data) >= 2:
                raw_value = (data[0] << 16) | data[1]
                value = f"{raw_value:08X}"  # 32位十六进制格式
                return value, raw_value
            else:
                return None, None
                
        elif field_type == 'string':
            # 字符串解析：每个寄存器2字节
            chars = []
            for reg in data:
                high_byte = (reg >> 8) & 0xFF
                low_byte = reg & 0xFF
                chars.append(chr(high_byte))  # 高字节在前
                chars.append(chr(low_byte))   # 低字节在后
            value = ''.join(chars).rstrip('\x00').strip()
            return value, value
            
        elif field_type == "hex":
            # hex类型：直接显示16进制数据
            hex_values = []
            for reg in data:
                hex_values.append(f"{reg:04X}")
            
            if size == 16 and len(hex_values) == 16:
                # size为16时，分两行显示
                line1 = ' '.join(hex_values[:8])
                line2 = ' '.join(hex_values[8:])
                value = f"{line1}\n{line2}"
            else:
                value = ' '.join(hex_values)  # 用空格分隔多个寄存器
            return value, value
            
        else:
            # 其他类型直接显示原始
            raw_value = data[0]
            return raw_value, raw_value
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