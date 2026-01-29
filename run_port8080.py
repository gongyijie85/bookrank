"""
应用入口文件 - 使用8080端口
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
    # 使用8080端口
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=app.config.get('DEBUG', True)
    )
