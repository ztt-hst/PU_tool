# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['unified_tool_manager.py'],
    pathex=[],
    binaries=[
        ('can_tool/ControlCAN.dll', '.'),  # 改到根目录
    ],
    datas=[
        # 共用图标（根目录）
        ('mobus_tool/BQC.ico', '.'),

        # CAN 配置（根目录可省，但放着不影响）
        ('can_tool/can_protocol_config.py', '.'),
        ('can_tool/lang_config.py', '.'),

        # Modbus 模型（改到根目录，代码用 sys._MEIPASS 直接找文件名）
        ('mobus_tool/model_1.json', '.'),
        ('mobus_tool/model_802.json', '.'),
        ('mobus_tool/model_805.json', '.'),
        ('mobus_tool/model_64900.json', '.'),
        ('mobus_tool/model_64901.json', '.'),
        ('mobus_tool/model_899.json', '.'),

        # UART 资源（改到根目录，代码直接找 label.json / uart_command_set.json）
        ('uart_test/pu_app.bin', '.'),
        ('uart_test/uart_command_set.json', '.'),
        ('uart_test/label.json', '.'),
    ],
    hiddenimports=[
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.scrolledtext', 'tkinter.filedialog',
        'serial', 'serial.tools.list_ports',
        'threading', 'time', 'json', 'os', 'functools', 'traceback', 'subprocess', 'ctypes',
        'datetime', 'struct',
        'can_tool.can_protocol_config', 'can_tool.lang_config', 'can_tool.can_host_computer',
        'mobus_tool.main', 'mobus_tool.sunspec_protocol', 'mobus_tool.modbus_client',
        'mobus_tool.gui_components', 'mobus_tool.language_manager',
        'uart_test.uart_gui', 'uart_test.protocol', 'uart_test.uart_interface',
        'uart_test.log_manager', 'uart_test.label_manager', 'uart_test.item_manager',
        'uart_test.uart_service', 'uart_test.utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='PU_Integrated_Tools',
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=True, upx_exclude=[], runtime_tmpdir=None,
    console=False,  # 先保留，便于看日志；确认OK后可改回 False
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon='mobus_tool/BQC.ico',
)