import time
import signal
import traceback
import threading
from typing import List
import datetime
from wxhook import Bot
from wxhook.logger import WxLogger
from wxhook.message_handler import MessageHandler
from wxhook.contact_handler import ContactHandler
from wxhook.thread_pool import ThreadPoolManager
from wxhook.bot_handler import BotHandler

logger = WxLogger.get_logger()

class WeChatBot:
    def __init__(self):
        self.handler = BotHandler()
        self.running = True
        self.setup_signal_handlers()

    def handle_signal(self, signum, frame):
        """处理退出信号"""
        logger.info("\n接收到退出信号")
        self.running = False
        self.handler.cleanup()

    def setup_signal_handlers(self):
        """设置信号处理器"""
        try:
            signal.signal(signal.SIGINT, self.handle_signal)
            signal.signal(signal.SIGTERM, self.handle_signal)
        except Exception as e:
            logger.error(f"设置信号处理器失败: {e}")

    def run(self):
        """运行主程序"""
        try:
            logger.info("程序启动...")
            
            # 初始化并检查微信
            if not self.handler.initialize_wechat():
                logger.error("微信初始化失败，程序退出")
                return
                
            # 等待初始化完成
            retry_count = 0
            while not self.handler._initialized.is_set() and retry_count < 3:
                logger.info("等待微信初始化完成...")
                time.sleep(2)
                retry_count += 1
                
            if not self.handler._initialized.is_set():
                logger.error("微信初始化超时，程序退出")
                return

            # 处理消息配置
            if not self.handler.process_messages():
                logger.info("没有需要执行的任务，程序退出")
                return
                
            logger.info("\n所有定时任务已设置，按Ctrl+C退出程序")
            
            # 主循环等待退出信号
            self.handler.run_main_loop(self)
                    
        except KeyboardInterrupt:
            logger.info("\n程序被用户中断")
        except Exception as e:
            logger.error("程序运行出错", exc_info=e)
            logger.error(traceback.format_exc())
        finally:
            self.handler.cleanup()

def main():
    """主函数"""
    wx_bot = WeChatBot()
    wx_bot.run()

if __name__ == "__main__":
    main()