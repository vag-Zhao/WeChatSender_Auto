import time
import threading
import datetime
from typing import Optional, List, Tuple
from .logger import WxLogger
from wxhook import Bot
from .message_handler import MessageHandler
from .contact_handler import ContactHandler
from .thread_pool import ThreadPoolManager

logger = WxLogger.get_logger()

class BotHandler:
    def __init__(self):
        self.bot = None
        self.pool_manager = ThreadPoolManager()
        self.task_ids = []
        self._initialize_lock = threading.Lock()
        self._initialized = threading.Event()

    def check_login_once(self) -> bool:
        """单次检查登录状态"""
        try:
            if self.bot is None:
                logger.error("Bot未初始化")
                return False

            login_response = self.bot.check_login()
            logger.info(f"登录状态检查: {login_response}")
            
            if login_response.code == 1:
                logger.info("登录成功")
                # 异步获取联系人信息
                self.pool_manager.submit_thread(self.fetch_and_save_contacts)
                return True
        except Exception as e:
            logger.error("状态检查出错", exc_info=e)
        return False

    def wait_for_login(self, timeout: int = 30, check_interval: float = 1.0) -> bool:
        """等待登录完成"""
        logger.info(f"等待登录... (超时时间: {timeout}秒)")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.check_login_once():
                return True
            time.sleep(check_interval)
        
        logger.warning(f"登录超时 (>{timeout}秒)")
        return False

    def initialize_wechat(self) -> bool:
        """初始化微信并检查就绪状态"""
        with self._initialize_lock:
            try:
                logger.info("开始初始化微信...")
                self.bot = Bot(faked_version="3.9.10.19")
                
                # 立即进行一次登录检查
                if self.check_login_once():
                    self._initialized.set()
                    return True
                    
                # 如果首次检查失败,进入轮询等待
                success = self.wait_for_login()
                if success:
                    self._initialized.set()
                return success
                
            except Exception as e:
                logger.error(f"初始化微信失败: {e}")
                self.bot = None
                return False

    def fetch_and_save_contacts(self):
        """获取并保存联系人信息"""
        try:
            if self.bot is None:
                logger.error("Bot未初始化，无法获取联系人信息")
                return

            logger.info("\n=== 获取联系人列表 ===")
            
            # 首先检查是否存在联系人数据文件
            existing_data = ContactHandler.load_contacts_from_file()
            if existing_data:
                logger.info("使用现有联系人数据")
                return
                
            all_contacts = self.bot.get_contacts()
            logger.info(f"总联系人数量: {len(all_contacts)}")

            # 获取并保存联系人信息
            all_contacts_data = ContactHandler.get_contact_details(self.bot, all_contacts)
            self._save_contacts_data(all_contacts_data)
                    
        except Exception as e:
            logger.error(f"获取联系人信息时出错: {e}")
            if not isinstance(e, KeyboardInterrupt):
                raise

    def _save_contacts_data(self, contact_data: dict):
        """保存联系人数据"""
        try:
            ContactHandler.save_to_json(contact_data) 
        except Exception as e:
            logger.error(f"保存联系人数据失败: {e}")

    def process_messages(self) -> bool:
        """处理消息配置"""
        if not self._initialized.is_set():
            logger.error("微信尚未初始化完成，无法处理消息")
            return False
            
        if self.bot is None:
            logger.error("Bot实例无效，无法处理消息")
            return False
            
        try:
            future = self.pool_manager.submit_thread(self._process_message_box)
            self.task_ids = future.result()
            return bool(self.task_ids)
        except Exception as e:
            logger.error(f"处理消息配置失败: {e}")
            return False

    def _process_message_box(self) -> List[str]:
        """处理messageBox.json中的消息"""
        if self.bot is None:
            logger.error("Bot实例无效，无法处理消息")
            return []
            
        messages = MessageHandler.load_message_box()
        if not messages:
            logger.info("没有找到待发送的消息")
            return []
            
        time_groups = MessageHandler.group_messages_by_time(messages)
        task_ids = []
        
        for time_str, messages_dict in time_groups.items():
            try:
                target_time = MessageHandler.parse_time(time_str)
                task_id = MessageHandler.schedule_messages(self.bot, messages_dict, target_time)
                if task_id:
                    task_ids.append(task_id)
                    self._log_task_info(task_id, target_time, len(messages_dict))
                
            except ValueError as e:
                logger.error(f"设置定时任务失败: {e}")
                continue
        
        return task_ids

    def _log_task_info(self, task_id: str, target_time: datetime.datetime, message_count: int):
        """记录任务信息"""
        logger.info(f"\n定时任务已设置 [{task_id}]")
        logger.info(f"将在 {target_time.strftime('%Y-%m-%d %H:%M:%S')} 发送消息")
        logger.info(f"目标用户数: {message_count}")

    def run_main_loop(self, bot_instance):
        """运行主循环"""
        while bot_instance.running:
            try:
                time.sleep(0.1)  # 减少CPU使用率
            except KeyboardInterrupt:
                logger.info("\n接收到 Ctrl+C 信号")
                break

    def cleanup(self):
        """清理资源"""
        logger.info("开始清理资源...")
        try:
            # 清理定时任务
            MessageHandler.cleanup_tasks()
            
            # 关闭线程池
            if hasattr(self, 'pool_manager') and self.pool_manager:
                self.pool_manager.shutdown()
            
            # 关闭微信
            if hasattr(self, 'bot') and self.bot:
                self.bot.exit()
                
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")
        finally:
            logger.info("程序结束")