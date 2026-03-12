"""
Logging utilities (local-only friendly).
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger():
    """配置全局日志"""
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format
    )
    
    # 过滤 werkzeug 的 INFO 级别日志（减少噪音）
    # 只保留 WARNING 及以上级别
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.WARNING)
    
    # 过滤 kline 路由的 INFO 级别日志（减少噪音）
    # 只保留 WARNING 及以上级别
    kline_logger = logging.getLogger('app.routes.kline')
    kline_logger.setLevel(logging.WARNING)
    
    # 创建日志目录
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 添加文件处理器
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        Logger 实例
    """
    return logging.getLogger(name)

