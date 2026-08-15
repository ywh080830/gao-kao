# -*- coding: utf-8 -*-
"""主窗口：左侧分组导航 + 顶栏（省份/年份/科类/批次/主题）+ 内容区 QStackedWidget。

关键修复（相对旧版）：
- 7 个面板在 __init__ 中一次性 addWidget 到 stack，首屏即绘制，杜绝「内容全白」。
- 不任何 opacity 动画；切换用 setCurrentWidget。
- 数据默认来自云端 GitHub（userdata/gk_local.db），启动自动同步；查询毫秒级。
"""
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox,
    QStackedWidget, QFrame, QStatusBar, QMessageBox,
)
from PySide6.QtCore import Qt, QSettings, QThread, Signal

from app.config import PROVINCES, YEARS, THEME_NAMES, get_province
from app.db import DataStore
from app.state import STATE
from app import cloud, user_config, log
from app.ui import theme
from app.ui.panels import (
    HomePanel, ScorePanel, RecommendPanel, VolunteerPanel, AnalysisPanel,
    SchoolPanel, DataPanel, HelpPanel, AboutPanel,
)


class CloudSyncThread(QThread):
    """后台线程：从云端 GitHub 下载最新高考数据（避免阻塞 UI）。

    先轻量检查版本（need_update），无需更新则直接结束；需要更新再下载。
    所有网络操作均在子线程，主线程不阻塞。
    """
    progress = Signal(int, int, str, str)
    finished = Signal(bool, str, dict)

    def run(self):
        # 版本检查放到子线程，避免离线时主线程被 urlopen 超时阻塞
        try:
            need, _rv, _lv = cloud.need_update()
        except Exception:
            need = False
        if not need:
            # 已是最新或离线无法判断：不发警告，静默结束
            self.finished.emit(False, "SKIP", {})
            return
        # 与手动下载互斥，避免并发写同一数据库导致损坏
        if cloud.is_downloading():
            self.finished.emit(False, "SKIP", {})
            return
        cloud.set_downloading(True)
        try:
            stats = cloud.download_all(progress=self._on_prog)
        finally:
            cloud.set_downloading(False)
        self.finished.emit(stats.get("ok", False), stats.get("error", ""), stats)

    def _on_prog(self, idx, total, name, status):
        self.progress.emit(idx, total, name, status)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("高考模拟填报系统")
        self.resize(1180, 760)
        self.setMinimumSize(960, 680)

        self.ds = DataStore()  # 本地 SQLite，启动即开，毫秒级

        # 恢复上次选择的主题（持久化到 QSettings / 注册表）
        _s = QSettings("GKSim", "prefs")
        _saved = _s.value("theme", "学术蓝")
        if _saved in THEME_NAMES:
            STATE.theme = _saved

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 左侧导航 ----
        self.left = QFrame()
        self.left.setFixedWidth(190)
        lv = QVBoxLayout(self.left)
        lv.setContentsMargins(10, 14, 10, 14)
        lv.setSpacing(6)
        brand = QLabel("高考志愿")
        brand.setStyleSheet("color:#fff;font-size:16px;font-weight:800;padding:6px 8px;")
        lv.addWidget(brand)
        self.nav_buttons = []
        self.panels = []
        self.stack = QStackedWidget()
        nav_defs = [
            ("概览", HomePanel),
            ("分数录入", ScorePanel),
            ("智能推荐", RecommendPanel),
            ("模拟志愿", VolunteerPanel),
            ("位次分析", AnalysisPanel),
            ("院校库", SchoolPanel),
            ("数据管理", DataPanel),
            ("帮助", HelpPanel),
            ("关于", AboutPanel),
        ]
        for idx, (label, cls) in enumerate(nav_defs):
            btn = QPushButton(label)
            btn.setObjectName("Nav")
            btn.clicked.connect(lambda _checked, i=idx: self._show(i))
            lv.addWidget(btn)
            self.nav_buttons.append(btn)
            panel = cls(self.ds, STATE)
            # 把面板内容（self.frame）挂到 panel 自身，否则 QStackedWidget 显示的是空 QWidget
            plo = QVBoxLayout(panel)
            plo.setContentsMargins(0, 0, 0, 0)
            plo.addWidget(panel.frame)
            self.stack.addWidget(panel)
            self.panels.append(panel)
        lv.addStretch(1)
        root.addWidget(self.left)

        # 数据管理面板下载完成后，热切换数据源并刷新
        self.panels[6].data_changed.connect(self._on_data_updated)
        self.panels[6].data_cleared.connect(self._on_data_cleared)

        # ---- 右侧 ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # 顶栏
        self.top = QFrame()
        self.top.setFrameShape(QFrame.NoFrame)
        th = QHBoxLayout(self.top)
        th.setContentsMargins(16, 10, 16, 10)
        th.setSpacing(10)
        th.addWidget(QLabel("省份"))
        self.province_cb = QComboBox()
        self.province_cb.addItems(self.ds.list_provinces())
        self.province_cb.setCurrentText(STATE.province)
        th.addWidget(self.province_cb)
        th.addWidget(QLabel("年份"))
        self.year_cb = QComboBox()
        self.year_cb.addItems([str(y) for y in YEARS])
        self.year_cb.setCurrentText(str(STATE.year))
        th.addWidget(self.year_cb)
        th.addWidget(QLabel("科类"))
        self.subject_cb = QComboBox()
        th.addWidget(self.subject_cb)
        th.addWidget(QLabel("批次"))
        self.batch_cb = QComboBox()
        th.addWidget(self.batch_cb)
        th.addStretch(1)
        th.addWidget(QLabel("主题"))
        self.theme_cb = QComboBox()
        self.theme_cb.addItems(THEME_NAMES)
        self.theme_cb.setCurrentText(STATE.theme)
        th.addWidget(self.theme_cb)
        rv.addWidget(self.top)

        rv.addWidget(self.stack, 1)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        root.addWidget(right)

        # ---- 信号 ----
        self.province_cb.currentTextChanged.connect(self._on_province)
        self.year_cb.currentTextChanged.connect(lambda v: setattr(STATE, "year", int(v)))
        self.subject_cb.currentTextChanged.connect(lambda v: setattr(STATE, "subject", v))
        self.batch_cb.currentTextChanged.connect(lambda v: setattr(STATE, "batch", v))
        self.theme_cb.currentTextChanged.connect(self._on_theme)
        STATE.changed.connect(self._on_state_changed)

        # 初始化科类/批次
        self._fill_subject_batch()
        # 侧栏/顶栏背景跟随初始主题（之前漏写导致首屏默认主题下 left/top 没设背景）
        self._apply_chrome(STATE.theme)
        # 应用初始主题样式（QSettings 已在 __init__ 开头恢复 STATE.theme）
        from PySide6.QtWidgets import QApplication
        theme.apply_theme(QApplication.instance(), STATE.theme)
        # 移除输入框标准右键菜单（高考志愿填报场景不需要 Undo/Cut/Paste/Delete/SelectAll 系统菜单）；
        # 键盘快捷键 Ctrl+C/V/X/A/Z/Y 由部件自身 keyPressEvent 处理，仍可使用。
        self._disable_std_context_menu(self)
        # 首屏仅刷新当前显示的面板（_show 内部会刷新 HomePanel），其余面板
        # 惰性刷新（切到时再 refresh）。避免启动期在主线程同步执行 9 个面板的
        # 全量查询 + recommend 计算 + 数万行位次表构造，导致窗口「未响应」。
        self._show(0)
        self._update_status()
        # 安装全局异常钩子：任何未捕获异常都记录到日志（便于排查，错误码 UN001）
        self._install_excepthook()
        # 若当前省份+年份无投档线数据，自动切换到最近有数据的年份
        self._ensure_data_available()
        # 启动自动同步云端数据（无本地云库或版本落后时后台下载；离线则跳过）
        self._maybe_auto_sync()

    # ---- 顶栏联动 ----
    def _fill_subject_batch(self):
        cfg = get_province(STATE.province) or {"subjects": ["物理类"], "batches": ["本科批"]}
        self.subject_cb.blockSignals(True)
        self.subject_cb.clear()
        self.subject_cb.addItems(cfg["subjects"])
        if STATE.subject in cfg["subjects"]:
            self.subject_cb.setCurrentText(STATE.subject)
        else:
            self.subject_cb.setCurrentIndex(0)
            STATE.subject = self.subject_cb.currentText()
        self.subject_cb.blockSignals(False)

        self.batch_cb.blockSignals(True)
        self.batch_cb.clear()
        self.batch_cb.addItems(cfg["batches"])
        if STATE.batch in cfg["batches"]:
            self.batch_cb.setCurrentText(STATE.batch)
        else:
            self.batch_cb.setCurrentIndex(0)
            STATE.batch = self.batch_cb.currentText()
        self.batch_cb.blockSignals(False)

    def _apply_chrome(self, name):
        """同步侧栏/顶栏背景色到当前主题（否则硬编码会盖住全局 QSS，主题切换不彻底）。"""
        pal = theme.THEMES.get(name, theme.THEMES["学术蓝"])
        self.left.setStyleSheet("background:%s;" % pal["header_bg"])
        self.top.setStyleSheet("background:%s;" % pal["panel"])

    def _disable_std_context_menu(self, root):
        """递归把 root 下所有 QLineEdit / QPlainTextEdit / QTextEdit 的右键菜单禁掉。
        键盘快捷键 Ctrl+C/V/X/A/Z/Y 由部件自身 keyPressEvent 处理，仍可使用。"""
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit
        for cls in (QLineEdit, QPlainTextEdit, QTextEdit):
            for w in root.findChildren(cls):
                w.setContextMenuPolicy(Qt.NoContextMenu)

    def _on_province(self, v):
        STATE.province = v
        self._fill_subject_batch()

    def _on_theme(self, v):
        STATE.theme = v
        from PySide6.QtWidgets import QApplication
        theme.apply_theme(QApplication.instance(), v)
        self._apply_chrome(v)
        # 持久化主题选择，重启后恢复
        QSettings("GKSim", "prefs").setValue("theme", v)
        # 重新刷新当前可见面板，使卡片等自定义配色同步到新主题（全局 QSS 不会重绘已绘制的像素色）
        idx = self.stack.currentIndex()
        if 0 <= idx < len(self.panels):
            try:
                self.panels[idx].refresh()
            except Exception:
                pass

    def _on_state_changed(self, field):
        self._update_status()

    def _on_data_updated(self, stats):
        """云端下载完成后：把 DataStore 热切换到本地下载库，并刷新全部面板。"""
        try:
            self.ds.reload()
        except Exception:
            pass
        # 省份下拉：保持当前选择（若新库仍含该省）
        self.province_cb.blockSignals(True)
        self.province_cb.clear()
        self.province_cb.addItems(self.ds.list_provinces())
        items = [self.province_cb.itemText(i) for i in range(self.province_cb.count())]
        if STATE.province in items:
            self.province_cb.setCurrentText(STATE.province)
        else:
            self.province_cb.setCurrentIndex(0)
            STATE.province = self.province_cb.currentText()
        self.province_cb.blockSignals(False)
        self._fill_subject_batch()
        # 仅刷新当前可见面板（其余面板惰性刷新，切到时再刷），避免下载完成后
        # 一次性同步刷新全部面板（含数万行位次表构造）造成主线程卡顿
        for p in self.panels:
            if p.isVisible():
                try:
                    p.refresh()
                except Exception:
                    pass
        self._update_status()
        # 同步后重新检查：若当前年份仍无数据则自动回退
        self._ensure_data_available()
        QMessageBox.information(
            self, "数据已更新",
            "已切换至本地数据库（离线可用）：\n投档线 %s 条\n位次表 %s 条\n院校 %s 所"
            % (f"{stats.get('admissions', 0):,}", f"{stats.get('rank_rows', 0):,}",
               f"{stats.get('schools', 0):,}"))

    def _maybe_auto_sync(self):
        """启动后自动同步云端数据：后台检查版本，需更新则下载。

        版本检查与下载均在子线程进行，主线程不阻塞；离线时静默跳过。
        若用户在「数据管理」关闭了自动同步，则跳过（可手动下载）。
        """
        if not user_config.get_auto_sync():
            self.status.showMessage("已关闭自动同步，可到「数据管理」手动下载")
            return
        if cloud.is_downloading():
            self.status.showMessage("正在下载数据，请稍候…")
            return
        self.status.showMessage("正在检查数据更新…")
        self._sync = CloudSyncThread()
        self._sync.progress.connect(
            lambda i, t, n, s: self.status.showMessage("数据下载 %d/%d：%s" % (i, t, n)))
        self._sync.finished.connect(self._on_auto_sync_done)
        self._sync.start()

    def _on_auto_sync_done(self, ok, error, stats):
        if error == "SKIP":
            # 已是最新或离线：若本地云库存在即用，否则提示需联网
            if not os.path.exists(cloud.local_db_path()):
                self.status.showMessage("未检测到本地数据，请联网后到「数据管理」下载")
            else:
                self._update_status()
            return
        if ok:
            try:
                self.ds.reload()
            except Exception:
                pass
            # 省份下拉：保持当前选择
            self.province_cb.blockSignals(True)
            self.province_cb.clear()
            self.province_cb.addItems(self.ds.list_provinces())
            items = [self.province_cb.itemText(i) for i in range(self.province_cb.count())]
            if STATE.province in items:
                self.province_cb.setCurrentText(STATE.province)
            else:
                self.province_cb.setCurrentIndex(0)
                STATE.province = self.province_cb.currentText()
            self.province_cb.blockSignals(False)
            self._fill_subject_batch()
            for p in self.panels:
                if p.isVisible():
                    try:
                        p.refresh()
                    except Exception:
                        pass
            self._update_status()
            # 下载完成后重新检查：若默认年份仍无数据则自动回退到有数据的年份，
            # 否则用户会看到「数据已下载」却仍是空白面板（与手动下载路径保持一致）。
            self._ensure_data_available()
            QMessageBox.information(
                self, "数据已更新",
                "已下载最新数据（离线可用）：\n投档线 %s 条\n位次表 %s 条\n院校 %s 所"
                % (f"{stats.get('admissions', 0):,}", f"{stats.get('rank_rows', 0):,}",
                   f"{stats.get('schools', 0):,}"))
        else:
            self.status.showMessage("数据下载失败：%s" % error)
            if not os.path.exists(cloud.local_db_path()):
                QMessageBox.warning(
                    self, "需要数据",
                    "无法下载数据：%s\n\n本系统数据需联网获取，请联网后到「数据管理」点击「下载全部到本地」。" % error)

    def _update_status(self):
        src = "已加载" if os.path.exists(cloud.local_db_path()) else "未加载"
        self.status.showMessage("%s · 省份 %s · 年份 %s · 科类 %s" %
                                (src, STATE.province, STATE.year, STATE.subject))

    def _on_data_cleared(self):
        """清除已下载数据后：把 DataStore 热切换回内存占位，并刷新省份下拉与可见面板。"""
        try:
            self.ds.reload()
        except Exception:
            pass
        self.province_cb.blockSignals(True)
        self.province_cb.clear()
        provs = self.ds.list_provinces() or [STATE.province]
        self.province_cb.addItems(provs)
        items = [self.province_cb.itemText(i) for i in range(self.province_cb.count())]
        if STATE.province in items:
            self.province_cb.setCurrentText(STATE.province)
        else:
            self.province_cb.setCurrentIndex(0)
            STATE.province = self.province_cb.currentText()
        self.province_cb.blockSignals(False)
        self._fill_subject_batch()
        for p in self.panels:
            if p.isVisible():
                try:
                    p.refresh()
                except Exception:
                    pass
        self._update_status()
        self.status.showMessage("已清除已下载数据，数据库为空，请重新下载")

    def _ensure_data_available(self):
        """若当前省份+年份无投档线数据，自动切换到最近有数据的年份并提示用户。

        解决「打开应用后所有数据面板空白」的核心体验问题：
        默认河南/2026 可能无投档线（数据源未覆盖），用户看到空白以为程序坏了。
        """
        try:
            count = len(self.ds.get_admissions(STATE.province, STATE.year, STATE.subject))
            if count > 0:
                return
            # 遍历可选年份，找最近有数据的
            for y in YEARS:
                if y == STATE.year:
                    continue
                try:
                    c = len(self.ds.get_admissions(STATE.province, y, STATE.subject))
                except Exception:
                    continue
                if c > 0:
                    STATE.year = y
                    self.year_cb.blockSignals(True)
                    self.year_cb.setCurrentText(str(y))
                    self.year_cb.blockSignals(False)
                    self.status.showMessage(
                        "已自动切换到 %d 年（%s 该年有 %d 条投档线数据）" % (y, STATE.province, c), 10000)
                    # 刷新当前可见面板
                    idx = self.stack.currentIndex()
                    if 0 <= idx < len(self.panels):
                        self.panels[idx].refresh()
                    return
            # 所有年份都无数据
            self.status.showMessage("当前省份暂无投档线数据，请通过「数据管理」下载", 10000)
        except Exception:
            pass

    def _install_excepthook(self):
        """捕获未处理异常并记录到日志（带错误码 UN001），避免在用户机器上无声崩溃。"""
        import sys

        def _hook(etype, exc, tb):
            try:
                log.error("UN001", "未捕获异常", exc)
            except Exception:
                pass
        sys.excepthook = _hook

    # ---- 导航 ----
    def _show(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.setObjectName("NavActive" if i == idx else "Nav")
            b.setStyleSheet("")
        try:
            self.panels[idx].refresh()
        except Exception:
            pass
