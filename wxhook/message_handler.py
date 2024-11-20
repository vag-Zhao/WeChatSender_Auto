import time
import json
import datetime
import threading
from pathlib import Path
from typing import List, Dict, Tuple
import concurrent.futures
from threading import Timer
from .logger import WxLogger
from .thread_pool import async_task

logger = WxLogger.get_logger()

class ScheduledTask:
    """定时任务结构"""
    def __init__(self, id: str, scheduled_time: datetime.datetime, callback, *args, **kwargs):
        self.id = id
        self.scheduled_time = scheduled_time
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.timer = None
        self.status = 'pending'  # pending/running/completed/failed
        
    def start(self):
        """启动定时任务"""
        if self.status != 'pending':
            return
            
        delay = (self.scheduled_time - datetime.datetime.now()).total_seconds()
        if delay < 0:
            logger.error(f"任务 {self.id} 的计划时间已过")
            self.status = 'failed'
            return
            
        self.timer = Timer(delay, self._execute)
        self.timer.start()
        self.status = 'running'
        logger.info(f"任务 {self.id} 已启动，将在 {self.scheduled_time} 执行")
        
    def _execute(self):
        """执行任务"""
        try:
            result = self.callback(*self.args, **self.kwargs)
            self.status = 'completed'
            logger.info(f"任务 {self.id} 执行完成")
            return result
        except Exception as e:
            self.status = 'failed'
            logger.error(f"任务 {self.id} 执行失败: {e}")
            raise
            
    def cancel(self):
        """取消任务"""
        if self.timer:
            self.timer.cancel()
            self.status = 'cancelled'
            logger.info(f"任务 {self.id} 已取消")

class MessageHandler:
    _task_counter = 0
    _tasks = {}  # 静态类属性
    _lock = threading.Lock()  # 线程锁

    @classmethod
    def _generate_task_id(cls) -> str:
        """生成唯一任务ID"""
        with cls._lock:
            cls._task_counter += 1
            return f"task_{cls._task_counter}"

    @staticmethod
    def load_message_box() -> List[Dict]:
        """加载messageBox.json中的消息配置"""
        try:
            json_path = Path(__file__).parent / "messageBox.json"
            if not json_path.exists():
                logger.warning(f"消息配置文件不存在: {json_path}")
                return []
                
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, dict) or 'messages' not in data:
                logger.error("消息配置文件格式错误")
                return []
                
            return data['messages']
        except Exception as e:
            logger.error(f"加载消息配置文件失败: {e}")
            return []

    @staticmethod
    def group_messages_by_time(messages: List[Dict]) -> Dict[str, Dict[str, str]]:
        """将消息按发送时间分组"""
        time_groups = {}
        for msg in messages:
            time_str = msg.get('time', '')
            if not time_str:
                continue
                
            if time_str not in time_groups:
                time_groups[time_str] = {}
                
            time_groups[time_str][msg['wxid']] = msg['message']
        
        return time_groups

    @staticmethod
    def send_message_with_retry(bot, wxid: str, message: str, max_retries: int = 3) -> bool:
        """带重试的消息发送"""
        if bot is None:
            logger.error("Bot未初始化，无法发送消息")
            return False
            
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试发送消息 (第{attempt + 1}次)")
                logger.info(f"目标: {wxid}")
                logger.info(f"内容: {message}")
                
                response = bot.send_text(wxid, message)
                logger.info(f"发送结果: {response}")
                
                if response.code == 1:
                    logger.info("消息发送成功")
                    return True
                else:
                    logger.warning(f"发送失败，错误码: {response.code}")
                    
            except AttributeError:
                logger.error("Bot实例无效或未正确初始化")
                return False
            except Exception as e:
                logger.error("发送出错", exc_info=e)
            
            if attempt < max_retries - 1:
                logger.info("等待2秒后重试...")
                time.sleep(2)
        
        return False

    @staticmethod
    @async_task(pool_type='thread')
    def send_messages_to_multiple(bot, messages_dict: dict) -> Tuple[int, int]:
        """并行发送消息给多个用户"""
        success_count = 0
        fail_count = 0
        
        def send_single_message(wxid: str, message: str):
            nonlocal success_count, fail_count
            if MessageHandler.send_message_with_retry(bot, wxid, message):
                success_count += 1
            else:
                fail_count += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for wxid, message in messages_dict.items():
                future = executor.submit(send_single_message, wxid, message)
                futures.append(future)
            
            concurrent.futures.wait(futures)
        
        logger.info(f"群发完成 - 成功: {success_count}, 失败: {fail_count}")
        return success_count, fail_count

    @classmethod
    def schedule_messages(cls, bot, messages_dict: dict, schedule_time: datetime.datetime) -> str:
        """设置定时发送任务"""
        if bot is None:
            logger.error("Bot未初始化，无法设置定时任务")
            return ""
            
        task_id = cls._generate_task_id()
        
        def send_scheduled_messages():
            logger.info(f"开始执行定时任务 {task_id}")
            if bot is None:
                logger.error("Bot未初始化，任务执行失败")
                return 0, 0
            return cls.send_messages_to_multiple(bot, messages_dict)
        
        task = ScheduledTask(task_id, schedule_time, send_scheduled_messages)
        cls._tasks[task_id] = task
        task.start()
        
        return task_id

    @classmethod
    def parse_time(cls, time_str: str) -> datetime.datetime:
        """解析时间字符串"""
        try:
            now = datetime.datetime.now()
            
            if len(time_str.split()) == 1:  # HH:MM:SS
                time_parts = time_str.split(':')
                if len(time_parts) == 3:  # HH:MM:SS
                    hour, minute, second = map(int, time_parts)
                    target_time = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
                    if target_time <= now:
                        target_time += datetime.timedelta(days=1)
                else:
                    raise ValueError("时间格式必须为 HH:MM:SS")
                
            elif len(time_str.split()) == 2:  # 完整日期和时间
                date_part, time_part = time_str.split()
                time_parts = time_part.split(':')
                
                if len(time_parts) != 3:  # 必须包含秒
                    raise ValueError("时间格式必须为 HH:MM:SS")
                    
                hour, minute, second = map(int, time_parts)
                
                if len(date_part.split('-')) == 2:  # MM-DD
                    month, day = map(int, date_part.split('-'))
                    target_time = now.replace(month=month, day=day, hour=hour, 
                                            minute=minute, second=second, microsecond=0)
                    if target_time <= now:
                        target_time = target_time.replace(year=target_time.year + 1)
                    
                elif len(date_part.split('-')) == 3:  # YYYY-MM-DD
                    year, month, day = map(int, date_part.split('-'))
                    target_time = datetime.datetime(year, month, day, hour, minute, second)
                    if target_time <= now:
                        raise ValueError("完整日期时间不能早于当前时间")
                
                else:
                    raise ValueError("不支持的日期格式")
            
            else:
                raise ValueError("不支持的时间格式")
            
            logger.info(f"解析时间成功: {target_time}")
            return target_time
            
        except Exception as e:
            logger.error("时间格式错误", exc_info=e)
            raise ValueError(f"时间格式错误: {str(e)}")

    @classmethod
    def get_task_status(cls, task_id: str) -> Dict:
        """获取任务状态"""
        with cls._lock:
            if task_id not in cls._tasks:
                return {'id': task_id, 'status': 'unknown'}
                
            task = cls._tasks[task_id]
            return {
                'id': task_id,
                'status': task.status,
                'scheduled_time': task.scheduled_time.strftime("%Y-%m-%d %H:%M:%S")
            }

    @classmethod
    def cancel_task(cls, task_id: str) -> bool:
        """取消任务"""
        with cls._lock:
            if task_id not in cls._tasks:
                return False
                
            task = cls._tasks[task_id]
            task.cancel()
            del cls._tasks[task_id]
            return True

    @classmethod
    def cleanup_tasks(cls):
        """清理所有任务"""
        logger.info("开始清理定时任务...")
        try:
            with cls._lock:
                for task_id in list(cls._tasks.keys()):
                    try:
                        task = cls._tasks[task_id]
                        if hasattr(task, 'cancel'):
                            task.cancel()
                        logger.info(f"已取消任务: {task_id}")
                    except Exception as e:
                        logger.error(f"取消任务 {task_id} 时出错: {e}")
                cls._tasks.clear()
        except Exception as e:
            logger.error(f"清理任务时出错: {e}")