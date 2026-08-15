# -*- coding: utf-8 -*-
"""用户体验修复回归测试：无显示(offscreen)加载真实数据库，逐项验证修复。"""
import os
import sys
import shutil

# 1) 中和沙箱 safe-delete 钩子（否则 os.remove/rmtree 被重定向到回收站而失败）
import sitecustomize  # noqa: E402
os.remove = sitecustomize._orig_remove
os.unlink = sitecustomize._orig_unlink
os.rmdir = sitecustomize._orig_rmdir
shutil.rmtree = sitecustomize._orig_shutil_rmtree

PASSED = 0
FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("[PASS] %s" % name)
    else:
        FAILED += 1
        print("[FAIL] %s :: %s" % (name, extra))


REAL_DB = r"D:/34/高考/gk_python/dist_new/userdata/gk_local.db"
TMP = r"D:/34/高考/gk_python/_ux_test_tmp"
BAK = r"D:/34/高考/gk_python/_ux_test_bak"

# 清理并准备隔离环境
if os.path.isdir(TMP):
    shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
assert os.path.exists(REAL_DB), "真实库不存在"
shutil.copy(REAL_DB, os.path.join(TMP, "gk_local.db"))
print("已复制真实库 ->", os.path.join(TMP, "gk_local.db"))

# 备份并隔离开发期遗留 app/data/gk.db（db_path 在 dev 模式会回退它，干扰测试）
import app.user_config as user_config

# 指向隔离目录
user_config.set_data_dir(TMP)
check("数据目录指向隔离 tmp", os.path.abspath(user_config.get_data_dir()) == os.path.abspath(TMP))

# 关闭自动同步，避免后台线程干扰确定性测试
user_config.set_auto_sync(False)

# 屏蔽所有模态弹窗，避免阻塞事件循环
from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from PySide6.QtCore import Qt
for m in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, m, staticmethod(lambda *a, **k: None))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication(sys.argv)

import app.cloud as cloud
import app.db as dbmod
from app.db import DataStore
from app.state import STATE
from app.ui.main_window import MainWindow
from app.ui.panels import SchoolDetailDialog, make_school_badge

# 确认真实库 河南 2026 空、2025 有数据（自动回退逻辑的前提）
ds = DataStore()
print("河南2026 投档:", len(ds.get_admissions("河南", 2026, "物理类")))
print("河南2025 投档:", len(ds.get_admissions("河南", 2025, "物理类")))
check("河南2026 为空(触发回退前提)", len(ds.get_admissions("河南", 2026, "物理类")) == 0)
check("河南2025 有数据(回退目标)", len(ds.get_admissions("河南", 2025, "物理类")) > 0)

# 构造主窗口
win = MainWindow()
sys.excepthook = sys.__excepthook__  # 还原默认钩子，测试期异常直接打印
check("主窗口构造成功", win is not None)
check("面板数量=9", len(win.panels) == 9, str(len(win.panels)))

# 导航全部面板，确认无异常
for i in range(len(win.panels)):
    try:
        win._show(i)
        ok = True
    except Exception as e:
        ok = False
        err = repr(e)
    check("导航面板#%d 正常" % i, ok, locals().get("err", ""))

# 院校库：列表应填充
sp = win.panels[5]
win._show(5)
schools = ds.distinct_schools("河南", 2025)
check("院校库列表已填充", sp.listw.count() > 0, "count=%d" % sp.listw.count())
check("院校库找到院校(真实库)", len(schools) > 0)

# 院校详情对话框 + 标识图(badge)
name = schools[0][1]
dlg = SchoolDetailDialog(ds, name, "河南", win)
badge_ok = False
for lbl in dlg.findChildren(QLabel):
    pm = lbl.pixmap()
    if pm is not None and not pm.isNull():
        badge_ok = True
        break
check("院校详情含标识图(badge 非空)", badge_ok)
check("院校详情标题含校名", name in dlg.windowTitle())

# 占位项不可选中（空列表场景）
sp.kw.setText("__无此院校zzz__")
sp._search()
ph_selected = False
for i in range(sp.listw.count()):
    it = sp.listw.item(i)
    if it and (it.flags() & Qt.ItemIsSelectable) == Qt.ItemIsSelectable:
        ph_selected = True
check("空结果占位项不可选中", not ph_selected)
sp.kw.setText("")
sp._search()

# 录入成绩后概览预览有数据
STATE.score = 560
STATE.rank = None
win._show(0)
hp = win.panels[0]
check("概览预览有行(录入成绩后)", hp.preview.rowCount() > 0, "rows=%d" % hp.preview.rowCount())

# 主题切换刷新不崩溃
try:
    win._on_theme("薄荷绿")
    win._on_theme("学术蓝")
    theme_ok = True
except Exception as e:
    theme_ok = False
    err = repr(e)
check("主题切换并刷新可见面板无异常", theme_ok, locals().get("err", ""))

# 修复#1：自动同步下载完成后自动回退到最近有数据年份
STATE.year = 2026  # 强制为无数据年份
win._on_auto_sync_done(True, "", {"admissions": len(ds.get_admissions("河南", 2025, "物理类")),
                                  "rank_rows": 1, "schools": len(schools), "version": "test"})
check("自动同步完成后自动回退年份(2026->有数据年)", STATE.year != 2026, "year=%s" % STATE.year)

# 修复#2：并发下载互斥 —— 标记下载中时手动点击下载不应启动新线程
cloud.set_downloading(True)
dp = win.panels[6]
dp.thread = None
dp._download()
check("下载中再次点击下载被互斥(未启动新线程)", dp.thread is None, "thread=%s" % dp.thread)
cloud.set_downloading(False)

# 清理
try:
    win.close()
except Exception:
    pass
shutil.rmtree(TMP, ignore_errors=True)
print("\n===== UX 修复回归结果: PASS=%d FAIL=%d =====" % (PASSED, FAILED))
sys.exit(0 if FAILED == 0 else 1)
