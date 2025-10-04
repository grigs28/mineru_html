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
import gc
import threading
import tempfile
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

# 添加当前目录到Python路径
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入自定义模块
from src.task.models import TaskStatus, QueueStatus, TaskInfo
from src.task.manager import TaskManager
from src.task.processor import process_tasks_background
from src.file.manager import load_server_file_list, save_server_file_list
from src.file.handler import sanitize_filename, image_to_base64, replace_image_with_base64, cleanup_file, load_task_markdown_content, safe_stem
from src.file.pdf_processor import parse_pdf, to_pdf
from src.utils.vram import cleanup_vram, check_vram_available
from src.utils.helpers import _ensure_output_dir

# 尝试导入MinerU模块，如果失败则使用替代函数
try:
    from mineru.cli.common import pdf_suffixes, image_suffixes, read_fn
    from mineru.utils.cli_parser import arg_parse
    from mineru.utils.hash_utils import str_sha256
    MINERU_AVAILABLE = True
except ImportError:
    # 如果MinerU模块不可用，创建简单的替代函数
    MINERU_AVAILABLE = False
    pdf_suffixes = [".pdf"]
    image_suffixes = [".png", ".jpeg", ".jpg", ".webp", ".gif"]
    
    def read_fn(path):
        if not isinstance(path, Path):
            path = Path(path)
        with open(str(path), "rb") as input_file:
            return input_file.read()
    
    def arg_parse(ctx):
        return {}
    
    def str_sha256(text):
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:16]


# 创建任务管理器实例
task_manager = TaskManager()

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
        # 从file_list.json获取文件列表
        file_list = load_server_file_list()
        
        # 同时从任务管理器获取任务状态，确保一致性
        task_dict = {task.task_id: task for task in task_manager.tasks.values()}
        
        # 更新file_list中的状态与任务管理器保持一致
        for file_info in file_list:
            task_id = file_info.get("taskId")
            if task_id and task_id in task_dict:
                task = task_dict[task_id]
                # 同步任务状态到file_list
                file_info["status"] = task.status.value
                file_info["progress"] = task.progress
                file_info["message"] = task.message
                file_info["startTime"] = task.start_time.isoformat() if task.start_time else file_info.get("startTime")
                file_info["endTime"] = task.end_time.isoformat() if task.end_time else file_info.get("endTime")
                file_info["errorMessage"] = task.error_message
                file_info["result_path"] = task.result_path
                
                # 计算处理时间
                if task.start_time and task.end_time:
                    duration = (task.end_time - task.start_time).total_seconds()
                    file_info["processingTime"] = duration
                elif "startTime" in file_info and "endTime" in file_info and file_info["startTime"] and file_info["endTime"]:
                    start_time = datetime.fromisoformat(file_info["startTime"].replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(file_info["endTime"].replace('Z', '+00:00'))
                    duration = (end_time - start_time).total_seconds()
                    file_info["processingTime"] = duration
                else:
                    file_info["processingTime"] = None
        
        # 确保任务管理器中的任务也在file_list中（避免因file_list.json文件丢失导致任务信息丢失）
        for task in task_manager.tasks.values():
            # 检查是否已存在于file_list中
            existing = False
            for file_info in file_list:
                if file_info.get("taskId") == task.task_id:
                    existing = True
                    break
            
            if not existing:
                # 如果任务管理器中有但file_list中没有，则添加进去
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
                    "errorMessage": task.error_message,
                    "outputDir": task.result_path or None  # 添加输出目录字段
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
    """设置（合并）服务器端文件列表。payload: {"files": [...]}"""
    try:
        files = payload.get("files", [])
        if not isinstance(files, list):
            return JSONResponse(status_code=400, content={"error": "files必须是数组"})
        
        # 读取当前服务器文件列表
        current_file_list = load_server_file_list()
        
        # 创建当前文件列表的taskId到索引的映射
        current_task_ids = {}
        for i, file_info in enumerate(current_file_list):
            taskId = file_info.get("taskId")
            if taskId:
                current_task_ids[taskId] = i
        
        # 合并文件列表：新文件添加，已有taskId的文件更新
        for new_file in files:
            new_taskId = new_file.get("taskId")
            if new_taskId and new_taskId in current_task_ids:
                # 如果taskId存在，更新现有条目
                idx = current_task_ids[new_taskId]
                # 保留原始的size信息，更新其他字段
                original_size = current_file_list[idx].get("size", 0)
                new_file["size"] = original_size
                current_file_list[idx] = new_file
            else:
                # 如果taskId不存在，添加新条目
                current_file_list.append(new_file)
        
        # 保存合并后的文件列表
        save_server_file_list(current_file_list)
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
            # 任务已删除，无需保存到文件
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
        # 任务和队列状态已重置，无需保存到文件
        
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
        
        # 检查是否是完整的文件路径（用于进度接口生成的zip文件）
        full_path = os.path.join(output_dir, filename)
        if os.path.isfile(full_path):
            # 直接返回该文件
            return FileResponse(
                path=full_path,
                filename=os.path.basename(full_path),
                media_type="application/zip",
                background=BackgroundTask(lambda: os.remove(full_path))  # 下载后删除临时文件
            )
        
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
    """按本次任务提供的文件列表打包下载（支持文件和目录）。
    请求体示例: {"files": ["a.pdf", "b.pdf", "output_dir/"]}
    """
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(status_code=404, content={"error": "输出目录不存在"})

        file_names = request.get("files", []) or []
        if not isinstance(file_names, list) or not file_names:
            return JSONResponse(status_code=400, content={"error": "缺少待打包文件列表"})

        # 直接在输出目录中查找用户选择的文件和目录
        selected_items = []
        
        # 方法1: 直接匹配文件名和目录名
        if os.path.exists(output_dir):
            for item_name in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item_name)
                
                # 检查是否直接匹配用户选择的项目名
                for filename in file_names:
                    if item_name == filename:
                        selected_items.append({
                            'name': item_name,
                            'path': item_path,
                            'is_dir': os.path.isdir(item_path),
                            'is_file': os.path.isfile(item_path)
                        })
                        logger.info(f"直接匹配找到: {item_name} ({'目录' if os.path.isdir(item_path) else '文件'})")
                        break
                    elif os.path.isdir(item_path):
                        # 检查目录名是否包含用户选择的文件名（用于处理任务目录）
                        file_stem = Path(filename).stem
                        if (file_stem in item_name or 
                            item_name.startswith(file_stem)):
                            selected_items.append({
                                'name': item_name,
                                'path': item_path,
                                'is_dir': True,
                                'is_file': False
                            })
                            logger.info(f"目录匹配找到: {item_name} (对应文件: {filename})")
                            break
        
        # 方法2: 通过file_list.json查找对应的taskId目录（作为备用）
        if not selected_items:
            try:
                server_list = load_server_file_list()
                for filename in file_names:
                    for item in server_list:
                        if item.get("name") == filename:
                            task_id = item.get("taskId") or item.get("task_id")
                            if task_id:
                                task_id_prefix = task_id.replace('-', '_')
                                if os.path.exists(output_dir):
                                    for item_name in os.listdir(output_dir):
                                        item_path = os.path.join(output_dir, item_name)
                                        if (os.path.isdir(item_path) and 
                                            item_name.startswith(task_id_prefix)):
                                            selected_items.append({
                                                'name': item_name,
                                                'path': item_path,
                                                'is_dir': True,
                                                'is_file': False
                                            })
                                            logger.info(f"通过taskId找到目录: {item_name} (对应文件: {filename})")
                                            break
                            break
            except Exception as e:
                logger.warning(f"通过file_list.json查找目录失败: {e}")

        if not selected_items:
            return JSONResponse(status_code=404, content={"error": "没有可下载的文件或目录"})

        timestamp = time.strftime("%y%m%d_%H%M%S")
        zip_filename = f"selected_outputs_{timestamp}.zip"
        zip_path = os.path.join(output_dir, zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_items = len(selected_items)
            for i, item in enumerate(selected_items):
                item_name = item['name']
                item_path = item['path']
                
                if item['is_dir']:
                    logger.info(f"正在打包目录 {i+1}/{total_items}: {item_name}")
                    for root, _, files in os.walk(item_path):
                        for file in files:
                            file_path_full = os.path.join(root, file)
                            arcname = os.path.relpath(file_path_full, output_dir)
                            zipf.write(file_path_full, arcname)
                    logger.info(f"已打包目录 {i+1}/{total_items}: {item_name}")
                elif item['is_file']:
                    logger.info(f"正在打包文件 {i+1}/{total_items}: {item_name}")
                    arcname = os.path.relpath(item_path, output_dir)
                    zipf.write(item_path, arcname)
                    logger.info(f"已打包文件 {i+1}/{total_items}: {item_name}")

        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip",
            background=BackgroundTask(lambda: os.remove(zip_path))
        )

    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": f"下载所有文件失败: {str(e)}"})


# 用于存储打包进度的全局字典
download_progress = {}

# 新增进度追踪打包下载接口
@app.post("/download_all_with_progress")
async def download_all_with_progress(request: dict):
    """按本次任务提供的文件列表打包下载（支持文件和目录），支持进度反馈。
    请求体示例: {"files": ["a.pdf", "b.pdf", "output_dir/"]}
    """
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(status_code=404, content={"error": "输出目录不存在"})

        file_names = request.get("files", []) or []
        if not isinstance(file_names, list) or not file_names:
            return JSONResponse(status_code=400, content={"error": "缺少待打包文件列表"})

        # 直接在输出目录中查找用户选择的文件对应的目录
        selected_dirs = []
        
        # 方法1: 直接匹配文件名
        if os.path.exists(output_dir):
            for item_name in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item_name)
                if os.path.isdir(item_path):
                    # 检查目录名是否包含用户选择的文件名
                    for filename in file_names:
                        # 移除文件扩展名进行匹配
                        file_stem = Path(filename).stem
                        if (item_name == filename or 
                            file_stem in item_name or 
                            item_name.startswith(file_stem)):
                            selected_dirs.append(item_name)
                            logger.info(f"直接匹配找到目录: {item_name} (对应文件: {filename})")
                            break
        
        # 方法2: 通过file_list.json查找对应的taskId目录（作为备用）
        if not selected_dirs:
            try:
                server_list = load_server_file_list()
                for filename in file_names:
                    for item in server_list:
                        if item.get("name") == filename:
                            task_id = item.get("taskId") or item.get("task_id")
                            if task_id:
                                task_id_prefix = task_id.replace('-', '_')
                                if os.path.exists(output_dir):
                                    for item_name in os.listdir(output_dir):
                                        item_path = os.path.join(output_dir, item_name)
                                        if (os.path.isdir(item_path) and 
                                            item_name.startswith(task_id_prefix)):
                                            selected_dirs.append(item_name)
                                            logger.info(f"通过taskId找到目录: {item_name} (对应文件: {filename})")
                                            break
                            break
            except Exception as e:
                logger.warning(f"通过file_list.json查找目录失败: {e}")

        if not selected_dirs:
            return JSONResponse(status_code=404, content={"error": "没有可下载的目录"})

        # 生成唯一的任务ID用于跟踪进度
        task_id = str(uuid.uuid4())
        
        # 初始化进度
        download_progress[task_id] = {
            "status": "start",
            "message": f"开始打包 {len(selected_dirs)} 个目录",
            "current_dir": "-",
            "packed_count": 0,
            "total_count": len(selected_dirs),
            "progress": 0
        }
        
        # 创建最终的ZIP文件
        timestamp = time.strftime("%y%m%d_%H%M%S")
        zip_filename = f"all_results_with_progress_{timestamp}.zip"
        final_zip_path = os.path.join(output_dir, zip_filename)

        total_dirs = len(selected_dirs)
        
        # 异步执行打包任务
        def do_pack():
            try:
                with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as final_zip:
                    for i, directory in enumerate(selected_dirs):
                        # 更新进度
                        progress_info = {
                            "status": "packing",
                            "message": f"正在打包 {directory}",
                            "current_dir": directory,
                            "packed_count": i,
                            "total_count": total_dirs,
                            "progress": int((i / total_dirs) * 100) if total_dirs > 0 else 0
                        }
                        download_progress[task_id] = progress_info
                        logger.info(f"正在打包目录 {i+1}/{total_dirs}: {directory}")
                        
                        # 打包目录中的所有文件
                        dir_path = os.path.join(output_dir, directory)
                        for root, _, files in os.walk(dir_path):
                            for file in files:
                                file_path_full = os.path.join(root, file)
                                arcname = os.path.relpath(file_path_full, output_dir)
                                final_zip.write(file_path_full, arcname)
                        
                        # 更新完成进度
                        progress_info = {
                            "status": "packed",
                            "message": f"已打包 {directory}",
                            "current_dir": directory,
                            "packed_count": i + 1,
                            "total_count": total_dirs,
                            "progress": int(((i + 1) / total_dirs) * 100) if total_dirs > 0 else 100
                        }
                        download_progress[task_id] = progress_info
                
                # 完成
                completion_info = {
                    "status": "completed",
                    "message": f"打包完成，共打包 {total_dirs} 个目录",
                    "current_dir": "完成",
                    "packed_count": total_dirs,
                    "total_count": total_dirs,
                    "progress": 100,
                    "download_path": final_zip_path,
                    "filename": os.path.basename(final_zip_path)
                }
                download_progress[task_id] = completion_info
            except Exception as e:
                logger.exception(e)
                error_info = {
                    "status": "error",
                    "message": f"打包失败: {str(e)}",
                    "current_dir": "-",
                    "packed_count": 0,
                    "total_count": 0,
                    "progress": 0
                }
                download_progress[task_id] = error_info
        
        # 在后台线程中执行打包，这样可以返回任务ID立即
        import threading
        thread = threading.Thread(target=do_pack)
        thread.start()
        
        # 返回任务ID，前端将使用此ID查询进度
        return JSONResponse(content={
            "task_id": task_id,
            "status": "started",
            "message": "打包任务已启动",
            "total_count": len(selected_dirs)
        })

    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "message": f"启动打包任务失败: {str(e)}",
                "current_dir": "-",
                "packed_count": 0,
                "total_count": 0,
                "progress": 0
            }
        )


# 新增查询下载进度的接口
@app.get("/download_progress/{task_id}")
async def get_download_progress(task_id: str):
    """查询指定任务的下载进度"""
    try:
        if task_id in download_progress:
            return JSONResponse(content=download_progress[task_id])
        else:
            return JSONResponse(
                status_code=404, 
                content={
                    "status": "not_found",
                    "message": "任务不存在",
                    "current_dir": "-",
                    "packed_count": 0,
                    "total_count": 0,
                    "progress": 0
                }
            )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"查询进度失败: {str(e)}",
                "current_dir": "-",
                "packed_count": 0,
                "total_count": 0,
                "progress": 0
            }
        )

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
            
            # 检查是否已经有相同文件名的任务，且状态不是completed或failed
            existing_task = None
            for task in task_manager.tasks.values():
                if task.filename == file.filename and task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    existing_task = task
                    break
            
            if existing_task:
                # 如果存在未完成的相同文件任务，使用现有任务
                task_id = existing_task.task_id
                # 重新设置文件内容
                output_path = os.path.join("./output", f"{task_id}_{file.filename}")
                _ensure_output_dir()
                
                content = await file.read()
                with open(output_path, "wb") as f:
                    f.write(content)
                
                # 重置任务状态为PENDING并加入队列
                task_manager.update_task_status(task_id, TaskStatus.PENDING, 10, "文件重新上传完成")
                task_manager.add_to_queue(task_id)
            else:
                # 创建新任务
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
        asyncio.create_task(process_tasks_background(task_manager, task_ids))
        
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


@click.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.pass_context
@click.option(
    '--enable-sglang-engine',
    'sglang_engine_enable',
    type=bool,
    help="启用SgLang引擎后端以加快处理速度",
    default=True,
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
