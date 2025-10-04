# Copyright (c) Opendatalab. All rights reserved.

import os
import json
import threading
from typing import List

from loguru import logger

# 服务器端文件列表存储（使用相对于当前文件的绝对路径，避免工作目录差异影响）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
FILE_LIST_PATH = os.path.join(CONFIG_DIR, "file_list.json")

# 文件锁，确保线程安全
file_list_lock = threading.Lock()


def _ensure_config_dir():
    """确保配置目录存在"""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_server_file_list() -> list:
    """加载服务器端文件列表"""
    _ensure_config_dir()
    with file_list_lock:
        if os.path.exists(FILE_LIST_PATH):
            try:
                with open(FILE_LIST_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                logger.warning(f"读取文件列表失败: {e}")
        return []


def save_server_file_list(file_list: list) -> None:
    """保存服务器端文件列表"""
    _ensure_config_dir()
    with file_list_lock:
        try:
            with open(FILE_LIST_PATH, 'w', encoding='utf-8') as f:
                json.dump(file_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"写入文件列表失败: {e}")
