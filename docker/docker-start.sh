#!/bin/bash
# MinerU Web 单容器部署脚本（在 71 生产机的项目根目录执行）
# 前置：mineru-base:3.4 已由 docker/mineru-base.Dockerfile 构建（DOCKER_BUILDKIT=0）

set -e
cd "$(dirname "$0")/.."

echo "🛑 停止并移除旧容器..."
docker compose -f docker/compose.yaml down --remove-orphans 2>/dev/null \
  || docker-compose -f docker/compose.yaml down --remove-orphans

echo "🔨 构建定制镜像 mineru-web:latest..."
# 用 DOCKER_BUILDKIT=0：71 环境下 buildkit 容器网络异常，传统 build 走 docker daemon 网络（pip 正常）
DOCKER_BUILDKIT=0 docker build -t mineru-web:latest -f docker/Dockerfile .

echo "🚀 启动容器..."
docker compose -f docker/compose.yaml up -d

echo "⏳ 等待服务初始化（vllm 加载模型可能需要数分钟）..."
sleep 15
docker compose -f docker/compose.yaml ps

echo ""
echo "🌐 访问: http://<server_ip>:5555"
echo "📋 日志: docker compose -f docker/compose.yaml logs -f"
echo "🔍 显存: nvidia-smi -l 1"
