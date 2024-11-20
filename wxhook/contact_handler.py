import os
import json
import time
import datetime
import concurrent.futures
from typing import Dict, List, Optional
from tqdm import tqdm
from colorama import init, Fore, Style
from .logger import WxLogger
from .model import Contact
from .thread_pool import async_task

init()
logger = WxLogger.get_logger()

class ContactHandler:
    """联系人处理类"""
    CONTACTS_FILENAME = "contacts_data.json"  
    
    @staticmethod
    def save_to_json(data: Dict, filename: str = CONTACTS_FILENAME) -> None:
        """保存数据到JSON文件"""
        try:
            os.makedirs('user_info', exist_ok=True)
            filepath = os.path.join('user_info', filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, cls=ContactHandler.ContactEncoder)
            logger.info(f"数据已保存到 {filepath}")
        except Exception as e:
            logger.error(f"保存JSON文件失败: {e}")
            raise

    @staticmethod
    def load_contacts_from_file() -> Optional[Dict]:
        """从文件加载联系人信息"""
        try:
            filepath = os.path.join('user_info', ContactHandler.CONTACTS_FILENAME)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"从 {filepath} 加载了联系人数据")
                return data
            return None
        except Exception as e:
            logger.error(f"加载联系人数据失败: {e}")
            return None

    @staticmethod
    def get_contact_details(bot, contacts: List[Contact]) -> Dict:
        """并行获取联系人详细信息"""
        # 首先尝试从文件加载
        existing_data = ContactHandler.load_contacts_from_file()
        if existing_data:
            logger.info("找到现有联系人数据，跳过获取过程")
            return existing_data

        contact_data = {
            "total_contacts": len(contacts),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "contacts": []
        }
        
        def process_contact(contact):
            try:
                time.sleep(0.1)
                detail = bot.get_contact(contact.wxid)
                return {
                    "basic_info": {
                        "nickname": contact.nickname,
                        "wxid": contact.wxid,
                        "custom_account": contact.customAccount,
                        "pinyin": contact.pinyin,
                        "pinyin_full": contact.pinyinAll,
                        "type": contact.type,
                        "verify_flag": contact.verifyFlag
                    },
                    "detail_info": {
                        "account": detail.account,
                        "head_image": detail.headImage,
                        "nickname": detail.nickname,
                        "remark": detail.remark,
                        "v3": detail.v3,
                        "wxid": detail.wxid
                    }
                }
            except Exception as e:
                logger.error(f"获取用户 {contact.nickname}({contact.wxid}) 的详细信息失败: {e}")
                return {
                    "basic_info": {
                        "nickname": contact.nickname,
                        "wxid": contact.wxid,
                        "custom_account": contact.customAccount,
                        "pinyin": contact.pinyin,
                        "pinyin_full": contact.pinyinAll,
                        "type": contact.type,
                        "verify_flag": contact.verifyFlag
                    },
                    "detail_info": "获取失败",
                    "error": str(e)
                }

        def process_contacts_batch(contacts_batch, pbar):
            """处理联系人批次"""
            results = []
            for contact in contacts_batch:
                result = process_contact(contact)
                results.append(result)
                pbar.update(1)
                pbar.set_description(f"处理联系人: {contact.nickname[:10]}...")
            return results

        try:
            # 分批处理联系人
            batch_size = 50
            contact_batches = [
                contacts[i:i + batch_size] 
                for i in range(0, len(contacts), batch_size)
            ]
            
            total_contacts = len(contacts)
            processed_contacts = 0
            
            print(f"\n{Fore.CYAN}开始获取联系人详细信息...{Style.RESET_ALL}")
            with tqdm(total=total_contacts, 
                     desc="总进度", 
                     bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Style.RESET_ALL),
                     unit="联系人") as pbar:
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_batch = {
                        executor.submit(process_contacts_batch, batch, pbar): batch 
                        for batch in contact_batches
                    }
                    
                    for future in concurrent.futures.as_completed(future_to_batch):
                        try:
                            results = future.result()
                            contact_data["contacts"].extend(results)
                            processed_contacts += len(results)
                        except Exception as e:
                            logger.error(f"处理联系人批次时出错: {e}")
            
            # 显示完成信息
            success_count = len([c for c in contact_data["contacts"] if "error" not in c])
            fail_count = len([c for c in contact_data["contacts"] if "error" in c])
            
            print(f"\n{Fore.GREEN}处理完成：{Style.RESET_ALL}")
            print(f"{Fore.CYAN}总联系人数：{Style.RESET_ALL}{total_contacts}")
            print(f"{Fore.GREEN}成功处理：{Style.RESET_ALL}{success_count}")
            print(f"{Fore.RED}处理失败：{Style.RESET_ALL}{fail_count}")
            print(f"\n{Fore.YELLOW}等候定时任务中.......{Style.RESET_ALL}")

            return contact_data
            
        except Exception as e:
            logger.error(f"获取联系人详情时出错: {e}")
            raise

    class ContactEncoder(json.JSONEncoder):
        """自定义JSON编码器处理数据类的序列化"""
        def default(self, obj):
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            return super().default(obj)