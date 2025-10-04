#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取index.html中的JavaScript代码到独立的JS文件
"""

import re

def extract_javascript():
    """从index.html中提取JavaScript代码"""
    
    # 读取HTML文件
    with open('/opt/webapp/mineru_html/static/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找<script>标签内的JavaScript代码
    script_pattern = r'<script>(.*?)</script>'
    match = re.search(script_pattern, content, re.DOTALL)
    
    if not match:
        print("❌ 未找到JavaScript代码")
        return False
    
    js_code = match.group(1).strip()
    
    # 创建JS文件
    js_file_path = '/opt/webapp/mineru_html/static/js/app.js'
    
    # 确保目录存在
    import os
    os.makedirs(os.path.dirname(js_file_path), exist_ok=True)
    
    # 写入JavaScript代码
    with open(js_file_path, 'w', encoding='utf-8') as f:
        f.write(js_code)
    
    print(f"✅ JavaScript代码已提取到: {js_file_path}")
    print(f"📏 代码长度: {len(js_code)} 字符")
    
    return js_code

def create_updated_html():
    """创建更新后的HTML文件，引用外部JS文件"""
    
    # 读取原始HTML文件
    with open('/opt/webapp/mineru_html/static/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换内联JavaScript为外部引用
    script_pattern = r'<script>(.*?)</script>'
    replacement = '<script src="static/js/app.js"></script>'
    
    updated_content = re.sub(script_pattern, replacement, content, flags=re.DOTALL)
    
    # 写入更新后的HTML文件
    updated_file_path = '/opt/webapp/mineru_html/static/index_new.html'
    with open(updated_file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ 更新后的HTML文件已创建: {updated_file_path}")
    
    return updated_content

def analyze_js_structure(js_code):
    """分析JavaScript代码结构"""
    
    print("\n📊 JavaScript代码结构分析:")
    print("=" * 50)
    
    # 统计类和方法
    class_pattern = r'class\s+(\w+)'
    classes = re.findall(class_pattern, js_code)
    print(f"📦 类数量: {len(classes)}")
    for cls in classes:
        print(f"   - {cls}")
    
    # 统计方法
    method_pattern = r'(\w+)\s*\([^)]*\)\s*\{'
    methods = re.findall(method_pattern, js_code)
    unique_methods = list(set(methods))
    print(f"🔧 方法数量: {len(unique_methods)}")
    
    # 统计行数
    lines = js_code.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]
    print(f"📏 总行数: {len(lines)}")
    print(f"📏 非空行数: {len(non_empty_lines)}")
    
    # 统计字符数
    print(f"📏 字符数: {len(js_code)}")

if __name__ == "__main__":
    print("🚀 开始提取JavaScript代码...")
    
    # 提取JavaScript代码
    js_code = extract_javascript()
    
    if js_code:
        # 分析代码结构
        analyze_js_structure(js_code)
        
        # 创建更新后的HTML文件
        create_updated_html()
        
        print("\n🎉 JavaScript代码提取完成！")
        print("\n📋 下一步:")
        print("1. 检查生成的 app.js 文件")
        print("2. 测试 index_new.html 的功能")
        print("3. 如果正常，替换原 index.html 文件")
    else:
        print("❌ JavaScript代码提取失败")
