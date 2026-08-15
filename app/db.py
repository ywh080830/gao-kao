# -*- coding: utf-8 -*-
"""SQLite 数据访问层（内置数据库，本地毫秒级加载，零网络依赖）。

根治旧版「304 个 CSV 散文件 + 云端下载 fallback 链」导致的卡死 / 白屏 / 崩溃：
所有数据在构建期导入 gk.db，运行期仅做 SQLite 查询。
"""
import os
import sys
import sqlite3
from typing import List, Optional

from app.models import AdmissionRecord, RankRow
from app.cloud import local_db_path
from app import log


def db_path() -> Optional[str]:
    """定位数据库：默认使用云端同步生成的本地下载库（userdata/gk_local.db）。

    内置 gk.db 仅作为开发期（未打包运行）的安全回退，打包后的 EXE 不再携带
    gk.db，运行时数据完全来自云端 GitHub（见 DataPanel / 启动自动同步）。
    若无任何可用数据库（云端未下载且非开发环境），返回 None，由上层触发下载。
    """
    lp = local_db_path()
    if lp and os.path.exists(lp):
        try:
            # 轻量校验：能打开且含 admissions 表
            con = sqlite3.connect(lp)
            con.execute("SELECT 1 FROM admissions LIMIT 1")
            con.close()
            return lp
        except Exception as e:
            log.error("DB001", "本地数据库打开/校验失败：%s" % lp, e)
    # 仅开发期回退：打包 EXE 不含 gk.db
    if not getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        gk = os.path.join(base, "app", "data", "gk.db")
        if os.path.exists(gk):
            return gk
    return None


def _init_empty_schema(conn: sqlite3.Connection):
    """为占位内存库创建空表结构，使查询安全返回空结果（云端下载前不崩溃）。"""
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS admissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id TEXT, school_name TEXT, year INTEGER, province TEXT,
        batch TEXT, subject TEXT, major_group TEXT, major TEXT,
        score REAL, rank INTEGER, plan INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rank_tables(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        province TEXT, year INTEGER, subject TEXT, score REAL, rank INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS schools(
        id TEXT, name TEXT, province TEXT, level TEXT, type TEXT,
        category TEXT, tags TEXT)""")
    conn.commit()


def _ensure_indexes(conn: sqlite3.Connection):
    """为高频查询列建索引，消除 17 万行级全表扫描带来的查询延迟。

    仅在库打开后调用一次；索引对后续查询（按省份/科类/年份筛选投档线与位次表）
    收益显著，建索引本身一次性开销可接受。
    """
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_adm_prov ON admissions(province)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_adm_psb ON "
                     "admissions(province, subject, year, batch)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rank_psy ON "
                     "rank_tables(province, year, subject)")
        conn.commit()
    except Exception:
        pass


class DataStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or db_path()
        if self.path and os.path.exists(self.path):
            try:
                self.conn = sqlite3.connect(self.path)
            except Exception as e:
                log.error("DB001", "打开数据库失败：%s" % self.path, e)
                self.path = ":memory:"
                self.conn = sqlite3.connect(":memory:")
                _init_empty_schema(self.conn)
        else:
            # 无可用数据库（待云端下载）：用内存库占位并建空表结构，避免启动崩溃；
            # 下载完成后由 reload() 切换至真实的云端库。
            self.path = ":memory:"
            self.conn = sqlite3.connect(":memory:")
            _init_empty_schema(self.conn)
        self.conn.row_factory = sqlite3.Row
        _ensure_indexes(self.conn)

    # ---- 省份列表 ----
    def list_provinces(self) -> List[str]:
        cur = self.conn.execute("SELECT DISTINCT province FROM admissions ORDER BY province")
        return [r[0] for r in cur.fetchall()]

    # ---- 投档线查询 ----
    def get_admissions(self, province: str, year: Optional[int] = None,
                       subject: Optional[str] = None, batch: Optional[str] = None,
                       keyword: Optional[str] = None) -> List[AdmissionRecord]:
        sql = "SELECT * FROM admissions WHERE province=?"
        args = [province]
        if year is not None:
            sql += " AND year=?"
            args.append(year)
        if subject:
            sql += " AND subject=?"
            args.append(subject)
        if batch:
            sql += " AND batch=?"
            args.append(batch)
        if keyword:
            sql += " AND (school_name LIKE ? OR major LIKE ? OR major_group LIKE ?)"
            like = "%" + keyword + "%"
            args.extend([like, like, like])
        sql += " ORDER BY (score IS NULL), score DESC"
        cur = self.conn.execute(sql, args)
        out = []
        for r in cur.fetchall():
            out.append(AdmissionRecord(
                school_id=r["school_id"], school_name=r["school_name"] or "",
                year=r["year"], province=r["province"], batch=r["batch"],
                subject=r["subject"], major_group=r["major_group"] or "",
                major=r["major"] or "", score=r["score"], rank=r["rank"], plan=r["plan"],
            ))
        return out

    # ---- 院校列表（按省份/年份去重）----
    def distinct_schools(self, province: str, year: Optional[int] = None,
                         keyword: Optional[str] = None) -> List[tuple]:
        sql = ("SELECT DISTINCT school_id, school_name FROM admissions WHERE province=?")
        args = [province]
        if year is not None:
            sql += " AND year=?"
            args.append(year)
        if keyword:
            sql += " AND school_name LIKE ?"
            args.append("%" + keyword + "%")
        sql += " ORDER BY school_name"
        cur = self.conn.execute(sql, args)
        return [(r["school_id"], r["school_name"] or "") for r in cur.fetchall()]

    # ---- 某院校近年投档线 ----
    def school_history(self, school_name: str, province: str) -> List[AdmissionRecord]:
        cur = self.conn.execute(
            "SELECT * FROM admissions WHERE province=? AND school_name=? ORDER BY year DESC, (score IS NULL), score DESC",
            (province, school_name))
        return [AdmissionRecord(
            school_id=r["school_id"], school_name=r["school_name"] or "",
            year=r["year"], province=r["province"], batch=r["batch"],
            subject=r["subject"], major_group=r["major_group"] or "",
            major=r["major"] or "", score=r["score"], rank=r["rank"], plan=r["plan"],
        ) for r in cur.fetchall()]

    # ---- 院校详情（基本信息 + 投档线聚合）----
    def school_detail(self, school_name: str, province: Optional[str] = None) -> dict:
        """汇总某院校的详细信息。

        返回：
          info:       院校属性 dict（来自 schools 表，可能为空 dict）
          admissions: 投档线明细 List[AdmissionRecord]（按年份降序）
          provinces:  该院校出现过的招生省份列表
        """
        info: dict = {}
        try:
            cur = self.conn.execute(
                "SELECT * FROM schools WHERE name=? LIMIT 1", (school_name,))
            r = cur.fetchone()
            if r:
                info = {k: r[k] for k in r.keys()}
        except Exception:
            info = {}

        sql = "SELECT * FROM admissions WHERE school_name=?"
        args: list = [school_name]
        if province:
            sql += " AND province=?"
            args.append(province)
        sql += " ORDER BY year DESC, province, batch, (score IS NULL), score DESC"
        cur = self.conn.execute(sql, args)
        rows = [AdmissionRecord(
            school_id=r["school_id"], school_name=r["school_name"] or "",
            year=r["year"], province=r["province"], batch=r["batch"],
            subject=r["subject"], major_group=r["major_group"] or "",
            major=r["major"] or "", score=r["score"], rank=r["rank"], plan=r["plan"],
        ) for r in cur.fetchall()]
        provinces = sorted({r.province for r in rows if r.province})
        return {"info": info, "admissions": rows, "provinces": provinces}

    # ---- 位次表 ----
    def get_rank_rows(self, province: str, year: int, subject: str) -> List[RankRow]:
        cur = self.conn.execute(
            "SELECT * FROM rank_tables WHERE province=? AND year=? AND subject=? AND rank IS NOT NULL AND score IS NOT NULL ORDER BY rank ASC",
            (province, year, subject))
        return [RankRow(province=r["province"], year=r["year"], subject=r["subject"],
                        score=r["score"], rank=r["rank"]) for r in cur.fetchall()]

    # ---- 统计 ----
    def stats(self) -> dict:
        a = self.conn.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]
        rt = self.conn.execute("SELECT COUNT(*) FROM rank_tables").fetchone()[0]
        sc = self.conn.execute("SELECT COUNT(DISTINCT school_name) FROM admissions").fetchone()[0]
        return {"admissions": a, "rank_rows": rt, "schools": sc}

    def reload(self, path: Optional[str] = None):
        """热切换数据库：关闭旧连接，打开 path 或重新解析 db_path()（用于云端下载完成后切换）。"""
        try:
            self.conn.close()
        except Exception:
            pass
        self.path = path or db_path()
        if self.path and os.path.exists(self.path):
            self.conn = sqlite3.connect(self.path)
        else:
            # 无可用库（云端未下载且非开发环境）：回退内存占位，避免 sqlite3.connect(None) 崩溃
            self.path = ":memory:"
            self.conn = sqlite3.connect(":memory:")
            _init_empty_schema(self.conn)
        self.conn.row_factory = sqlite3.Row
        _ensure_indexes(self.conn)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
