# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec dosyası – PRGTOK Arşiv Sistemi
# Kullanım: pyinstaller build\PRGTOK.spec --distpath dist --workpath build\work

block_cipher = None

import os
from pathlib import Path

# Ana klasör: spec dosyasının üstü
BASE = Path(SPECPATH).parent

a = Analysis(
    [str(BASE / 'main.py')],
    pathex=[str(BASE)],
    binaries=[],
    datas=[
        # assets klasörü (logo, görseller)
        (str(BASE / 'assets'), 'assets'),
        # motor.py aynı dizinde olacak
        (str(BASE / 'motor.py'), '.'),
    ],
    hiddenimports=[
        # PDF okuma
        'pdfplumber',
        'pdfminer', 'pdfminer.high_level', 'pdfminer.layout',
        'pdfminer.utils', 'pdfminer.pdfpage', 'pdfminer.pdfinterp',
        'pdfminer.converter', 'pdfminer.image',
        # OCR
        'pytesseract',
        # Görsel
        'PIL', 'PIL.Image', 'PIL.ImageOps', 'PIL.ImageFilter',
        # Veri
        'pandas', 'pandas._libs', 'pandas._libs.tslibs',
        'openpyxl', 'openpyxl.styles', 'openpyxl.utils',
        # GUI
        'customtkinter',
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
        'tkinter.messagebox', 'tkinter.font',
        # Standart
        'shutil', 're', 'os', 'pathlib', 'datetime',
        # Cryptography (pdfplumber bağımlılığı)
        'cryptography',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'numpy.testing', 'IPython',
        'jupyter', 'notebook', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PRGTOK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI modu – siyah konsol penceresi açılmaz
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # assets klasöründe icon.ico varsa kullan, yoksa yorum satırı yap
    icon=str(BASE / 'assets' / 'icon.ico') if (BASE / 'assets' / 'icon.ico').exists() else None,
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PRGTOK',
)
