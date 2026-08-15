# -*- coding: utf-8 -*-
"""全局应用状态（单例），用 PyQt 信号在面板间同步。"""
from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    changed = Signal(str)  # 变更字段名

    def __init__(self):
        super().__init__()
        self._province = "河南"
        self._year = 2026
        self._subject = "物理类"
        self._batch = "本科批"
        self._score = None
        self._rank = None
        self._theme = "学术蓝"
        self._volunteers = []

    # ---- 省份 ----
    @property
    def province(self):
        return self._province

    @province.setter
    def province(self, v):
        if v != self._province:
            self._province = v
            self.changed.emit("province")

    # ---- 年份 ----
    @property
    def year(self):
        return self._year

    @year.setter
    def year(self, v):
        if v != self._year:
            self._year = v
            self.changed.emit("year")

    # ---- 科类 ----
    @property
    def subject(self):
        return self._subject

    @subject.setter
    def subject(self, v):
        if v != self._subject:
            self._subject = v
            self.changed.emit("subject")

    # ---- 批次 ----
    @property
    def batch(self):
        return self._batch

    @batch.setter
    def batch(self, v):
        if v != self._batch:
            self._batch = v
            self.changed.emit("batch")

    # ---- 高考分数 ----
    @property
    def score(self):
        return self._score

    @score.setter
    def score(self, v):
        self._score = v
        self.changed.emit("score")

    # ---- 位次 ----
    @property
    def rank(self):
        return self._rank

    @rank.setter
    def rank(self, v):
        self._rank = v
        self.changed.emit("rank")

    # ---- 主题 ----
    @property
    def theme(self):
        return self._theme

    @theme.setter
    def theme(self, v):
        if v != self._theme:
            self._theme = v
            self.changed.emit("theme")

    # ---- 志愿表 ----
    @property
    def volunteers(self):
        return self._volunteers

    @volunteers.setter
    def volunteers(self, v):
        self._volunteers = v
        self.changed.emit("volunteers")


# 模块级单例
STATE = AppState()
