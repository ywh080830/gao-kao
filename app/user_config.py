# -*- coding: utf-8 -*-
"""用户可配置项（保存位置、自动同步等），持久化到 exe 同级 userdata/user_config.json。

设计要点：
- 配置文件**固定**存放在 exe 同级 userdata（与 data_dir 分离），这样即使把数据保存位置
  改到其它盘，配置本身仍能被稳定找到，避免「找不到配置」的死循环。
- data_dir 才是真正存放 gk_local.db / volunteers.json / cloud/ 的位置，默认仍是 exe 同级
  userdata；用户可在「数据管理」里改成任意可写目录（如 D:/高考数据）。
- 带进程内缓存，set 后立即可见（配合 reload 即可近似即时生效）。
"""
import os
import sys
import json

_CACHE = {}


def _default_data_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "userdata")


def _config_path() -> str:
    d = _default_data_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "user_config.json")


def get_all() -> dict:
    p = _config_path()
    if p in _CACHE:
        return _CACHE[p]
    cfg = {"data_dir": "", "auto_sync": True}
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            # 配置损坏：恢复默认，不阻断启动
            from app import log
            log.error("CF001", "用户配置读取失败，已恢复默认", None)
    _CACHE[p] = cfg
    return cfg


def get_data_dir() -> str:
    d = get_all().get("data_dir", "")
    if d and os.path.isdir(d):
        return d
    return _default_data_dir()


def set_data_dir(d: str):
    d = (d or "").strip()
    get_all()["data_dir"] = d
    _save()


def get_auto_sync() -> bool:
    return bool(get_all().get("auto_sync", True))


def set_auto_sync(v: bool):
    get_all()["auto_sync"] = bool(v)
    _save()


def _save():
    p = _config_path()
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(get_all(), fh, ensure_ascii=False, indent=2)
    except Exception:
        from app import log
        log.error("IO001", "保存用户配置失败：%s" % p, None)
