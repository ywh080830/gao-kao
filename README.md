# 高考录取数据数据集 (Gaokao Admission Data)

本数据集为「高考模拟填报系统」提供云端数据源，支持客户端按省份懒加载。

## 文件结构
- `data/schools.csv`：全国院校库（2603 所）
- `data/admission/<省份>.csv`：各省院校投档线（共 161790 条，覆盖 30 省）
- `data/rank_tables/<省份>.csv`：各省一分一段表（共 81556 条）

## 字段说明
### admission/<省份>.csv
school_id, school_name, year, province, batch, subject, major_group, major, score, rank, ...

### rank_tables/<省份>.csv
province, year, subject, score, rank

### schools.csv
id, name, province, level, type, category, tags

## 许可
MIT —— 数据来源于公开教育考试院/阳光高考等渠道，仅供研究模拟，请以官方公布为准。

## 生成
由 `tools/split_for_hf.py` 自动拆分生成。
