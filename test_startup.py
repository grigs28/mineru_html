#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试服务启动（不实际启动服务）
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

def test_imports():
    """测试所有模块导入"""
    print("测试模块导入...")
    
    try:
        # 测试基础导入
        import gradio_app
        print("✅ gradio_app 导入成功")
        
        # 测试任务模块
        from src.task.models import TaskStatus, QueueStatus, TaskInfo
        from src.task.manager import TaskManager
        print("✅ 任务模块导入成功")
        
        # 测试文件模块
        from src.file.manager import load_server_file_list, save_server_file_list
        from src.file.handler import sanitize_filename
        print("✅ 文件模块导入成功")
        
        # 测试工具模块
        from src.utils.vram import cleanup_vram, check_vram_available
        print("✅ 工具模块导入成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_task_manager():
    """测试任务管理器初始化"""
    print("\n测试任务管理器...")
    
    try:
        from src.task.manager import TaskManager
        tm = TaskManager()
        print(f"✅ 任务管理器创建成功，当前任务数: {len(tm.tasks)}")
        return True
        
    except Exception as e:
        print(f"❌ 任务管理器测试失败: {e}")
        return False

def test_fastapi_app():
    """测试FastAPI应用初始化"""
    print("\n测试FastAPI应用...")
    
    try:
        import gradio_app
        app = gradio_app.app
        print(f"✅ FastAPI应用创建成功，标题: {app.title}")
        return True
        
    except Exception as e:
        print(f"❌ FastAPI应用测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始启动测试...")
    
    success = True
    
    # 测试导入
    if not test_imports():
        success = False
    
    # 测试任务管理器
    if not test_task_manager():
        success = False
    
    # 测试FastAPI应用
    if not test_fastapi_app():
        success = False
    
    if success:
        print("\n🎉 所有启动测试通过！服务可以正常启动。")
        print("\n📝 启动方式：")
        print("   1. 直接运行: python run_gradio.py")
        print("   2. 使用脚本: ./start_with_sglang.sh")
        print("   3. 原脚本: python gradio_app.py")
    else:
        print("\n❌ 启动测试失败，请检查错误信息。")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
