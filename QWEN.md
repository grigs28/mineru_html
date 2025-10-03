# MinerU Web界面 - 项目文档

## 项目概述

MinerU Web界面是一个基于Docker的PDF和图片文档转换工具，提供完整的文档解析与转换功能。该工具基于FastAPI后端和HTML/CSS/JavaScript前端实现，支持将PDF和图片文件转换为Markdown格式，并具备公式识别、表格识别、OCR等功能。

项目主要特点：
- 基于Docker容器化部署，提供稳定的运行环境
- 支持多种后端（Pipeline、VLM Transformers、VLM SgLang Client、VLM SgLang Engine）
- 支持PDF和图片文件的批量上传与处理
- 提供实时状态监控和进度显示
- 支持后台处理，可关闭浏览器后继续运行
- 具备多文件队列处理能力

## 架构与组件

### 后端技术栈
- **FastAPI**: Web框架，提供API接口
- **Uvicorn**: ASGI服务器
- **Python 3.10**: 主要编程语言
- **Loguru**: 日志处理
- **Click**: 命令行参数解析

### 前端技术栈
- **纯HTML/CSS/JavaScript**: 无前端框架，轻量级实现
- **Marked.js**: Markdown渲染
- **KaTeX**: 数学公式渲染
- **JSZip**: ZIP文件处理

### 核心文件结构
```
mineru_html/
├── gradio_app.py              # 主应用文件（FastAPI后端）
├── static/
│   ├── index.html             # 前端界面
│   └── styles.css             # 样式文件
├── compose.yaml               # Docker Compose配置
├── Dockerfile                 # Docker镜像构建文件
├── client.py                  # MinerU客户端接口
├── common.py                  # 共享功能模块
├── requirements.txt           # Python依赖
└── CHANGELOG.md               # 更新日志
```

## 核心功能

### 1. 文件上传与转换
- 支持PDF和图片文件（PNG, JPG, JPEG, BMP, TIFF）
- 批量文件上传，逐一处理
- 拖拽上传或点击选择
- 支持最大转换页数设置

### 2. 多后端支持
- Pipeline: 传统处理方式
- VLM Transformers: VLM模型
- VLM SgLang Client: SgLang客户端
- VLM SgLang Engine: SgLang引擎（默认，处理速度快）

### 3. 实时状态管理
- 任务状态：待处理、队列中、处理中、已完成、失败
- 进度条显示
- 处理时间统计
- 错误信息展示

### 4. 文件管理
- 单文件下载：打包该文件处理结果目录中的所有文件
- 全部下载：打包所有处理成功的文件目录
- 文件删除功能
- 结果预览功能

### 5. 高级特性
- 后台处理：转换开始后可关闭浏览器，服务器后台继续处理
- 状态持久化：文件列表和状态在页面刷新后保持
- 多PC支持：支持多台电脑同时添加文件
- 队列控制：当有队列正在处理时，自动禁用开始转换按钮

## 部署方式

### Docker Compose部署（推荐）
```bash
# 启动服务
docker-compose up -d

# 访问界面
http://localhost:7860
```

### 环境变量
- `HOST`: 服务监听地址（默认: 0.0.0.0）
- `PORT`: 服务端口（默认: 7860）
- `MAX_CONVERT_PAGES`: 最大转换页数（默认: 1000，最大: 2000）
- `MINERU_VIRTUAL_VRAM_SIZE`: 虚拟显存大小（默认: 6000）
- `MINERU_DEVICE_MODE`: 设备模式（默认: cuda:0）
- `ENABLE_SGLANG_ENGINE`: 是否启用SgLang引擎（默认: True）

### Docker命令部署
```bash
# 构建镜像
docker build -t mineru-web .

# 运行容器
docker run -d \
  --name mineru-web \
  -p 7860:7860 \
  -v /opt/mineru/web_mineru/output:/sgl-workspace/sglang/output \
  -v /opt/mineru/web_mineru/cli:/usr/local/lib/python3.10/dist-packages/mineru/cli \
  mineru-web
```

## API接口

### 主要API端点
- `/` - 主页面
- `/api/file_list` - 获取文件列表
- `/api/tasks` - 获取所有任务状态
- `/api/task/{task_id}` - 获取特定任务状态
- `/api/upload_with_progress` - 上传文件并创建后台处理任务
- `/api/queue/start` - 启动任务队列
- `/api/queue/stop` - 停止任务队列
- `/api/queue/status` - 获取队列状态
- `/download_file/{filename}` - 下载单个文件结果
- `/download_all` - 下载所有完成文件
- `/list_output_files` - 列出输出目录文件
- `/delete_output_files` - 删除输出目录文件

## 开发与测试

### 本地开发
```bash
# 安装依赖
pip install -r requirements.txt

# 运行开发服务器
python gradio_app.py --host 0.0.0.0 --port 7860
```

### 构建镜像
```bash
# 构建Docker镜像
docker build -t mineru-web .

# 推送镜像
docker tag mineru-web:latest your-registry/mineru-web:latest
docker push your-registry/mineru-web:latest
```

## 性能优化

### 资源配置
- 建议内存: 4GB+（Docker配置16GB）
- 建议CPU: 2核+
- 磁盘空间: 10GB+
- 建议GPU: CUDA支持以启用SgLang引擎

### 处理策略
- 逐一处理：文件按顺序逐一处理，避免资源冲突
- 显存管理：自动清理显存，避免重复加载导致的显存耗尽
- 队列处理：即使某个任务失败也不会停止整个队列处理

## 系统配置

### Docker Compose配置
```yaml
version: '3.8'
services:
  mineru-web:
    build: .
    container_name: mineru-web
    ports:
      - "7860:7860"
    environment:
      - HOST=0.0.0.0
      - PORT=7860
      - MAX_CONVERT_PAGES=1000
      - MINERU_VIRTUAL_VRAM_SIZE=6000
      - MINERU_DEVICE_MODE=cuda:0
      - ENABLE_SGLANG_ENGINE=True
    volumes:
      - /opt/mineru/web_mineru/output:/sgl-workspace/sglang/output
      - /opt/mineru/web_mineru/cli:/usr/local/lib/python3.10/dist-packages/mineru/cli
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7860/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          memory: 16G
          cpus: '4.0'
        reservations:
          memory: 8G
          cpus: '2.0'
```

## 故障排除

### 常见问题
1. **容器启动失败**:
   ```bash
   # 查看容器日志
   docker-compose logs
   
   # 检查端口占用
   netstat -tlnp | grep 7860
   ```

2. **文件转换失败**:
   ```bash
   # 检查输出目录权限
   ls -la /opt/mineru/web_mineru/output
   
   # 查看详细日志
   docker-compose logs -f
   ```

3. **内存不足**:
   ```bash
   # 增加Docker内存限制
   # 在compose.yaml中调整memory限制
   ```

### 日志查看
```bash
# 查看实时日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs mineru-web
```

## 更新与维护

### 版本更新
```bash
# 拉取最新代码
git pull origin main

# 重新构建镜像
docker-compose build

# 重启服务
docker-compose up -d
```

### 数据备份
```bash
# 备份输出目录
tar -czf mineru_output_backup.tar.gz /opt/mineru/web_mineru/output
```

## 版权与许可证

本项目基于MIT许可证开源，原始代码版权归Opendatalab所有，由MinerU项目团队开发。