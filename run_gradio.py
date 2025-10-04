#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU Gradio App 启动脚本
确保正确的Python路径设置
"""

import sys
import os
from pathlib import Path

# 获取脚本所在目录
script_dir = Path(__file__).parent.absolute()
project_root = script_dir

# 添加项目根目录到Python路径
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置工作目录为项目根目录
os.chdir(project_root)

# 现在可以安全导入gradio_app
if __name__ == "__main__":
    try:
        import gradio_app
        gradio_app.main()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
