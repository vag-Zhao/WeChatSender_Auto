import time
import threading
import datetime
from typing import Dict, List, Callable
from dataclasses import dataclass
from queue import Queue

@dataclass
class ScheduledTask:
    """定时任务结构"""
    id: str  # 任务唯一标识符
    time: datetime.datetime  # 计划执行时间
    task: Callable  # 要执行的函数
    args: tuple  # 函数参数
    kwargs: dict  # 函数关键字参数
    repeat: bool = False  # 是否重复
    interval: int = 0  # 重复间隔(秒)
    status: str = 'pending'  # 任务状态：pending/running/completed/failed

class MessageScheduler:
    """消息调度器"""
    def __init__(self):
        self.tasks: List[ScheduledTask] = []
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.task_results = Queue()
        self.task_counter = 0

    def start(self):
        """启动调度器"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run)
            self.thread.daemon = True
            self.thread.start()
            print("调度器已启动")

    def stop(self):
        """停止调度器"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
                print("调度器已停止")

    def _generate_task_id(self) -> str:
        """生成唯一任务ID"""
        self.task_counter += 1
        return f"task_{self.task_counter}"

    def add_task(self, 
                 scheduled_time: datetime.datetime, 
                 task: Callable, 
                 *args, 
                 repeat: bool = False, 
                 interval: int = 0, 
                 **kwargs) -> str:
        """添加定时任务，返回任务ID"""
        with self.lock:
            task_id = self._generate_task_id()
            scheduled_task = ScheduledTask(
                id=task_id,
                time=scheduled_time,
                task=task,
                args=args,
                kwargs=kwargs,
                repeat=repeat,
                interval=interval,
                status='pending'
            )
            self.tasks.append(scheduled_task)
            print(f"已添加定时任务 [{task_id}]: 计划执行时间 {scheduled_time}")
            
        if not self.running:
            self.start()
        
        return task_id

    def _execute_task(self, task: ScheduledTask):
        """执行任务并处理结果"""
        try:
            print(f"开始执行任务 [{task.id}]")
            task.status = 'running'
            start_time = datetime.datetime.now()
            
            result = task.task(*task.args, **task.kwargs)
            
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            task.status = 'completed'
            self.task_results.put({
                'task_id': task.id,
                'status': 'completed',
                'execution_time': execution_time,
                'result': result
            })
            print(f"任务 [{task.id}] 执行完成，耗时: {execution_time:.2f}秒")
            
        except Exception as e:
            task.status = 'failed'
            self.task_results.put({
                'task_id': task.id,
                'status': 'failed',
                'error': str(e)
            })
            print(f"任务 [{task.id}] 执行失败: {e}")

    def _run(self):
        """运行调度器主循环"""
        while self.running:
            now = datetime.datetime.now()
            
            with self.lock:
                tasks_to_remove = []
                tasks_to_add = []
                
                for task in self.tasks:
                    if task.status == 'pending' and task.time <= now:
                        # 在新线程中执行任务
                        thread = threading.Thread(
                            target=self._execute_task,
                            args=(task,)
                        )
                        thread.start()
                        
                        if task.repeat and task.interval > 0:
                            next_time = task.time + datetime.timedelta(seconds=task.interval)
                            new_task_id = self._generate_task_id()
                            tasks_to_add.append(ScheduledTask(
                                id=new_task_id,
                                time=next_time,
                                task=task.task,
                                args=task.args,
                                kwargs=task.kwargs,
                                repeat=True,
                                interval=task.interval,
                                status='pending'
                            ))
                        
                        tasks_to_remove.append(task)
                
                for task in tasks_to_remove:
                    self.tasks.remove(task)
                
                self.tasks.extend(tasks_to_add)
            
            time.sleep(0.1)  # 更频繁地检查任务

    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        with self.lock:
            for task in self.tasks:
                if task.id == task_id:
                    return {
                        'id': task.id,
                        'status': task.status,
                        'scheduled_time': task.time,
                        'type': 'pending'
                    }
        
        # 检查已完成的任务结果
        while not self.task_results.empty():
            result = self.task_results.get()
            if result['task_id'] == task_id:
                return result
        
        return {'id': task_id, 'status': 'unknown'}

    def wait_for_task(self, task_id: str, timeout: float = None) -> dict:
        """等待任务完成"""
        start_time = time.time()
        while True:
            status = self.get_task_status(task_id)
            if status['status'] in ['completed', 'failed']:
                return status
            
            if timeout is not None and time.time() - start_time > timeout:
                return {'id': task_id, 'status': 'timeout'}
            
            time.sleep(0.1)

    def get_all_tasks_status(self) -> List[Dict]:
        """获取所有任务的状态"""
        with self.lock:
            return [
                {
                    'id': task.id,
                    'time': task.time.strftime("%Y-%m-%d %H:%M:%S"),
                    'status': task.status,
                    'repeat': task.repeat,
                    'interval': task.interval
                }
                for task in self.tasks
            ]

    def clear_tasks(self):
        """清除所有任务"""
        with self.lock:
            self.tasks.clear()
            print("所有任务已清除")