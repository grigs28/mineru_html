# Copyright (c) Opendatalab. All rights reserved.

import os
import re
import base64
from pathlib import Path
from typing import Tuple

from loguru import logger


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


async def load_task_markdown_content(filename: str, result_path: str) -> Tuple[str, str]:
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
