# -*- coding: utf-8 -*-
"""省份 / 批次 / 科类 / 主题 配置。"""
# 综合改革（3+3）省份
_COMP = {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["综合改革"],
         "volunteer_count": 24, "volunteer_mode": "院校专业组"}
# 新高考（3+1+2）省份
_NEW = {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"],
        "volunteer_count": 40, "volunteer_mode": "院校专业组"}
# 老高考（文理分科）省份
_OLD = {"mode": "old", "batches": ["本科一批", "本科二批", "专科批"], "subjects": ["理工", "文史"],
        "volunteer_count": 12, "volunteer_mode": "院校+专业"}

PROVINCES = {
    "河南":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 48, "volunteer_mode": "院校专业组"},
    "广东":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 45, "volunteer_mode": "院校专业组"},
    "江苏":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 40, "volunteer_mode": "院校专业组"},
    "山东":  {"mode": "new", "batches": ["常规批"], "subjects": ["综合改革"], "volunteer_count": 96, "volunteer_mode": "专业+院校"},
    "四川":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 45, "volunteer_mode": "院校专业组"},
    "浙江":  {"mode": "new", "batches": ["普通类", "体育类", "艺术类"], "subjects": ["综合改革"], "volunteer_count": 80, "volunteer_mode": "专业+院校"},
    "河北":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 96, "volunteer_mode": "专业+院校"},
    "北京":  {"mode": "new", "batches": ["本科普通批", "本科提前批普通A段", "本科提前批普通B段", "本科提前批艺术B段"], "subjects": ["综合改革"], "volunteer_count": 30, "volunteer_mode": "院校专业组"},
    "湖北":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 45, "volunteer_mode": "院校专业组"},
    "湖南":  {"mode": "new", "batches": ["本科批", "专科批"], "subjects": ["物理类", "历史类"], "volunteer_count": 45, "volunteer_mode": "院校专业组"},
    "陕西":  {"mode": "old", "batches": ["本科一批", "本科二批", "专科批"], "subjects": ["理工", "文史"], "volunteer_count": 12, "volunteer_mode": "院校+专业"},
    "上海":  dict(_COMP), "天津": dict(_COMP), "海南": dict(_COMP),
    "重庆":  dict(_NEW), "辽宁": dict(_NEW), "福建": dict(_NEW), "安徽": dict(_NEW),
    "江西":  dict(_NEW), "贵州": dict(_NEW), "广西": dict(_NEW), "甘肃": dict(_NEW),
    "吉林":  dict(_NEW), "黑龙江": dict(_NEW), "内蒙": dict(_NEW), "青海": dict(_NEW),
    "山西":  dict(_OLD), "云南": dict(_OLD), "新疆": dict(_OLD), "西藏": dict(_OLD), "宁夏": dict(_OLD),
}

# 可选年份（最新年份排在首位作为默认）
YEARS = [2026, 2025, 2024, 2023, 2022]

# 5 套主题（名称）
THEME_NAMES = ["学术蓝", "薄荷绿", "暖阳橙", "樱粉", "石墨灰"]


def get_province(name):
    return PROVINCES.get(name)


def default_province():
    return "河南" if "河南" in PROVINCES else next(iter(PROVINCES))
