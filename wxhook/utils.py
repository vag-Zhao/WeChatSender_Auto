import json
import typing
import pathlib
import subprocess
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

BASE_DIR = pathlib.Path(__file__).resolve().parent
TOOLS = BASE_DIR / "tools"
DLL = TOOLS / "wxhook.dll"
START_WECHAT = TOOLS / "start-wechat.exe"
FAKER = TOOLS / "faker.exe"

class ProcessTimeoutError(Exception):
    pass

def start_wechat_with_inject(port: int) -> typing.Tuple[int, str]:
    """启动微信进程并注入DLL"""
    def kill_process_tree(process):
        try:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            for child in children:
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass

    try:
        # 使用Popen异步启动进程
        process = subprocess.Popen(
            f"{START_WECHAT} {DLL} {port}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW  # Windows下隐藏控制台窗口
        )

        # 设置超时时间（秒）
        timeout = 10
        result = {"success": False, "code": None, "output": None}
        
        def target():
            try:
                stdout, stderr = process.communicate()
                if stdout:
                    code, output = stdout.strip().split(",")
                    result["success"] = True
                    result["code"] = int(code)
                    result["output"] = output
            except Exception as e:
                result["error"] = str(e)

        # 创建并启动线程
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            # 如果线程还活着，说明超时了
            kill_process_tree(process)
            raise ProcessTimeoutError(f"启动微信超时 (>{timeout}秒)")

        if not result["success"]:
            if "error" in result:
                raise Exception(f"启动失败: {result['error']}")
            raise Exception("启动失败，未知错误")

        return result["code"], result["output"]

    except ProcessTimeoutError:
        raise
    except Exception as e:
        raise Exception(f"启动微信失败: {str(e)}")

def fake_wechat_version(pid: int, old_version: str, new_version: str) -> int:
    """伪装微信版本"""
    try:
        result = subprocess.run(
            f"{FAKER} {pid} {old_version} {new_version}",
            capture_output=True,
            text=True,
            timeout=5  # 添加超时限制
        )
        return int(result.stdout)
    except subprocess.TimeoutExpired:
        raise Exception("伪装版本号操作超时")
    except Exception as e:
        raise Exception(f"伪装版本号失败: {str(e)}")

def get_pid(port: int) -> typing.Tuple[int, int]:
    """通过端口号获取进程ID"""
    try:
        # 使用更可靠的方式获取进程信息
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                return 0, conn.pid
                
        # 如果上面方法失败，使用netstat命令作为备选方案
        output = subprocess.run(
            f"netstat -ano | findStr \"{port}\"", 
            capture_output=True,
            text=True,
            shell=True,
            timeout=5  # 添加超时限制
        ).stdout
        
        if not output:
            raise Exception(f"未找到端口 {port} 对应的进程")
            
        for line in output.split('\n'):
            if 'LISTENING' in line:
                pid = int(line.split()[-1])
                return 0, pid
                
        raise Exception(f"未找到端口 {port} 的监听进程")
        
    except Exception as e:
        raise Exception(f"获取进程ID失败: {str(e)}")

class WeChatManager:
    """微信管理器类"""
    
    def __init__(self):
        self.filename = BASE_DIR / "tools" / "wxhook.json"
        self._lock = threading.Lock()
        self._init_file()

    def _init_file(self) -> None:
        """初始化配置文件"""
        try:
            if not self.filename.exists():
                with self._lock:
                    with open(self.filename, "w", encoding="utf-8") as file:
                        json.dump({
                            "increase_remote_port": 19000,
                            "wechat": []
                        }, file, indent=2)
        except Exception as e:
            raise Exception(f"初始化配置文件失败: {str(e)}")

    def get_port(self) -> typing.Tuple[int, int]:
        """获取可用端口"""
        try:
            with self._lock:
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                remote_port = data["increase_remote_port"] + 1
                server_port = 19000 - (remote_port - 19000)
                
                # 检查端口是否被占用
                while self._is_port_in_use(remote_port) or self._is_port_in_use(server_port):
                    remote_port += 1
                    server_port = 19000 - (remote_port - 19000)
                
                return remote_port, server_port
        except Exception as e:
            raise Exception(f"获取端口失败: {str(e)}")

    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == port:
                    return True
            return False
        except:
            return False

    def add(self, pid: int, remote_port: int, server_port: int) -> None:
        """添加微信进程记录"""
        try:
            with self._lock:
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                
                # 清理已经不存在的进程记录
                data["wechat"] = [
                    w for w in data["wechat"] 
                    if psutil.pid_exists(w["pid"])
                ]
                
                # 添加新记录
                data["increase_remote_port"] = remote_port
                data["wechat"].append({
                    "pid": pid,
                    "remote_port": remote_port,
                    "server_port": server_port
                })
                
                with open(self.filename, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=2)
        except Exception as e:
            raise Exception(f"添加进程记录失败: {str(e)}")

    def cleanup(self):
        """清理无效的进程记录"""
        try:
            with self._lock:
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                
                # 只保留仍在运行的进程记录
                data["wechat"] = [
                    w for w in data["wechat"] 
                    if psutil.pid_exists(w["pid"])
                ]
                
                with open(self.filename, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=2)
        except Exception as e:
            raise Exception(f"清理进程记录失败: {str(e)}")