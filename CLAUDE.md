# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

MinerU Web 界面（Docker 版）—— 基于 **FastAPI** 的 PDF/图片文档转 Markdown 服务，是 Opendatalab [MinerU](https://github.com/opendatalab/MinerU) 的定制 Web 封装，支持 OCR、公式识别（KaTeX）、表格识别、多文件批量队列处理。默认端口 **7860**。

## 常用命令

### 运行服务（本地）
```bash
# 推荐入口（自动修复 sys.path，避免 ModuleNotFoundError: No module named 'src'）
python run_gradio.py --enable-sglang-engine --host 0.0.0.0 --port 7860

# 单 GPU 环境（设置显存/设备环境变量）
bash tests/start_with_sglang.sh

# 直接运行（等价，但需注意工作目录与 PYTHONPATH）
python gradio_app.py --host 0.0.0.0 --port 7860
```
启动后访问 `http://localhost:7860`，交互式 API 文档在 `/docs`（Swagger）与 `/redoc`。

### Docker（v0.7.0 起：docker/ 目录化 + 单容器 vlm-engine）
docker 相关文件集中在 `docker/` 目录（`Dockerfile`、`mineru-base.Dockerfile`、`compose.yaml`、`docker-start.sh`）。
```bash
# 两段构建（必须 DOCKER_BUILDKIT=0：71 环境 buildkit 容器 apt/python DNS 异常，传统 build 走 daemon 网络正常）
DOCKER_BUILDKIT=0 docker build -t mineru-base:3.3 -f docker/mineru-base.Dockerfile .  # 基础镜像(mineru3.3+vllm+模型)
DOCKER_BUILDKIT=0 docker build -t mineru-web:latest  -f docker/Dockerfile .            # 定制镜像(叠加本仓库代码)
docker compose -f docker/compose.yaml up -d        # 启动单容器
docker compose -f docker/compose.yaml logs -f      # 日志
bash docker/docker-start.sh                        # 一键停旧+构建+启动
```

### 测试
```bash
python -m pytest tests/ -v           # 跑全部测试
python tests/test_refactoring.py     # 单独运行某个测试脚本（也可直接 python 执行）
```
`tests/` 下为 pytest 风格的 `test_xxx` 函数；仓库无 pytest 配置文件，也支持直接 `python` 执行。

### 关键 CLI 参数（`gradio_app.py` 的 click 入口）
- `--enable-sglang-engine`（默认 True）：启用 VLM SgLang 引擎后端
- `--max-convert-pages`（默认 1000）：单 PDF 最大转换页数
- `--host` / `--port`（默认 `0.0.0.0` / `7860`）

## 架构总览

### 入口与命名陷阱
- **`gradio_app.py`（约 1775 行）是唯一真正的运行入口**，但它用的是 FastAPI + uvicorn，**不是 Gradio**——名字是历史遗留。该文件内 `app = FastAPI(...)`、`@click.command` 的 `main()` 末尾 `uvicorn.run(app, ...)`。
- `run_gradio.py` 只是把项目根目录插入 `sys.path` 后调用 `gradio_app.main()`，用来规避 `src` 包导入问题。
- `fast_api.py`、`client.py`、`common.py` 是 **早期/参考实现或 MinerU 源码的本地修改副本**，直接 `from mineru...` 硬依赖 MinerU，**不是运行入口**；`gradio_app.py.sample` 是改造前的原始模板。改功能时不要误改这几个文件。
- `vlm_sglang_server.py` 是 **sglang 时代的 4 行残留**（`from ..model.vlm_sglang_model.server import main`，该相对包已不存在），v0.7.0 移除 sglang 后端后已废弃，不是运行入口。
- `fix_imports.py`、`extract_js.py`、`models_download.py` 是 **一次性维护脚本**（修导入、从 HTML 抽 JS、下载模型），非常驻运行代码。

### MinerU 依赖是可选的（优雅降级）
`gradio_app.py` 与 `src/file/pdf_processor.py` 通过 `try/except ImportError` 包裹 `from mineru...` 导入，设全局标志 `MINERU_AVAILABLE`。**无 MinerU 时服务仍能启动**（走简化替代函数），便于在无 GPU/无 MinerU 环境下做前端与路由调试。v0.7.0 起 mineru 3.x 已内置在 `mineru-base` 基础镜像中，**不再从宿主挂载 MinerU CLI**（旧 sglang 时代 `/opt/mineru/web_mineru/cli → 容器 mineru/cli` 的挂载已废弃，compose.yaml 中无此 volume）。
改 MinerU 相关逻辑时，**两处导入与降级分支都要同步**（入口处 + `pdf_processor.py`）。

### 后端引擎（v0.7.0 起固定 vlm-engine）
- **固定 `vlm-engine`（底层 vllm-async-engine）**：移除了 pipeline / vlm-sglang-client / vlm-transformers。`backend_options` 端点与前端 `<select>` 只返回 vlm-engine。
- `main()` 用官方 `mineru.cli.vlm_preload.preload_vlm_model()` 预加载引擎（**不要直接 `get_model("vlm-engine")`**——"vlm-engine" 是 `aio_do_parse` 的高层 backend 名，`get_model` 要底层名 `vllm-async-engine`，否则报 `Unsupported backend`）。
- `src/task/manager.py` 的 `process_single_task` 调 `parse_pdf` 时 backend 也必须是 `"vlm-engine"`（曾遗漏导致异步队列 `Invalid backend`）。
- **v0.7.1 起 `parse_pdf` 内部强制 `backend = "vlm-engine"`**（`src/file/pdf_processor.py`），外部传入的 backend 参数仅作向后兼容、不影响实际引擎——API 调用方传 `pipeline` 等旧值也会走 VLM 引擎，不要再在调用侧做 backend 分支逻辑。
- CLI 参数 `--enable-sglang-engine`（默认 True）保留作启用 VLM 引擎的 bool 开关（内部走 vlm-engine），向后兼容现有脚本/compose。

### 任务与状态（两层）
1. **任务状态（内存）**：`TaskManager`（`src/task/manager.py`）单例，持有 `tasks: Dict[task_id, TaskInfo]` 与 `queue_status`。状态机 `PENDING → QUEUED → PROCESSING → COMPLETED | FAILED`；队列 `QueueStatus(IDLE/RUNNING/PAUSED)`。文件 **逐一串行处理**（`processing_lock`），避免 GPU 资源冲突。**任务状态不持久化**，重启即丢失。
2. **文件列表（持久化）**：`src/file/manager.py` 把文件列表写入 `config/file_list.json`（`threading.Lock` 线程安全），保证刷新页面 / 多客户端共享同一文件列表。该 JSON 是运行时数据，已纳入 git 跟踪。

### 模块拆分（v0.6.0 重构）
```
src/task/   models.py(TaskStatus/QueueStatus/TaskInfo) · manager.py(TaskManager) · processor.py(后台处理)
src/file/   manager.py(文件列表持久化) · handler.py(文件名清洗/base64/Markdown 内容加载) · pdf_processor.py(parse_pdf/to_pdf)
src/utils/  vram.py(显存清理与可用性检查，≥1.5GB 才处理) · helpers.py(_ensure_output_dir)
```
新增任务相关功能优先落到 `src/task/`，文件操作落到 `src/file/`，`gradio_app.py` 只保留路由层。`CHANGELOG.md` 显示该重构把原 2269 行单体拆成了 8 个模块。

### 前端（纯 HTML/CSS/JS，无构建工具）
`static/index.html` 引用三个自研 JS 类（v0.6.1 从内联代码分离）：
- `app.js` → `MinerUApp`：主应用逻辑（上传、队列、状态更新、下载、预览）
- `api.js` → `MinerUAPI`：所有后端 HTTP 调用封装
- `utils.js` → `MinerUUtils`：格式化、防抖节流等工具函数
- 第三方：`marked.min.js`（Markdown）、`katex.min.js` + `auto-render.min.js`（公式）、`jszip.min.js`（ZIP 打包）
改前端时按职责分到对应文件，不要把逻辑塞回 `index.html`。

## API 路由速查
路由全部定义在 `gradio_app.py`。主要分组：
- 文档转换：`POST /file_parse`、`POST /convert_to_pdf`
- 任务/队列：`POST /api/upload_with_progress`、`GET /api/task/{id}`、`POST /api/queue/start|stop`、`GET /api/queue/status`、`POST /api/start_background_processing`
- 文件列表：`GET|POST /api/file_list`、`POST /api/remove_file`、`POST /api/clear_all`
- 下载：`GET /download_file/{name}`、`GET|POST /download_all`、`POST /download_all_with_progress`、`GET /download_progress/{task_id}`
- 输出：`GET /list_output_files`、`GET /output/raw/{path}`、`GET /output/find_pdf`
- 元信息：`GET /api/version`、`GET /api/backend_options`、`GET /CHANGELOG.md`
完整参数与示例见 `docs/API调用说明.md`（注意：该文档示例里写的是 `192.168.0.71:5555`，实际默认端口是 7860，按部署环境替换）。

## 关键约定与陷阱
- **无 lint / type-check 配置**；代码风格以现有文件为准（中文注释 + loguru 日志）。
- **版本单一来源**：项目版本只在 `CHANGELOG.md` 维护（首条 `## [x.y.z]`）；`gradio_app.py` 的 `_project_version()` 统一读取，FastAPI `version=` 与 `/api/version` 都用它，**不要在代码里硬编码版本号**。`/api/version` 另返回 `mineru_version`（从 `mineru.version.__version__` 读）。前端 `index.html` 版本文本是占位"加载中…"，由 app.js 启动时从 `/api/version` 填充。
- **docker 构建四坑**：①必须 `DOCKER_BUILDKIT=0`；②容器只有 `python3`（CMD 用 python3）；③apt 步骤用 `|| true` 允许失败（容器内 apt http method DNS 异常，python/pip 正常，vlm-engine 不依赖 libgl/fonts）；④mineru 3.x `pdf_suffixes=['pdf']`（无点），文件类型检查用 `suffix.lower().lstrip(".")`。
- Dockerfile `COPY` 了 `gradio_app.py`、`src/`、`static/`、`config/`、`CHANGELOG.md`——**新增顶层 `.py` 入口或资源需同步更新 docker/Dockerfile 与 docker/compose.yaml**。
- 全局用户指令要求：项目有修改时同步更新 `NOTICE` 文件（v0.7.0 起已建，记录 mineru/vllm 等第三方组件）。
- 显存敏感：单 GPU 互斥（vllm 预分配），启动前必须停其他占显存容器；`MINERU_VIRTUAL_VRAM_SIZE=6000`，容器内存限 16G，`ipc: host` + `shm_size: 32gb`。
- 任何对外发布/版本变更，参考现有 `RELEASE_vX.Y.Z.md` 与 `CHANGELOG.md` 的格式续写。
- **`QWEN.md` 内容已过时**（仍描述 v0.7.0 前的多后端 Pipeline/VLM Transformers/VLM SgLang 架构），以本文件（CLAUDE.md）与 CHANGELOG.md 为准；改架构时如保留 QWEN.md 需同步更新。
- `docs/` 下多份分析文档（`vlm_sglang_engine_scheduling.md`、`model_loading_analysis.md` 等）写于 sglang 时代，引用前注意时效。
