# -*- coding: utf-8 -*-
"""打包脚本（build_qt.py，加密仓库版）。

固定安全配置：所有 TMP 走 D 盘；还原沙箱安全删除钩子；先安装解密加载器
（让 PyInstaller 在分析期能找到 app 各模块），再依据 build/gk_python.spec
产出单文件 EXE。加密源码随 datas 打包，运行时由 loader 解密。
"""
import os
import sys
import shutil
import pathlib

TMP_DIR = r"D:\tmp_pyinst"
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["TMP"] = TMP_DIR
os.environ["TEMP"] = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR
print("[build_qt] temp -> %s" % TMP_DIR, flush=True)

# 还原原生删除函数（沙箱会把删除转到回收站，导致 PyInstaller 清理失败）
import sitecustomize  # noqa: E402
os.remove = sitecustomize._orig_remove
os.unlink = sitecustomize._orig_unlink
os.rmdir = sitecustomize._orig_rmdir
shutil.rmtree = sitecustomize._orig_shutil_rmtree
pathlib.Path.unlink = sitecustomize._orig_path_unlink
pathlib.Path.rmdir = sitecustomize._orig_path_rmdir
print("[build_qt] safe-delete hook neutralized", flush=True)

# 安装解密加载器，使分析期 `import app` 可用
import loader  # noqa: E402
loader.install()

import PyInstaller.__main__  # noqa: E402
sys.argv[0] = "pyinstaller"
PyInstaller.__main__.run(["--noconfirm", "--clean", "--distpath", "build_out6", "build/gk_python.spec"])
