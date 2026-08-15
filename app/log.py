# -*- coding: utf-8 -*-
"""应用日志：写入「保存目录 / userdata / app.log」。

设计要点：
- 纯标准库 logging，零额外依赖。
- 日志目录跟随用户配置的 data_dir（见 app.user_config），默认 exe 同级 userdata。
- 提供 error(code, detail, exc) 便捷方法：自动带上错误码（见 app.errors）与异常堆栈，
  便于在帮助页 / 日志中按错误码检索。
- 仅记录到文件，不在 UI 直接打印大段堆栈；UI 仍用精简的带码提示（errors.fmt）。
"""
import os
import sys
import logging
import traceback

_logger = None


def _log_dir() -> str:
    """日志目录：优先用户配置的 data_dir，否则 exe 同级 userdata。"""
    try:
        from app import user_config
        d = user_config.get_data_dir()
    except Exception:
        d = None
    if not d or not os.path.isdir(d):
        if getattr(sys, "frozen", False):
            d = os.path.dirname(sys.executable)
        else:
            d = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(d, "userdata")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("gk_sim")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        path = os.path.join(_log_dir(), "app.log")
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
    except Exception:
        # 日志不可用绝不应影响主流程
        pass
    _logger = logger
    return logger


def info(msg: str):
    get_logger().info(msg)


def warning(msg: str):
    get_logger().warning(msg)


def error(code: str, detail: str = "", exc: BaseException = None):
    """记录一条带错误码的错误。exc 提供时一并写入堆栈。"""
    msg = "[%s] %s" % (code, detail) if detail else "[%s]" % code
    if exc is not None:
        try:
            stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            msg += "\n" + stack
        except Exception:
            msg += "\n" + str(exc)
    if exc is not None:
        get_logger().error(msg, exc_info=False)
    else:
        get_logger().error(msg)


def log_path() -> str:
    return os.path.join(_log_dir(), "app.log")
