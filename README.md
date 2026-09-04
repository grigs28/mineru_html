# MinerU Web 界面（定制版）

基于 [Opendatalab MinerU](https://github.com/opendatalab/MinerU) 的 Web 封装，提供 PDF/图片文档转 Markdown 服务。

> **v0.7.x**：基于官方 MinerU docker 构建，固定 **vlm-engine（vllm）** 后端，单容器部署。

- 后端：FastAPI + mineru 3.x + vllm（VLM 推理）
- 前端：纯 HTML/CSS/JS（marked + KaTeX）
- 默认端口：**5555**

## 🚀 快速部署（Docker）

### 两段构建（必须 `DOCKER_BUILDKIT=0`）

```bash
git clone https://github.com/grigs28/mineru_html.git
cd mineru_html

# 1) 基础镜像（首次，含 mineru 3.x + vllm + 全部模型，约 20-40 分钟）
DOCKER_BUILDKIT=0 docker build -t mineru-base:3.4 -f docker/mineru-base.Dockerfile .

# 2) 定制镜像（叠加本仓库 FastAPI 后端 + 静态前端）
DOCKER_BUILDKIT=0 docker build -t mineru-web:latest -f docker/Dockerfile .

# 3) 启动单容器
docker compose -f docker/compose.yaml up -d
```

访问 **http://\<server_ip\>:5555** （界面显示版本号（由 /api/version 动态读取））

> 一键脚本：`bash docker/docker-start.sh`（停旧 + 构建 + 启动）

### 前置要求
- NVIDIA GPU（Volta 架构及以上，≥8GB 显存，推荐 RTX 3090 24GB）
- Docker + nvidia container toolkit
- 构建必须 `DOCKER_BUILDKIT=0`（构建注意事项见 `docker/README.md`）

## 📁 项目结构

```
mineru_html/
├── gradio_app.py            # FastAPI 主应用（路由 + click 入口）
├── src/                     # 后端模块：task/ · file/ · utils/
├── static/                  # 前端：index.html + js/{app,api,utils}.js + css/
├── config/                  # 文件列表持久化（file_list.json）
├── docker/                  # docker 化（v0.7.0 起）
│   ├── Dockerfile           # 定制镜像（FROM mineru-base:3.4）
│   ├── mineru-base.Dockerfile  # 基础镜像（官方 china 版）
│   ├── compose.yaml         # 单容器编排（5555:7860, nvidia, ipc/shm）
│   ├── docker-start.sh      # 部署脚本
│   └── README.md            # docker 详细说明
├── docs/                    # 文档（API调用说明.md 等）
├── CHANGELOG.md             # 更新日志（版本号单一来源）
└── NOTICE                   # 第三方组件声明
```

## ✨ 主要功能

- **多文件批量转换**：PDF/图片 → Markdown，逐一串行处理（避免显存冲突）
- **VLM 引擎**：固定 vlm-engine（vllm），OCR + 数学公式（KaTeX）+ 表格识别
- **实时状态**：待处理 / 处理中(进度) / 已完成 / 失败
- **预览**：点击文件列表任务卡片 → 左侧 PDF 预览（产物 layout PDF）+ 右侧 Markdown rendering / Markdown text / 输出文件
- **下载**：单文件 / 全部 ZIP 打包；**API 直接获取 ZIP**（`/api/download_zip`）
- **后台处理**：可关闭浏览器，服务端继续处理
- **状态持久化**：文件列表刷新页面 / 多客户端共享

## 🔌 API 速查

完整文档见 `docs/API调用说明.md`，交互式文档 `/docs`（Swagger）、`/redoc`。

```bash
# 上传（自动创建任务并入队）
curl -F "files=@xxx.pdf" http://<ip>:5555/api/upload_with_progress

# 轮询任务状态
curl http://<ip>:5555/api/task/{task_id}

# 获取 Markdown 结果
curl http://<ip>:5555/api/task/{task_id}/markdown

# 直接获取 ZIP（v0.7.1 新增，同步一次请求拿到）
curl -o result.zip "http://<ip>:5555/api/download_zip?task_id={task_id}"
#   ?files=a.pdf,b.pdf  按文件名
#   无参                全部已完成文件
```

## 🔧 关键约定

- **版本单一来源**：`CHANGELOG.md`（`/api/version` 动态读取，同时返回 `mineru_version`）
- **后端固定 vlm-engine**：`gradio_app.py` 用官方 `preload_vlm_model()` 预加载
- **docker 构建四坑**：`DOCKER_BUILDKIT=0` / 容器内是 `python3` / apt 步骤允许失败跳过 / 文件后缀无点比较（详见 `CLAUDE.md`）
- **单 GPU 互斥**：vllm 预分配显存，启动前必须停止其他占显存容器

## 📝 开发

```bash
# 本地调试（无 mineru 时走降级模式，仍可起服务做前端/路由调试）
python run_gradio.py --enable-sglang-engine --host 0.0.0.0 --port 7860

# 测试
python -m pytest tests/ -v
```

更多架构与约定见 `CLAUDE.md`，版本历史见 `CHANGELOG.md` 与 `RELEASE_vX.Y.Z.md`。

## 📄 许可证

见 `NOTICE`（含 MinerU / vLLM / FastAPI / 前端库等第三方组件声明）。

---

**当前版本**：见 CHANGELOG.md（MinerU 3.4.x · vllm 0.21.0）
