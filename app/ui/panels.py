# -*- coding: utf-8 -*-
"""7 大功能面板 + 位次曲线 Canvas。

设计要点（根治旧版崩溃）：
- 所有面板在 MainWindow.__init__ 中一次性 addWidget 到 QStackedWidget，首屏即绘制，无白屏。
- 不依赖任何 opacity 动画；切换面板用 setCurrentWidget。
- 数据来自本地 SQLite（DataStore），同步查询毫秒级，不阻塞、不卡死。
"""
import os
import sys
import csv
import json
import time
import shutil

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QFormLayout, QGroupBox, QFrame, QMessageBox, QFileDialog, QAbstractItemView,
    QScrollArea, QSizePolicy, QProgressBar, QCheckBox, QDialog, QGridLayout,
    QTextBrowser,
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QDesktopServices, QPixmap, QBrush

from app.config import YEARS, THEME_NAMES
from app.models import Volunteer
from app.recommender import recommend, categorize
from app.rank_table import RankTable
from app.state import STATE
from app.ui import theme
from app import cloud, user_config, log, errors


# --------------------------------------------------------------------------- #
# 用户数据目录（志愿表持久化，写在 exe 同级 userdata，避免占用 C 盘）
# --------------------------------------------------------------------------- #
def userdata_dir():
    # 跟随用户配置的保存位置（可在「数据管理」修改）
    d = user_config.get_data_dir()
    os.makedirs(d, exist_ok=True)
    return d


def volunteers_path():
    return os.path.join(userdata_dir(), "volunteers.json")


def load_volunteers():
    p = volunteers_path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            return [Volunteer.from_dict(d) for d in json.load(fh)]
    except Exception:
        return []


def save_volunteers(vols):
    with open(volunteers_path(), "w", encoding="utf-8") as fh:
        json.dump([v.to_dict() for v in vols], fh, ensure_ascii=False, indent=2)


def _to_float(s):
    """安全浮点解析：空/非法返回 None，避免 float() 抛 ValueError 导致崩溃。"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _to_int(s):
    """安全整数解析：空/非法返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        try:
            return int(float(s))
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# 公共工具
# --------------------------------------------------------------------------- #
def fill_table(table, headers, rows):
    # 关闭更新避免逐行绘制带来的闪烁，整表填完一次性刷新
    table.setUpdatesEnabled(False)
    try:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem("" if val is None else str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
    finally:
        table.setUpdatesEnabled(True)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)
    # 行号列对数据表价值低、占用横向空间，默认隐藏
    table.verticalHeader().setVisible(False)


def hint_table(table, message):
    """空状态提示：在表格区域居中显示提示文字。

    不使用 setWordWrap（会导致 QScrollArea 内行高塌缩为 0、内容不可见），
    改用固定最小行高 + 显式前景色 + 居中对齐，确保在任何主题下均可读。
    """
    table.setUpdatesEnabled(False)
    try:
        table.setColumnCount(1)
        table.setRowCount(1)
        table.setHorizontalHeaderLabels(["提示"])
        item = QTableWidgetItem(message)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setTextAlignment(Qt.AlignCenter)
        # 从当前主题取文字色强制设置，避免 QSS 继承导致文字与背景同色
        t = theme.THEMES.get(STATE.theme, theme.THEMES["学术蓝"])
        item.setForeground(QColor(t["text"]))
        table.setItem(0, 0, item)
        # 固定行高，不依赖 resizeRowsToContents（word-wrap 场景下行高计算不准）
        table.setRowHeight(0, 56)
        table.horizontalHeader().setStretchLastSection(True)
    finally:
        table.setUpdatesEnabled(True)
    table.verticalHeader().setVisible(False)


def new_panel(title_text, sub_text):
    """返回一个带标题、内容可滚动的面板外壳 (QScrollArea)。

    用 QScrollArea 包裹内容，避免窗口高度不足时（如院校库长列表、数据管理
    多区块）内容被截断、无法查看。widgetResizable 保证内容可完整滚动。
    """
    frame = QScrollArea()
    frame.setObjectName("Panel")
    frame.setWidgetResizable(True)
    frame.setFrameShape(QFrame.NoFrame)
    inner = QWidget()
    inner.setObjectName("Panel")
    root = QVBoxLayout(inner)
    root.setContentsMargins(22, 22, 22, 22)
    root.setSpacing(14)
    title = QLabel(title_text)
    title.setObjectName("Title")
    sub = QLabel(sub_text)
    sub.setObjectName("Sub")
    sub.setWordWrap(True)
    root.addWidget(title)
    root.addWidget(sub)
    root.addSpacing(6)
    frame.setWidget(inner)
    return frame, root


def card(label, value, color):
    # 边框颜色跟随当前主题，切换主题后自动更新
    pal = theme.THEMES.get(STATE.theme, theme.THEMES["学术蓝"])
    c = QFrame()
    c.setObjectName("Panel")
    c.setStyleSheet("border:1px solid %s;border-radius:10px;padding:14px;" % pal["border"])
    lo = QVBoxLayout(c)
    lo.setSpacing(4)
    lbl = QLabel(label)
    lbl.setWordWrap(True)
    lo.addWidget(lbl)
    v = QLabel(str(value))
    v.setObjectName("CardValue")
    v.setStyleSheet("color:%s;" % color)
    lo.addWidget(v)
    return c


# --------------------------------------------------------------------------- #
# 院校标识图（本地生成，零网络依赖；解决数据源无图片时的视觉缺位）
# --------------------------------------------------------------------------- #
def _badge_color(name, level):
    """依据办学层次/名称返回 (底色, 文字色) 配色。"""
    s = "%s %s" % (name or "", level or "")
    if "985" in s or "北京大学" in s or "清华大学" in s:
        return ("#b8860b", "#fff7e0")          # 深金（顶尖）
    if "211" in s:
        return ("#2c5f8a", "#dce8f5")          # 蓝
    if "双一流" in s:
        return ("#7a4fb5", "#ece0f7")          # 紫
    if "专科" in s or "职业" in s:
        return ("#d9722e", "#fbe9d8")          # 橙
    if "本科" in s:
        return ("#2f8f6b", "#dcefe6")          # 绿
    return ("#4a5568", "#dfe3ea")              # 灰（默认）


def make_school_badge(name, level, size=96):
    """生成本地院校标识图（圆角牌 + 首字），零外部依赖。

    不使用任何网络图片源（数据源锁定且 UI 不外联），完全本地绘制，
    既满足「院校要有图片」的体验需求，又符合数据合规约束。
    """
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    bg, fg = _badge_color(name, level)
    margin = int(size * 0.06)
    rect = px.rect().adjusted(margin, margin, -margin, -margin)
    p.setBrush(QColor(bg))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(rect, size * 0.18, size * 0.18)
    ch = (name or "校").strip()
    ch = ch[0] if ch else "校"
    p.setPen(QColor(fg))
    p.setFont(QFont("Microsoft YaHei", int(size * 0.42), QFont.Bold))
    p.drawText(rect, Qt.AlignCenter, ch)
    p.end()
    return px


# --------------------------------------------------------------------------- #
# 基类
# --------------------------------------------------------------------------- #
class BasePanel(QWidget):
    def __init__(self, ds, state):
        super().__init__()
        self.ds = ds
        self.state = state

    def refresh(self):
        """子类按需刷新。"""
        pass

    def _on_state(self, field):
        """状态变更统一回调：主题切换无需重算；非可见面板延迟到切回时刷新，
        避免后台无谓 recompute，提升切换流畅度。"""
        if field == "theme":
            return
        if not self.isVisible():
            return
        self.refresh()


# --------------------------------------------------------------------------- #
# 1. 概览
# --------------------------------------------------------------------------- #
class HomePanel(BasePanel):
    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel(
            "高考模拟填报系统", "本地数据 · 智能推荐 · 冲稳保梯度一目了然")
        self.cards = QHBoxLayout()
        self.cards.setSpacing(12)
        self.root.addLayout(self.cards)
        self.preview = QTableWidget()
        self.preview.setAlternatingRowColors(True)
        self.root.addWidget(QLabel("为你推荐（基于当前成绩）"))
        self.root.addWidget(self.preview, 1)
        self.state.changed.connect(self._on_state)

    def refresh(self):
        # 清空卡片
        while self.cards.count():
            w = self.cards.takeAt(0).widget()
            if w:
                w.deleteLater()
        st = self.state
        stats = self.ds.stats()
        colors = ["#2c5f8a", "#2f8f6b", "#d9722e", "#c85a8a"]
        for (lab, val, col) in [
            ("省份", st.province, colors[0]),
            ("年份", st.year, colors[1]),
            ("科类", st.subject, colors[2]),
            ("院校库", "%d 所" % stats["schools"], colors[3]),
        ]:
            self.cards.addWidget(card(lab, val, col))
        self.cards.addStretch(1)

        if st.score is None and st.rank is None:
            # 未填成绩时显示引导提示，而非空白表格
            hint_table(self.preview, "请先前往「分数录入」填写高考成绩或位次")
            return
        recs = self.ds.get_admissions(st.province, st.year, st.subject)
        rt_rows = self.ds.get_rank_rows(st.province, st.year, st.subject)
        rt = RankTable(rt_rows) if rt_rows else None
        res = recommend(st.rank, st.score, st.province, st.subject, st.year, recs, top=8, rank_table=rt)
        rows = []
        for tier in ("冲", "稳", "保"):
            for rec, meta in res.get(tier, []):
                rows.append([tier, rec.school_name, rec.major_group or "—",
                             rec.score if rec.score is not None else "—",
                             rec.rank if rec.rank is not None else "—",
                             "%d%%" % round(meta["prob"] * 100), meta["smart"]])
        if not rows:
            self.preview.setRowCount(0)
            self.preview.setColumnCount(0)
        else:
            fill_table(self.preview,
                       ["梯度", "院校", "专业组", "最低分", "位次", "概率", "智能分"], rows)


# --------------------------------------------------------------------------- #
# 2. 分数录入
# --------------------------------------------------------------------------- #
class ScorePanel(BasePanel):
    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("分数录入", "填写高考成绩，作为推荐与梯度诊断的依据")
        form = QFormLayout()
        form.setSpacing(12)
        self.score_edit = QLineEdit()
        self.rank_edit = QLineEdit()
        self.score_edit.setPlaceholderText("例如 580")
        self.rank_edit.setPlaceholderText("例如 40000")
        form.addRow("高考总分：", self.score_edit)
        form.addRow("全省位次：", self.rank_edit)
        self.root.addLayout(form)
        self.hint = QLabel("")
        self.hint.setObjectName("Sub")
        self.hint.setWordWrap(True)
        self.root.addWidget(self.hint)
        btn = QPushButton("保存成绩")
        btn.clicked.connect(self._save)
        self.root.addWidget(btn)
        self.root.addStretch(1)
        # 初始化
        if state.score is not None:
            self.score_edit.setText(str(state.score))
        if state.rank is not None:
            self.rank_edit.setText(str(state.rank))
        # 回车即保存，减少鼠标操作
        self.score_edit.returnPressed.connect(self._save)
        self.rank_edit.returnPressed.connect(self._save)

    def _save(self):
        s = self.score_edit.text().strip()
        r = self.rank_edit.text().strip()
        score = _to_float(s)
        rank = _to_int(r)
        if score is None and rank is None:
            self.hint.setText("请至少填写总分或位次之一")
            return
        self.state.score = score
        self.state.rank = rank
        self.hint.setText("已保存：总分=%s，位次=%s" % (score, rank))


# --------------------------------------------------------------------------- #
# 3. 智能推荐
# --------------------------------------------------------------------------- #
class RecommendPanel(BasePanel):
    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("智能推荐", "AI 算法引擎：录取概率 + 多因子匹配分，自适应冲稳保")
        self.tables = {}
        self.boxes = {}
        for tier in ("冲", "稳", "保"):
            box = QGroupBox("%s 志愿" % tier)
            bl = QVBoxLayout(box)
            tw = QTableWidget()
            tw.setAlternatingRowColors(True)
            bl.addWidget(tw)
            self.tables[tier] = tw
            self.boxes[tier] = box
            self.root.addWidget(box, 1)
        self.summary = QLabel("")
        self.summary.setObjectName("Sub")
        self.summary.setWordWrap(True)
        self.root.addWidget(self.summary)
        self.state.changed.connect(self._on_state)

    def refresh(self):
        st = self.state
        if st.score is None and st.rank is None:
            for tier in self.tables:
                self.boxes[tier].setTitle("%s 志愿" % tier)
                self.tables[tier].setRowCount(0)
                self.tables[tier].setColumnCount(0)
            self.summary.setText("填写成绩后即可查看冲 / 稳 / 保 梯度推荐")
            return
        recs = self.ds.get_admissions(st.province, st.year, st.subject, st.batch)
        rt_rows = self.ds.get_rank_rows(st.province, st.year, st.subject)
        rt = RankTable(rt_rows) if rt_rows else None
        res = recommend(st.rank, st.score, st.province, st.subject, st.year, recs,
                        top=15, rank_table=rt)
        counts = {}
        for tier in ("冲", "稳", "保"):
            rows = []
            for rec, meta in res.get(tier, []):
                reasons = "；".join(meta["reasons"])
                rows.append([rec.school_name, rec.major_group or "—",
                             rec.score if rec.score is not None else "—",
                             rec.rank if rec.rank is not None else "—",
                             "%d%%" % round(meta["prob"] * 100), meta["smart"], reasons])
            counts[tier] = len(rows)
            self.boxes[tier].setTitle("%s 志愿 (%d)" % (tier, len(rows)))
            if not rows:
                self.tables[tier].setRowCount(0)
                self.tables[tier].setColumnCount(0)
            else:
                fill_table(self.tables[tier],
                           ["院校", "专业组", "最低分", "位次", "概率", "智能分", "说明"], rows)
        total = sum(counts.values())
        self.summary.setText("共推荐 %d 所：冲 %d · 稳 %d · 保 %d"
                             % (total, counts["冲"], counts["稳"], counts["保"]))


# --------------------------------------------------------------------------- #
# 4. 模拟志愿
# --------------------------------------------------------------------------- #
class VolunteerPanel(BasePanel):
    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("模拟志愿", "增删志愿、保存本地、梯度诊断、导出 CSV")
        form = QFormLayout()
        self.school_edit = QLineEdit()
        self.mg_edit = QLineEdit()
        self.score_edit = QLineEdit()
        self.rank_edit = QLineEdit()
        self.batch_edit = QLineEdit()
        self.school_edit.setPlaceholderText("院校名称")
        self.mg_edit.setPlaceholderText("专业组（可空）")
        self.score_edit.setPlaceholderText("预估最低分（可空）")
        self.rank_edit.setPlaceholderText("预估位次（可空）")
        self.batch_edit.setPlaceholderText("批次（可空）")
        form.addRow("院校：", self.school_edit)
        form.addRow("专业组：", self.mg_edit)
        form.addRow("最低分：", self.score_edit)
        form.addRow("位次：", self.rank_edit)
        form.addRow("批次：", self.batch_edit)
        self.root.addLayout(form)

        btns = QHBoxLayout()
        for (txt, fn) in [("添加", self._add), ("删除选中", self._del),
                          ("上移", self._move_up), ("下移", self._move_down),
                          ("保存", self._save), ("导出CSV", self._export)]:
            b = QPushButton(txt)
            b.clicked.connect(fn)
            btns.addWidget(b)
        self.root.addLayout(btns)

        self.count_label = QLabel("")
        self.count_label.setObjectName("Sub")
        self.count_label.setWordWrap(True)
        self.root.addWidget(self.count_label)

        self.gradient = QLabel("")
        self.gradient.setObjectName("Sub")
        self.gradient.setWordWrap(True)
        self.root.addWidget(self.gradient)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.root.addWidget(self.table, 1)
        # 回车直接添加当前填写的志愿，减少鼠标操作
        self.school_edit.returnPressed.connect(self._add)
        self.score_edit.returnPressed.connect(self._add)
        self.state.changed.connect(self._on_state)
        self.refresh()

    def _rows_from_table(self):
        vols = []
        for i in range(self.table.rowCount()):
            def g(c):
                it = self.table.item(i, c)
                return it.text() if it else ""
            s_score = g(3).strip()
            s_rank = g(4).strip()
            # 表格列序：# 院校 专业组 最低分 位次 批次 梯度 备注
            # 备注位于第 7 列（index 7），切勿误读为第 6 列（梯度）
            vols.append(Volunteer(
                school=g(1), major_group=g(2),
                score=_to_float(s_score),
                rank=_to_int(s_rank),
                batch=g(5), priority=i + 1, note=g(7)))
        return vols

    def _add(self):
        rows = self._rows_from_table()
        rows.append(Volunteer(school=self.school_edit.text().strip(),
                              major_group=self.mg_edit.text().strip(),
                              score=_to_float(self.score_edit.text()),
                              rank=_to_int(self.rank_edit.text()),
                              batch=self.batch_edit.text().strip(),
                              priority=len(rows) + 1))
        self.state.volunteers = [v.to_dict() for v in rows]
        save_volunteers(rows)
        self.school_edit.clear()
        self.mg_edit.clear()
        self.score_edit.clear()
        self.rank_edit.clear()
        self.batch_edit.clear()
        self.refresh()

    def _del(self):
        idx = self.table.currentRow()
        if idx < 0:
            return
        rows = self._rows_from_table()
        rows.pop(idx)
        save_volunteers(rows)
        self.refresh()

    def _save(self):
        rows = self._rows_from_table()
        save_volunteers(rows)
        QMessageBox.information(self, "已保存", "志愿表已保存到本地 userdata/volunteers.json")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出志愿表", "volunteers.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self._rows_from_table()
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["序号", "院校", "专业组", "最低分", "位次", "批次", "梯度", "备注"])
            for i, v in enumerate(rows, 1):
                tier = categorize(v.to_dict(), self.state.score, self.state.rank)
                w.writerow([i, v.school, v.major_group, v.score, v.rank, v.batch, tier, v.note])
        QMessageBox.information(self, "已导出", "已导出到 %s" % path)

    def _move_up(self):
        self._swap(-1)

    def _move_down(self):
        self._swap(1)

    def _swap(self, delta):
        """上移/下移选中志愿：重排优先级并落盘，便于调整冲稳保顺序。"""
        idx = self.table.currentRow()
        if idx < 0:
            return
        rows = self._rows_from_table()
        j = idx + delta
        if j < 0 or j >= len(rows):
            return
        rows[idx], rows[j] = rows[j], rows[idx]
        for k, v in enumerate(rows, 1):
            v.priority = k
        save_volunteers(rows)
        STATE.volunteers = [v.to_dict() for v in rows]
        self.refresh()
        self.table.selectRow(j)

    def refresh(self):
        vols = load_volunteers()
        self.count_label.setText("共 %d 条志愿" % len(vols))
        rows = []
        for i, v in enumerate(vols, 1):
            tier = categorize(v.to_dict(), self.state.score, self.state.rank)
            rows.append([i, v.school, v.major_group,
                         v.score if v.score is not None else "",
                         v.rank if v.rank is not None else "", v.batch, tier, v.note])
        fill_table(self.table, ["#", "院校", "专业组", "最低分", "位次", "批次", "梯度", "备注"], rows)
        self._render_gradient(vols)

    def _render_gradient(self, vols):
        colors = {"冲": "#d9722e", "稳": "#2f8f6b", "保": "#3b82c4", "—": "#b8c2cc"}
        labels = {"冲": "冲", "稳": "稳", "保": "保", "—": "未定"}
        counts = {k: 0 for k in colors}
        for v in vols:
            t = categorize(v.to_dict(), self.state.score, self.state.rank)
            counts[t] = counts.get(t, 0) + 1
        total = len(vols)
        if not total:
            self.gradient.setText("尚未添加志愿，添加后这里显示冲/稳/保梯度分布")
            return
        parts = ['<span style="font-size:12px;">梯度分布：</span>']
        for k in ("冲", "稳", "保", "—"):
            if counts[k]:
                parts.append('<span style="background:%s;color:#fff;padding:2px 10px;'
                             'margin-right:4px;border-radius:4px;">%s %d</span>'
                             % (colors[k], labels[k], counts[k]))
        self.gradient.setText('<div>' + ''.join(parts) + '</div>')


# --------------------------------------------------------------------------- #
# 5. 位次分析（Canvas 曲线）
# --------------------------------------------------------------------------- #
class RankCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.user_score = None
        self.user_rank = None
        self.setMinimumHeight(280)

    def set_data(self, rows, user_score, user_rank):
        self.rows = [r for r in rows if r.score is not None and r.rank is not None]
        # 绘制降采样：一分一段表常达数万行，paintEvent 逐点 drawLine 会很卡。
        # 此处数据仅用于绘图，等间隔抽样（保留端点）即可保持曲线形态；
        # 分数↔位次的精确估算由 AnalysisPanel 用全量 RankTable 完成，不受影响。
        if len(self.rows) > 2000:
            step = (len(self.rows) - 1) // 1999 + 1
            sampled = self.rows[::step]
            if sampled and sampled[-1] is not self.rows[-1]:
                sampled.append(self.rows[-1])
            self.rows = sampled
        self.user_score = user_score
        self.user_rank = user_rank
        self.update()

    def paintEvent(self, ev):
        from PySide6.QtGui import QPaintEvent
        super().paintEvent(ev)
        if not self.rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 50, 20, 20, 40
        plot_w, plot_h = w - ml - mr, h - mt - mb
        scores = [r.score for r in self.rows]
        ranks = [r.rank for r in self.rows]
        s_min, s_max = min(scores), max(scores)
        r_min, r_max = min(ranks), max(ranks)
        if s_max == s_min:
            s_max += 1
        if r_max == r_min:
            r_max += 1

        def px(score):
            return ml + (score - s_min) / (s_max - s_min) * plot_w

        def py(rank):
            # rank 越大越靠下
            return mt + (rank - r_min) / (r_max - r_min) * plot_h

        # 网格（淡色，先画网格再画坐标轴，避免盖住刻度）
        NX, NY = 5, 5
        p.setPen(QPen(QColor("#e6ebf1"), 1))
        for i in range(NX + 1):
            gx = ml + plot_w * i / NX
            p.drawLine(int(gx), mt, int(gx), mt + plot_h)
        for j in range(NY + 1):
            gy = mt + plot_h * j / NY
            p.drawLine(ml, int(gy), ml + plot_w, int(gy))

        # 坐标轴
        p.setPen(QPen(QColor("#888888"), 1))
        p.drawLine(ml, mt, ml, mt + plot_h)
        p.drawLine(ml, mt + plot_h, ml + plot_w, mt + plot_h)
        # 曲线
        p.setPen(QPen(QColor("#2c5f8a"), 2))
        pts = [(px(r.score), py(r.rank)) for r in self.rows]
        for i in range(1, len(pts)):
            p.drawLine(int(pts[i - 1][0]), int(pts[i - 1][1]),
                       int(pts[i][0]), int(pts[i][1]))
        # 用户点
        if self.user_score is not None and self.user_rank is not None:
            ux, uy = px(self.user_score), py(self.user_rank)
            p.setPen(QPen(QColor("#d9722e"), 2))
            p.setBrush(QColor("#d9722e"))
            p.drawEllipse(int(ux) - 5, int(uy) - 5, 10, 10)

        # 标签与刻度
        p.setFont(QFont("sans-serif", 9))
        p.setPen(QColor("#333333"))
        p.drawText(ml, mt - 6, "分数→位次 曲线（一分一段表）")

        # X 轴刻度（分数）
        p.setPen(QColor("#666666"))
        for i in range(NX + 1):
            gx = ml + plot_w * i / NX
            p.drawLine(int(gx), mt + plot_h, int(gx), mt + plot_h + 4)
            sv = s_min + (s_max - s_min) * i / NX
            label = "%.0f" % sv
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(int(gx) - tw // 2, mt + plot_h + 18, label)
        p.drawText(ml + plot_w - 22, mt + plot_h + 34, "分数")

        # Y 轴刻度（位次，数值越大越靠下）
        for j in range(NY + 1):
            gy = mt + plot_h * j / NY
            p.drawLine(ml - 4, int(gy), ml, int(gy))
            rv = r_min + (r_max - r_min) * j / NY
            label = "%.0f" % rv
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(ml - 6 - tw, int(gy) + 4, label)
        p.drawText(2, mt + 4, "位次")


class AnalysisPanel(BasePanel):
    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("位次分析", "基于一分一段表，标注你的成绩在全省的位置")
        self.canvas = RankCanvas()
        self.root.addWidget(self.canvas, 1)
        self.info = QLabel("")
        self.info.setObjectName("Sub")
        self.info.setWordWrap(True)
        self.root.addWidget(self.info)
        self.state.changed.connect(self._on_state)

    def refresh(self):
        st = self.state
        rows = self.ds.get_rank_rows(st.province, st.year, st.subject)
        self.canvas.set_data(rows, st.score, st.rank)
        if not rows:
            self.info.setText("该省份/年份/科类暂无位次表数据")
            return
        if st.score is not None:
            rt = RankTable(rows)
            est = rt.rank_for(st.score)
            self.info.setText("你的分数 %s 约对应位次 %s" % (st.score, int(est) if est else "—"))
        elif st.rank is not None:
            rt = RankTable(rows)
            est = rt.score_for(st.rank)
            self.info.setText("你的位次 %s 约对应分数 %s" % (st.rank, est if est else "—"))
        else:
            self.info.setText("填写成绩后可估算等效位次/分数")


# --------------------------------------------------------------------------- #
# 6. 院校库
# --------------------------------------------------------------------------- #
class SchoolPanel(BasePanel):
    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("院校库", "按省份/年份检索院校，查看近年投档线")
        top = QHBoxLayout()
        self.kw = QLineEdit()
        self.kw.setPlaceholderText("搜索院校名称关键词")
        top.addWidget(self.kw)
        btn = QPushButton("搜索")
        btn.clicked.connect(self._search)
        top.addWidget(btn)
        self.btn_add = QPushButton("加入志愿")
        self.btn_add.clicked.connect(self._add_to_volunteers)
        self.btn_add.setEnabled(False)
        top.addWidget(self.btn_add)
        self.btn_detail = QPushButton("查看详情")
        self.btn_detail.clicked.connect(self._open_detail)
        self.btn_detail.setEnabled(False)
        top.addWidget(self.btn_detail)
        self.root.addLayout(top)

        self.count_label = QLabel("")
        self.count_label.setObjectName("Sub")
        self.count_label.setWordWrap(True)
        self.root.addWidget(self.count_label)

        mid = QHBoxLayout()
        self.listw = QListWidget()
        self.listw.setFixedWidth(300)
        self.listw.currentTextChanged.connect(self._on_select)
        self.listw.itemDoubleClicked.connect(lambda item: self._open_detail())
        self.hist = QTableWidget()
        self.hist.setAlternatingRowColors(True)
        mid.addWidget(self.listw)
        mid.addWidget(self.hist, 1)
        self.root.addLayout(mid, 1)
        self.kw.returnPressed.connect(self._search)
        self.state.changed.connect(self._on_state)
        self._search()

    def _on_state(self, field):
        """院校库刷新走 _search（非 refresh），故此处覆盖基类逻辑。"""
        if field == "theme":
            return
        if not self.isVisible():
            return
        self._search()

    def refresh(self):
        """覆盖基类 refresh：切换到院校库面板时重新执行搜索，确保列表与当前省份/年份一致。"""
        self._search()

    def _search(self):
        st = self.state
        kw = self.kw.text().strip() or None
        schools = self.ds.distinct_schools(st.province, st.year, kw)
        self.listw.clear()
        for sid, name in schools:
            self.listw.addItem(QListWidgetItem(name))
        if not schools:
            # 占位项：禁用选中/点击，避免被误当作院校触发「无数据」提示
            ph = QListWidgetItem("当前筛选暂无院校数据（请切换省份/年份或下载更新）")
            ph.setFlags(Qt.NoItemFlags)
            ph.setForeground(QColor("#b8c2cc"))
            self.listw.addItem(ph)
        self.count_label.setText("找到 %d 所院校%s"
                                 % (len(schools), "（关键词：%s）" % kw if kw else ""))

    def _on_select(self, name):
        if not name or name.startswith("当前筛选"):
            self.current_school = None
            self.btn_add.setEnabled(False)
            self.btn_detail.setEnabled(False)
            return
        self.current_school = name
        self.btn_add.setEnabled(bool(name))
        self.btn_detail.setEnabled(bool(name))
        if not name:
            return
        st = self.state
        hist = self.ds.school_history(name, st.province)
        rows = [[r.year, r.batch, r.subject, r.major_group or "—",
                 r.score if r.score is not None else "—",
                 r.rank if r.rank is not None else "—",
                 r.plan if r.plan is not None else "—"] for r in hist]
        fill_table(self.hist, ["年份", "批次", "科类", "专业组", "最低分", "位次", "计划"], rows)

    def _add_to_volunteers(self):
        """把当前选中院校的最新一条投档线一键加入模拟志愿，避免重复手填。"""
        name = getattr(self, "current_school", None)
        if not name:
            return
        hist = self.ds.school_history(name, self.state.province)
        cand = None
        for r in hist:
            if r.score is not None:
                if cand is None or (r.year or 0) > (cand.year or 0):
                    cand = r
        if cand is None:
            QMessageBox.information(self, "提示", "该院校暂无可用投档线数据，无法加入志愿")
            return
        vols = load_volunteers()
        vols.append(Volunteer(
            school=name,
            major_group=cand.major_group or "",
            score=cand.score,
            rank=cand.rank,
            batch=cand.batch,
            priority=len(vols) + 1,
        ))
        save_volunteers(vols)
        STATE.volunteers = vols
        QMessageBox.information(self, "已加入", "已将「%s」加入模拟志愿（可在「模拟志愿」面板查看）" % name)

    def _open_detail(self):
        """打开院校详情对话框：基本信息 + 历年投档线明细 + 趋势总结。"""
        name = getattr(self, "current_school", None)
        if not name:
            QMessageBox.information(self, "提示", "请先在左侧选择一所院校")
            return
        dlg = SchoolDetailDialog(self.ds, name, self.state.province, self)
        dlg.exec()


class SchoolDetailDialog(QDialog):
    """院校详情弹窗：聚合 schools 表基础信息与 admissions 历年投档线。"""

    def __init__(self, ds, school_name, province, parent=None):
        super().__init__(parent)
        self.ds = ds
        self.school_name = school_name
        self.province = province
        self.setWindowTitle("院校详情 - %s" % school_name)
        self.setMinimumSize(820, 560)
        self.resize(940, 660)
        self._build()

    def _build(self):
        try:
            detail = self.ds.school_detail(self.school_name, None)
        except Exception:
            detail = {"info": {}, "admissions": [], "provinces": []}
        info = detail.get("info") or {}
        adm = detail.get("admissions") or []
        provinces = detail.get("provinces") or []

        root = QVBoxLayout(self)

        # ---- 头部：标识图 + 校名 ----
        head = QHBoxLayout()
        badge = QLabel()
        badge.setPixmap(make_school_badge(self.school_name, info.get("level")))
        badge.setFixedSize(96, 96)
        head.addWidget(badge)
        hbox = QVBoxLayout()
        hname = QLabel(self.school_name)
        hname.setObjectName("Title")
        hname.setStyleSheet("font-size:18px;")
        hbox.addWidget(hname)
        hsub = QLabel(info.get("level") or info.get("type") or "院校")
        hsub.setObjectName("Sub")
        hbox.addWidget(hsub)
        head.addLayout(hbox, 1)
        root.addLayout(head)

        # ---- 基本信息 ----
        box = QGroupBox("院校基本信息")
        grid = QGridLayout(box)
        meta_map = [
            ("省份", info.get("province")),
            ("城市", info.get("city")),
            ("办学层次", info.get("level")),
            ("院校类型", info.get("type")),
            ("院校门类", info.get("category")),
            ("主管部门", info.get("department")),
            ("标签", info.get("tags")),
        ]
        row = col = shown = 0
        for label, val in meta_map:
            if val:
                grid.addWidget(QLabel("<b>%s</b>" % label), row, col * 2)
                grid.addWidget(QLabel(str(val)), row, col * 2 + 1)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1
                shown += 1
        if shown == 0:
            grid.addWidget(QLabel("（数据来源未提供该校基础信息，以下为录取数据聚合）"), 0, 0)
        root.addWidget(box)

        # ---- 趋势总结 ----
        tb = QTextBrowser()
        tb.setReadOnly(True)
        tb.setMaximumHeight(96)
        tb.setHtml(self._summary(info, adm, provinces))
        root.addWidget(tb)

        # ---- 明细表 ----
        tab_box = QGroupBox("历年投档线明细（共 %d 条）" % len(adm))
        v2 = QVBoxLayout(tab_box)
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        rows = [[r.year, r.province, r.batch, r.subject, r.major_group or "—",
                 r.score if r.score is not None else "—",
                 r.rank if r.rank is not None else "—",
                 r.plan if r.plan is not None else "—"] for r in adm]
        fill_table(table, ["年份", "省份", "批次", "科类", "专业组", "最低分", "位次", "计划"], rows)
        v2.addWidget(table)
        root.addWidget(tab_box, 1)

        # ---- 关闭按钮 ----
        btn = QPushButton("关闭")
        btn.clicked.connect(self.accept)
        hb = QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(btn)
        root.addLayout(hb)

    def _summary(self, info, adm, provinces):
        parts = []
        if provinces:
            parts.append("招生省份：%s" % "、".join(provinces))
        prov_adm = [r for r in adm if (not self.province or r.province == self.province)]
        scored = [r for r in prov_adm if r.score is not None]
        if scored:
            years = sorted({r.year for r in scored})
            lo = min(r.score for r in scored)
            hi = max(r.score for r in scored)
            parts.append("在%s共有 %d 个年份投档记录（%d~%d）"
                         % (self.province or "全国", len(years), min(years), max(years)))
            parts.append("最低分区间：%g ~ %g 分" % (lo, hi))
            ranks = [r.rank for r in scored if r.rank is not None]
            if ranks:
                parts.append("对应位次区间：%s ~ %s 名" % (f"{min(ranks):,}", f"{max(ranks):,}"))
            trend = self._trend(prov_adm)
            if trend:
                parts.append(trend)
        else:
            parts.append("暂无可用分数数据")
        return "<p style='line-height:1.6'>%s</p>" % "　|　".join(parts)

    def _trend(self, prov_adm):
        cand = [r for r in prov_adm if "本科" in (r.batch or "")]
        if not cand:
            cand = prov_adm
        scored = [r for r in cand if r.score is not None]
        if len(scored) < 2:
            return ""
        by_year = sorted(scored, key=lambda r: r.year or 0)
        first, last = by_year[0], by_year[-1]
        if first.year == last.year:
            return ""
        diff = (last.score or 0) - (first.score or 0)
        if abs(diff) <= 3:
            verdict = "总体平稳"
        elif diff > 0:
            verdict = "整体呈上升（分数走高）趋势"
        else:
            verdict = "整体呈下降（分数走低）趋势"
        return "趋势：%d 年 %g 分 → %d 年 %g 分，%s" % (
            first.year, first.score, last.year, last.score, verdict)


# --------------------------------------------------------------------------- #
# 7. 数据管理（含云端数据源同步）
# --------------------------------------------------------------------------- #
class DownloadThread(QThread):
    """后台下载线程：避免网络 IO 阻塞主界面。"""
    progress = Signal(int, int, str, str)        # (当前, 总数, 文件名, 状态)
    finished = Signal(bool, str, dict)            # (成功, 错误信息, 统计)

    def run(self):
        if cloud.is_downloading():
            self.finished.emit(False, "SKIP", {})
            return
        cloud.set_downloading(True)
        try:
            stats = cloud.download_all(progress=self._on_progress)
        finally:
            cloud.set_downloading(False)
        self.finished.emit(bool(stats.get("ok")), stats.get("error", ""), stats)

    def _on_progress(self, idx, total, name, status):
        self.progress.emit(idx, total, name, status)


class DataPanel(BasePanel):
    data_changed = Signal(dict)  # 下载完成后通知主窗口热切换数据源
    data_cleared = Signal()      # 清除已下载数据后通知主窗口

    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("数据管理", "本地数据库状态与志愿表维护")
        self.thread = None

        # ---- 云端数据源区 ----
        box = QGroupBox("数据下载")
        bl = QVBoxLayout(box)
        bl.setSpacing(8)
        self.cloud_info = QLabel("")
        self.cloud_info.setObjectName("Sub")
        self.cloud_info.setWordWrap(True)
        bl.addWidget(self.cloud_info)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        bl.addWidget(self.progress)

        cbtns = QHBoxLayout()
        self.btn_check = QPushButton("检查更新")
        self.btn_check.clicked.connect(self._check)
        self.btn_download = QPushButton("下载全部到本地")
        self.btn_download.clicked.connect(self._download)
        cbtns.addWidget(self.btn_check)
        cbtns.addWidget(self.btn_download)
        bl.addLayout(cbtns)
        self.root.addWidget(box)

        # ---- 本地库状态 ----
        self.stat_label = QLabel("")
        self.stat_label.setWordWrap(True)
        self.root.addWidget(self.stat_label)

        self.path_label = QLabel("")
        self.path_label.setObjectName("Sub")
        self.path_label.setWordWrap(True)
        self.root.addWidget(self.path_label)

        self.btn_open = QPushButton("打开数据文件夹")
        self.btn_open.setObjectName("Ghost")
        self.btn_open.clicked.connect(self._open_folder)
        self.root.addWidget(self.btn_open)

        # ---- 清除已下载数据 ----
        self.btn_clear_data = QPushButton("清除已下载数据")
        self.btn_clear_data.setObjectName("Ghost")
        self.btn_clear_data.clicked.connect(self._clear_data)
        self.root.addWidget(self.btn_clear_data)

        # ---- 数据设置（可调控项）----
        set_box = QGroupBox("数据设置")
        sl = QVBoxLayout(set_box)
        sl.setSpacing(8)
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(user_config.get_data_dir())
        self.dir_edit.setReadOnly(True)
        btn_browse = QPushButton("选择位置")
        btn_browse.clicked.connect(self._browse_dir)
        btn_apply = QPushButton("应用并重载")
        btn_apply.clicked.connect(self._apply_data_dir)
        dir_row.addWidget(QLabel("保存位置"))
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(btn_browse)
        dir_row.addWidget(btn_apply)
        sl.addLayout(dir_row)
        self.auto_sync_cb = QCheckBox("启动时自动同步云端数据")
        self.auto_sync_cb.setChecked(user_config.get_auto_sync())
        self.auto_sync_cb.toggled.connect(self._on_auto_sync_toggle)
        sl.addWidget(self.auto_sync_cb)
        self.root.addWidget(set_box)

        # ---- 志愿表维护 ----
        btns = QHBoxLayout()
        b1 = QPushButton("导出志愿表CSV")
        b1.clicked.connect(self._export)
        b2 = QPushButton("清空志愿表")
        b2.setObjectName("Ghost")
        b2.clicked.connect(self._clear)
        btns.addWidget(b1)
        btns.addWidget(b2)
        self.root.addLayout(btns)
        self.root.addStretch(1)

        self.refresh()

    # ---- 检查更新 ----
    def _check(self):
        self.btn_check.setEnabled(False)
        self.cloud_info.setText("正在检查数据更新…")
        try:
            has_update, rv, lv = cloud.need_update()
            if rv is None:
                self.cloud_info.setText("无法连接数据服务，请检查网络后重试。")
            else:
                size_mb = cloud.total_bytes() / (1024 * 1024)
                ver_line = "最新版本：%s\n本地版本：%s" % (rv, lv or "（未下载）")
                if has_update:
                    tip = "● 有更新可用，建议点击「下载全部到本地」"
                elif lv:
                    tip = "✓ 已是最新版本（可重新下载覆盖）"
                else:
                    tip = "尚未下载本地数据，点击下载即可离线使用"
                self.cloud_info.setText("%s\n数据总量：约 %.1f MB\n%s"
                                        % (ver_line, size_mb, tip))
        except Exception as e:  # noqa: BLE001
            self.cloud_info.setText("检查失败：%s" % e)
        finally:
            self.btn_check.setEnabled(True)

    # ---- 下载全部到本地 ----
    def _download(self):
        if self.thread and self.thread.isRunning():
            return
        if cloud.is_downloading():
            QMessageBox.information(self, "提示", "正在下载数据，请稍候…")
            return
        self.btn_check.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.progress.setValue(0)
        self.cloud_info.setText("开始下载数据（请保持网络通畅）…")
        self.thread = DownloadThread()
        self.thread.progress.connect(self._on_progress)
        self.thread.finished.connect(self._on_finished)
        self.thread.start()

    def _on_progress(self, idx, total, name, status):
        pct = int(idx / total * 100) if total else 0
        self.progress.setValue(pct)
        self.cloud_info.setText("正在%s（%d/%d）：%s" % (status, idx, total, name))

    def _on_finished(self, ok, error, stats):
        self.btn_check.setEnabled(True)
        self.btn_download.setEnabled(True)
        if ok:
            self.progress.setValue(100)
            self.cloud_info.setText("✓ 下载完成，已生成本地数据库（版本 %s）" % stats.get("version"))
            self.refresh()
            self.data_changed.emit(stats)
        else:
            self.progress.setValue(0)
            self.cloud_info.setText("✗ 下载失败：%s" % error)
            QMessageBox.warning(self, "下载失败", error)

    # ---- 志愿表 ----
    def _export(self):
        from app.ui.panels import load_volunteers
        vols = load_volunteers()
        if not vols:
            QMessageBox.information(self, "提示", "暂无志愿数据")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出志愿表", "volunteers.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["序号", "院校", "专业组", "最低分", "位次", "批次", "梯度", "备注"])
            for i, v in enumerate(vols, 1):
                w.writerow([i, v.school, v.major_group, v.score, v.rank, v.batch,
                            categorize(v.to_dict(), self.state.score, self.state.rank), v.note])
        QMessageBox.information(self, "已导出", path)

    def _clear(self):
        save_volunteers([])
        QMessageBox.information(self, "已清空", "志愿表已清空")
        self.refresh()

    def refresh(self):
        s = self.ds.stats()
        lp = cloud.local_db_path()
        if os.path.exists(lp) and self.ds.path == lp:
            ver = cloud.local_version() or "未知"
        elif self.ds.path and self.ds.path != ":memory:":
            ver = "开发版本"
        else:
            ver = "—"
        self.stat_label.setText(
            "投档线记录：%s 条\n位次表记录：%s 条\n院校数量：%s 所\n"
            "数据版本：%s"
            % (f"{s['admissions']:,}", f"{s['rank_rows']:,}", f"{s['schools']:,}", ver))
        # 数据库路径与维护信息
        p = self.ds.path
        if os.path.exists(p):
            size = os.path.getsize(p)
            mtime = os.path.getmtime(p)
            mts = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            size_s = "%.1f MB" % (size / 1024 / 1024) if size >= 1024 * 1024 else "%d KB" % (size // 1024)
            self.path_label.setText("数据库路径：%s\n大小：%s · 修改时间：%s" % (p, size_s, mts))
            self.btn_open.setVisible(True)
        else:
            self.path_label.setText("数据库路径：%s（文件不存在）" % p)
            self.btn_open.setVisible(False)

    def _open_folder(self):
        d = os.path.dirname(self.ds.path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ---- 清除已下载数据 ----
    def _clear_data(self):
        r = QMessageBox.question(
            self, "清除已下载数据",
            "将删除已下载的本地数据库与缓存（不影响你的志愿表）。\n"
            "删除后需重新联网下载。确定继续？",
            QMessageBox.Yes | QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.btn_clear_data.setEnabled(False)
        try:
            lp = cloud.local_db_path()
            # 先关闭数据库连接，释放文件句柄，否则 Windows 下 os.remove
            # 会因 gk_local.db 被本进程占用而失败（WinError 32），清除无效。
            try:
                self.ds.close()
            except Exception:
                pass
            if lp and os.path.exists(lp):
                os.remove(lp)
            cd = cloud.cloud_dir()
            if os.path.isdir(cd):
                shutil.rmtree(cd, ignore_errors=True)
            # 热切换回内存占位库，避免后续查询崩溃
            try:
                self.ds.reload()
            except Exception:
                pass
            self.cloud_info.setText("已清除已下载数据。点击「下载全部到本地」可重新获取。")
            self.refresh()
            self.data_cleared.emit()
        except Exception as e:  # noqa: BLE001
            log.error("IO001", "清除已下载数据失败", e)
            QMessageBox.warning(self, "清除失败", errors.fmt("IO001", str(e)))
        finally:
            self.btn_clear_data.setEnabled(True)

    # ---- 保存位置设置 ----
    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择数据保存位置", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _apply_data_dir(self):
        new = self.dir_edit.text().strip()
        if not new:
            QMessageBox.warning(self, "保存位置", "请选择有效的保存目录")
            return
        try:
            os.makedirs(new, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "保存位置", errors.fmt("IO001", "无法创建目录：%s" % new))
            return
        old = user_config.get_data_dir()
        if os.path.abspath(old) == os.path.abspath(new):
            return
        # 先关闭当前数据库连接，释放文件句柄，
        # 否则 Windows 下正在使用的 gk_local.db 无法被移动（WinError 32）。
        try:
            self.ds.close()
        except Exception:
            pass
        # 迁移现有数据到新位置（gk_local.db / volunteers.json / cloud 缓存）
        try:
            for name in ("gk_local.db", "volunteers.json"):
                src = os.path.join(old, name)
                if os.path.exists(src):
                    shutil.move(src, os.path.join(new, name))
            old_cloud = os.path.join(old, "cloud")
            new_cloud = os.path.join(new, "cloud")
            if os.path.isdir(old_cloud):
                if os.path.isdir(new_cloud):
                    shutil.rmtree(new_cloud, ignore_errors=True)
                shutil.move(old_cloud, new_cloud)
        except Exception as e:  # noqa: BLE001
            log.error("IO001", "迁移数据文件失败", e)
            # 迁移失败：重新打开旧库，恢复可用状态
            try:
                self.ds.reload()
            except Exception:
                pass
            QMessageBox.warning(self, "保存位置", errors.fmt("IO001", "迁移数据失败：%s" % e))
            return
        user_config.set_data_dir(new)
        # 立即让 DataStore 指向新位置（新位置有库则加载，否则回退内存占位）
        try:
            self.ds.reload()
        except Exception:
            pass
        QMessageBox.information(
            self, "保存位置",
            "已应用新保存位置：\n%s\n\n（建议重启程序以完全生效）" % new)
        self.refresh()

    # ---- 自动同步开关 ----
    def _on_auto_sync_toggle(self, checked):
        user_config.set_auto_sync(bool(checked))


# --------------------------------------------------------------------------- #
# 8. 帮助（使用指南 + 各功能提示）
# --------------------------------------------------------------------------- #
class HelpPanel(BasePanel):
    """集中展示所有使用指南和提示性内容，避免散落在各功能面板中造成 UI 问题。"""

    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("使用帮助", "操作指南 · 常见问题 · 功能说明")
        self.root.addSpacing(6)

        # ---- 快速开始 ----
        start_box = QGroupBox("快速开始")
        sl = QVBoxLayout(start_box)
        steps = [
            ("1", "填写成绩", "在「分数录入」中输入高考总分和位次（至少填一项）"),
            ("2", "查看推荐", "切换到「智能推荐」，系统自动计算冲 / 稳 / 保 三档院校"),
            ("3", "调整志愿", "在「模拟志愿」中添加、排序、导出你的志愿清单"),
            ("4", "分析位次", "在「位次分析」查看历年录取位次曲线，辅助判断"),
        ]
        for num, title, desc in steps:
            row = QHBoxLayout()
            n = QLabel(num)
            n.setObjectName("CardValue")
            n.setStyleSheet("color:%s;font-size:18px;" % theme.THEMES.get(STATE.theme, theme.THEMES["学术蓝"])["primary"])
            n.setFixedWidth(28)
            row.addWidget(n)
            col = QVBoxLayout()
            t = QLabel(title)
            t.setStyleSheet("font-weight:700;")
            col.addWidget(t)
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setObjectName("Sub")
            col.addWidget(d)
            row.addLayout(col, 1)
            sl.addLayout(row)
        self.root.addWidget(start_box)

        # ---- 各功能说明 ----
        func_box = QGroupBox("功能说明")
        fl = QVBoxLayout(func_box)
        help_items = [
            ("概览页", "显示当前省份/年份/科类的数据概况，以及基于已填成绩的快速推荐预览。未填写成绩时请先去「分数录入」。"),
            ("分数录入", "输入高考总分和位次。支持回车快捷保存。保存后所有推荐和分析面板会自动刷新。"),
            ("智能推荐", "AI 算法引擎综合录取概率、多因子匹配分，将院校分为冲（20-40%）、稳（40-70%）、保（>70%）三档。每档最多显示 15 所。"),
            ("模拟志愿", "手动管理你的志愿清单：添加院校、上移/下移调整优先级、删除、保存到本地、导出 CSV。支持键盘操作（回车添加）。"),
            ("位次分析", "选中院校后展示历年投档线位次变化曲线，帮助判断该院校录取趋势是上升还是下降。"),
            ("院校库", "按关键词搜索院校，查看历史录取数据，一键加入志愿清单。支持回车触发搜索。"),
            ("数据管理", "查看当前数据库状态（记录数、版本），支持联网下载最新数据到本地实现离线使用。点击「打开数据文件夹」可查看数据库文件。"),
        ]
        for title, text in help_items:
            item = QFrame()
            item.setObjectName("Panel")
            il = QVBoxLayout(item)
            il.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("font-weight:700;color:%s;" % theme.THEMES.get(STATE.theme, theme.THEMES["学术蓝"])["primary"])
            il.addWidget(t)
            c = QLabel(text)
            c.setWordWrap(True)
            c.setObjectName("Sub")
            il.addWidget(c)
            fl.addWidget(item)
        self.root.addWidget(func_box, 1)

        # ---- 常见问题 ----
        faq_box = QGroupBox("常见问题")
        faql = QVBoxLayout(faq_box)
        faqs = [
            ("推荐结果为空？", "检查：① 是否已填写成绩；② 当前省份/年份/科类是否有数据；③ 可尝试在「数据管理」下载最新数据扩充数据库。"),
            ("概率是什么意思？", "基于历史位次计算的录取概率估计，仅供参考。实际录取受当年招生计划、报考热度等多种因素影响。"),
            ("如何备份数据？", "志愿表保存在 exe 同目录的 userdata/volunteers.json，复制整个 userdata 文件夹即可备份。"),
            ("数据可以离线使用吗？", "可以。在「数据管理」中点击「下载全部到本地」后，数据存储在本地 SQLite 数据库，之后无需网络即可使用全部功能。"),
        ]
        for q, a in faqs:
            ql = QLabel("Q：" + q)
            ql.setStyleSheet("font-weight:700;padding-top:6px;")
            faql.addWidget(ql)
            al = QLabel("A：" + a)
            al.setWordWrap(True)
            al.setObjectName("Sub")
            faql.addWidget(al)
        self.root.addWidget(faq_box)

        # ---- 错误码与日志 ----
        err_box = QGroupBox("错误码与日志")
        el = QVBoxLayout(err_box)
        intro = QLabel("若程序发生异常，弹窗会以 [错误码] 开头（如 [DL001]）。下表列出常见错误码的含义与处理建议；"
                       "详细的异常堆栈会记录在日志文件中，排查问题时反馈该文件即可。")
        intro.setWordWrap(True)
        intro.setObjectName("Sub")
        el.addWidget(intro)
        err_table = QTableWidget()
        err_table.setColumnCount(3)
        err_table.setHorizontalHeaderLabels(["错误码", "含义", "处理建议"])
        codes = list(errors.ERROR_CODES.items())
        err_table.setRowCount(len(codes))
        for i, (code, (title, suggest)) in enumerate(codes):
            err_table.setItem(i, 0, QTableWidgetItem(code))
            err_table.setItem(i, 1, QTableWidgetItem(title))
            err_table.setItem(i, 2, QTableWidgetItem(suggest))
        err_table.setEditTriggers(QTableWidget.NoEditTriggers)
        err_table.resizeColumnsToContents()
        err_table.horizontalHeader().setStretchLastSection(True)
        err_table.verticalHeader().setVisible(False)
        el.addWidget(err_table)
        try:
            lp = log.log_path()
        except Exception:
            lp = "（保存目录/userdata/app.log）"
        log_info = QLabel("日志文件位置：%s\n包含带时间戳与错误码的详细记录。遇到问题时请将该文件反馈以便定位。" % lp)
        log_info.setWordWrap(True)
        log_info.setObjectName("Sub")
        el.addWidget(log_info)
        self.root.addWidget(err_box)


# --------------------------------------------------------------------------- #
# 9. 关于
# --------------------------------------------------------------------------- #
class AboutPanel(BasePanel):
    """关于页面：版本信息、技术栈、致谢。"""

    def __init__(self, ds, state):
        super().__init__(ds, state)
        self.frame, self.root = new_panel("关于", "高考模拟填报系统")
        self.root.addSpacing(10)

        # 应用信息卡片
        info = QFrame()
        info.setObjectName("Panel")
        info.setStyleSheet("border:1px solid %s;border-radius:12px;padding:24px;text-align:center;"
                           % theme.THEMES.get(STATE.theme, theme.THEMES["学术蓝"])["border"])
        il = QVBoxLayout(info)
        il.setAlignment(Qt.AlignCenter)

        name = QLabel("高考模拟填报系统")
        name.setObjectName("Title")
        name.setStyleSheet("font-size:24px;")
        il.addWidget(name)

        ver = QLabel("版本 1.0.0")
        ver.setObjectName("Sub")
        il.addWidget(ver)

        tagline = QLabel("本地数据 · 智能推荐 · 冲稳保梯度一目了然")
        tagline.setWordWrap(True)
        tagline.setObjectName("Sub")
        il.addWidget(tagline)
        il.addSpacing(12)

        stats = ds.stats()
        detail = QLabel(
            "数据统计\n"
            "─────────────\n"
            f"投档线记录：{stats.get('admissions', 0):,} 条\n"
            f"位次表记录：{stats.get('rank_rows', 0):,} 条\n"
            f"院校数量：{stats.get('schools', 0):,} 所"
        )
        detail.setAlignment(Qt.AlignCenter)
        detail.setObjectName("Sub")
        il.addWidget(detail)
        self.root.addWidget(info)

        # 技术栈
        tech_box = QGroupBox("技术栈")
        tl = QVBoxLayout(tech_box)
        techs = [
            "Python 3.13 + PySide6 (Qt6)",
            "SQLite 本地数据库",
            "PyInstaller 单文件打包",
            "数据自动同步",
        ]
        for t in techs:
            tl.addWidget(QLabel("• " + t))
        self.root.addWidget(tech_box)

        # 免责声明（不暴露数据来源）
        disc_box = QGroupBox("免责声明")
        dl = QVBoxLayout(disc_box)
        disc_label = QLabel(
            "数据仅供模拟与志愿填报参考，不构成任何报考建议。\n"
            "实际填报请以各省教育考试院官方公布为准。"
        )
        disc_label.setWordWrap(True)
        disc_label.setObjectName("Sub")
        dl.addWidget(disc_label)
        self.root.addWidget(disc_box)
        self.root.addStretch(1)
