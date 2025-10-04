#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入问题修复脚本
用于解决 ModuleNotFoundError: No module named 'src' 错误
"""

import sys
import os
from pathlib import Path

def fix_imports():
    """修复导入问题"""
    print("🔧 开始修复导入问题...")
    
    # 获取当前脚本目录
    script_dir = Path(__file__).parent.absolute()
    
    # 检查必要文件是否存在
    required_files = [
        "gradio_app.py",
        "src/task/models.py",
        "src/task/manager.py",
        "src/file/manager.py",
        "src/utils/vram.py"
    ]
    
    print("📋 检查必要文件...")
    missing_files = []
    for file_path in required_files:
        full_path = script_dir / file_path
        if not full_path.exists():
            missing_files.append(file_path)
            print(f"❌ 缺少文件: {file_path}")
        else:
            print(f"✅ 文件存在: {file_path}")
    
    if missing_files:
        print(f"\n❌ 发现 {len(missing_files)} 个缺失文件，请检查项目完整性。")
        return False
    
    # 检查gradio_app.py是否已包含路径设置
    gradio_app_path = script_dir / "gradio_app.py"
    with open(gradio_app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))" in content:
        print("✅ gradio_app.py 已包含路径设置")
    else:
        print("⚠️  gradio_app.py 缺少路径设置，正在修复...")
        
        # 在导入语句前添加路径设置
        lines = content.split('\n')
        new_lines = []
        imports_started = False
        
        for line in lines:
            if line.startswith('from src.') and not imports_started:
                # 在第一个src导入前添加路径设置
                new_lines.extend([
                    "# 添加当前目录到Python路径",
                    "import sys",
                    "import os",
                    "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
                    "",
                    line
                ])
                imports_started = True
            else:
                new_lines.append(line)
        
        # 写回文件
        with open(gradio_app_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print("✅ gradio_app.py 路径设置已修复")
    
    # 测试导入
    print("\n🧪 测试导入...")
    try:
        # 添加路径
        sys.path.insert(0, str(script_dir))
        
        # 测试导入
        import gradio_app
        print("✅ gradio_app 导入成功")
        
        from src.task.models import TaskStatus, QueueStatus, TaskInfo
        print("✅ 任务模型导入成功")
        
        from src.task.manager import TaskManager
        print("✅ 任务管理器导入成功")
        
        from src.file.manager import load_server_file_list, save_server_file_list
        print("✅ 文件管理器导入成功")
        
        from src.utils.vram import cleanup_vram, check_vram_available
        print("✅ 工具模块导入成功")
        
        print("\n🎉 所有导入测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 导入测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("🚀 MinerU 导入问题修复工具")
    print("=" * 50)
    
    success = fix_imports()
    
    if success:
        print("\n✅ 修复完成！现在可以使用以下方式启动：")
        print("   1. python run_gradio.py")
        print("   2. ./start_with_sglang.sh")
        print("   3. python gradio_app.py")
    else:
        print("\n❌ 修复失败，请检查错误信息。")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
