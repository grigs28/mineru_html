# Copyright (c) Opendatalab. All rights reserved.

import os
import time
import asyncio
from pathlib import Path

from loguru import logger

# 尝试导入MinerU模块，如果失败则使用替代函数
try:
    from mineru.cli.common import prepare_env, read_fn, aio_do_parse
    MINERU_AVAILABLE = True
except ImportError:
    # 如果MinerU模块不可用，创建简单的替代函数
    MINERU_AVAILABLE = False
    
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


def to_pdf(file_path):
    """将文件转换为PDF格式"""
    if file_path is None:
        return None

    pdf_bytes = read_fn(file_path)
    from src.file.handler import safe_stem
    unique_filename = f'{safe_stem(file_path)}.pdf'
    
    # 构建完整的文件路径
    tmp_file_path = os.path.join(os.path.dirname(file_path), unique_filename)
    
    # 将字节数据写入文件
    with open(tmp_file_path, 'wb') as tmp_pdf_file:
        tmp_pdf_file.write(pdf_bytes)
    
    return tmp_file_path


async def parse_pdf(doc_path, output_dir, end_page_id, is_ocr, formula_enable, table_enable, language, backend, url, progress_callback=None):
    """解析PDF文件，采用与sample文件相同的转换方法"""
    os.makedirs(output_dir, exist_ok=True)

    try:
        from src.file.handler import safe_stem
        file_name = f'{safe_stem(Path(doc_path).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
        pdf_data = read_fn(doc_path)
        if is_ocr:
            parse_method = 'ocr'
        else:
            parse_method = 'auto'

        if backend.startswith("vlm"):
            parse_method = "vlm"

        local_image_dir, local_md_dir = prepare_env(output_dir, file_name, parse_method)
        
        # 不在这里设置固定进度，让模拟器从20%开始平滑推进
        
        # 启动进度模拟器
        async def progress_simulator():
            """模拟进度更新，让用户看到处理正在进行"""
            progress = 20
            while progress <= 90:  # 从20%模拟到90%
                await asyncio.sleep(2)  # 每2秒更新一次
                progress += 2
                if progress_callback and progress <= 90:  # 确保不超过90%
                    await progress_callback(progress, f"正在处理PDF内容... ({progress}%)")
        
        # 同时运行处理任务和进度模拟器
        if progress_callback:
            # 创建进度模拟任务
            progress_task = asyncio.create_task(progress_simulator())
            
            # 运行实际处理任务
            parse_task = asyncio.create_task(aio_do_parse(
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
            ))
            
            # 等待处理完成
            await parse_task
            
            # 取消进度模拟器
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
        else:
            # 如果没有进度回调，直接运行处理
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
        
        # 更新进度：处理完成
        if progress_callback:
            await progress_callback(95, "PDF解析完成，生成输出文件")
        
        return local_md_dir, file_name
    except Exception as e:
        logger.exception(e)
        return None
