# Render/Railway/Heroku 启动文件
# 注意：数据库初始化由应用启动后的惰性迁移逻辑处理，避免全新库先执行历史索引迁移失败。
# 优化：增加内存监控和启动参数
web: pip install -r requirements-prod.txt && python build.py && gunicorn -c gunicorn.conf.py --preload run:application
