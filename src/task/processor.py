# Copyright (c) Opendatalab. All rights reserved.

import os
from typing import List

from loguru import logger

from .models import TaskStatus
from .manager import TaskManager


async def process_tasks_background(task_manager: TaskManager, task_ids: List[str]):
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
            
            # 定义进度回调函数
            async def update_progress(progress, message):
                task_manager.update_task_status(task_id, TaskStatus.PROCESSING, progress, message)
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
                backend="vlm-sglang-engine",
                url=None,
                progress_callback=update_progress
            )
            
            if result:
                local_md_dir, file_name = result
                task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 80, "处理完成，生成结果文件")
                
                # 保存结果路径
                task.result_path = local_md_dir
                task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100, "转换完成", None)
                
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
                task_manager.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", "解析过程中出现错误")
                
        except Exception as e:
            logger.exception(f"处理任务 {task_id} 时出错: {e}")
            task_manager.update_task_status(task_id, TaskStatus.FAILED, 0, "处理失败", str(e))
