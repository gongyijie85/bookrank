#!/usr/bin/env python3
"""生成周报"""

import sys
from app import create_app


def generate_weekly_report():
    """生成周报"""
    app = create_app()
    
    with app.app_context():
        try:
            from app.tasks.weekly_report_task import generate_weekly_report as task_generate_report
            
            print("生成周报...")
            
            # 调用任务函数生成周报
            report = task_generate_report()
            
            if report:
                print(f"✅ 成功生成周报: {report.title}")
                print(f"📅 报告日期: {report.report_date}")
                print(f"📊 周期间隔: {report.week_start} 至 {report.week_end}")
                print(f"📝 摘要: {report.summary[:100]}...")
            else:
                print("❌ 生成周报失败或已存在")
                return False
        except Exception as e:
            print(f"❌ 执行失败: {e}")
            return False
    return True


if __name__ == "__main__":
    success = generate_weekly_report()
    sys.exit(0 if success else 1)