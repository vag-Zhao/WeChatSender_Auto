import json
import socketserver
import typing
import psutil
import requests
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
from typing import Optional
from datetime import datetime
from .model import Event, Account, Contact, ContactDetail, Room, RoomMembers, Table, DB, Response
from .utils import WeChatManager, start_wechat_with_inject, fake_wechat_version, get_pid
from .logger import WxLogger

logger = WxLogger.get_logger()

class RequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            data = self.request.recv(1024)
            logger.debug(f"收到请求数据: {data}")
            self.request.sendall("200 OK".encode())
        except Exception as e:
            logger.error("处理请求时出错", exc_info=e)
        finally:
            self.request.close()

class Bot:
    def __init__(self, faked_version: Optional[str] = None,
                on_login=None, on_start=None, on_stop=None,
                on_before_message=None, on_after_message=None):
        
        self.logger = logger
        self.logger.info("初始化微信机器人...")
        
        # 基础配置
        self.version = "3.9.5.81"
        self.server_host = "127.0.0.1"
        self.remote_host = "127.0.0.1"
        self.faked_version = faked_version
        
        # 回调函数
        self.on_login = on_login
        self.on_start = on_start 
        self.on_stop = on_stop
        self.on_before_message = on_before_message
        self.on_after_message = on_after_message
        
        # 事件处理器
        self._event_handlers = {}
        
        try:
            # 并行初始化关键组件
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 初始化管理器和获取端口
                manager_future = executor.submit(self._init_manager)
                # 创建session可以同时进行
                session_future = executor.submit(self._create_session)
                
                # 等待管理器初始化完成
                self.wechat_manager, ports = manager_future.result()
                self.remote_port, self.server_port = ports
                
                # 获取创建的session
                self.session = session_future.result()
                
                # 启动微信进程
                self.process = self._start_wechat()
                
            self.BASE_URL = f"http://{self.remote_host}:{self.remote_port}"
            self.logger.info(f"API服务地址: {self.BASE_URL}")
            
            # 版本伪装
            if self.faked_version:
                self._fake_version()

            # 注册进程
            self.wechat_manager.add(self.process.pid, self.remote_port, self.server_port)
                
            # 调用启动回调
            if self.on_start:
                try:
                    self.on_start(self)
                except Exception as e:
                    self.logger.error("执行启动回调时出错", exc_info=e)
                    
        except Exception as e:
            self.logger.error("Bot初始化失败", exc_info=e)
            self.exit()
            raise
            
    def _init_manager(self):
        """初始化管理器并获取端口"""
        manager = WeChatManager()
        ports = manager.get_port()
        return manager, ports
        
    def _start_wechat(self):
        """启动微信进程"""
        try:
            code, output = start_wechat_with_inject(self.remote_port)
        except Exception as e:
            self.logger.error("启动微信失败，尝试获取现有进程", exc_info=e)
            code, output = get_pid(self.remote_port)

        if code == 1:
            error_msg = f"初始化失败: {output}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
            
        process = psutil.Process(int(output))
        self.logger.info(f"微信进程已启动，PID: {process.pid}")
        return process
        
    def _fake_version(self):
        """伪装微信版本"""
        if fake_wechat_version(self.process.pid, self.version, self.faked_version) == 0:
            self.logger.info(f"微信版本已伪装: {self.version} -> {self.faked_version}")
        else:
            self.logger.warning("微信版本伪装失败")

    def _create_session(self):
        """创建具有重试机制的会话"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        
        # 配置适配器
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
            pool_block=False
        )
        
        # 注册适配器
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    def check_login(self) -> Response:
        """检查登录状态"""
        try:
            response = Response(**self.call_api("/api/checkLogin"))
            return response
        except Exception as e:
            self.logger.error("检查登录状态失败", exc_info=e)
            raise
        
    def send_text(self, wxid: str, msg: str) -> Response:
        """发送文本消息"""
        data = {
            "wxid": wxid,
            "msg": msg
        }
        try:
            self.logger.info(f"发送消息 -> {wxid}: {msg}")
            response = self.call_api("/api/sendTextMsg", json=data)
            self.logger.info(f"发送结果: {response}")
            return Response(**response)
        except Exception as e:
            self.logger.error(f"发送消息失败", exc_info=e)
            raise

    def get_contacts(self) -> typing.List[Contact]:
        """获取联系人列表"""
        try:
            contacts_data = self.call_api("/api/getContactList")
            return [Contact(**item) for item in contacts_data.get("data", [])]
        except Exception as e:
            self.logger.error("获取联系人列表失败", exc_info=e)
            raise

    def get_contact(self, wxid: str) -> ContactDetail:
        """获取联系人详情"""
        try:
            data = {"wxid": wxid}
            contact_info = self.call_api("/api/getContactProfile", json=data)["data"]
            
            try:
                remark_data = {
                    "wxid": wxid,
                    "type": 1
                }
                remark_info = self.call_api("/api/getContactRemark", json=remark_data)
                if remark_info.get("code") == 1 and remark_info.get("data"):
                    remark = remark_info["data"].get("remark", "")
                    if isinstance(remark, dict) and "remark" in remark:
                        contact_info["remark"] = remark["remark"]
                    else:
                        contact_info["remark"] = remark
                else:
                    contact_info["remark"] = ""
                    
                self.logger.debug(f"获取到的备注信息: {remark_info}")
            except Exception as e:
                self.logger.error(f"获取用户备注失败: {e}")
                contact_info["remark"] = ""
            
            return ContactDetail(**contact_info)
        except Exception as e:
            self.logger.error(f"获取联系人 {wxid} 详情失败", exc_info=e)
            raise

    def call_api(self, api: str, *args, **kwargs) -> dict:
        """调用API接口"""
        max_retries = 3
        retry_delay = 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                self.logger.debug(f"调用API: {api}, 参数: {kwargs}")
                response = self.session.request(
                    "POST", 
                    self.BASE_URL + api, 
                    *args, 
                    **kwargs,
                    timeout=10
                )
                response_data = response.json()
                self.logger.debug(f"API返回: {response_data}")
                return response_data
            except Exception as e:
                last_error = e
                self.logger.error(f"API调用失败 {api} (尝试 {attempt + 1}/{max_retries})", exc_info=e)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
        
        raise last_error or Exception(f"API调用失败: {api}")

    def handle(self, event_type: int):
        """事件处理装饰器"""
        def decorator(func):
            self._event_handlers[event_type] = func
            return func
        return decorator

    def _handle_event(self, event: Event):
        """处理接收到的事件"""
        try:
            if self.on_before_message:
                self.on_before_message(self, event)

            if event.type in self._event_handlers:
                handler = self._event_handlers[event.type]
                try:
                    handler(self, event)
                except Exception as e:
                    self.logger.error(f"事件处理出错: {event.type}", exc_info=e)

            if self.on_after_message:
                self.on_after_message(self, event)

        except Exception as e:
            self.logger.error("事件处理过程出错", exc_info=e)

    def run(self):
        """运行Bot"""
        try:
            self.logger.info("启动消息服务器...")
            server = socketserver.ThreadingTCPServer(
                (self.server_host, self.server_port), 
                RequestHandler
            )
            self.logger.info(f"监听地址: {self.server_host}:{self.server_port}")
            server.serve_forever()
        except Exception as e:
            self.logger.error("运行服务器时出错", exc_info=e)
            raise
        finally:
            self.exit()

    def exit(self):
        """清理资源并退出"""
        try:
            if hasattr(self, 'session'):
                self.session.close()
                
            if hasattr(self, 'process'):
                self.process.terminate()
                self.logger.info("微信进程已关闭")
                
            if self.on_stop:
                try:
                    self.on_stop(self)
                except Exception as e:
                    self.logger.error("执行停止回调时出错", exc_info=e)
                    
        except Exception as e:
            self.logger.error("退出时发生错误", exc_info=e)