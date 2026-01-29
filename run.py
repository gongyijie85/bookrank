"""
应用入口文件

用法:
    开发环境: python run.py
    生产环境: gunicorn -w 4 -b 0.0.0.0:8000 run:application
"""

import os
from app import create_app

# 获取环境配置
config_name = os.environ.get('FLASK_ENV', 'development')

# 创建应用实例
app = create_app(config_name)

# 为Elastic Beanstalk兼容
application = app

if __name__ == '__main__':
    # 开发服务器配置
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 8000)),
        debug=app.config.get('DEBUG', True)
    )
