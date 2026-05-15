#!/usr/bin/env python3
"""检查数据库中的周报记录"""

import sys
from app import create_app
from app.models.schemas import WeeklyReport


def check_report_date():
    """检查数据库中的周报记录"""
    app = create_app()
    
    with app.app_context():
        try:
            # 查询所有周报记录
            reports = WeeklyReport.query.all()
            
            if reports:
                print("数据库中的周报记录:")
                for report in reports:
                    print(f"ID: {report.id}")
                    print(f"标题: {report.title}")
                    print(f"报告日期: {report.report_date}")
                    print(f"周开始: {report.week_start}")
                    print(f"周结束: {report.week_end}")
                    print(f"摘要: {report.summary[:100]}...")
                    print("---")
            else:
                print("数据库中没有周报记录")
        except Exception as e:
            print(f"执行失败: {e}")
            return False
    return True


if __name__ == "__main__":
    success = check_report_date()
    sys.exit(0 if success else 1)