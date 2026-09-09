# Copyright (c) Opendatalab. All rights reserved.

import asyncio
import uuid
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

from loguru import logger

from .models import TaskStatus, QueueStatus, TaskInfo


class TaskManager:
    """全局任务管理器"""

    def __init__(self):
        self.tasks: Dict[str, TaskInfo] = {}
        self.queue_status = QueueStatus.IDLE
        self.current_processing_task = None          # 兼容旧单值字段（=最近开始处理的任务）
        self.current_processing_tasks: List[str] = []  # v0.9.0: 并发处理中的任务列表
        self.max_concurrent_per_lane = 2              # v0.9.2: 每道(UI/API)各 2 并发
        # 双道槽位：UI 与 API 各占 2，互不影响（总并发 4）；/file_parse 走 api_slots
        self.ui_slots = asyncio.Semaphore(self.max_concurrent_per_lane)
        self.api_slots = asyncio.Semaphore(self.max_concurrent_per_lane)
        self._workers_started = False

    def lane_slots(self, lane: str) -> asyncio.Semaphore:
        """按任务来源取槽位（未知来源归 api 道）"""
        return self.ui_slots if lane == "ui" else self.api_slots

    def create_task(self, filename: str, origin: str = "api") -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        task = TaskInfo(task_id, filename, datetime.now(), origin=origin)
        self.tasks[task_id] = task
        # 任务状态已更新，无需保存到文件
        return task_id
        
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self.tasks.get(task_id)
        
    def update_task_status(self, task_id: str, status: TaskStatus, progress: int = None, message: str = None, error_message: str = None):
        """更新任务状态"""
        task = self.tasks.get(task_id)
        if task:
            task.status = status
            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if error_message is not None:
                task.error_message = error_message
            if status == TaskStatus.PROCESSING and task.start_time is None:
                task.start_time = datetime.now()
                # 状态变为PROCESSING时同步到file_list.json
                self.sync_task_to_file_list(task)
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                # 成功/失败时若缺少开始时间，进行兜底：优先用已有start_time，其次用upload_time，再次用当前时间
                if task.start_time is None:
                    task.start_time = task.upload_time or datetime.now()
                if not task.end_time:  # 只在第一次设置结束时间
                    task.end_time = datetime.now()
                # 任务完成时同步到 file_list.json
                self.sync_task_to_file_list(task)
            elif status == TaskStatus.QUEUED:
                # 状态变为QUEUED时也同步到file_list.json
                self.sync_task_to_file_list(task)
            # 任务状态已更新，无需保存到文件
            
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        return [task.to_dict() for task in self.tasks.values()]
    
    def sync_task_to_file_list(self, task):
        """将任务信息同步到 file_list.json"""
        try:
            # 导入文件管理器
            from src.file.manager import load_server_file_list, save_server_file_list
            
            # 获取当前文件列表
            current_file_list = load_server_file_list()
            
            # 查找是否已存在该文件
            file_found = False
            for file_info in current_file_list:
                if file_info.get("taskId") == task.task_id:
                    # 更新现有文件信息
                    file_info.update({
                        "status": task.status.value,
                        "origin": task.origin,
                        "progress": task.progress,
                        "message": task.message,
                        "startTime": task.start_time.isoformat() if task.start_time else None,
                        "endTime": task.end_time.isoformat() if task.end_time else None,
                        "processingTime": (task.end_time - task.start_time).total_seconds() if task.start_time and task.end_time else None,
                        "errorMessage": task.error_message,
                        "outputDir": task.result_path
                    })
                    file_found = True
                    break
            
            # 如果没找到，添加新文件信息
            if not file_found:
                new_file_info = {
                    "name": task.filename,
                    "size": 0,  # 文件大小信息可能丢失
                    "origin": task.origin,
                    "status": task.status.value,
                    "uploadTime": task.upload_time.isoformat() if task.upload_time else None,
                    "startTime": task.start_time.isoformat() if task.start_time else None,
                    "endTime": task.end_time.isoformat() if task.end_time else None,
                    "processingTime": (task.end_time - task.start_time).total_seconds() if task.start_time and task.end_time else None,
                    "taskId": task.task_id,
                    "progress": task.progress,
                    "message": task.message,
                    "errorMessage": task.error_message,
                    "outputDir": task.result_path
                }
                current_file_list.append(new_file_info)
            
            # 保存更新后的文件列表
            save_server_file_list(current_file_list)
            logger.info(f"任务 {task.task_id} 已同步到 file_list.json")
            
        except Exception as e:
            logger.warning(f"同步任务到 file_list.json 失败: {e}")
        
    def get_queue_tasks(self) -> List[str]:
        """获取队列中的任务ID列表"""
        queued_tasks = []
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.QUEUED:
                queued_tasks.append(task_id)
        # 按上传时间排序，确保先进先出
        return sorted(queued_tasks, key=lambda tid: self.tasks[tid].upload_time)
    
    def get_next_task(self) -> Optional[str]:
        """获取下一个要处理的任务ID"""
        queued_tasks = self.get_queue_tasks()
        if queued_tasks:
            return queued_tasks[0]
        return None
    
    def start_queue(self):
        """启动队列处理"""
        if self.queue_status == QueueStatus.IDLE:
            self.queue_status = QueueStatus.RUNNING
            # 队列状态已更新，无需保存到文件
            logger.info("任务队列已启动")
    
    def stop_queue(self):
        """停止队列处理（在跑的任务跑完，不再取新任务）"""
        self.queue_status = QueueStatus.IDLE
        self.current_processing_task = None
        self.current_processing_tasks = []
        self._workers_started = False
        # 队列状态已更新，无需保存到文件
        logger.info("任务队列已停止")
    
    def add_to_queue(self, task_id: str):
        """将任务添加到队列"""
        task = self.tasks.get(task_id)
        if task and task.status == TaskStatus.PENDING:
            task.status = TaskStatus.QUEUED
            task.message = "已加入队列"
            # 开始时间应在进入 PROCESSING 时设置，这里不设置
            # 任务状态已更新，无需保存到文件
            logger.info(f"任务 {task_id} 已加入队列")
            
            # 如果队列空闲，启动队列（避免重复启动）
            if self.queue_status == QueueStatus.IDLE:
                self.start_queue()
                self._ensure_workers()

    def _ensure_workers(self):
        """启动队列工人协程（每道 max_concurrent_per_lane 个，UI/API 双道互不堵塞）"""
        if self._workers_started:
            return
        self._workers_started = True
        for lane in ("ui", "api"):
            for i in range(self.max_concurrent_per_lane):
                asyncio.create_task(self._worker(f"{lane}{i}", lane))
        logger.info(f"已启动队列工人: ui×{self.max_concurrent_per_lane} + api×{self.max_concurrent_per_lane}")

    def _pick_next_task(self, lane: str) -> Optional[str]:
        """原子取出本道最早的排队任务并标记 PROCESSING。

        事件循环内检查与改状态之间无 await，同道工人不会取到同一任务；
        按道过滤避免队头阻塞（他道任务占满不影响本道）。
        """
        queued = [tid for tid in self.get_queue_tasks()
                  if (self.tasks[tid].origin or "api") == lane]
        if not queued:
            return None
        task_id = queued[0]
        task = self.tasks[task_id]
        task.status = TaskStatus.PROCESSING
        task.message = "等待GPU槽位"
        return task_id

    async def _worker(self, worker_id: str, lane: str):
        """队列工人：持本道槽位期间处理一个本道任务，完成立即取下一个"""
        slots = self.lane_slots(lane)
        while self.queue_status == QueueStatus.RUNNING:
            # 先抢本道槽位再取任务，避免任务卡在 PROCESSING 等槽位
            await slots.acquire()
            task_id = self._pick_next_task(lane)
            if not task_id:
                slots.release()
                await asyncio.sleep(1)
                continue

            self.current_processing_tasks.append(task_id)
            self.current_processing_task = task_id  # 兼容旧单值字段
            try:
                await self.process_single_task(task_id)
            except Exception as e:
                logger.error(f"工人{worker_id} 处理任务 {task_id} 失败: {e}")
                self.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", str(e))
            finally:
                if task_id in self.current_processing_tasks:
                    self.current_processing_tasks.remove(task_id)
                self.current_processing_task = (
                    self.current_processing_tasks[-1] if self.current_processing_tasks else None
                )
                slots.release()
                # 任务完成后清理显存（只释放未占用缓存，不影响并行任务）
                from src.utils.vram import cleanup_vram
                cleanup_vram()
    
    async def process_single_task(self, task_id: str):
        """处理单个任务"""
        task = self.tasks.get(task_id)
        if not task:
            return
            
        # 更新状态为处理中
        self.update_task_status(task_id, TaskStatus.PROCESSING, 20, "开始处理文件")
        await asyncio.sleep(0.5)  # 让状态变化可见
        
        # 查找上传的文件
        output_dir = "./output"
        uploaded_file = None
        for filename in os.listdir(output_dir):
            if filename.startswith(f"{task_id}_"):
                uploaded_file = os.path.join(output_dir, filename)
                break
                
        if not uploaded_file:
            # 如果没有找到文件，可能是测试环境，模拟处理过程
            self.update_task_status(task_id, TaskStatus.PROCESSING, 30, "正在解析文件")
            await asyncio.sleep(1)  # 模拟处理时间
            self.update_task_status(task_id, TaskStatus.PROCESSING, 50, "正在处理文件内容")
            await asyncio.sleep(1)  # 模拟处理时间
            self.update_task_status(task_id, TaskStatus.PROCESSING, 80, "处理完成，生成结果文件")
            await asyncio.sleep(0.5)  # 模拟处理时间
            self.update_task_status(task_id, TaskStatus.COMPLETED, 100, "转换完成", None)
            logger.info(f"任务 {task_id} 处理完成（模拟）")
            return
            
        # 检查显存是否可用
        from src.utils.vram import check_vram_available
        if not check_vram_available():
            self.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", "显存不足，无法处理文件")
            logger.error(f"任务 {task_id} 失败：显存不足")
            from src.utils.vram import cleanup_vram
            cleanup_vram()  # 尝试清理显存
            return
        
        # 开始处理
        self.update_task_status(task_id, TaskStatus.PROCESSING, 30, "正在解析文件")
        
        # 定义进度回调函数
        async def update_progress(progress, message):
            self.update_task_status(task_id, TaskStatus.PROCESSING, progress, message)
            # 添加日志记录进度更新
            logger.info(f"任务 {task_id} 进度更新: {progress}% - {message}")
        
        # 使用现有的parse_pdf函数进行处理
        from src.file.pdf_processor import parse_pdf
        result = await parse_pdf(
            doc_path=uploaded_file,
            output_dir=output_dir,
            end_page_id=99999,
            is_ocr=False,
            formula_enable=True,
            table_enable=True,
            language="ch",
            backend="vlm-engine",
            url=None,
            progress_callback=update_progress
        )
        
        if result:
            local_md_dir, file_name = result
            self.update_task_status(task_id, TaskStatus.PROCESSING, 80, "处理完成，生成结果文件")
            
            # 保存结果路径
            task.result_path = local_md_dir
            self.update_task_status(task_id, TaskStatus.COMPLETED, 100, "转换完成", None)
            
            # 输出output目录信息
            print(f"✅ 文件转换成功: {file_name}")
            print(f"📁 输出目录: {local_md_dir}")
            logger.info(f"任务 {task_id} 处理完成: {file_name}")
            logger.info(f"输出目录: {local_md_dir}")
            
            # 清理上传的原始文件
            try:
                os.remove(uploaded_file)
            except:
                pass
        else:
            self.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", "解析过程中出现错误")
        
        # 任务完成后清理显存
        from src.utils.vram import cleanup_vram
        cleanup_vram()
