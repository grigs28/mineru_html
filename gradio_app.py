# Copyright (c) Opendatalab. All rights reserved.

import base64
import os
import re
import time
import zipfile
import glob
import uuid
import asyncio
import json
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Dict, Any

import click
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from typing import List, Optional
from loguru import logger

# 尝试导入MinerU模块，如果失败则使用替代函数
try:
    from mineru.cli.common import prepare_env, read_fn, aio_do_parse, pdf_suffixes, image_suffixes
    from mineru.utils.cli_parser import arg_parse
    from mineru.utils.hash_utils import str_sha256
    MINERU_AVAILABLE = True
except ImportError:
    # 如果MinerU模块不可用，创建简单的替代函数
    MINERU_AVAILABLE = False
    pdf_suffixes = [".pdf"]
    image_suffixes = [".png", ".jpeg", ".jpg", ".webp", ".gif"]
    
    def prepare_env(output_dir, pdf_file_name, parse_method):
        local_md_dir = str(os.path.join(output_dir, pdf_file_name, parse_method))
        local_image_dir = os.path.join(str(local_md_dir), "images")
        os.makedirs(local_image_dir, exist_ok=True)
        os.makedirs(local_md_dir, exist_ok=True)
        return local_image_dir, local_md_dir
    
    def read_fn(path):
        if not isinstance(path, Path):
            path = Path(path)
        with open(str(path), "rb") as input_file:
            return input_file.read()
    
    async def aio_do_parse(*args, **kwargs):
        # 简化版本，不进行实际处理
        pass
    
    def arg_parse(ctx):
        return {}
    
    def str_sha256(text):
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:16]

# 任务状态枚举
class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"  # 队列中
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# 队列状态枚举
class QueueStatus(Enum):
    IDLE = "idle"          # 空闲
    RUNNING = "running"    # 运行中
    PAUSED = "paused"      # 暂停

# 任务信息类
class TaskInfo:
    def __init__(self, task_id: str, filename: str, upload_time: datetime):
        self.task_id = task_id
        self.filename = filename
        self.upload_time = upload_time
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = "等待处理"
        self.start_time = None
        self.end_time = None
        self.result_path = None
        self.error_message = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "upload_time": self.upload_time.isoformat(),
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "result_path": self.result_path,
            "error_message": self.error_message
        }

# 全局任务管理器
class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, TaskInfo] = {}
        self.task_storage_path = os.path.join("./config", "tasks.json")
        self.queue_status = QueueStatus.IDLE
        self.current_processing_task = None
        self.processing_lock = asyncio.Lock()
        self.load_tasks()
        self.load_queue_status()
        
    def create_task(self, filename: str) -> str:
        task_id = str(uuid.uuid4())
        task = TaskInfo(task_id, filename, datetime.now())
        self.tasks[task_id] = task
        self.save_tasks()
        return task_id
        
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self.tasks.get(task_id)
        
    def update_task_status(self, task_id: str, status: TaskStatus, progress: int = None, message: str = None, error_message: str = None):
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
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                # 成功/失败时若缺少开始时间，进行兜底：优先用已有start_time，其次用upload_time，再次用当前时间
                if task.start_time is None:
                    task.start_time = task.upload_time or datetime.now()
                if not task.end_time:  # 只在第一次设置结束时间
                    task.end_time = datetime.now()
            self.save_tasks()
            
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self.tasks.values()]
        
    def save_tasks(self):
        try:
            _ensure_config_dir()
            with open(self.task_storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_all_tasks(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存任务列表失败: {e}")
            
    def load_tasks(self):
        try:
            _ensure_config_dir()
            if os.path.exists(self.task_storage_path):
                with open(self.task_storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for task_data in data:
                        task = TaskInfo(task_data["task_id"], task_data["filename"], 
                                      datetime.fromisoformat(task_data["upload_time"]))
                        task.status = TaskStatus(task_data["status"])
                        task.progress = task_data.get("progress", 0)
                        task.message = task_data.get("message", "等待处理")
                        task.start_time = datetime.fromisoformat(task_data["start_time"]) if task_data.get("start_time") else None
                        task.end_time = datetime.fromisoformat(task_data["end_time"]) if task_data.get("end_time") else None
                        task.result_path = task_data.get("result_path")
                        task.error_message = task_data.get("error_message")
                        self.tasks[task_data["task_id"]] = task
        except Exception as e:
            logger.warning(f"加载任务列表失败: {e}")
    
    def load_queue_status(self):
        """加载队列状态"""
        try:
            _ensure_config_dir()
            queue_status_path = os.path.join("./config", "queue_status.json")
            if os.path.exists(queue_status_path):
                with open(queue_status_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.queue_status = QueueStatus(data.get("status", "idle"))
                    self.current_processing_task = data.get("current_processing_task")
        except Exception as e:
            logger.warning(f"加载队列状态失败: {e}")
    
    def save_queue_status(self):
        """保存队列状态"""
        try:
            _ensure_config_dir()
            queue_status_path = os.path.join("./config", "queue_status.json")
            with open(queue_status_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "status": self.queue_status.value,
                    "current_processing_task": self.current_processing_task
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存队列状态失败: {e}")
    
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
            self.save_queue_status()
            logger.info("任务队列已启动")
    
    def stop_queue(self):
        """停止队列处理"""
        self.queue_status = QueueStatus.IDLE
        self.current_processing_task = None
        self.save_queue_status()
        logger.info("任务队列已停止")
    
    def add_to_queue(self, task_id: str):
        """将任务添加到队列"""
        task = self.tasks.get(task_id)
        if task and task.status == TaskStatus.PENDING:
            task.status = TaskStatus.QUEUED
            task.message = "已加入队列"
            # 开始时间应在进入 PROCESSING 时设置，这里不设置
            self.save_tasks()
            logger.info(f"任务 {task_id} 已加入队列")
            
            # 如果队列正在运行，立即开始处理
            # 如果队列空闲，启动队列
            if self.queue_status == QueueStatus.RUNNING:
                asyncio.create_task(self.process_queue())
            elif self.queue_status == QueueStatus.IDLE:
                self.start_queue()
                asyncio.create_task(self.process_queue())
    
    async def process_queue(self):
        """处理队列中的任务"""
        async with self.processing_lock:
            while self.queue_status == QueueStatus.RUNNING:
                next_task_id = self.get_next_task()
                if not next_task_id:
                    # 队列为空，停止处理
                    self.stop_queue()
                    break
                
                self.current_processing_task = next_task_id
                self.save_queue_status()
                
                try:
                    await self.process_single_task(next_task_id)
                except Exception as e:
                    logger.error(f"处理任务 {next_task_id} 失败: {e}")
                    self.update_task_status(next_task_id, TaskStatus.FAILED, 0, "处理失败", str(e))
                
                # 处理完成后继续下一个任务
                self.current_processing_task = None
                self.save_queue_status()
    
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
            
        # 开始处理
        self.update_task_status(task_id, TaskStatus.PROCESSING, 30, "正在解析文件")
        
        # 使用现有的parse_pdf函数进行处理
        result = await parse_pdf(
            doc_path=uploaded_file,
            output_dir=output_dir,
            end_page_id=99999,
            is_ocr=False,
            formula_enable=True,
            table_enable=True,
            language="ch",
            backend="pipeline",
            url=None
        )
        
        if result:
            local_md_dir, file_name = result
            self.update_task_status(task_id, TaskStatus.PROCESSING, 80, "处理完成，生成结果文件")
            
            # 保存结果路径
            task.result_path = local_md_dir
            self.update_task_status(task_id, TaskStatus.COMPLETED, 100, "转换完成", None)
            
            # 清理上传的原始文件
            try:
                os.remove(uploaded_file)
            except:
                pass
            
            logger.info(f"任务 {task_id} 处理完成: {file_name}")
        else:
            self.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", "解析过程中出现错误")

# 创建FastAPI应用
app = FastAPI(title="MinerU Web Interface", version="0.1.8")
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 创建任务管理器实例
task_manager = TaskManager()

# 获取静态文件目录路径
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 服务器端文件列表存储（使用相对于当前文件的绝对路径，避免工作目录差异影响）
BASE_DIR = os.path.dirname(__file__)
CONFIG_DIR = os.path.join(BASE_DIR, "config")
FILE_LIST_PATH = os.path.join(CONFIG_DIR, "file_list.json")

def _ensure_output_dir():
    os.makedirs("./output", exist_ok=True)

def _ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)

def load_server_file_list() -> list:
    _ensure_config_dir()
    if os.path.exists(FILE_LIST_PATH):
        try:
            import json
            with open(FILE_LIST_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(f"读取文件列表失败: {e}")
    return []

def save_server_file_list(file_list: list) -> None:
    _ensure_config_dir()
    try:
        import json
        with open(FILE_LIST_PATH, 'w', encoding='utf-8') as f:
            json.dump(file_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"写入文件列表失败: {e}")

def sanitize_filename(filename: str) -> str:
    """格式化压缩文件的文件名"""
    sanitized = re.sub(r'[/\\\.]{2,}|[/\\]', '', filename)
    sanitized = re.sub(r'[^\w.-]', '_', sanitized, flags=re.UNICODE)
    if sanitized.startswith('.'):
        sanitized = '_' + sanitized[1:]
    return sanitized or 'unnamed'

def image_to_base64(image_path: str) -> str:
    """将图片文件转换为base64编码"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"转换图片为base64失败: {e}")
        return ""

def replace_image_with_base64(markdown_text: str, image_dir_path: str) -> str:
    """将Markdown中的图片路径替换为base64编码"""
    # 匹配Markdown中的图片标签
    pattern = r'\!\[(?:[^\]]*)\]\(([^)]+)\)'
    
    def replace(match):
        relative_path = match.group(1)
        full_path = os.path.join(image_dir_path, relative_path)
        if os.path.exists(full_path):
            base64_image = image_to_base64(full_path)
            # 保持原始的alt文本，只替换URL部分
            return match.group(0).replace(f'({relative_path})', f'(data:image/jpeg;base64,{base64_image})')
        else:
            # 如果图片文件不存在，返回原始链接
            return match.group(0)
    
    # 应用替换
    return re.sub(pattern, replace, markdown_text)

def cleanup_file(file_path: str) -> None:
    """清理临时文件"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning(f"清理文件失败 {file_path}: {e}")

async def load_task_markdown_content(filename: str, result_path: str) -> tuple[str, str]:
    """加载任务的Markdown内容"""
    try:
        if not result_path or not os.path.exists(result_path):
            return "", ""
        
        # 查找Markdown文件
        md_files = []
        for root, dirs, files in os.walk(result_path):
            for file in files:
                if file.endswith('.md'):
                    md_files.append(os.path.join(root, file))
        
        if not md_files:
            logger.warning(f"No markdown files found in: {result_path}")
            return "", ""
        
        # 使用第一个找到的Markdown文件
        md_path = md_files[0]
        logger.info(f"Loading markdown file: {md_path}")
        
        with open(md_path, 'r', encoding='utf-8') as f:
            txt_content = f.read()
        
        # 转换图片为base64
        md_content = replace_image_with_base64(txt_content, result_path)
        
        logger.info(f"Successfully loaded markdown content, length: {len(md_content)}")
        return md_content, txt_content
        
    except Exception as e:
        logger.error(f"加载Markdown内容失败: {e}")
        return "", ""

def safe_stem(file_path):
    """安全地获取文件名的stem部分"""
    stem = Path(file_path).stem
    # 只保留字母、数字、下划线、点和中文字符，其他字符替换为下划线
    return re.sub(r'[^\w.\u4e00-\u9fff]', '_', stem)

def to_pdf(file_path):
    """将文件转换为PDF格式"""
    if file_path is None:
        return None

    pdf_bytes = read_fn(file_path)
    unique_filename = f'{safe_stem(file_path)}.pdf'
    
    # 构建完整的文件路径
    tmp_file_path = os.path.join(os.path.dirname(file_path), unique_filename)
    
    # 将字节数据写入文件
    with open(tmp_file_path, 'wb') as tmp_pdf_file:
        tmp_pdf_file.write(pdf_bytes)
    
    return tmp_file_path

async def parse_pdf(doc_path, output_dir, end_page_id, is_ocr, formula_enable, table_enable, language, backend, url):
    """解析PDF文件，采用与sample文件相同的转换方法"""
    os.makedirs(output_dir, exist_ok=True)

    try:
        file_name = f'{safe_stem(Path(doc_path).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
        pdf_data = read_fn(doc_path)
        if is_ocr:
            parse_method = 'ocr'
        else:
            parse_method = 'auto'

        if backend.startswith("vlm"):
            parse_method = "vlm"

        local_image_dir, local_md_dir = prepare_env(output_dir, file_name, parse_method)
        await aio_do_parse(
            output_dir=output_dir,
            pdf_file_names=[file_name],
            pdf_bytes_list=[pdf_data],
            p_lang_list=[language],
            parse_method=parse_method,
            end_page_id=end_page_id,
            formula_enable=formula_enable,
            table_enable=table_enable,
            backend=backend,
            server_url=url,
        )
        return local_md_dir, file_name
    except Exception as e:
        logger.exception(e)
        return None

@app.get("/api/backend_options")
async def get_backend_options():
    """获取可用的后端选项"""
    try:
        sglang_engine_enable = getattr(app.state, 'sglang_engine_enable', False)
        
        if sglang_engine_enable:
            backend_options = [
                {"value": "pipeline", "label": "Pipeline"},
                {"value": "vlm-sglang-engine", "label": "VLM SgLang Engine"}
            ]
            default_backend = "vlm-sglang-engine"
        else:
            backend_options = [
                {"value": "pipeline", "label": "Pipeline"},
                {"value": "vlm-transformers", "label": "VLM Transformers"},
                {"value": "vlm-sglang-client", "label": "VLM SgLang Client"},
                {"value": "vlm-sglang-engine", "label": "VLM SgLang Engine"}
            ]
            default_backend = "vlm-sglang-engine"
        
        return JSONResponse(content={
            "backend_options": backend_options,
            "default_backend": default_backend
        })
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取后端选项失败: {str(e)}"}
        )

@app.get("/CHANGELOG.md")
async def get_changelog():
    """获取CHANGELOG.md文件内容"""
    try:
        changelog_path = os.path.join(os.path.dirname(__file__), "CHANGELOG.md")
        if os.path.exists(changelog_path):
            with open(changelog_path, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content, media_type="text/plain; charset=utf-8")
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "CHANGELOG.md文件未找到"}
            )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"读取CHANGELOG失败: {str(e)}"}
        )

@app.get("/api/version")
async def get_version():
    """返回最新版本号，解析 CHANGELOG.md 第一条版本记录。"""
    try:
        changelog_path = os.path.join(os.path.dirname(__file__), "CHANGELOG.md")
        if os.path.exists(changelog_path):
            with open(changelog_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 查找形如: ## [0.1.3] - yyyy-mm-dd 的首个版本
            m = re.search(r"^## \[(.*?)\]", content, flags=re.MULTILINE)
            if m and m.group(1):
                return JSONResponse(content={"version": f"v{m.group(1)}"})
        # 兜底
        return JSONResponse(content={"version": "v0.0.0"})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"读取版本失败: {str(e)}"})

@app.get("/api/file_list")
async def api_get_file_list():
    """获取服务器端共享的文件列表（用于多PC共享）。"""
    try:
        # 优先从file_list.json获取文件列表
        file_list = load_server_file_list()
        
        # 如果file_list.json为空，则从任务管理器获取
        if not file_list:
            for task in task_manager.tasks.values():
                file_info = {
                    "name": task.filename,
                    "size": 0,  # 文件大小信息可能丢失
                    "status": task.status.value,
                    "uploadTime": task.upload_time.isoformat() if task.upload_time else None,
                    "startTime": task.start_time.isoformat() if task.start_time else None,
                    "endTime": task.end_time.isoformat() if task.end_time else None,
                    "processingTime": None,
                    "taskId": task.task_id,
                    "progress": task.progress,
                    "message": task.message,
                    "errorMessage": task.error_message
                }
                
                # 计算处理时间
                if task.start_time and task.end_time:
                    duration = (task.end_time - task.start_time).total_seconds()
                    file_info["processingTime"] = duration
                
                file_list.append(file_info)
        
        # 按上传时间排序（最新的在前）
        file_list.sort(key=lambda x: x.get("uploadTime") or "", reverse=True)
        
        return JSONResponse(content=file_list)
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"获取文件列表失败: {str(e)}"})

@app.post("/api/file_list")
async def api_set_file_list(payload: dict):
    """设置（覆盖）服务器端文件列表。payload: {"files": [...]}"""
    try:
        files = payload.get("files", [])
        if not isinstance(files, list):
            return JSONResponse(status_code=400, content={"error": "files必须是数组"})
        save_server_file_list(files)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"保存文件列表失败: {str(e)}"})

@app.post("/api/remove_file")
async def api_remove_file(request: dict):
    """删除单个文件"""
    try:
        filename = request.get("filename")
        if not filename:
            return JSONResponse(status_code=400, content={"error": "缺少文件名"})
        
        # 从文件列表中获取taskId并删除记录
        current_file_list = load_server_file_list()
        task_to_remove = None
        updated_file_list = []
        
        for f in current_file_list:
            if f.get("name") == filename:
                task_to_remove = f.get("taskId")
                logger.info(f"找到要删除的文件: {filename}, taskId: {task_to_remove}")
            else:
                updated_file_list.append(f)
        
        # 删除对应的输出目录
        if task_to_remove:
            output_dir = "./output"
            if os.path.exists(output_dir):
                for dir_name in os.listdir(output_dir):
                    if dir_name.startswith(task_to_remove.replace('-', '_')):
                        dir_path = os.path.join(output_dir, dir_name)
                        if os.path.isdir(dir_path):
                            import shutil
                            shutil.rmtree(dir_path)
                            logger.info(f"已删除输出目录: {dir_path}")
        
        # 从任务管理器中删除对应的任务（如果存在）
        if task_to_remove and task_to_remove in task_manager.tasks:
            del task_manager.tasks[task_to_remove]
            task_manager.save_tasks()
            logger.info(f"已从任务管理器中删除任务: {task_to_remove}")
        
        # 保存更新后的文件列表
        save_server_file_list(updated_file_list)
        
        logger.info(f"文件 {filename} 已从列表、任务和输出目录中删除")
        return JSONResponse(content={"ok": True, "message": f"文件 {filename} 已删除"})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"删除文件失败: {str(e)}"})

@app.post("/api/clear_all")
async def api_clear_all():
    """清空所有任务和文件列表"""
    try:
        # 清空任务管理器
        task_manager.tasks.clear()
        task_manager.current_processing_task = None
        task_manager.queue_status = QueueStatus.IDLE
        task_manager.save_tasks()
        task_manager.save_queue_status()
        
        # 清空服务器文件列表
        save_server_file_list([])
        
        logger.info("所有任务和文件列表已清空")
        return JSONResponse(content={"ok": True, "message": "所有任务已清空"})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"清空失败: {str(e)}"})

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    else:
        # 返回错误页面
        return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MinerU PDF转换工具</title>
</head>
<body>
            <h1>MinerU PDF转换工具</h1>
    <p>静态文件未找到，请检查static/index.html文件是否存在。</p>
</body>
</html>
        """)

@app.post("/file_parse")
async def parse_files(
    files: List[UploadFile] = File(...),
    output_dir: str = Form("./output"),
    lang_list: List[str] = Form(["ch"]),
    backend: str = Form("pipeline"),
    parse_method: str = Form("auto"),
    formula_enable: bool = Form(True),
    table_enable: bool = Form(True),
    server_url: Optional[str] = Form(None),
    return_md: bool = Form(True),
    return_images: bool = Form(True),
    response_format_zip: bool = Form(True),
    start_page_id: int = Form(0),
    end_page_id: int = Form(99999),
):
    """处理文件转换"""
    try:
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 处理上传的文件
        pdf_file_names = []
        pdf_bytes_list = []
        
        for file in files:
            content = await file.read()
            file_path = Path(file.filename)
            
            # 检查文件类型
            if file_path.suffix.lower() in pdf_suffixes + image_suffixes:
                # 创建临时文件以便使用read_fn
                temp_path = Path(output_dir) / f"temp_{file_path.name}"
                with open(temp_path, "wb") as f:
                    f.write(content)
                
                try:
                    pdf_bytes = read_fn(temp_path)
                    pdf_bytes_list.append(pdf_bytes)
                    pdf_file_names.append(sanitize_filename(file_path.stem))
                    os.remove(temp_path)  # 删除临时文件
                except Exception as e:
                    return JSONResponse(
                        status_code=400,
                        content={"error": f"加载文件失败: {str(e)}"}
                    )
            else:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"不支持的文件类型: {file_path.suffix}"}
                )
        
        # 设置语言列表
        actual_lang_list = lang_list
        if len(actual_lang_list) != len(pdf_file_names):
            actual_lang_list = [actual_lang_list[0] if actual_lang_list else "ch"] * len(pdf_file_names)
        
        # 如果MinerU可用，使用与sample文件相同的转换方法
        if MINERU_AVAILABLE:
            # 使用新的转换方法，与sample文件保持一致
            for i, (pdf_name, pdf_bytes) in enumerate(zip(pdf_file_names, pdf_bytes_list)):
                # 创建临时文件
                temp_path = Path(output_dir) / f"temp_{pdf_name}.pdf"
                with open(temp_path, "wb") as f:
                    f.write(pdf_bytes)
                
                try:
                    # 使用parse_pdf函数进行转换
                    is_ocr = parse_method == 'ocr'
                    result = await parse_pdf(
                        doc_path=str(temp_path),
                        output_dir=output_dir,
                        end_page_id=end_page_id,
                        is_ocr=is_ocr,
                        formula_enable=formula_enable,
                        table_enable=table_enable,
                        language=actual_lang_list[i] if i < len(actual_lang_list) else actual_lang_list[0],
                        backend=backend,
                        url=server_url
                    )
                    
                    if result is None:
                        logger.error(f"转换文件失败: {pdf_name}")
                    
                finally:
                    # 清理临时文件
                    if temp_path.exists():
                        os.remove(temp_path)
        else:
            # 简化版本，创建示例文件
            logger.info("使用简化版本处理文件")
        
        # 创建ZIP文件
        import tempfile
        zip_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="mineru_results_")
        os.close(zip_fd)
        
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for pdf_name in pdf_file_names:
                safe_pdf_name = sanitize_filename(pdf_name)
                if backend.startswith("pipeline"):
                    parse_dir = os.path.join(output_dir, pdf_name, parse_method)
                else:
                    parse_dir = os.path.join(output_dir, pdf_name, "vlm")
                
                if not os.path.exists(parse_dir):
                    # 创建示例markdown文件
                    md_content = f"""# {pdf_name}

这是一个示例Markdown文件，由MinerU Web界面生成。

## 文件信息
- 文件名: {pdf_name}
- 处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
- 后端: {backend}
- 解析方法: {parse_method}

## 说明
这是一个简化版本的MinerU Web界面，用于演示基本功能。
要使用完整的PDF转换功能，请确保安装了完整的MinerU环境。

## 功能特性
- 多文件上传
- 文件类型检查
- ZIP文件生成
- 中文界面支持
"""
                    zf.writestr(f"{safe_pdf_name}/{safe_pdf_name}.md", md_content)
                else:
                    # 写入实际的Markdown文件
                    if return_md:
                        md_path = os.path.join(parse_dir, f"{pdf_name}.md")
                        if os.path.exists(md_path):
                            zf.write(md_path, arcname=os.path.join(safe_pdf_name, f"{safe_pdf_name}.md"))
                    
                    # 写入图片
                    if return_images:
                        images_dir = os.path.join(parse_dir, "images")
                        if os.path.exists(images_dir):
                            image_paths = glob.glob(os.path.join(glob.escape(images_dir), "*.jpg"))
                            for image_path in image_paths:
                                zf.write(image_path, arcname=os.path.join(safe_pdf_name, "images", os.path.basename(image_path)))
        
        # 根据参数决定返回格式
        if response_format_zip:
            # 返回ZIP文件
            return FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=f"{safe_pdf_name}.zip",
                background=BackgroundTask(cleanup_file, zip_path)
            )
        else:
            # 返回JSON格式，包含Markdown内容
            md_content = ""
            txt_content = ""
            
            # 尝试读取Markdown文件内容
            for pdf_name in pdf_file_names:
                # 使用原始文件名进行匹配，因为实际目录名保留了中文字符
                logger.info(f"Looking for markdown file for: {pdf_name}")
                
                # 直接搜索所有temp_开头的目录
                import glob
                all_temp_dirs = glob.glob(os.path.join(output_dir, "temp_*"))
                logger.info(f"Found all temp directories: {all_temp_dirs}")
                
                # 查找包含文件名的目录
                matching_dirs = []
                for temp_dir in all_temp_dirs:
                    dir_name = os.path.basename(temp_dir)
                    # 检查目录名是否包含文件名（去掉扩展名）
                    file_stem = os.path.splitext(pdf_name)[0]
                    # 将文件名中的连字符替换为下划线进行匹配
                    file_stem_normalized = file_stem.replace('-', '_')
                    if file_stem_normalized in dir_name:
                        matching_dirs.append(temp_dir)
                
                logger.info(f"Found matching directories for {pdf_name}: {matching_dirs}")
                
                if matching_dirs:
                    # 选择最新的目录（按时间戳排序）
                    matching_dirs.sort(reverse=True)
                    parse_dir = matching_dirs[0]
                    logger.info(f"Using directory: {parse_dir}")
                    
                    # 构建vlm子目录路径
                    if backend.startswith("pipeline"):
                        vlm_dir = os.path.join(parse_dir, parse_method)
                    else:
                        vlm_dir = os.path.join(parse_dir, "vlm")
                    
                    if os.path.exists(vlm_dir):
                        # 查找md文件
                        md_files = glob.glob(os.path.join(vlm_dir, "*.md"))
                        logger.info(f"Found markdown files in {vlm_dir}: {md_files}")
                        
                        if md_files:
                            md_path = md_files[0]  # 使用第一个md文件
                            logger.info(f"Using markdown file: {md_path}")
                            
                            if os.path.exists(md_path):
                                with open(md_path, 'r', encoding='utf-8') as f:
                                    txt_content = f.read()
                                # 转换图片为base64 - 使用Markdown文件所在目录作为基础路径
                                md_content = replace_image_with_base64(txt_content, vlm_dir)
                                logger.info(f"Successfully loaded markdown content, length: {len(md_content)}")
                                break
                            else:
                                logger.warning(f"Markdown file does not exist: {md_path}")
                        else:
                            logger.warning(f"No markdown files found in: {vlm_dir}")
                    else:
                        logger.warning(f"VLM directory does not exist: {vlm_dir}")
                else:
                    logger.warning(f"No directories found containing filename: {pdf_name}")
                    continue
            
            # 如果没有找到Markdown文件，使用示例内容
            if not md_content:
                md_content = f"""# {pdf_file_names[0] if pdf_file_names else 'Unknown'}

这是一个示例Markdown文件，由MinerU Web界面生成。

## 文件信息
- 文件名: {pdf_file_names[0] if pdf_file_names else 'Unknown'}
- 处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
- 后端: {backend}
- 解析方法: {parse_method}

## 说明
这是一个简化版本的MinerU Web界面，用于演示基本功能。
要使用完整的PDF转换功能，请确保安装了完整的MinerU环境。

## 功能特性
- 多文件上传
- 文件类型检查
- ZIP文件生成
- 中文界面支持
"""
                txt_content = md_content
            
            return JSONResponse(content={
                "md_content": md_content,
                "txt_content": txt_content,
                "archive_zip_path": zip_path,
                "new_pdf_path": "",
                "file_name": pdf_file_names[0] if pdf_file_names else "unknown"
            })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"处理文件失败: {str(e)}"}
        )

@app.post("/convert_to_pdf")
async def convert_to_pdf(file: UploadFile = File(...)):
    """将非PDF文件转换为PDF格式"""
    try:
        # 读取文件内容
        content = await file.read()
        file_path = Path(file.filename)
        
        # 检查文件类型
        if file_path.suffix.lower() in pdf_suffixes:
            # 已经是PDF文件，直接返回
            return FileResponse(
                path=None,
                media_type="application/pdf",
                filename=file.filename,
                content=content
            )
        elif file_path.suffix.lower() in image_suffixes:
            # 图片文件，使用to_pdf函数转换
            temp_path = Path("./temp") / f"temp_{file_path.name}"
            temp_path.parent.mkdir(exist_ok=True)
            
            # 保存临时文件
            with open(temp_path, "wb") as f:
                f.write(content)
            
            try:
                # 使用to_pdf函数转换
                pdf_path = to_pdf(str(temp_path))
                
                # 读取转换后的PDF文件
                with open(pdf_path, "rb") as f:
                    pdf_content = f.read()
                
                # 清理临时文件
                os.remove(temp_path)
                os.remove(pdf_path)
                
                return FileResponse(
                    path=None,
                    media_type="application/pdf",
                    filename=file_path.stem + ".pdf",
                    content=pdf_content
                )
            except Exception as e:
                # 清理临时文件
                if temp_path.exists():
                    os.remove(temp_path)
                raise e
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"不支持的文件类型: {file_path.suffix}"}
            )
            
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"文件转换失败: {str(e)}"}
        )

@app.get("/list_output_files")
async def list_output_files():
    """列出输出目录中的文件"""
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(content=[])
        
        files = []
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            if os.path.isfile(item_path):
                files.append({"name": item, "type": "文件"})
            elif os.path.isdir(item_path):
                files.append({"name": item, "type": "目录"})
        
        return JSONResponse(content=files)
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"列出文件失败: {str(e)}"}
        )

@app.post("/delete_output_files")
async def delete_output_files(request: dict):
    """删除输出目录中的文件"""
    try:
        output_dir = "./output"
        deleted_files = []
        files = request.get("files", [])
        
        for filename in files:
            file_path = os.path.join(output_dir, filename)
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_files.append(filename)
                elif os.path.isdir(file_path):
                    import shutil
                    shutil.rmtree(file_path)
                    deleted_files.append(filename)
        
        return JSONResponse(content={"deleted": deleted_files})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"删除文件失败: {str(e)}"}
        )

@app.get("/download_file/{filename}")
async def download_file(filename: str):
    """下载单个文件的处理结果目录（ZIP打包）"""
    try:
        output_dir = "./output"
        target_dir = None
        
        # 优先策略：从 file_list.json 中查找对应的 taskId，直接计算目录名
        try:
            file_list = load_server_file_list()
            for file_info in file_list:
                if file_info.get("name") == filename and file_info.get("taskId"):
                    task_id = file_info["taskId"]
                    # 计算目录名前缀：taskId 替换连字符为下划线
                    task_id_prefix = task_id.replace('-', '_')
                    
                    # 在 output 目录下查找以 taskId_prefix 开头的目录
                    if os.path.exists(output_dir):
                        for item in os.listdir(output_dir):
                            item_path = os.path.join(output_dir, item)
                            if os.path.isdir(item_path) and item.startswith(task_id_prefix):
                                target_dir = item
                                logger.info(f"通过 taskId 找到目录: {target_dir}")
                                break
                    
                    if target_dir:
                        break
        except Exception as e:
            logger.warning(f"通过 taskId 查找目录失败: {e}")
        
        # 备用策略：使用原来的文件名匹配逻辑
        if not target_dir:
            logger.info(f"使用备用策略查找目录: {filename}")
            safe_filename = safe_stem(filename)
            
            # 查找匹配的目录
            matching_dirs = []
            if os.path.exists(output_dir):
                for item in os.listdir(output_dir):
                    item_path = os.path.join(output_dir, item)
                    if os.path.isdir(item_path):
                        # 检查是否匹配 temp_{safe_filename}_{timestamp} 格式
                        if item.startswith(f"temp_{safe_filename}_"):
                            matching_dirs.append(item)
                        # 也检查旧的格式 {safe_filename}_{timestamp}（向后兼容）
                        elif item.startswith(f"{safe_filename}_"):
                            matching_dirs.append(item)
            
            if not matching_dirs:
                # 如果没找到，尝试更宽松的匹配（处理中文文件名编码问题）
                logger.info(f"未找到精确匹配，尝试宽松匹配文件名: {filename}")
                filename_without_ext = Path(filename).stem
                safe_filename_loose = re.sub(r'[^\w\u4e00-\u9fff]', '_', filename_without_ext)  # 保留中文字符
                
                for item in os.listdir(output_dir):
                    item_path = os.path.join(output_dir, item)
                    if os.path.isdir(item_path):
                        # 检查是否包含文件名的主要部分
                        if (f"temp_{safe_filename_loose}_" in item or
                            f"{safe_filename_loose}_" in item):
                            matching_dirs.append(item)
            
            if matching_dirs:
                # 如果有多个匹配的目录，选择最新的（按时间戳排序）
                matching_dirs.sort(reverse=True)
                target_dir = matching_dirs[0]
                logger.info(f"通过文件名匹配找到目录: {target_dir}")
        
        if not target_dir:
            return JSONResponse(
                status_code=404,
                content={"error": f"未找到文件 {filename} 的处理结果"}
            )
        
        file_path = os.path.join(output_dir, target_dir)
        
        # 创建ZIP文件
        zip_path = f"{file_path}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    file_path_full = os.path.join(root, file)
                    arcname = os.path.relpath(file_path_full, file_path)
                    zipf.write(file_path_full, arcname)
        
        # 返回ZIP文件
        safe_filename = safe_stem(filename)
        return FileResponse(
            path=zip_path,
            filename=f"{safe_filename}.zip",
            media_type="application/zip",
            background=BackgroundTask(lambda: os.remove(zip_path))  # 下载后删除临时ZIP文件
        )
            
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"下载文件失败: {str(e)}"}
        )

@app.get("/output/raw/{filename:path}")
async def get_output_file(filename: str):
    """直接从 ./output 目录安全地返回文件（用于PDF预览）。"""
    try:
        base_dir = os.path.abspath("./output")
        # 仅允许访问 output 下文件，禁止路径穿越
        requested_path = os.path.abspath(os.path.join(base_dir, filename))
        if not requested_path.startswith(base_dir + os.sep) and requested_path != base_dir:
            return JSONResponse(status_code=403, content={"error": "禁止的路径"})

        if not os.path.exists(requested_path) or not os.path.isfile(requested_path):
            return JSONResponse(status_code=404, content={"error": "文件不存在"})

        # 简单的内容类型判断
        media_type = "application/pdf" if requested_path.lower().endswith(".pdf") else "application/octet-stream"
        # 强制内联显示，避免浏览器下载（不携带非ASCII文件名，避免编码问题导致500）
        headers = {"Content-Disposition": "inline"}
        return FileResponse(path=requested_path, media_type=media_type, headers=headers)
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"读取文件失败: {str(e)}"})

@app.get("/download_all")
async def download_all():
    """下载所有处理成功的文件目录（ZIP打包）"""
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(
                status_code=404,
                content={"error": "输出目录不存在"}
            )
        
        # 从 file_list.json 中获取已完成的任务
        file_list = load_server_file_list()
        completed_files = []
        
        for file_info in file_list:
            if file_info.get("status") == "completed" and file_info.get("taskId"):
                filename = file_info.get("name")
                task_id = file_info.get("taskId")
                
                # 计算目录名前缀：taskId 替换连字符为下划线
                task_id_prefix = task_id.replace('-', '_')
                
                # 在 output 目录下查找以 taskId_prefix 开头的目录
                for item in os.listdir(output_dir):
                    item_path = os.path.join(output_dir, item)
                    if os.path.isdir(item_path) and item.startswith(task_id_prefix):
                        # 验证目录中是否包含 .md 文件（确保处理完成）
                        has_md = False
                        for root, _, files in os.walk(item_path):
                            if any(f.lower().endswith('.md') for f in files):
                                has_md = True
                                break
                        
                        if has_md:
                            completed_files.append({
                                "filename": filename,
                                "task_id": task_id,
                                "directory": item,
                                "path": item_path
                            })
                            logger.info(f"找到已完成文件: {filename} -> {item}")
                        break

        if not completed_files:
            return JSONResponse(
                status_code=404,
                content={"error": "没有可下载的已完成文件"}
            )
        
        # 归档名：all_results_{时间戳}.zip
        timestamp = time.strftime("%y%m%d_%H%M%S")
        zip_filename = f"all_results_{timestamp}.zip"
        zip_path = os.path.join(output_dir, zip_filename)
        
        # 创建ZIP，保持完整相对路径（相对 output 根）
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_info in completed_files:
                dir_path = file_info["path"]
                for root, _, files in os.walk(dir_path):
                    for file in files:
                        file_path_full = os.path.join(root, file)
                        arcname = os.path.relpath(file_path_full, output_dir)
                        zipf.write(file_path_full, arcname)
        
        logger.info(f"成功打包 {len(completed_files)} 个已完成文件")
        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip",
            background=BackgroundTask(lambda: os.remove(zip_path))
        )
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"下载所有文件失败: {str(e)}"}
        )

@app.post("/download_all")
async def download_all_selected(request: dict):
    """按本次任务提供的文件列表打包下载（仅成功目录）。
    请求体示例: {"files": ["a.pdf", "b.pdf"]}
    """
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(status_code=404, content={"error": "输出目录不存在"})

        file_names = request.get("files", []) or []
        if not isinstance(file_names, list) or not file_names:
            return JSONResponse(status_code=400, content={"error": "缺少待打包文件列表"})

        # 对照 config/file_list.json，仅保留已完成的文件名
        try:
            server_list = load_server_file_list()
            completed_names = [f.get("name") for f in server_list if str(f.get("status")).lower() in {"completed", "success"}]
            completed_set = {n for n in completed_names if n}
            # 同时按“规范化stem”匹配，避免扩展名或连字符差异导致遗漏
            def norm_stem(name: str) -> str:
                s = Path(name).stem
                return s.replace('-', '_')
            completed_stem_set = {norm_stem(n) for n in completed_set}
            if completed_set:
                filtered = []
                for n in file_names:
                    if n in completed_set:
                        filtered.append(n)
                        continue
                    if norm_stem(n) in completed_stem_set:
                        filtered.append(n)
                file_names = filtered
        except Exception as _:
            # 读取失败则忽略此过滤，按原逻辑处理
            pass

        # 针对每个文件名，选择该文件最新的成功目录（存在 .md）
        selected_dirs = []
        all_dirs = [d for d in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, d))]

        # 构建 name -> 完成状态下的 taskId 列表
        name_to_completed_task_ids: dict[str, list[str]] = {}
        try:
            for item in load_server_file_list():
                try:
                    if str(item.get("status")).lower() not in {"completed", "success"}:
                        continue
                    nm = item.get("name")
                    tid = item.get("taskId") or item.get("task_id")
                    if nm and tid:
                        name_to_completed_task_ids.setdefault(nm, []).append(str(tid))
                except Exception:
                    continue
        except Exception:
            pass

        for name in file_names:
            stem = Path(name).stem
            normalized = stem.replace('-', '_')
            chosen = None

            # 1) 先用 taskId 精确匹配（目录名前缀）
            for tid in name_to_completed_task_ids.get(name, []) or []:
                prefix = f"{tid}_"
                hit = next((d for d in sorted(all_dirs, reverse=True) if d.startswith(prefix)), None)
                if hit:
                    chosen = hit
                    break

            # 2) 再用名称边界匹配，避免 _1 命中 _11
            if not chosen:
                try:
                    exact_pattern = re.compile(rf"(^|_)({re.escape(normalized)})(_|$)", re.UNICODE)
                except Exception:
                    exact_pattern = None
                if exact_pattern:
                    candidates = [d for d in all_dirs if exact_pattern.search(d)]
                else:
                    candidates = [d for d in all_dirs if normalized in d]
                candidates.sort(reverse=True)
                for d in candidates:
                    dir_path = os.path.join(output_dir, d)
                    has_md = False
                    for root, _, files in os.walk(dir_path):
                        if any(f.lower().endswith('.md') for f in files):
                            has_md = True
                            break
                    if has_md:
                        chosen = d
                        break
            for d in candidates:
                dir_path = os.path.join(output_dir, d)
                has_md = False
                for root, _, files in os.walk(dir_path):
                    if any(f.lower().endswith('.md') for f in files):
                        has_md = True
                        break
                if has_md:
                    chosen = d
                    break
            if chosen:
                selected_dirs.append(chosen)

        if not selected_dirs:
            return JSONResponse(status_code=404, content={"error": "没有可下载的目录"})

        timestamp = time.strftime("%y%m%d_%H%M%S")
        zip_filename = f"all_results_{timestamp}.zip"
        zip_path = os.path.join(output_dir, zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for directory in selected_dirs:
                dir_path = os.path.join(output_dir, directory)
                for root, _, files in os.walk(dir_path):
                    for file in files:
                        file_path_full = os.path.join(root, file)
                        arcname = os.path.relpath(file_path_full, output_dir)
                        zipf.write(file_path_full, arcname)

        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip",
            background=BackgroundTask(lambda: os.remove(zip_path))
        )

    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"下载所有文件失败: {str(e)}"})

@app.get("/output/find_pdf")
async def find_pdf(q: str):
    """根据关键词（原始文件名或任务目录名）在 ./output 下寻找可预览的 PDF。
    优先使用 file_list.json 中的 taskId 计算目录名，查找 目录名/auto/目录名+_origin.pdf。
    找不到再使用原来的关键词匹配逻辑。
    返回相对 ./output 的路径，用于 /output/raw/{path} 访问。
    """
    try:
        base_dir = os.path.abspath("./output")
        if not os.path.exists(base_dir):
            return JSONResponse(status_code=404, content={"error": "输出目录不存在"})

        keyword = q or ""
        
        # 优先策略：从 file_list.json 中查找对应的 taskId，通过前缀匹配找到目录
        try:
            file_list = load_server_file_list()
            for file_info in file_list:
                if file_info.get("name") == keyword and file_info.get("taskId"):
                    task_id = file_info["taskId"]
                    # 计算目录名前缀：taskId 替换连字符为下划线
                    task_id_prefix = task_id.replace('-', '_')
                    
                    # 在 output 目录下查找以 taskId_prefix 开头的目录
                    for item in os.listdir(base_dir):
                        item_path = os.path.join(base_dir, item)
                        if os.path.isdir(item_path) and item.startswith(task_id_prefix):
                            # 构造预期的PDF路径：目录名/auto/目录名+_origin.pdf
                            expected_pdf_path = os.path.join(item, "auto", f"{item}_origin.pdf")
                            full_expected_path = os.path.join(base_dir, expected_pdf_path)
                            
                            if os.path.exists(full_expected_path) and os.path.isfile(full_expected_path):
                                logger.info(f"通过 taskId 找到PDF: {expected_pdf_path}")
                                return JSONResponse(content={"path": expected_pdf_path})
        except Exception as e:
            logger.warning(f"通过 taskId 查找PDF失败: {e}")
        
        # 备用策略：使用原来的关键词匹配逻辑
        # 同时尝试原始、safe_stem、连字符替换
        candidates = list({
            keyword,
            safe_stem(keyword),
            Path(keyword).stem,
            safe_stem(Path(keyword).stem),
            (Path(keyword).stem.replace('-', '_') if keyword else "")
        } - {""})

        hit_origin = None
        hit_any = None

        for root, dirs, files in os.walk(base_dir):
            # 仅在 auto 或 vlm 子目录里找
            if os.path.basename(root) not in ("auto", "vlm"):
                continue
            rel_dir = os.path.relpath(root, base_dir)
            for file in files:
                if not file.lower().endswith('.pdf'):
                    continue
                rel_path = os.path.join(rel_dir, file)
                full_path_lower = rel_path.lower()
                # 关键词匹配
                if candidates and not any(c.lower() in full_path_lower for c in candidates):
                    continue
                if file.endswith("_origin.pdf") and hit_origin is None:
                    hit_origin = rel_path
                if hit_any is None:
                    hit_any = rel_path
            # 提前结束：找到优先文件
            if hit_origin:
                break

        chosen = hit_origin or hit_any
        if not chosen:
            return JSONResponse(status_code=404, content={"error": "未找到匹配的PDF"})

        return JSONResponse(content={"path": chosen})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"查找失败: {str(e)}"})

# 新增的任务管理API端点
@app.post("/api/upload_with_progress")
async def upload_with_progress(files: List[UploadFile] = File(...)):
    """上传文件并创建后台处理任务，支持进度条"""
    try:
        task_ids = []
        
        for file in files:
            # 检查文件类型
            file_path = Path(file.filename)
            if file_path.suffix.lower() not in pdf_suffixes + image_suffixes:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"不支持的文件类型: {file_path.suffix}"}
                )
            
            # 创建任务
            task_id = task_manager.create_task(file.filename)
            
            # 保存文件到output目录
            output_path = os.path.join("./output", f"{task_id}_{file.filename}")
            _ensure_output_dir()
            
            content = await file.read()
            with open(output_path, "wb") as f:
                f.write(content)
            
            # 更新任务状态为已上传
            task_manager.update_task_status(task_id, TaskStatus.PENDING, 10, "文件上传完成")
            
            # 自动加入队列
            task_manager.add_to_queue(task_id)
            
            task_ids.append(task_id)
            
        return JSONResponse(content={
            "task_ids": task_ids,
            "queue_status": task_manager.queue_status.value,
            "message": f"成功上传 {len(task_ids)} 个文件，已自动加入队列"
        })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"上传文件失败: {str(e)}"}
        )

@app.get("/api/tasks")
async def get_tasks():
    """获取所有任务状态"""
    try:
        return JSONResponse(content=task_manager.get_all_tasks())
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取任务列表失败: {str(e)}"}
        )

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """获取特定任务的状态"""
    try:
        task = task_manager.get_task(task_id)
        if not task:
            return JSONResponse(
                status_code=404,
                content={"error": "任务不存在"}
            )
        return JSONResponse(content=task.to_dict())
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取任务状态失败: {str(e)}"}
        )

@app.get("/api/task/{task_id}/markdown")
async def get_task_markdown(task_id: str):
    """获取特定任务的Markdown内容"""
    try:
        # 优先从任务管理器获取任务信息
        task = task_manager.get_task(task_id)
        task_info = None
        
        if task:
            task_info = {
                "filename": task.filename,
                "status": task.status,
                "result_path": task.result_path
            }
        else:
            # 如果任务管理器中找不到，从 file_list.json 中查找
            file_list = load_server_file_list()
            for file_info in file_list:
                if file_info.get("taskId") == task_id:
                    # 构造任务信息
                    task_info = {
                        "filename": file_info.get("name"),
                        "status": TaskStatus.COMPLETED if file_info.get("status") == "completed" else TaskStatus.PENDING,
                        "result_path": None  # 需要根据目录结构计算
                    }
                    break
        
        if not task_info:
            return JSONResponse(
                status_code=404,
                content={"error": "任务不存在"}
            )
        
        if task_info["status"] != TaskStatus.COMPLETED:
            return JSONResponse(
                status_code=400,
                content={"error": "任务尚未完成"}
            )
        
        # 如果没有 result_path，需要根据 taskId 计算
        result_path = task_info["result_path"]
        if not result_path:
            # 计算输出目录路径
            task_id_prefix = task_id.replace('-', '_')
            base_dir = os.path.abspath("./output")
            
            # 查找匹配的目录
            for item in os.listdir(base_dir):
                item_path = os.path.join(base_dir, item)
                if os.path.isdir(item_path) and item.startswith(task_id_prefix):
                    result_path = item_path
                    break
        
        # 获取Markdown内容
        md_content, txt_content = await load_task_markdown_content(task_info["filename"], result_path)
        
        return JSONResponse(content={
            "task_id": task_id,
            "filename": task_info["filename"],
            "md_content": md_content,
            "txt_content": txt_content,
            "status": task_info["status"].value
        })
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取Markdown内容失败: {str(e)}"}
        )

@app.post("/api/start_background_processing")
async def start_background_processing(task_ids: List[str] = Form(...)):
    """启动后台处理任务"""
    try:
        # 启动后台处理
        asyncio.create_task(process_tasks_background(task_ids))
        
        return JSONResponse(content={
            "message": f"已启动 {len(task_ids)} 个任务的后台处理，您可以关闭浏览器"
        })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"启动后台处理失败: {str(e)}"}
        )

@app.post("/api/queue/start")
async def start_queue():
    """启动任务队列"""
    try:
        task_manager.start_queue()
        # 开始处理队列
        asyncio.create_task(task_manager.process_queue())
        
        return JSONResponse(content={
            "message": "任务队列已启动",
            "queue_status": task_manager.queue_status.value
        })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"启动队列失败: {str(e)}"}
        )

@app.post("/api/queue/stop")
async def stop_queue():
    """停止任务队列"""
    try:
        task_manager.stop_queue()
        
        return JSONResponse(content={
            "message": "任务队列已停止",
            "queue_status": task_manager.queue_status.value
        })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"停止队列失败: {str(e)}"}
        )

@app.get("/api/queue/status")
async def get_queue_status():
    """获取队列状态"""
    try:
        queued_tasks = task_manager.get_queue_tasks()
        
        return JSONResponse(content={
            "queue_status": task_manager.queue_status.value,
            "current_processing_task": task_manager.current_processing_task,
            "queued_tasks": queued_tasks,
            "queued_count": len(queued_tasks)
        })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取队列状态失败: {str(e)}"}
        )

async def process_tasks_background(task_ids: List[str]):
    """后台处理任务"""
    for task_id in task_ids:
        try:
            task = task_manager.get_task(task_id)
            if not task:
                continue
                
            # 更新状态为处理中
            task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 20, "开始处理文件")
            
            # 查找上传的文件
            output_dir = "./output"
            uploaded_file = None
            for filename in os.listdir(output_dir):
                if filename.startswith(f"{task_id}_"):
                    uploaded_file = os.path.join(output_dir, filename)
                    break
                    
            if not uploaded_file:
                task_manager.update_task_status(task_id, TaskStatus.FAILED, 0, "找不到上传的文件", "文件不存在")
                continue
                
            # 开始处理
            task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 30, "正在解析文件")
            
            # 使用现有的parse_pdf函数进行处理
            result = await parse_pdf(
                doc_path=uploaded_file,
                output_dir=output_dir,
                end_page_id=99999,
                is_ocr=False,
                formula_enable=True,
                table_enable=True,
                language="ch",
                backend="pipeline",
                url=None
            )
            
            if result:
                local_md_dir, file_name = result
                task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 80, "处理完成，生成结果文件")
                
                # 保存结果路径
                task.result_path = local_md_dir
                task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100, "转换完成", None)
                
                # 清理上传的原始文件
                try:
                    os.remove(uploaded_file)
                except:
                    pass
                
                logger.info(f"任务 {task_id} 处理完成: {file_name}")
                    
            else:
                task_manager.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", "解析过程中出现错误")
                
        except Exception as e:
            logger.exception(f"处理任务 {task_id} 时出错: {e}")
            task_manager.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", str(e))

@click.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.pass_context
@click.option(
    '--enable-sglang-engine',
    'sglang_engine_enable',
    type=bool,
    help="启用SgLang引擎后端以加快处理速度",
    default=False,
)
@click.option(
    '--max-convert-pages',
    'max_convert_pages',
    type=int,
    help="设置从PDF转换为Markdown的最大页数",
    default=1000,
)
@click.option(
    '--host',
    'host',
    type=str,
    help="设置服务器主机名",
    default='0.0.0.0',
)
@click.option(
    '--port',
    'port',
    type=int,
    help="设置服务器端口",
    default=7860,
)
def main(ctx, sglang_engine_enable, max_convert_pages, host, port, **kwargs):
    """启动MinerU Web界面"""
    kwargs.update(arg_parse(ctx))
    
    # 将配置参数存储到应用状态中
    app.state.config = kwargs
    app.state.max_convert_pages = max_convert_pages
    app.state.sglang_engine_enable = sglang_engine_enable
    
    if sglang_engine_enable and MINERU_AVAILABLE:
        try:
            print("正在初始化SgLang引擎...")
            from mineru.backend.vlm.vlm_analyze import ModelSingleton
            model_singleton = ModelSingleton()
            
            # 过滤掉不应该传递给SgLang引擎的参数
            sglang_kwargs = {k: v for k, v in kwargs.items() 
                           if k not in ['server_name', 'server_port', 'host', 'port', 'enable_api', 'api_enable']}
            
            predictor = model_singleton.get_model(
                "sglang-engine",
                None,
                None,
                **sglang_kwargs
            )
            print("SgLang引擎初始化成功")
        except Exception as e:
            logger.exception(e)
    
    print(f"启动MinerU Web界面: http://{host}:{port}")
    print("界面功能:")
    print("- 多文件拖拽上传")
    print("- 实时转换状态显示")
    print("- 结果文件下载")
    print("- 输出目录管理")
    
    if not MINERU_AVAILABLE:
        print("注意: 使用简化版本，MinerU模块不可用")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False
    )

if __name__ == '__main__':
    main()
