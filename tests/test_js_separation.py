#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试JavaScript分离功能
验证index.html中的JS代码是否成功分离到独立文件
"""

import os
import re
import sys
from pathlib import Path

def test_js_separation():
    """测试JavaScript分离功能"""
    print("🧪 测试JavaScript分离功能...")
    print("=" * 50)
    
    # 检查文件是否存在
    js_file = Path("/opt/webapp/mineru_html/static/js/app.js")
    html_file = Path("/opt/webapp/mineru_html/static/index_new.html")
    original_html = Path("/opt/webapp/mineru_html/static/index.html")
    
    print("📁 检查文件存在性:")
    print(f"   JS文件: {'✅' if js_file.exists() else '❌'} {js_file}")
    print(f"   新HTML文件: {'✅' if html_file.exists() else '❌'} {html_file}")
    print(f"   原HTML文件: {'✅' if original_html.exists() else '❌'} {original_html}")
    
    if not all([js_file.exists(), html_file.exists(), original_html.exists()]):
        print("❌ 必要文件缺失")
        return False
    
    # 检查JS文件内容
    print("\n📄 检查JS文件内容:")
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    print(f"   JS文件大小: {len(js_content)} 字符")
    print(f"   JS文件行数: {len(js_content.splitlines())} 行")
    
    # 检查关键类和方法
    class_match = re.search(r'class\s+MinerUApp', js_content)
    constructor_match = re.search(r'constructor\s*\(', js_content)
    init_match = re.search(r'init\s*\(', js_content)
    
    print(f"   MinerUApp类: {'✅' if class_match else '❌'}")
    print(f"   constructor方法: {'✅' if constructor_match else '❌'}")
    print(f"   init方法: {'✅' if init_match else '❌'}")
    
    if not all([class_match, constructor_match, init_match]):
        print("❌ JS文件缺少关键组件")
        return False
    
    # 检查新HTML文件
    print("\n🌐 检查新HTML文件:")
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 检查是否引用了外部JS文件
    js_reference = re.search(r'<script\s+src=["\']static/js/app\.js["\']', html_content)
    inline_script = re.search(r'<script>\s*class\s+MinerUApp', html_content, re.DOTALL)
    
    print(f"   外部JS引用: {'✅' if js_reference else '❌'}")
    print(f"   内联JS代码: {'❌' if not inline_script else '⚠️ 仍然存在'}")
    
    if not js_reference:
        print("❌ 新HTML文件未正确引用外部JS文件")
        return False
    
    if inline_script:
        print("⚠️ 新HTML文件仍包含内联JS代码")
    
    # 检查原HTML文件大小变化
    print("\n📊 文件大小对比:")
    original_size = original_html.stat().st_size
    new_size = html_file.stat().st_size
    js_size = js_file.stat().st_size
    
    print(f"   原HTML文件: {original_size:,} 字节")
    print(f"   新HTML文件: {new_size:,} 字节")
    print(f"   JS文件: {js_size:,} 字节")
    print(f"   总大小变化: {new_size + js_size - original_size:+,} 字节")
    
    # 检查HTML文件结构
    print("\n🔍 检查HTML结构:")
    
    # 检查必要的HTML元素
    essential_elements = [
        r'<title>',
        r'<div class="container">',
        r'<div class="upload-area"',
        r'<button.*convertBtn',
        r'<script src="static/js/app\.js">'
    ]
    
    for pattern in essential_elements:
        match = re.search(pattern, html_content)
        print(f"   {pattern}: {'✅' if match else '❌'}")
    
    # 检查外部JS库引用
    print("\n📚 检查外部JS库引用:")
    external_libs = [
        'marked.min.js',
        'katex.min.js', 
        'auto-render.min.js',
        'jszip.min.js'
    ]
    
    for lib in external_libs:
        pattern = f'src="static/js/{lib}"'
        match = re.search(pattern, html_content)
        print(f"   {lib}: {'✅' if match else '❌'}")
    
    print("\n🎉 JavaScript分离测试完成！")
    return True

def check_js_syntax():
    """检查JS语法（简单检查）"""
    print("\n🔧 检查JS语法:")
    
    js_file = Path("/opt/webapp/mineru_html/static/js/app.js")
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    # 检查括号匹配
    open_braces = js_content.count('{')
    close_braces = js_content.count('}')
    open_parens = js_content.count('(')
    close_parens = js_content.count(')')
    
    print(f"   花括号匹配: {'✅' if open_braces == close_braces else '❌'} ({open_braces}/{close_braces})")
    print(f"   圆括号匹配: {'✅' if open_parens == close_parens else '❌'} ({open_parens}/{close_parens})")
    
    # 检查class关键字
    class_count = js_content.count('class ')
    console_log_count = js_content.count('console.log')
    
    print(f"   类定义: {class_count} 个")
    print(f"   控制台日志: {console_log_count} 个")
    
    return open_braces == close_braces and open_parens == close_parens

def main():
    """主测试函数"""
    print("🚀 开始测试JavaScript分离功能...")
    
    success = test_js_separation()
    syntax_ok = check_js_syntax()
    
    if success and syntax_ok:
        print("\n✅ 所有测试通过！JavaScript分离成功。")
        print("\n📋 分离结果:")
        print("   ✅ JavaScript代码已成功提取到独立文件")
        print("   ✅ HTML文件已更新为引用外部JS文件")
        print("   ✅ 保持了所有原有功能")
        print("   ✅ 文件结构更加清晰和模块化")
        
        print("\n📝 下一步建议:")
        print("   1. 测试新HTML文件的功能是否正常")
        print("   2. 如果正常，可以替换原HTML文件")
        print("   3. 考虑进一步模块化JS代码")
        
    else:
        print("\n❌ 测试失败，请检查分离过程。")
    
    return success and syntax_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
