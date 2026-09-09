# Copyright (c) Opendatalab. All rights reserved.

from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    QUEUED = "queued"  # 队列中
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueStatus(Enum):
    """队列状态枚举"""
    IDLE = "idle"          # 空闲
    RUNNING = "running"    # 运行中
    PAUSED = "paused"      # 暂停


class TaskInfo:
    """任务信息类"""
    
    def __init__(self, task_id: str, filename: str, upload_time: datetime, origin: str = "api"):
        self.task_id = task_id
        self.filename = filename
        self.upload_time = upload_time
        self.origin = origin  # v0.9.2: 任务来源 "ui" / "api"（UI 上传带 source=ui，默认 api）
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = "等待处理"
        self.start_time = None
        self.end_time = None
        self.result_path = None
        self.error_message = None
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "origin": self.origin,
            "upload_time": self.upload_time.isoformat(),
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "result_path": self.result_path,
            "error_message": self.error_message
        }
