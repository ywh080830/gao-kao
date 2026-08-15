# -*- coding: utf-8 -*-
"""位次表：位次 <-> 等效分 线性插值。"""
from typing import List, Optional

from app.models import RankRow


class RankTable:
    def __init__(self, rows: List[RankRow]):
        self.rows = sorted([r for r in rows if r.rank is not None and r.score is not None],
                           key=lambda r: r.rank)

    def empty(self) -> bool:
        return len(self.rows) == 0

    def score_for(self, rank):
        """位次 -> 等效分（线性插值）。rank 越大数据越小。"""
        if rank is None or not self.rows:
            return None
        rows = self.rows
        if rank <= rows[0].rank:
            return rows[0].score
        if rank >= rows[-1].rank:
            return rows[-1].score
        for i in range(1, len(rows)):
            if rows[i].rank >= rank:
                lo, hi = rows[i - 1], rows[i]
                if lo.rank == hi.rank:
                    return hi.score
                t = (rank - lo.rank) / (hi.rank - lo.rank)
                return lo.score + t * (hi.score - lo.score)
        return None

    def rank_for(self, score):
        """分 -> 位次（反向插值）。"""
        if score is None or not self.rows:
            return None
        rows = self.rows
        if score >= rows[0].score:
            return rows[0].rank
        if score <= rows[-1].score:
            return rows[-1].rank
        for i in range(1, len(rows)):
            if rows[i].score <= score:
                hi, lo = rows[i - 1], rows[i]
                if hi.score == lo.score:
                    return lo.rank
                t = (score - hi.score) / (lo.score - hi.score)
                return hi.rank + t * (lo.rank - hi.rank)
        return None
