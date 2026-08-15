# -*- coding: utf-8 -*-
"""AI 智能算法引擎（志愿推荐 / 录取概率 / 冲稳保分层）。

保留旧版价值内核：统一录取概率模型(logistic) + 多因子智能匹配分 + 自适应冲稳保分层。
本次重写改为「按校名关键词识别院校层次」（数据无独立 tags 字段）。
"""
import math
from app.models import AdmissionRecord

ENGINE_NAME = "AI 智能算法引擎"
ENGINE_VERSION = "AI-1.0"

WEIGHTS = {"prob": 0.50, "tier": 0.22, "major": 0.13, "stab": 0.15}
PROB_S_BASE = 5.0
PROB_S_MAX_BONUS = 3.0
TIER_SAFE = 0.80
TIER_MATCH = 0.45
TIER_REACH = 0.12


def _prob_rank(ratio):
    if ratio < 0.6:
        return 0.08
    if ratio < 0.7:
        return 0.16
    if ratio < 0.8:
        return 0.30
    if ratio < 0.85:
        return 0.40
    if ratio < 0.92:
        return 0.52
    if ratio < 1.0:
        return 0.64
    if ratio < 1.08:
        return 0.76
    if ratio < 1.15:
        return 0.85
    if ratio < 1.3:
        return 0.92
    return 0.97


def _prob_score(diff):
    if diff < -18:
        return 0.05
    if diff < -10:
        return 0.15
    if diff < 0:
        return 0.30
    if diff < 8:
        return 0.50
    if diff < 18:
        return 0.70
    if diff < 28:
        return 0.85
    return 0.95


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _int(v):
    n = _num(v)
    if n is None:
        return None
    try:
        return int(n)
    except Exception:
        return None


def _record_fields(r):
    if isinstance(r, AdmissionRecord):
        return (r.rank, r.score, r.school_name, r.major, r.major_group,
                r.school_id, r.plan, r.year)
    return (r.get("rank"), r.get("score"), r.get("school_name", ""),
            r.get("major", ""), r.get("major_group", ""), r.get("school_id", ""),
            r.get("plan"), r.get("year"))


def _school_tier(name):
    """按校名关键词识别院校层次 -> 0~1。"""
    if not name:
        return 0.5
    s = str(name)
    if "985" in s or "北京大学" in s or "清华大学" in s:
        return 1.0
    if "211" in s:
        return 0.85
    if "双一流" in s:
        return 0.80
    if "专科" in s or "职业技术" in s or "职业" in s:
        return 0.30
    if "民办" in s or "独立学院" in s:
        return 0.42
    if "大学" in s or "学院" in s:
        return 0.62
    return 0.5


def _match(user_score, user_rank, f, rank_table):
    rr, sc = f[0], f[1]
    if user_score is not None and sc is not None:
        return user_score - sc, "score"
    if rank_table is not None and user_rank is not None and rr is not None:
        try:
            user_eq = rank_table.score_for(user_rank)
            rec_eq = rank_table.score_for(rr) if sc is None else sc
            if user_eq is not None and rec_eq is not None:
                return user_eq - rec_eq, "rank"
        except Exception:
            pass
    if user_rank is not None and rr is not None:
        return rr / user_rank, "ratio"
    return 0.0, "score"


def _probability(gap, mode, plan):
    if mode == "ratio":
        return _prob_rank(gap)
    s = PROB_S_BASE + min(PROB_S_MAX_BONUS, math.log10((plan or 1) + 1))
    return 1.0 / (1.0 + math.exp(-gap / s))


def _tier_of(prob):
    if prob >= TIER_SAFE:
        return "保"
    if prob >= TIER_MATCH:
        return "稳"
    if prob >= TIER_REACH:
        return "冲"
    return None


def _build_hist_index(history):
    idx = {}
    for r in history:
        rr, sc, sname, major, mg, sid, plan, ryear = _record_fields(r)
        if sc is None:
            continue
        idx.setdefault((sid or sname, mg), []).append(sc)
    return idx


def _stability(hist_index, key):
    scores = hist_index.get(key)
    if not scores or len(scores) < 2:
        return 0.55
    m = sum(scores) / len(scores)
    if m == 0:
        return 0.55
    var = sum((x - m) ** 2 for x in scores) / len(scores)
    cv = math.sqrt(var) / m
    return 1.0 / (1.0 + cv)


def _smart_score(prob, tier_score, major_score, stability):
    w = WEIGHTS
    return 100.0 * (w["prob"] * prob + w["tier"] * tier_score
                    + w["major"] * major_score + w["stab"] * stability)


def _reasons(prob, tier, name, kw, stability, mode):
    out = ["录取概率 %d%%" % round(prob * 100)]
    if tier == "冲":
        out.append("冲刺档·搏一搏")
    elif tier == "稳":
        out.append("稳妥档·主力")
    else:
        out.append("保底档·求稳")
    if name:
        blob = str(name)
        for label, token in (("985", "985"), ("211", "211"), ("双一流", "双一流")):
            if token in blob:
                out.append("院校层次：%s" % label)
                break
    if kw:
        out.append("专业匹配：%s" % kw)
    if stability >= 0.85:
        out.append("历年分数稳定")
    elif stability < 0.5:
        out.append("历年波动较大")
    if mode == "ratio":
        out.append("线差估算")
    return out


def recommend(user_rank, user_score, province, subject, year, records,
              top=20, major_keyword="", rank_table=None, history=None):
    """返回 {'冲':[(rec,meta)...], '稳':[...], '保':[...]}。"""
    if history is None:
        history = records
    hist_index = _build_hist_index(history)
    kw = (major_keyword or "").strip().lower()
    buckets = {"冲": [], "稳": [], "保": []}
    seen = set()
    for r in records:
        f = _record_fields(r)
        rr, sc, sname, major, mg, sid, plan, ryear = f
        if kw:
            hay = (str(sname) + str(major) + str(mg)).lower()
            if kw not in hay:
                continue
        dup_key = (sid or sname, mg, sc)
        if dup_key in seen:
            continue
        seen.add(dup_key)
        gap, mode = _match(user_score, user_rank, f, rank_table)
        prob = _probability(gap, mode, plan)
        tier = _tier_of(prob)
        if tier is None:
            continue
        tier_score = _school_tier(sname)
        major_score = 1.0 if (kw and kw in (str(sname) + str(major) + str(mg)).lower()) else 0.5
        stability = _stability(hist_index, (sid or sname, mg))
        smart = _smart_score(prob, tier_score, major_score, stability)
        meta = {
            "prob": round(prob, 4), "gap": round(gap, 3), "mode": mode,
            "smart": round(smart, 1), "tier": tier,
            "reasons": _reasons(prob, tier, sname, kw, stability, mode),
        }
        buckets[tier].append((r, meta))
    for k in buckets:
        buckets[k].sort(key=lambda x: x[1]["smart"], reverse=True)
    return {k: v[:top] for k, v in buckets.items()}


def categorize(volunteer, user_score, user_rank):
    """志愿梯度诊断：冲/稳/保/—。"""
    sc = _num(volunteer.get("score"))
    rr = _int(volunteer.get("rank"))
    if user_score is not None and sc is not None:
        gap, mode = user_score - sc, "score"
    elif user_rank is not None and rr is not None:
        gap, mode = rr / user_rank, "ratio"
    else:
        return "—"
    prob = _probability(gap, mode, None)
    t = _tier_of(prob)
    return t if t else "—"
