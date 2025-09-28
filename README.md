# MinerU Web界面 - Docker版本

## 🐳 Docker部署说明

这是一个基于Docker的MinerU Web界面，提供完整的PDF和图片文档转换功能。

## 🚀 快速启动

### 使用Docker Compose（推荐）

1. **克隆仓库**
```bash
git clone https://github.com/grigs28/mineru_html.git
cd mineru_html
```

2. **启动服务**
```bash
docker-compose up -d
```

3. **访问界面**
- 打开浏览器访问: http://localhost:7860

### 使用Docker命令

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

## 📁 项目结构

```
mineru_html/
├── gradio_app.py              # 主应用文件
├── static/
│   ├── index.html             # 前端界面
│   └── styles.css             # 样式文件
├── compose.yaml               # Docker Compose配置
├── Dockerfile                 # Docker镜像构建文件
└── README.md                  # 本文档
```

## ✨ 主要功能

### 1. 多文件上传
- 支持PDF和图片文件（PNG, JPG, JPEG, BMP, TIFF）
- 拖拽上传或点击选择
- 批量文件上传，逐一处理

### 2. 智能转换
- **PDF转换**: 将PDF文档转换为Markdown格式
- **图片OCR**: 图片文件自动OCR识别
- **公式识别**: 自动识别数学公式和化学式
- **表格识别**: 智能识别表格结构

### 3. 实时状态
- **待处理**: 文件已上传，等待处理
- **处理中**: 显示开始时间和处理进度（逐一处理）
- **已完成**: 显示处理时长和结果
- **失败**: 显示错误信息

### 4. 文件管理
- **单文件下载**: 下载该文件处理结果目录中的所有文件（ZIP打包）
- **全部下载**: 打包所有处理成功的文件目录，统一下载
- **队列控制**: 当有队列正在处理时，自动禁用开始转换按钮
- 文件删除
- 结果预览

### 5. 特殊功能
- **后台处理**: 点击开始转换后可关闭浏览器，服务器后台继续处理
- **状态持久化**: 文件列表和状态在页面刷新后保持，支持多PC同时添加文件
- **逐一处理**: 文件按顺序逐一处理，避免资源冲突，确保稳定性
- **队列控制**: 当有队列正在处理时，自动禁用开始转换按钮，防止重复提交
- **实时状态**: 显示处理开始时间、处理时长等详细信息
- **智能下载**: 
  - 单文件下载：打包该文件处理结果目录中的所有文件
  - 全部下载：打包所有处理成功的文件目录，统一下载
- **输出目录显示**: 文件转换成功时在控制台和日志中显示output目录路径

## 🔧 技术特性

### 前端技术
- 纯HTML + CSS + JavaScript
- 响应式设计
- 实时状态更新
- 文件拖拽上传

### 后端技术
- FastAPI框架
- 异步文件处理
- Docker容器化
- 自动文件清理
- ZIP文件打包下载

## 🐳 Docker配置

### 环境变量
- `HOST`: 服务监听地址（默认: 0.0.0.0）
- `PORT`: 服务端口（默认: 7860）
- `MAX_CONVERT_PAGES`: 最大转换页数（默认: 1000，最大: 2000）

### 数据卷挂载
- `/sgl-workspace/sglang/output`: 输出目录
- `/usr/local/lib/python3.10/dist-packages/mineru/cli`: MinerU CLI模块

## 📊 使用流程

1. **启动服务**
```bash
docker-compose up -d
```

2. **上传文件**
- 拖拽文件到上传区域
- 或点击选择文件

3. **配置参数**
- 设置最大转换页数
- 选择后端类型
- 配置OCR选项

4. **开始转换**
- 点击"开始转换"按钮
- 文件将逐一处理，显示实时状态
- **可关闭浏览器**: 转换开始后可关闭浏览器，服务器后台继续处理

5. **下载结果**
- **单文件下载**: 下载该文件处理结果目录中的所有文件（ZIP打包）
- **全部下载**: 打包所有处理成功的文件目录，统一下载

## 🛠️ 故障排除

### 常见问题

1. **容器启动失败**
```bash
# 查看容器日志
docker-compose logs

# 检查端口占用
netstat -tlnp | grep 7860
```

2. **文件转换失败**
```bash
# 检查输出目录权限
ls -la /opt/mineru/web_mineru/output

# 查看详细日志
docker-compose logs -f
```

3. **内存不足**
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

## 🔄 更新说明

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

## 📝 开发说明

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

## 🎯 性能优化

### 资源限制
- 建议内存: 4GB+
- 建议CPU: 2核+
- 磁盘空间: 10GB+

### 文件处理特性
- **逐一处理**: 文件按顺序逐一处理，避免资源冲突
- **后台运行**: 点击开始转换后可关闭浏览器，服务器后台继续处理
- **状态持久化**: 文件列表和状态在页面刷新后保持
- **多PC支持**: 支持多台电脑同时添加文件到队列

## 📞 支持

如有问题，请提交Issue或联系维护者。

## 📄 许可证

本项目基于MIT许可证开源。

---

**立即开始使用**: `docker-compose up -d` 🚀