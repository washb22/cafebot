# -*- mode: python ; coding: utf-8 -*-
"""CafeBot PyInstaller spec file.
PyArmor 난독화된 코드(dist_obf/)를 기반으로 빌드."""

import os
import sys
import glob

block_cipher = None
BASE = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
OBF = os.path.join(BASE, 'dist_obf')

# playwright driver (node.exe + package) 경로
import playwright
pw_dir = os.path.dirname(playwright.__file__)
pw_driver = os.path.join(pw_dir, 'driver')

# 난독화된 .py 파일들을 datas로 명시적 포함 (PyArmor 코드는 import 감지 불가)
obf_datas = [
    (os.path.join(OBF, 'templates'), 'templates'),
    (pw_driver, os.path.join('playwright', 'driver')),
]

# dist_obf/*.py → 루트에 포함
for py in glob.glob(os.path.join(OBF, '*.py')):
    name = os.path.basename(py)
    if name != 'main.py':  # main.py는 scripts로 이미 포함
        obf_datas.append((py, '.'))

# dist_obf/modules/*.py → modules/ 에 포함
for py in glob.glob(os.path.join(OBF, 'modules', '*.py')):
    obf_datas.append((py, 'modules'))

# pyarmor_runtime 폴더 통째로 포함
pyarmor_rt = os.path.join(OBF, 'pyarmor_runtime_000000')
if os.path.isdir(pyarmor_rt):
    obf_datas.append((pyarmor_rt, 'pyarmor_runtime_000000'))

a = Analysis(
    [os.path.join(OBF, 'main.py')],
    pathex=[OBF],
    binaries=[],
    datas=obf_datas,
    hiddenimports=[
        'engineio.async_drivers.threading',
        'playwright',
        'playwright.async_api',
        'pyperclip',
        'webview',
        'clr_loader',
        'pythonnet',
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'idna',
        'flask',
        'werkzeug',
        'jinja2',
        'markupsafe',
        'click',
        'itsdangerous',
        'blinker',
        'greenlet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CafeBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(BASE, 'build', 'icon.ico') if os.path.exists(os.path.join(BASE, 'build', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='CafeBot',
)
