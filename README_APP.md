# 高考模拟填报系统（桌面应用）

基于 PySide6 的 Windows 桌面应用，帮助高考生根据分数/位次模拟志愿填报，并提供院校库查询、智能推荐、位次分析等功能。

## 功能
- 9 大模块：概览 / 分数录入 / 智能推荐 / 模拟志愿 / 位次分析 / 院校库 / 数据管理 / 帮助 / 关于
- 院校详情（基本信息 + 历年投档线明细 + 本地生成的校徽图）
- 数据管理：清除已下载数据、修改保存位置、自动同步开关
- 统一错误码 + 日志体系，便于排查
- 启动自动回退到最近有数据的年份，避免空白面板

## 技术栈
- Python 3.13
- PySide6 6.11.1
- PyInstaller 6.22.0（onefile 打包）
- SQLite 本地数据库（云端同步构建）

## 目录结构
    gk_python/
    ├── main.py                 # 入口
    ├── build_qt.py             # 打包脚本
    ├── build/gk_python.spec    # PyInstaller 配置
    ├── app/                    # 应用源码
    │   ├── cloud.py            # 云端数据同步（从本仓库 data/ 拉取）
    │   ├── db.py               # SQLite 数据访问层
    │   ├── recommender.py      # AI 推荐引擎
    │   ├── ui/                 # 界面与面板
    │   └── ...
    ├── test_user_e2e.py        # 全流程端到端测试
    └── test_ux_fixes.py        # 用户体验修复回归测试

## 构建安装包（EXE）
    pip install PySide6==6.11.1 PyInstaller==6.22.0
    python build_qt.py
> 注意：build/gk_python.spec 中的 PROJECT_ROOT 与 ICON_PATH 为当前构建机的绝对路径，
  克隆到其他机器需相应修改。产物默认输出到 build_out6/高考模拟填报系统.exe。

## 下载安装包
最新安装包（EXE）以 GitHub Release 附件形式提供，请在仓库 Releases 页面下载。

## 数据来源
运行时数据（院校库、各省投档线、一分一段表）由应用自动从本仓库的 data/ 目录同步到本地
（userdata/gk_local.db），联网可用、离线回退。

## 许可
MIT。数据来源于公开教育考试院/阳光高考等渠道，仅供研究模拟，请以官方公布为准。
