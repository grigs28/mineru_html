#!/bin/bash

# Docker单GPU环境启动脚本
# 解决多PDF文件处理问题

echo "🐳 启动Docker容器（单GPU环境）"
echo "📋 配置信息："
echo "   - 启用SgLang Engine后端"
echo "   - 内存限制：16GB"
echo "   - 显存限制：6GB"
echo "   - 单GPU环境优化"
echo ""

# 停止现有容器
echo "🛑 停止现有容器..."
docker-compose down

# 重新构建镜像
echo "🔨 重新构建镜像..."
docker-compose build

# 启动容器
echo "🚀 启动容器..."
docker-compose up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "🔍 检查服务状态..."
docker-compose ps

echo ""
echo "✅ Docker容器启动完成！"
echo "🌐 访问地址: http://localhost:7860"
echo ""
echo "📝 使用说明："
echo "   1. 上传多个PDF文件"
echo "   2. 点击'开始转换'"
echo "   3. 系统将逐一处理所有文件"
echo "   4. 支持后台处理，可关闭浏览器"
echo ""
echo "🔍 监控容器状态："
echo "   docker-compose logs -f"
echo ""
echo "🔍 监控显存使用："
echo "   nvidia-smi -l 1"
