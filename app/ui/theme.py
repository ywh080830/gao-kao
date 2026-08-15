# -*- coding: utf-8 -*-
"""5 套主题（学术蓝 / 薄荷绿 / 暖阳橙 / 樱粉 / 石墨灰）。

Qt 不支持 CSS 变量，故每套主题生成一份完整 QSS 字符串；切换主题即整体替换样式表。
"""
from app.config import THEME_NAMES

THEMES = {
    "学术蓝": dict(
        bg="#eef3f9", panel="#ffffff", text="#1f2d3d", subtext="#6b7c93",
        primary="#2c5f8a", primary_dark="#1d476b", border="#d4e0ee",
        header_bg="#2c5f8a", header_text="#ffffff", accent="#3b82c4",
        hover="#e3eefb", table_alt="#f3f8fd",
    ),
    "薄荷绿": dict(
        bg="#eaf6f1", panel="#ffffff", text="#1d3a30", subtext="#5f8475",
        primary="#2f8f6b", primary_dark="#1f6a4d", border="#cfe9dd",
        header_bg="#2f8f6b", header_text="#ffffff", accent="#39b08a",
        hover="#e0f3ec", table_alt="#f0f9f5",
    ),
    "暖阳橙": dict(
        bg="#fbf1e8", panel="#ffffff", text="#3a2a1c", subtext="#94765c",
        primary="#d9722e", primary_dark="#b25a1e", border="#f1dcc6",
        header_bg="#d9722e", header_text="#ffffff", accent="#e8914a",
        hover="#fbe9d8", table_alt="#fdf4ec",
    ),
    "樱粉": dict(
        bg="#fbeef4", panel="#ffffff", text="#3a2230", subtext="#946a7e",
        primary="#c85a8a", primary_dark="#a3416c", border="#f3d6e4",
        header_bg="#c85a8a", header_text="#ffffff", accent="#e07ba6",
        hover="#fbe3ee", table_alt="#fdf2f7",
    ),
    "石墨灰": dict(
        bg="#eceef1", panel="#ffffff", text="#252a31", subtext="#6c7480",
        primary="#4a5568", primary_dark="#333c49", border="#d6dbe2",
        header_bg="#4a5568", header_text="#ffffff", accent="#647088",
        hover="#e6e9ee", table_alt="#f3f5f8",
    ),
}


def theme_qss(name: str) -> str:
    t = THEMES.get(name, THEMES["学术蓝"])
    g = t  # 短别名
    return f"""
    QWidget {{
        background: {g['bg']};
        color: {g['text']};
        font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
        font-size: 13px;
    }}
    QFrame#Panel, QWidget#Panel {{
        background: {g['panel']};
    }}
    QLabel#Title {{
        font-size: 20px;
        font-weight: 700;
        color: {g['primary']};
    }}
    QLabel#Sub {{
        color: {g['subtext']};
        font-size: 12px;
    }}
    QLabel#CardValue {{
        font-size: 22px;
        font-weight: 700;
        color: {g['primary']};
    }}
    QPushButton {{
        background: {g['primary']};
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 7px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {g['primary_dark']}; }}
    QPushButton:disabled {{ background: {g['border']}; color: {g['subtext']}; }}
    QPushButton#Ghost {{
        background: transparent;
        color: {g['primary']};
        border: 1px solid {g['border']};
    }}
    QPushButton#Ghost:hover {{ background: {g['hover']}; }}
    QPushButton#Nav {{
        background: transparent;
        color: {g['text']};
        border: none;
        border-radius: 6px;
        text-align: left;
        padding: 10px 14px;
        font-weight: 600;
    }}
    QPushButton#Nav:hover {{ background: {g['hover']}; }}
    QPushButton#NavActive {{
        background: {g['primary']};
        color: #ffffff;
        border: none;
        border-radius: 6px;
        text-align: left;
        padding: 10px 14px;
        font-weight: 700;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background: #ffffff;
        border: 1px solid {g['border']};
        border-radius: 5px;
        padding: 6px 8px;
        color: {g['text']};
    }}
    QComboBox QAbstractItemView {{
        background: #ffffff;
        selection-background-color: {g['hover']};
    }}
    QTableWidget {{
        background: #ffffff;
        gridline-color: {g['border']};
        border: 1px solid {g['border']};
        border-radius: 6px;
        alternate-background-color: {g['table_alt']};
    }}
    QHeaderView::section {{
        background: {g['header_bg']};
        color: {g['header_text']};
        padding: 7px;
        border: none;
        font-weight: 700;
    }}
    QTableWidget::item {{ padding: 5px; }}
    QListWidget {{
        background: #ffffff;
        border: 1px solid {g['border']};
        border-radius: 6px;
    }}
    QListWidget::item {{ padding: 7px; }}
    QListWidget::item:selected {{ background: {g['hover']}; color: {g['text']}; }}
    QGroupBox {{
        border: 1px solid {g['border']};
        border-radius: 8px;
        margin-top: 12px;
        padding: 10px;
        font-weight: 700;
        color: {g['primary']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }}
    QScrollArea {{ border: none; background: {g['panel']}; }}
    QStatusBar {{ background: {g['header_bg']}; color: {g['header_text']}; }}
    """


def apply_theme(app, name: str):
    app.setStyleSheet(theme_qss(name))
