"""周报任务辅助函数

将周报生成中的"计算期望周区间"逻辑独立出来，供以下场景共用：
- 定时任务生成周报（app/tasks/weekly_report_task.py）
- 应用层自愈检测缺失周报（app/services/weekly_report_service.py::get_or_trigger_current_week_report）
- 轮询端点判断 current week 是否存在（app/routes/main.py::weekly_report_status）
"""

import datetime


def compute_expected_week_range(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """根据当天日期计算"应当存在"的周报区间。

    业务规则（与 v0.9.46 之前 weekly_report_task.py 保持一致）：
    - 周一/二/三（weekday 0/1/2）→ 期望"上周"的周报（上周一到上周日）
        说明：NYT 周三发布新榜，工作日 1-2 拿到数据比较保险，故取上周完整数据
    - 周四/五/六/日（weekday 3/4/5/6）→ 期望"本周"的周报（本周一到本周日）
        说明：本周数据已有，等本周日汇总

    Args:
        today: 当天日期

    Returns:
        (week_start, week_end) 元组，均为 date 对象
    """
    current_monday = today - datetime.timedelta(days=today.weekday())

    if today.weekday() <= 2:
        last_monday = current_monday - datetime.timedelta(days=7)
        last_sunday = current_monday - datetime.timedelta(days=1)
        return last_monday, last_sunday

    week_start = current_monday
    week_end = current_monday + datetime.timedelta(days=6)
    return week_start, week_end
