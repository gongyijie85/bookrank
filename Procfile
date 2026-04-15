# Render/Railway/Heroku 启动文件
# 注意：首次部署时自动运行数据库迁移
# 优化：增加内存监控和启动参数
web: flask db upgrade && gunicorn -c gunicorn.conf.py --preload run:application
