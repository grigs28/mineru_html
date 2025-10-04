# Copyright (c) Opendatalab. All rights reserved.

import os


def _ensure_output_dir():
    """确保输出目录存在"""
    os.makedirs("./output", exist_ok=True)
