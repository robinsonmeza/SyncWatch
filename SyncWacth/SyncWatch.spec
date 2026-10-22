# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para generar SyncWatch.exe (un solo archivo, sin necesitar Python).
# Uso:  pyinstaller --noconfirm --clean SyncWatch.spec

import sys

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("static", "static")],          # interfaz web (HTML/CSS/JS + Chart.js)
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tests", "tkinter", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SyncWatch",
    icon="assets/syncwatch.ico" if sys.platform == "win32" else None,
    console=True,      # ventana de consola: muestra la URL y la carpeta de registros; cerrarla detiene el programa
    upx=False,         # sin compresión UPX: reduce falsos positivos de antivirus
    strip=False,
    debug=False,
    runtime_tmpdir=None,
)
