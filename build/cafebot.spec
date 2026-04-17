# -*- mode: python ; coding: utf-8 -*-
"""CafeBot PyInstaller spec file.
PyArmor 난독화된 코드(dist_obf/)를 기반으로 빌드."""

import os
import sys

block_cipher = None
BASE = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
OBF = os.path.join(BASE, 'dist_obf')

# playwright driver (node.exe + package) 경로
import playwright
pw_dir = os.path.dirname(playwright.__file__)
pw_driver = os.path.join(pw_dir, 'driver')

a = Analysis(
    [os.path.join(OBF, 'main.py')],
    pathex=[OBF],
    binaries=[],
    datas=[
        (os.path.join(OBF, 'templates'), 'templates'),
        (pw_driver, os.path.join('playwright', 'driver')),
    ],
    hiddenimports=[
        'engineio.async_drivers.threading',
        'playwright',
        'playwright.async_api',
        'pyperclip',
        'webview',
        'clr_loader',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest', 'email', 'xml', 'xmlrpc'],
    cipher=block_cipher,
    noarchive=False,
)

# PyArmor runtime 포함
pyarmor_runtime = os.path.join(OBF, 'pyarmor_runtime_000000')
if os.path.isdir(pyarmor_runtime):
    for dirpath, dirnames, filenames in os.walk(pyarmor_runtime):
        for f in filenames:
            src = os.path.join(dirpath, f)
            rel = os.path.relpath(dirpath, OBF)
            a.datas.append((os.path.join(rel, f), src, 'DATA'))

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
    console=False,  # GUI 모드 (터미널 창 없음)
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
