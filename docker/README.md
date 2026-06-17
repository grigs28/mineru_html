# Docker 部署说明

本目录用于 MinerU Web（定制版）的容器化部署。**单容器、in-process vlm-engine（vllm）**，前后端同容器运行。

## 文件说明

| 文件 | 作用 |
|------|------|
| `mineru-base.Dockerfile` | 构建基础镜像 `mineru-base:3.3`（上游官方 china 版，含 mineru 3.x + vllm + 模型）。一次性、耗时主要在模型下载 |
| `Dockerfile` | 构建定制镜像 `mineru-web:latest`，`FROM mineru:latest` 叠加本仓库 FastAPI 后端 + 静态前端 |
| `compose.yaml` | 单容器编排（nvidia GPU、ipc/shm、output+config 卷） |
| `docker-start.sh` | 停旧→构建→启动 |

## 构建链（两段）

```bash
# 1) 基础镜像（首次，慢：下载模型数 GB）
#    必须加 --network=host：buildkit 容器不继承 daemon.json 的 DNS，否则 apt 解析失败
docker build --network=host -t mineru-base:3.3 -f docker/mineru-base.Dockerfile .

# 2) 定制镜像（快：仅叠加本仓库代码 + web 依赖）
docker compose -f docker/compose.yaml build
```

## 启动

```bash
bash docker/docker-start.sh
# 或
docker compose -f docker/compose.yaml up -d
```

## 与官方的差异

官方 `mineru-gradio` 入口是 **Gradio 库原生 UI**（运行时渲染，无静态 HTML）。本定制版用 **FastAPI + 纯 HTML 前端** 替代它，故容器启动命令为 `python gradio_app.py` 而非 `mineru-gradio`。后端固定 `vlm-engine`。

## 关键约束

- **单 GPU 互斥**：vllm 预分配显存，启动前必须停止其他占显存的容器（如旧 `mineru-gradio`）。
- **CUDA 版本**：默认基础镜像为 CUDA 13.0；若 71 驱动不支持，改用 `mineru-base.Dockerfile` 中的 `cu129` 变体。
- **卷**：`/opt/mineru/web_mineru/output` 与 `/opt/mineru/web_mineru/config` 需在宿主预先创建（`config` 内放初始 `file_list.json`，可为 `[]`）。
