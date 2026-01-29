"""
Gunicorn 配置文件
用于生产环境部署
"""

import os
import multiprocessing

# 服务器绑定
bind = "0.0.0.0:" + os.environ.get("PORT", "8000")

# 工作进程数
# 使用 2-4 个 workers（免费套餐通常有内存限制）
workers = int(os.environ.get("WEB_CONCURRENCY", 2))

# 工作进程类型（使用 sync 模式更稳定）
worker_class = "sync"

# 每个 worker 的线程数
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# 超时时间（秒）
timeout = 120

# 保持连接时间（秒）
keepalive = 5

# 最大请求数（防止内存泄漏）
max_requests = 1000
max_requests_jitter = 50

# 日志配置
accesslog = "-"  # 输出到 stdout
errorlog = "-"   # 输出到 stderr
loglevel = "info"

# 进程名称
proc_name = "book-rank-app"

# 预加载应用（节省内存）
preload_app = True

# 优雅重启超时
graceful_timeout = 30
