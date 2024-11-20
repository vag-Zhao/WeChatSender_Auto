import concurrent.futures
from threading import Lock
from typing import Optional
from functools import wraps
from .logger import WxLogger

logger = WxLogger.get_logger()

class ThreadPoolManager:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=10,
                thread_name_prefix="WxHook"
            )
            self.process_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=4
            )
            self.futures = []
            self.initialized = True
            logger.info("线程池管理器已初始化")
    
    def submit_thread(self, fn, *args, **kwargs):
        """提交线程任务"""
        future = self.thread_pool.submit(fn, *args, **kwargs)
        self.futures.append(future)
        return future
    
    def submit_process(self, fn, *args, **kwargs):
        """提交进程任务"""
        future = self.process_pool.submit(fn, *args, **kwargs)
        self.futures.append(future)
        return future
    
    def wait_all(self):
        """等待所有任务完成"""
        concurrent.futures.wait(self.futures)
        self.futures.clear()
    
    def shutdown(self):
        """关闭线程池和进程池"""
        try:
            # 先取消所有未完成的任务
            for future in self.futures:
                if not future.done():
                    future.cancel()
            
            # 等待所有任务完成或被取消
            concurrent.futures.wait(self.futures, timeout=5)
            
            # 关闭线程池
            self.thread_pool.shutdown(wait=False)
            
            # 关闭进程池
            self.process_pool.shutdown(wait=False)
            
            logger.info("线程池管理器已关闭")
        except Exception as e:
            logger.error(f"关闭线程池时出错: {e}")

def async_task(pool_type: str = 'thread'):
    """异步任务装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            pool_manager = ThreadPoolManager()
            if pool_type == 'thread':
                return pool_manager.submit_thread(func, *args, **kwargs)
            elif pool_type == 'process':
                return pool_manager.submit_process(func, *args, **kwargs)
            else:
                raise ValueError(f"不支持的池类型: {pool_type}")
        return wrapper
    return decorator