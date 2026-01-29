"""
应用入口文件 - 生产模式（无调试）
"""

import os
from app import create_app

# 强制使用生产配置
os.environ['FLASK_ENV'] = 'production'

# 创建应用实例
app = create_app('production')

# 为Elastic Beanstalk兼容
application = app

if __name__ == '__main__':
    # 生产服务器配置 - 禁用调试
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 8000)),
        debug=False,
        threaded=True
    )
