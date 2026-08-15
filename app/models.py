# -*- coding: utf-8 -*-
"""数据模型（纯数据结构，无 IO 依赖）。"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class AdmissionRecord:
    school_id: Optional[str] = None
    school_name: str = ""
    year: Optional[int] = None
    province: str = ""
    batch: str = ""
    subject: str = ""
    major_group: str = ""
    major: str = ""
    score: Optional[float] = None
    rank: Optional[int] = None
    plan: Optional[int] = None


@dataclass
class RankRow:
    province: str = ""
    year: Optional[int] = None
    subject: str = ""
    score: Optional[float] = None
    rank: Optional[int] = None


@dataclass
class Volunteer:
    school: str = ""
    major_group: str = ""
    score: Optional[float] = None
    rank: Optional[int] = None
    batch: str = ""
    priority: int = 0
    note: str = ""

    def to_dict(self):
        return {
            "school": self.school, "major_group": self.major_group,
            "score": self.score, "rank": self.rank, "batch": self.batch,
            "priority": self.priority, "note": self.note,
        }

    @staticmethod
    def from_dict(d):
        return Volunteer(
            school=d.get("school", ""), major_group=d.get("major_group", ""),
            score=d.get("score"), rank=d.get("rank"), batch=d.get("batch", ""),
            priority=d.get("priority", 0), note=d.get("note", ""),
        )
