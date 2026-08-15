# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for 高考模拟填报系统 (Python 干净重写版)
# 安全配置（已验证可正常启动）：
#   * upx=False            不用 UPX，避免原生扩展被压缩损坏
#   * excludes=['PIL','Pillow']  排除 Pillow 整链（应用未引用）
#   * runtime_tmpdir=D:\tmp_pyinst  运行期解压目录钉在 D 盘，彻底绕开 C 盘空间依赖
#   * datas 不内置 gk.db：运行期数据来自云端 GitHub（userdata/gk_local.db）
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # enc_stage/
ICON_PATH = Path(r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Lib\site-packages\PyInstaller\bootloader\images\icon-windowed.ico")
RUNTIME_TMP = r"D:\tmp_pyinst"
os.makedirs(RUNTIME_TMP, exist_ok=True)

# 云端数据运行时下载到 userdata/gk_local.db，EXE 不打包任何本地数据库
# 加密仓库：把全部 *.py.enc 作为 datas 随包分发，运行时由 loader 解密
datas = []
for _dp, _dirs, _files in os.walk(PROJECT_ROOT):
    for _fn in _files:
        if _fn.endswith(".py.enc"):
            _full = os.path.join(_dp, _fn)
            datas.append((_full, os.path.relpath(_dp, PROJECT_ROOT)))

hiddenimports = [
    "app", "app.config", "app.models", "app.state", "app.db", "app.rank_table",
    "app.recommender", "app.importer", "app.cloud",
    "app.ui", "app.ui.theme", "app.ui.main_window", "app.ui.panels",
    "loader",
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PIL", "Pillow", "tkinter", "test", "unittest", "setuptools",
        "pip", "_pytest", "pytest", "IPython", "matplotlib", "numpy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="高考模拟填报系统",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=RUNTIME_TMP,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
)
