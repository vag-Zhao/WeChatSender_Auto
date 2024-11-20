import os
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional

class WxLogger:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not WxLogger._initialized:
            self.setup_logger()
            WxLogger._initialized = True
    
    def setup_logger(self):
        """设置日志配置"""
        # 创建日志目录
        log_dir = Path(__file__).parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # 生成日志文件名
        current_date = datetime.now().strftime('%Y%m%d')
        log_file = log_dir / f'wxhook_{current_date}.log'
        
        # 创建logger
        self.logger = logging.getLogger('wxhook')
        
        # 如果logger已经有处理器，说明已经初始化过，直接返回
        if self.logger.handlers:
            return
            
        self.logger.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 添加按时间轮转的文件处理器
        time_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        time_handler.setFormatter(formatter)
        self.logger.addHandler(time_handler)
        
        # 添加按大小轮转的文件处理器
        size_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        size_handler.setFormatter(formatter)
        self.logger.addHandler(size_handler)
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 避免日志向上层传播
        self.logger.propagate = False
    
    @classmethod
    def get_logger(cls):
        """获取logger实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance.logger
    
    def get_log_file(self) -> Path:
        """获取当前日志文件路径"""
        log_dir = Path(__file__).parent.parent / 'logs'
        current_date = datetime.now().strftime('%Y%m%d')
        return log_dir / f'wxhook_{current_date}.log'
    
    def clean_old_logs(self, days: int = 30):
        """清理指定天数之前的日志文件"""
        try:
            log_dir = Path(__file__).parent.parent / 'logs'
            current_time = datetime.now()
            
            for log_file in log_dir.glob('wxhook_*.log*'):
                try:
                    # 获取文件的修改时间
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    # 如果文件超过指定天数，则删除
                    if (current_time - file_time).days > days:
                        log_file.unlink()
                        self.logger.info(f"已删除旧日志文件: {log_file}")
                except Exception as e:
                    self.logger.error(f"删除日志文件失败: {log_file}", exc_info=e)
        except Exception as e:
            self.logger.error("清理旧日志文件时出错", exc_info=e)

    def set_log_level(self, level: str):
        """设置日志级别"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        if level.upper() in level_map:
            self.logger.setLevel(level_map[level.upper()])
            self.logger.info(f"日志级别已设置为: {level}")
        else:
            self.logger.warning(f"无效的日志级别: {level}")

    def add_file_handler(self, filename: str, 
                        max_bytes: int = 10*1024*1024,
                        backup_count: int = 5):
        """添加额外的文件处理器"""
        try:
            handler = RotatingFileHandler(
                filename,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.info(f"已添加文件处理器: {filename}")
        except Exception as e:
            self.logger.error(f"添加文件处理器失败: {filename}", exc_info=e)

    def remove_all_handlers(self):
        """移除所有日志处理器"""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)

    def __del__(self):
        """析构函数，确保处理器正确关闭"""
        if hasattr(self, 'logger'):
            for handler in self.logger.handlers[:]:
                handler.close()
