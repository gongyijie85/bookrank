"""
Gunicorn 配置文件 - Render 免费版专用
针对 Render 免费版优化（512MB 内存限制）
"""

import os
import logging

# 服务器绑定 - Render 使用 PORT 环境变量，默认为 10000
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# 工作进程数
# Render 免费版 512MB 内存：1 个 worker 最合适
workers = int(os.environ.get("WEB_CONCURRENCY", 1))

# 工作进程类型（使用 sync 模式更稳定）
worker_class = "sync"

# 每个 worker 的线程数
# 减少线程数以降低内存使用（Render 免费版优化）
threads = int(os.environ.get("GUNICORN_THREADS", 1))

# 超时时间（秒）
# Render 免费版响应可能慢，延长超时
timeout = 180

# 保持连接时间（秒）
keepalive = 5

# 最大请求数（防止内存泄漏）
max_requests = 500
max_requests_jitter = 50

# 日志配置
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 日志格式优化（适合 Render 日志查看
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# 进程名称
proc_name = "book-rank-app"

# 预加载应用（节省内存）
preload_app = True

# 优雅重启超时
graceful_timeout = 30

# Worker 启动时的钩子
def post_fork(server, worker):
    """Worker 启动后的处理"""
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    
    # 强制垃圾回收
    import gc
    gc.collect()

# Worker 退出时的钩子
def worker_exit(server, worker):
    """Worker 退出时清理"""
    server.log.info("Worker exiting (pid: %s)", worker.pid)
    
    # 强制垃圾回收
    import gc
    gc.collect()

# Worker 中断时的钩子
def worker_abort(worker):
    """Worker 被中断时处理"""
    worker.log.info("Worker received SIGABRT signal")

# 启动前的钩子
def on_starting(server):
    """服务器启动时"""
    server.log.info("Starting Gunicorn server on Render")
    server.log.info("Workers: %s, Threads per worker: %s", workers, threads)
