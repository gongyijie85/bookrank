#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
用于部署时自动创建数据库表
"""

import os
from app import create_app
from app.models import db

def init_database():
    """初始化数据库"""
    # 使用生产环境配置
    config_name = os.environ.get('FLASK_ENV', 'production')
    app = create_app(config_name)
    
    with app.app_context():
        print(f"正在初始化数据库...")
        print(f"数据库URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        # 创建所有表
        db.create_all()
        
        print("数据库表创建成功！")

if __name__ == '__main__':
    init_database()
