# -*- coding: utf-8 -*-
"""构建脚本：把 admission/ 与 rank_tables/ 下的 CSV 导入内置 SQLite（gk.db）。

仅在开发期运行一次：
    python app/importer.py
生成 app/data/gk.db，随后由 PyInstaller 作为 datas 打包进 EXE。
"""
import os
import csv
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
ADM_DIR = os.path.join(DATA_DIR, "admission")
RANK_DIR = os.path.join(DATA_DIR, "rank_tables")
DB_PATH = os.path.join(DATA_DIR, "gk.db")


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


def build():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE admissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id TEXT, school_name TEXT, year INTEGER, province TEXT,
        batch TEXT, subject TEXT, major_group TEXT, major TEXT,
        score REAL, rank INTEGER, plan INTEGER)""")
    c.execute("""CREATE TABLE rank_tables(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        province TEXT, year INTEGER, subject TEXT, score REAL, rank INTEGER)""")

    adm_files = sorted(os.listdir(ADM_DIR)) if os.path.isdir(ADM_DIR) else []
    a_count = 0
    for fn in adm_files:
        if not fn.endswith(".csv"):
            continue
        with open(os.path.join(ADM_DIR, fn), encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                c.execute(
                    "INSERT INTO admissions(school_id,school_name,year,province,batch,subject,major_group,major,score,rank,plan) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (row.get("school_id") or None, row.get("school_name") or None,
                     _int(row.get("year")), row.get("province") or None,
                     row.get("batch") or None, row.get("subject") or None,
                     row.get("major_group") or None, row.get("major") or None,
                     _num(row.get("score")), _int(row.get("rank")),
                     _int(row.get("plan"))))
                a_count += 1

    rank_files = sorted(os.listdir(RANK_DIR)) if os.path.isdir(RANK_DIR) else []
    r_count = 0
    for fn in rank_files:
        if not fn.endswith(".csv"):
            continue
        with open(os.path.join(RANK_DIR, fn), encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                c.execute(
                    "INSERT INTO rank_tables(province,year,subject,score,rank) VALUES(?,?,?,?,?)",
                    (row.get("province") or None, _int(row.get("year")),
                     row.get("subject") or None, _num(row.get("score")),
                     _int(row.get("rank"))))
                r_count += 1

    c.execute("CREATE INDEX ix_adm ON admissions(province,year,subject,batch)")
    c.execute("CREATE INDEX ix_rank ON rank_tables(province,year,subject)")

    # 院校库（可选：data/schools.csv 存在才导入，与云端数据源保持一致）
    s_count = 0
    schools_path = os.path.join(DATA_DIR, "schools.csv")
    if os.path.exists(schools_path):
        c.execute("""CREATE TABLE schools(
            id TEXT, name TEXT, province TEXT, level TEXT, type TEXT,
            category TEXT, tags TEXT)""")
        with open(schools_path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                c.execute(
                    "INSERT INTO schools(id,name,province,level,type,category,tags) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (row.get("id"), row.get("name"), row.get("province"),
                     row.get("level"), row.get("type"), row.get("category"),
                     row.get("tags")))
                s_count += 1

    conn.commit()
    conn.close()
    print("import done: admissions=%d rank_rows=%d schools=%d -> %s"
          % (a_count, r_count, s_count, DB_PATH))


if __name__ == "__main__":
    build()
