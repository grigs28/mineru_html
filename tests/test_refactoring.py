#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试重构后的模块功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.task.models import TaskStatus, QueueStatus, TaskInfo
from src.task.manager import TaskManager
from src.file.manager import load_server_file_list, save_server_file_list
from src.utils.vram import cleanup_vram, check_vram_available
from datetime import datetime


def test_task_models():
    """测试任务模型"""
    print("测试任务模型...")
    
    # 测试枚举
    assert TaskStatus.PENDING.value == "pending"
    assert QueueStatus.IDLE.value == "idle"
    
    # 测试TaskInfo
    task = TaskInfo("test-id", "test.pdf", datetime.now())
    assert task.task_id == "test-id"
    assert task.filename == "test.pdf"
    assert task.status == TaskStatus.PENDING
    
    # 测试to_dict方法
    task_dict = task.to_dict()
    assert "task_id" in task_dict
    assert "filename" in task_dict
    assert "status" in task_dict
    
    print("✅ 任务模型测试通过")


def test_task_manager():
    """测试任务管理器"""
    print("测试任务管理器...")
    
    manager = TaskManager()
    assert manager.queue_status == QueueStatus.IDLE
    assert len(manager.tasks) == 0
    
    # 测试创建任务
    task_id = manager.create_task("test.pdf")
    assert task_id is not None
    assert len(manager.tasks) == 1
    
    # 测试获取任务
    task = manager.get_task(task_id)
    assert task is not None
    assert task.filename == "test.pdf"
    
    # 测试更新任务状态
    manager.update_task_status(task_id, TaskStatus.PROCESSING, 50, "处理中")
    task = manager.get_task(task_id)
    assert task.status == TaskStatus.PROCESSING
    assert task.progress == 50
    assert task.message == "处理中"
    
    # 测试获取所有任务
    all_tasks = manager.get_all_tasks()
    assert len(all_tasks) == 1
    assert all_tasks[0]["task_id"] == task_id
    
    print("✅ 任务管理器测试通过")


def test_file_manager():
    """测试文件管理器"""
    print("测试文件管理器...")
    
    # 测试加载文件列表
    file_list = load_server_file_list()
    assert isinstance(file_list, list)
    
    # 测试保存文件列表
    test_data = [{"name": "test.pdf", "size": 1024}]
    save_server_file_list(test_data)
    
    # 验证保存
    loaded_data = load_server_file_list()
    assert len(loaded_data) == 1
    assert loaded_data[0]["name"] == "test.pdf"
    
    print("✅ 文件管理器测试通过")


def test_vram_utils():
    """测试显存工具"""
    print("测试显存工具...")
    
    # 测试显存检查
    available = check_vram_available()
    assert isinstance(available, bool)
    
    # 测试显存清理
    cleanup_vram()  # 应该不会抛出异常
    
    print("✅ 显存工具测试通过")


def main():
    """运行所有测试"""
    print("开始测试重构后的模块...")
    
    try:
        test_task_models()
        test_task_manager()
        test_file_manager()
        test_vram_utils()
        
        print("\n🎉 所有测试通过！重构成功！")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
