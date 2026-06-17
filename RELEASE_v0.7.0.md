# MinerU Web v0.7.0 发布说明

## 🎉 版本概述

MinerU Web v0.7.0 是部署架构的重大升级：**基于上游 MinerU 官方 docker 方法构建**，固定使用 **vlm-engine（vllm）** 后端，前后端容器化单容器部署，并标识底层 MinerU 引擎版本。

## ✨ 主要变更

### 🐳 Docker 化部署（基于官方方法）
- **基础镜像 `mineru-base:3.3`**：采用上游 MinerU 官方 china 版 Dockerfile（daocloud 镜像 + 阿里云 pip + modelscope 模型源），内置 mineru 3.x + vllm 0.21.0 + 全部模型
- **定制镜像 `mineru-web`**：`FROM mineru-base:3.3`，叠加本仓库 FastAPI 后端 + 纯 HTML 静态前端，替代官方 mineru-gradio 入口
- **单容器部署**：前后端同容器（FastAPI 挂载 static/），in-process vlm-engine
- **docker 目录化**：`Dockerfile` / `compose.yaml` / `mineru-base.Dockerfile` / `docker-start.sh` / `README.md` 集中到 `docker/` 目录

### 🔧 后端固定 vlm-engine（vllm）
- 移除 pipeline / vlm-sglang-client / vlm-transformers 等后端选项，统一 `vlm-engine`
- `gradio_app.py` 的 `ModelSingleton.get_model` 改为 `"vlm-engine"`；底层推理框架从 sglang 切换到 **vllm**（mineru 3.x）
- 前端后端选择 `<select>` 只保留 VLM Engine（app.js 走 else 兜底，零改动）

### 🏷️ 版本标识
- 界面显示项目版本 **v0.7.0 · MinerU 3.3.x**
- `/api/version` 返回 `{version, mineru_version}`

### 🚀 生产部署（192.168.0.71）
- 停用旧 `mineru-gradio`（mineru 2.2.2 + sglang）容器
- 切换为单容器 `mineru-web`（mineru 3.x + vllm）

## 🔨 构建与部署

```bash
# 1) 基础镜像（首次，含模型下载，约 20-40 分钟）
DOCKER_BUILDKIT=0 docker build -t mineru-base:3.3 -f docker/mineru-base.Dockerfile .

# 2) 定制镜像（叠加本仓库代码）
DOCKER_BUILDKIT=0 docker build -t mineru-web:latest -f docker/Dockerfile .

# 3) 启动单容器
docker compose -f docker/compose.yaml up -d
```

## ⚠️ 环境适配说明（71 生产环境踩坑记录）
- **DNS**：daemon.json 配置稳定公共 DNS（223.5.5.5 / 114.114.114.114）
- **构建器**：必须用 `DOCKER_BUILDKIT=0`（71 环境 buildkit 容器网络异常，传统 build 走 docker daemon 网络正常）
- **apt**：容器内 apt 的 http method 存在 DNS 异常（python/pip 网络均正常），故 apt 步骤用 `|| true` 允许失败跳过；vlm-engine 后端不依赖 opencv/libgl1

## 📋 与官方的差异

官方 `mineru-gradio` 入口是 **Gradio 库原生 UI**（运行时渲染，无静态 HTML）。本定制版用 **FastAPI + 纯 HTML 前端** 替代，故容器启动命令为 `python gradio_app.py` 而非 `mineru-gradio`。

---

**发布日期**: 2026-06-17
**版本**: v0.7.0
**MinerU 引擎**: 3.3.x
**推理框架**: vllm 0.21.0
