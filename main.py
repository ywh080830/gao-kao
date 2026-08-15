# -*- coding: utf-8 -*-
"""入口：创建 QApplication、应用主题、打开主窗口。

崩溃兜底：任何启动期异常写入 userdata/startup_error.log（落在 exe 同级，避开 C 盘），
不再像旧版那样静默白屏。
"""
import os
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.panels import userdata_dir


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("高考模拟填报系统")
    theme.apply_theme(app, "学术蓝")
    try:
        win = MainWindow()
        win.show()
        return app.exec()
    except Exception:
        log = os.path.join(userdata_dir(), "startup_error.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
        QMessageBox.critical(None, "启动失败", "程序启动异常，日志见：\n" + log)
        return 1


if __name__ == "__main__":
    sys.exit(main())
