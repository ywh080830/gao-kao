# -*- coding: utf-8 -*-
"""云端数据源同步：从 GitHub(ywh080830/gao-kao) 拉取最新高考录取数据到本地使用。

设计要点：
- 数据源为公开仓库，客户端依据 version.json 做完整性校验（每文件 sha256）。
- 下载落盘到 userdata/cloud/（exe 同级，可写），并据 CSV 构建本地 SQLite（userdata/gk_local.db）。
- 应用启动后优先使用本地库；下载完成后由 UI 触发 DataStore.reload 切换。
- 纯标准库实现（urllib / sqlite3 / hashlib），无第三方依赖，打包后零额外体积。

如需更换数据源（如镜像），仅需修改 REPO_RAW_BASE。
"""
import os
import sys
import csv
import json
import hashlib
import sqlite3
import threading
import urllib.request
from urllib.parse import quote
from typing import Optional, Callable, Dict, Tuple

from app import user_config, log, errors

# GitHub 公开数据源（raw 根）。raw.githubusercontent 在部分网络下偏慢，可替换为其它镜像根。
REPO_RAW_BASE = "https://raw.githubusercontent.com/ywh080830/gao-kao/main/"
# jsDelivr 镜像（国内通常比 raw.githubusercontent.com 更易到达，作为主源自动回退）
MIRROR_BASE = "https://cdn.jsdelivr.net/gh/ywh080830/gao-kao/"
# 数据源优先级：主源取最新数据；主源不可达（超时/被墙）时自动切换镜像，提升国内成功率
DATA_SOURCES = [REPO_RAW_BASE, MIRROR_BASE]
VERSION_FILE = "version.json"
USER_AGENT = "GKSim-DataSync/1.0 (+local-use)"

# 下载互斥锁：自动同步线程与手动下载按钮共用，避免两者并发写同一
# gk_local.db / cloud/ 目录导致数据库损坏（并发写 SQLite 文件会损坏）。
_downloading = False
_download_lock = threading.Lock()


def is_downloading() -> bool:
    """是否正在下载（自动同步或手动下载任一进行中）。"""
    with _download_lock:
        return _downloading


def set_downloading(v: bool):
    global _downloading
    with _download_lock:
        _downloading = bool(v)


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
def _userdata_dir() -> str:
    """userdata 目录：跟随用户配置的 data_dir（默认 exe 同级 userdata，可在「数据管理」修改）。"""
    d = user_config.get_data_dir()
    os.makedirs(d, exist_ok=True)
    return d


def cloud_dir() -> str:
    """下载缓存目录（CSV 落盘处）。"""
    d = os.path.join(_userdata_dir(), "cloud")
    os.makedirs(d, exist_ok=True)
    return d


def local_db_path() -> str:
    """本地下载库（优先于内置 gk.db 使用）。"""
    return os.path.join(_userdata_dir(), "gk_local.db")


def meta_path() -> str:
    return os.path.join(cloud_dir(), "meta.json")


# --------------------------------------------------------------------------- #
# 网络
# --------------------------------------------------------------------------- #
def _http_get(rel_path: str, timeout: int = 60, expected_sha: Optional[str] = None) -> bytes:
    """按相对仓库根的路径下载（rel_path 如 "version.json" / "data/admission/青海.csv"）。

    关键修复：
    - 用 urllib.parse.quote 对路径做百分号编码，否则含中文文件名（上海.csv 等）
      的 URL 会让 urllib 在连接前抛 UnicodeEncodeError，导致整批下载失败。
    - 自动遍历多个数据源，主源不可达时回退镜像（提升国内成功率）。
    - 传入 expected_sha 时校验完整性，校验不通过自动换源重试（应对镜像缓存滞后）。
      注意：jsDelivr 路径不要带 @版本（@main 会返回 400），留空走默认分支即可。
    """
    last_err = None
    for base in DATA_SOURCES:
        url = quote(base + rel_path, safe=":/")
        for _ in range(2):  # 每源轻量重试 1 次，应对偶发断开
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                if expected_sha:
                    got = hashlib.sha256(data).hexdigest().lower()
                    if got != expected_sha.lower():
                        last_err = RuntimeError("sha256 校验不一致(%s)" % rel_path)
                        break  # 换下一源重试
                return data
            except Exception as e:  # noqa: BLE001
                last_err = e
    raise last_err or RuntimeError("网络请求失败")


def fetch_version(timeout: int = 30) -> Optional[dict]:
    """拉取远端 version.json，失败返回 None。"""
    try:
        data = _http_get(VERSION_FILE, timeout)
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def local_meta() -> Optional[dict]:
    p = meta_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def local_version() -> Optional[str]:
    m = local_meta()
    return m.get("generated") if m else None


def need_update(timeout: int = 15) -> Tuple[bool, Optional[str], Optional[str]]:
    """返回 (是否有更新, 云端版本, 本地版本)。启动检查用较短超时，避免离线空等。"""
    lv = local_version()
    rv = fetch_version(timeout)
    rv_gen = rv.get("generated") if rv else None
    if rv_gen is None:
        return (False, None, lv)
    if lv is None:
        return (True, rv_gen, None)
    return (rv_gen > lv, rv_gen, lv)


def total_bytes(ver: Optional[dict] = None) -> int:
    if ver is None:
        ver = fetch_version()
    if not ver:
        return 0
    return sum(f.get("bytes", 0) for f in ver.get("files", {}).values())


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# 类型转换（与 importer.py 保持一致）
# --------------------------------------------------------------------------- #
def _num(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _int(v):
    n = _num(v)
    if n is None:
        return None
    return int(n)


# --------------------------------------------------------------------------- #
# 下载 + 建库
# --------------------------------------------------------------------------- #
def _fail(code: str, detail: str) -> dict:
    """统一构造带错误码的失败返回，并记录到日志。"""
    log.error(code, detail, None)
    return {"ok": False, "error": errors.fmt(code, detail),
            "admissions": 0, "rank_rows": 0, "schools": 0, "version": ""}


def download_all(progress: Optional[Callable[[int, int, str, str], None]] = None,
                 timeout: int = 60) -> dict:
    """下载 version.json 中列出的全部文件到 cloud_dir 并校验 sha256，随后构建本地 gk_local.db。

    progress(idx, total, name, status_text)
    返回 {"ok": bool, "error": str, "admissions": int, "rank_rows": int, "schools": int, "version": str}
    """
    ver = fetch_version(timeout)
    if not ver:
        return _fail("DL003", "无法获取 version.json（请检查网络或数据源地址）")
    files = ver.get("files", {})
    total = len(files)
    if total == 0:
        return _fail("DL003", "数据源未返回任何文件清单")

    cdir = cloud_dir()

    # 1) 逐个下载 + 校验
    idx = 0
    for rel, meta in files.items():
        idx += 1
        name = os.path.basename(rel)
        try:
            if progress:
                progress(idx, total, name, "下载中…")
            expect = meta.get("sha256")
            # version.json 的 files 键相对 data/ 目录（真实仓库结构：
            # data/admission/<省>.csv、data/rank_tables/<省>.csv、data/schools.csv），
            # 因此下载 URL 必须加 data/ 前缀，否则全部 404；sha 校验在 _http_get 内完成。
            raw = _http_get("data/" + rel, timeout, expect)
            dst = os.path.join(cdir, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(raw)
            if expect:
                got = _sha256_file(dst)
                if got.lower() != expect.lower():
                    return _fail("DL002", "校验失败：%s（期望 %s 实得 %s）"
                                 % (name, expect[:8], got[:8]))
        except Exception as e:  # noqa: BLE001
            return _fail("DL001", "下载失败：%s（%s）" % (name, e))

    # 2) 构建本地 DB（放在最后，避免中途中断留下半截库）
    try:
        if progress:
            progress(total, total, "gk_local.db", "构建本地数据库…")
        stats = _build_local_db(cdir)
    except Exception as e:  # noqa: BLE001
        return _fail("DB001", "构建本地库失败：%s" % e)

    # 3) 写 meta（记录已下载版本与每文件 sha，供增量判断）
    try:
        with open(meta_path(), "w", encoding="utf-8") as fh:
            json.dump({
                "generated": ver.get("generated"),
                "files": {k: (v.get("sha256") if isinstance(v, dict) else v)
                          for k, v in files.items()},
            }, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {"ok": True, "error": "", "version": ver.get("generated"), **stats}


def _build_local_db(cdir: str) -> dict:
    dbp = local_db_path()
    if os.path.exists(dbp):
        os.remove(dbp)
    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    c.execute("""CREATE TABLE admissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id TEXT, school_name TEXT, year INTEGER, province TEXT,
        batch TEXT, subject TEXT, major_group TEXT, major TEXT,
        score REAL, rank INTEGER, plan INTEGER)""")
    c.execute("""CREATE TABLE rank_tables(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        province TEXT, year INTEGER, subject TEXT, score REAL, rank INTEGER)""")
    c.execute("""CREATE TABLE schools(
        id TEXT, name TEXT, province TEXT, city TEXT, level TEXT, type TEXT,
        category TEXT, tags TEXT, department TEXT)""")

    a_count = r_count = s_count = 0

    # 投档线
    adm_dir = os.path.join(cdir, "admission")
    if os.path.isdir(adm_dir):
        for fn in sorted(os.listdir(adm_dir)):
            if not fn.endswith(".csv"):
                continue
            with open(os.path.join(adm_dir, fn), encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    c.execute(
                        "INSERT INTO admissions"
                        "(school_id,school_name,year,province,batch,subject,major_group,major,score,rank,plan) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (row.get("school_id") or None, row.get("school_name") or None,
                         _int(row.get("year")), row.get("province") or None,
                         row.get("batch") or None, row.get("subject") or None,
                         row.get("major_group") or None, row.get("major") or None,
                         _num(row.get("score")), _int(row.get("rank")),
                         _int(row.get("plan"))))
                    a_count += 1

    # 一分一段表
    rank_dir = os.path.join(cdir, "rank_tables")
    if os.path.isdir(rank_dir):
        for fn in sorted(os.listdir(rank_dir)):
            if not fn.endswith(".csv"):
                continue
            with open(os.path.join(rank_dir, fn), encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    c.execute(
                        "INSERT INTO rank_tables(province,year,subject,score,rank) VALUES(?,?,?,?,?)",
                        (row.get("province") or None, _int(row.get("year")),
                         row.get("subject") or None, _num(row.get("score")),
                         _int(row.get("rank"))))
                    r_count += 1

    # 院校库（可选，存在则导入）
    sp = os.path.join(cdir, "schools.csv")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                c.execute(
                    "INSERT INTO schools(id,name,province,city,level,type,category,tags,department) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (row.get("id"), row.get("name"), row.get("province"),
                     row.get("city"), row.get("level"), row.get("type"),
                     row.get("category"), row.get("tags"), row.get("department")))
                s_count += 1

    c.execute("CREATE INDEX ix_adm ON admissions(province,year,subject,batch)")
    c.execute("CREATE INDEX ix_rank ON rank_tables(province,year,subject)")
    conn.commit()
    conn.close()
    return {"admissions": a_count, "rank_rows": r_count, "schools": s_count}
