#!/bin/bash

# 单GPU环境启动脚本 - 启用SgLang Engine
# 解决多PDF文件处理问题

echo "🚀 启动MinerU Web界面（单GPU环境）"
echo "📋 配置信息："
echo "   - 启用SgLang Engine后端（避免模型重复加载）"
echo "   - 单GPU环境优化"
echo "   - 显存限制：6GB"
echo "   - 内存限制：16GB"
echo ""

# 设置环境变量
export MINERU_DEVICE_MODE=cuda:0
export MINERU_VIRTUAL_VRAM_SIZE=6000
export HOST=0.0.0.0
export PORT=7860

echo "🔧 环境变量设置完成"
echo "   - MINERU_DEVICE_MODE=cuda:0"
echo "   - MINERU_VIRTUAL_VRAM_SIZE=6000"
echo ""

# 启动服务
echo "🎯 启动服务..."
python gradio_app.py \
    --enable-sglang-engine \
    --host 0.0.0.0 \
    --port 7860 \
    --enable-api

echo ""
echo "✅ 服务启动完成！"
echo "🌐 访问地址: http://localhost:7860"
echo ""
echo "📝 使用说明："
echo "   1. 上传多个PDF文件"
echo "   2. 点击'开始转换'"
echo "   3. 系统将逐一处理所有文件"
echo "   4. 支持后台处理，可关闭浏览器"
echo ""
echo "🔍 监控显存使用："
echo "   nvidia-smi -l 1"
