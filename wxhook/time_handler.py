import datetime
from typing import Tuple
from .logger import WxLogger
from .scheduler import MessageScheduler

logger = WxLogger.get_logger()

class TimeHandler:
    @staticmethod
    def parse_time(time_str: str) -> datetime.datetime:
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

    @staticmethod
    def setup_schedule(bot, messages_dict: dict, time_str: str) -> Tuple[MessageScheduler, str, datetime.datetime]:
        """设置定时任务"""
        try:
            target_time = TimeHandler.parse_time(time_str)
            wait_seconds = (target_time - datetime.datetime.now()).total_seconds()
            
            logger.info(f"\n定时设置:")
            logger.info(f"目标时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"等待时间: {wait_seconds:.0f} 秒")
            
            scheduler = MessageScheduler()
            
            def send_scheduled_messages():
                from .message_handler import MessageHandler
                logger.info(f"开始发送定时消息，时间: {datetime.datetime.now()}")
                success_count, fail_count = MessageHandler.send_messages_to_multiple(bot, messages_dict)
                logger.info(f"定时发送完成！成功: {success_count}, 失败: {fail_count}")
                return {'success': success_count, 'failed': fail_count}
            
            task_id = scheduler.add_task(target_time, send_scheduled_messages)
            return scheduler, task_id, target_time
            
        except ValueError as e:
            logger.error("时间设置错误", exc_info=e)
            raise