# GitHub上传指南

## 📤 上传到GitHub

### 1. 配置Git用户信息（如果未配置）
```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 2. 推送到GitHub
```bash
# 推送到远程仓库
git push -u origin main
```

如果遇到认证问题，可以使用以下方法之一：

#### 方法1: 使用Personal Access Token
```bash
# 在GitHub设置中生成Personal Access Token
# 然后使用以下命令推送
git push https://your-token@github.com/grigs28/mineru_html.git main
```

#### 方法2: 使用SSH密钥
```bash
# 生成SSH密钥
ssh-keygen -t ed25519 -C "your.email@example.com"

# 将公钥添加到GitHub账户
cat ~/.ssh/id_ed25519.pub

# 修改远程URL为SSH
git remote set-url origin git@github.com:grigs28/mineru_html.git

# 推送
git push -u origin main
```

## 🐳 Docker部署测试

### 本地测试
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

# 查看日志
docker logs mineru-web

# 停止容器
docker stop mineru-web
docker rm mineru-web
```

### 使用Docker Compose
```bash
# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 📁 项目文件说明

- `gradio_app.py`: 主应用文件（基于FastAPI）
- `static/index.html`: 前端界面文件
- `static/styles.css`: 样式文件
- `compose.yaml`: Docker Compose配置
- `Dockerfile`: Docker镜像构建文件
- `requirements.txt`: Python依赖包
- `README.md`: 项目说明文档
- `DEPLOY.md`: 部署说明文档
- `UPLOAD_GUIDE.md`: 上传指南（本文件）

## ✅ 功能特点

- ✅ 逐一文件处理（非并发）
- ✅ 后台处理（可关闭浏览器）
- ✅ 状态持久化（页面刷新保持）
- ✅ 多PC支持（同时添加文件）
- ✅ 实时状态显示
- ✅ Docker容器化部署
- ✅ 响应式前端界面
