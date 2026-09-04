# MinerU Web 定制镜像
# 基于 mineru-base:3.4（mineru 3.4 + vllm + 模型已内置，由 docker/mineru-base.Dockerfile 构建），
# 叠加本仓库的 FastAPI 后端（gradio_app.py + src/）与纯 HTML 静态前端（static/）。
# 固定使用 vlm-engine（vllm）后端，替代官方 mineru-gradio 入口。
FROM mineru-base:3.4

WORKDIR /app

# 复制本仓库定制代码（build context 为项目根）
COPY gradio_app.py /app/
COPY src/ /app/src/
COPY static/ /app/static/
COPY config/ /app/config/
# CHANGELOG.md 是项目版本号单一来源（_project_version / /api/version 读取），必须带入镜像
COPY CHANGELOG.md /app/

# Web 层依赖（mineru / vllm / torch 已在 base 镜像内，这里只补 FastAPI 运行时）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple \
        fastapi==0.104.1 \
        uvicorn==0.24.0 \
        python-multipart==0.0.6 \
        loguru==0.7.2 \
        click==8.1.7

# 输出目录（与历史路径保持一致）
RUN mkdir -p /sgl-workspace/sglang/output /app/output

EXPOSE 7860

# start-period 拉长：vllm 首次加载模型耗时较长
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# base 镜像 ENTRYPOINT 会注入 MINERU_MODEL_SOURCE=local 后 exec "$@"
# 启动本仓库 FastAPI 入口（替代官方 mineru-gradio），--enable-sglang-engine 仅作启用 VLM 引擎的 bool 开关，内部走 vlm-engine
CMD ["python3", "gradio_app.py", "--host", "0.0.0.0", "--port", "7860"]
