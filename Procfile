# Render/Railway/Heroku 启动文件
# 数据库迁移必须在发布前显式执行并验证；生产 HTTP 请求不运行迁移。
# 依赖和前端产物在构建阶段准备；启动命令与 render.yaml 保持一致。
web: gunicorn -c gunicorn.conf.py run:application
