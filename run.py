"""
应用入口文件

用法:
    开发环境: python run.py
    生产环境: gunicorn -c gunicorn.conf.py app:app
"""

import os
from app import create_app, app

if __name__ == '__main__':
    # 开发服务器配置
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 8000)),
        debug=app.config.get('DEBUG', True)
    )
