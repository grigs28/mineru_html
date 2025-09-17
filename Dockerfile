FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY gradio_app.py /app/
COPY static/ /app/static/

# 安装Python依赖
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    loguru \
    click

# 创建输出目录
RUN mkdir -p /sgl-workspace/sglang/output

# 暴露端口
EXPOSE 7860

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# 启动命令
CMD ["python", "gradio_app.py", "--host", "0.0.0.0", "--port", "7860"]
