#!/usr/bin/env python3
"""
添加缺失的中文字段到book_metadata表
"""
import sys
from app import create_app
from app.models.database import db
from sqlalchemy import text

def add_chinese_fields():
    """添加中文字段到book_metadata表"""
    app = create_app()
    
    with app.app_context():
        try:
            # 检查book_metadata表的列
            result = db.session.execute(text('PRAGMA table_info(book_metadata)'))
            columns = [row[1] for row in result]
            
            print(f'当前book_metadata表字段: {columns}')
            
            # 定义需要添加的字段
            fields_to_add = {
                'title_zh': 'TEXT',
                'description_zh': 'TEXT',
                'details_zh': 'TEXT',
                'translated_at': 'DATETIME'
            }
            
            # 只添加不存在的字段
            for field_name, field_type in fields_to_add.items():
                if field_name not in columns:
                    print(f'添加字段: {field_name}')
                    db.session.execute(text(f'ALTER TABLE book_metadata ADD COLUMN {field_name} {field_type}'))
                else:
                    print(f'字段已存在: {field_name}')
            
            db.session.commit()
            print('✅ 成功添加中文字段到book_metadata表')
            return True
        except Exception as e:
            print(f'❌ 添加字段失败: {e}')
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = add_chinese_fields()
    sys.exit(0 if success else 1)
