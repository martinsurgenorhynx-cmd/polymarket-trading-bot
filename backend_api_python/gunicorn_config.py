"""
Gunicorn 配置文件（生产环境）
"""
import multiprocessing

# 服务器 socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker 进程
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 600  # 10 minutes for long-running backtests
keepalive = 5

# 日志
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程命名
proc_name = "quantdinger_python_api"

# 服务器机制
daemon = False
pidfile = "logs/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL（如果需要）
# keyfile = None
# certfile = None

