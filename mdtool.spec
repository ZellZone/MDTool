# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 採 onedir、停用 UPX，降低被防毒誤判機率。
注意：未簽章的 exe 仍可能被 SmartScreen 提示「未知發行者」，這與病毒無關。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
root = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = [
    "app",
    "app.main",
    "app.paths",
    "app.clipboard_util",
    "app.table_converter",
    "app.mermaid_converter",
    "app.reverse_table",
    "app.reverse_mermaid",
    "win32clipboard",
    "win32con",
    "pywintypes",
    "pythoncom",
]

for pkg in (
    "customtkinter",
    "docx",
    "rapidocr_onnxruntime",
    "onnxruntime",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

icon_path = root / "packaging" / "mdtool.ico"
version_path = root / "packaging" / "version_info.txt"

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "scipy",
        "pandas",
        "tkinter.test",
        "unittest",
        "test",
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
    name="MDTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 壓縮極易被誤判，務必關閉
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
    version=str(version_path) if version_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MDTool",
)
