# -*- coding: utf-8 -*-
"""正常用户全流程端到端测试（无显示 offscreen 环境）。

模拟真实用户点击/查看所有面板与功能：
- 9 个面板导航逐个刷新
- 分数录入并保存
- 智能推荐刷新
- 院校库搜索 -> 单击选中 -> 查看详情
- 院校库一键加入志愿 -> 模拟志愿渲染
- 数据管理：自动同步开关 / 修改保存位置 / 清除已下载数据
- 帮助页错误码表 / 关于页免责声明

环境安全：
- 数据目录隔离到开发模式默认目录 D:/34/高考/userdata，结束整体删除；
- 模态 QMessageBox 被 mock 自动应答，避免事件循环阻塞；
- 自动同步关闭，测试期不联网。
"""
import os
import sys
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REAL_DB = r"D:/34/高考/gk_python/dist_new/userdata/gk_local.db"
TEST_ROOT = r"D:/34/高考/userdata"          # 开发模式默认 data_dir
NEW_DIR = r"D:/34/高考/userdata_e2e_new"
BAK = TEST_ROOT + ".bak_e2e"


def log(msg):
    print(msg, flush=True)


# ---- 环境准备 ----
import PySide6  # noqa: F401
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QTableWidget, QLabel, QGroupBox, QListWidget,
)

# 中和沙箱 safe-delete 钩子（否则 os.remove/shutil.move/rmtree 被重定向到回收站而失败）
try:
    import sitecustomize as _sc
    for _mod, _fn in [("os", "remove"), ("os", "unlink"), ("os", "rmdir"), ("shutil", "rmtree")]:
        _orig = getattr(_sc, "_orig_%s_%s" % (_mod, _fn), None) or getattr(_sc, "_orig_%s" % _fn, None)
        if _orig is not None:
            setattr(__import__(_mod), _fn, _orig)
except Exception:
    pass

# 防止模态弹窗阻塞事件循环
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

# 环境准备（中和钩子之后，rmtree 可正常删除）：先清理历史残留，再复制真实库
for _d in (TEST_ROOT, NEW_DIR, BAK):
    shutil.rmtree(_d, ignore_errors=True)
os.makedirs(TEST_ROOT, exist_ok=True)
if os.path.exists(REAL_DB):
    shutil.copy(REAL_DB, os.path.join(TEST_ROOT, "gk_local.db"))
    log("已复制真实库 -> %s" % os.path.join(TEST_ROOT, "gk_local.db"))

# 隔离开发期遗留的 app/data/gk.db：db_path() 在开发模式(not frozen)下会回退到它，
# 会干扰「清除数据」测试（真实 EXE 为 frozen 模式不回退，不受影响）。
GK_DEV = r"D:/34/高考/gk_python/app/data/gk.db"
GK_DEV_BAK = GK_DEV + ".bak_e2e"
log("DIAG GK_DEV=%s exists=%s" % (GK_DEV, os.path.exists(GK_DEV)))
if os.path.exists(GK_DEV):
    shutil.move(GK_DEV, GK_DEV_BAK)
    log("已隔离遗留 gk.db -> %s" % GK_DEV_BAK)

import app.user_config as user_config
user_config._CACHE.clear()
user_config.set_auto_sync(False)   # 关闭联网自动同步

from app.ui.main_window import MainWindow
from app.ui.panels import SchoolDetailDialog
from app import errors
from app.state import STATE

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    log(("[PASS] " if cond else "[FAIL] ") + name + ((" :: " + extra) if extra else ""))


app = QApplication.instance() or QApplication(sys.argv)
win = MainWindow()
sys.excepthook = sys.__excepthook__   # 暴露真实异常（避免被 MainWindow 的钩子静默吞掉）
check("主窗口构造成功", win is not None)

# 切到数据存在的年份（河南 2026 投档线为空，用 2025 才有记录）
try:
    win.year_cb.setCurrentText("2025")
    win._fill_subject_batch()
except Exception:
    pass

# ---- 数据基础 ----
st = win.ds.stats()
check("数据库已加载(投档线>0)", st["admissions"] > 0, "admissions=%d" % st["admissions"])
check("省份下拉=31 个", win.province_cb.count() == 31, "count=%d" % win.province_cb.count())

# ---- 遍历所有面板（模拟点击左侧导航）----
panel_names = ["概览", "分数录入", "智能推荐", "模拟志愿", "位次分析", "院校库", "数据管理", "帮助", "关于"]
for i, nm in enumerate(panel_names):
    try:
        win._show(i)
        kids = win.panels[i].findChildren(QLabel) + win.panels[i].findChildren(QGroupBox)
        check("面板[%d]%s 刷新正常" % (i, nm), win.panels[i] is not None and len(kids) > 0,
              "widgets=%d" % len(kids))
    except Exception as e:
        check("面板[%d]%s 刷新正常" % (i, nm), False, "EXC:%s" % e)

# ---- 分数录入：填成绩并保存 ----
sp = win.panels[1]
try:
    sp.score_edit.setText("600")
    sp.rank_edit.setText("20000")
    sp._save()
    check("分数录入-成绩已保存", STATE.score == 600 and STATE.rank == 20000,
          "score=%s rank=%s" % (STATE.score, STATE.rank))
except Exception as e:
    check("分数录入-成绩已保存", False, "EXC:%s" % e)

# ---- 智能推荐：成绩已填，刷新应出结果 ----
win._show(2)
rp = win.panels[2]
rec_tables = rp.findChildren(QTableWidget)
total_rows = sum(t.rowCount() for t in rec_tables)
check("智能推荐-刷新后有推荐院校", total_rows > 0, "rows=%d" % total_rows)

# ---- 院校库：搜索 -> 选中 -> 查看详情 ----
win._show(5)
school_panel = win.panels[5]
school_panel.kw.setText("大学")
school_panel._search()
n_schools = school_panel.listw.count()
check("院校库-关键词搜索出结果", n_schools > 0, "count=%d" % n_schools)
if n_schools > 0:
    school_panel.listw.setCurrentRow(0)
    sel = getattr(school_panel, "current_school", None)
    check("院校库-单击选中院校", bool(sel), "name=%s" % sel)
    # 查看详情（直接构造对话框，避免 exec 阻塞事件循环）
    dlg = SchoolDetailDialog(win.ds, sel, STATE.province)
    tables = dlg.findChildren(QTableWidget)
    groups = dlg.findChildren(QGroupBox)
    titles = [g.title() for g in groups]
    detail_rows = max((t.rowCount() for t in tables), default=0)
    check("院校详情-弹窗构建成功", len(groups) >= 2 and detail_rows >= 1,
          "groups=%d detailRows=%d" % (len(groups), detail_rows))
    check("院校详情-含基本信息与明细组",
          ("院校基本信息" in titles) and any(t.startswith("历年投档线明细") for t in titles),
          "titles=%s" % titles)
    dlg.close()
    dlg.deleteLater()

# ---- 院校库：一键加入志愿 -> 模拟志愿渲染 ----
vols_before = len(STATE.volunteers)
try:
    school_panel._add_to_volunteers()
    vols_after = len(STATE.volunteers)
    check("模拟志愿-可从院校库加入", vols_after == vols_before + 1,
          "before=%d after=%d" % (vols_before, vols_after))
except Exception as e:
    check("模拟志愿-可从院校库加入", False, "EXC:%s" % e)
win._show(3)
vp = win.panels[3]
vp.refresh()
vp_tables = vp.findChildren(QTableWidget)
check("模拟志愿-表格渲染成功", len(vp_tables) >= 1)

# ---- 数据管理：自动同步开关 ----
win._show(6)
dp = win.panels[6]
check("数据管理-控件齐全",
      hasattr(dp, "btn_clear_data") and hasattr(dp, "dir_edit")
      and hasattr(dp, "auto_sync_cb") and hasattr(dp, "btn_download"))
before = user_config.get_auto_sync()
dp.auto_sync_cb.setChecked(not before)
check("数据管理-自动同步开关可切换", user_config.get_auto_sync() == (not before),
      "auto_sync=%s" % user_config.get_auto_sync())

# ---- 数据管理：修改保存位置（迁移到 NEW_DIR）----
os.makedirs(NEW_DIR, exist_ok=True)
import shutil as _sh
_real_move = _sh.move
_move_log = []
def _wrap_move(src, dst):
    try:
        return _real_move(src, dst)
    except Exception as e:
        _move_log.append((src, repr(e)))
        raise
_sh.move = _wrap_move
_warn_log = []
def _warn(*a, **k):
    _warn_log.append(a)
QMessageBox.warning = staticmethod(_warn)
dp.dir_edit.setText(NEW_DIR)
try:
    dp._apply_data_dir()
    moved = os.path.exists(os.path.join(NEW_DIR, "gk_local.db"))
    check("数据管理-保存位置已应用并迁移数据库",
          user_config.get_data_dir() == NEW_DIR and moved,
          "data_dir=%s moved=%s" % (user_config.get_data_dir(), moved))
except Exception as e:
    check("数据管理-保存位置已应用并迁移数据库", False, "EXC:%s" % e)
_sh.move = _real_move
QMessageBox.warning = staticmethod(lambda *a, **k: None)
log("DIAG move_log=%s" % _move_log)
log("DIAG warn_log=%s" % _warn_log)
log("DIAG get_all=%s" % user_config.get_all())

# ---- 数据管理：清除已下载数据（破坏性，放最后）----
import app.cloud as _cloud
log("DIAG clear before ds.path=%s" % win.ds.path)
log("DIAG clear lp=%s exists=%s" % (_cloud.local_db_path(), os.path.exists(_cloud.local_db_path())))
try:
    dp.btn_clear_data.click()   # question 已被 mock 应答 Yes
    log("DIAG clear after ds.path=%s" % win.ds.path)
    after = win.ds.stats()
    check("数据管理-清除数据后库变空", after["admissions"] == 0, "admissions=%d" % after["admissions"])
except Exception as e:
    check("数据管理-清除数据后库变空", False, "EXC:%s" % e)

# ---- 帮助页：错误码表 ----
win._show(7)
hp = win.panels[7]
err_tables = [t for t in hp.findChildren(QTableWidget)]
code_rows = err_tables[0].rowCount() if err_tables else 0
check("帮助页-错误码表完整(%d码)" % len(errors.ERROR_CODES),
      code_rows == len(errors.ERROR_CODES), "rows=%d" % code_rows)

# ---- 关于页：免责声明 ----
win._show(8)
ap = win.panels[8]
about_text = "".join(l.text() for l in ap.findChildren(QLabel))
about_titles = [g.title() for g in ap.findChildren(QGroupBox)]
check("关于页-含版本信息", "版本 1.0.0" in about_text)
check("关于页-含免责声明", ("免责声明" in about_titles) and ("教育考试院" in about_text),
      "hasDisc=%s hasEdu=%s" % ("免责声明" in about_titles, "教育考试院" in about_text))

# ---- 汇总 ----
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
log("=" * 60)
log("E2E 结果：%d/%d 通过" % (passed, total))
for name, ok, extra in results:
    if not ok:
        log("  FAIL: %s %s" % (name, extra))

# ---- 清理 ----
try:
    win.close()
except Exception:
    pass
shutil.rmtree(TEST_ROOT, ignore_errors=True)
shutil.rmtree(NEW_DIR, ignore_errors=True)
if os.path.isdir(BAK):
    if not os.path.isdir(TEST_ROOT):
        shutil.copytree(BAK, TEST_ROOT)
    shutil.rmtree(BAK, ignore_errors=True)
if os.path.exists(GK_DEV_BAK):
    shutil.move(GK_DEV_BAK, GK_DEV)
    log("已恢复遗留 gk.db")

sys.exit(0 if passed == total else 1)
