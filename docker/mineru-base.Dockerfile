# mineru-base:3.4 基础镜像构建文件
# 来源：上游 MinerU docker/china/Dockerfile（国内 daocloud 镜像源 + 阿里云 pip + modelscope 模型源）
# 构建命令（在项目根目录执行）：
#   docker build -t mineru-base:3.4 -f docker/mineru-base.Dockerfile .
# 含 mineru 3.4.x + vllm 0.21.0 (CUDA 13.0) + 全部模型；体积大，耗时主要在模型下载。

# 默认 CUDA 13.0；若 71 驱动不支持，改用下一行 cu129 (CUDA 12.9)
FROM docker.m.daocloud.io/vllm/vllm-openai:v0.21.0
# FROM docker.m.daocloud.io/vllm/vllm-openai:v0.21.0-cu129

# 中文字体 + opencv 依赖（可选）
# 注意：71 环境下容器内 apt 的 http method 存在 DNS 异常（getaddrinfo/python/pip 网络均正常，仅 apt 失败），
# 故用 || true 允许失败不阻断构建；vlm-engine 后端不依赖 opencv/libgl1，缺失不影响 VLM 推理。
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g; s|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    rm -f /etc/apt/sources.list.d/cuda-ubuntu2204-x86_64.list /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-jammy.list && \
    (apt-get update && apt-get install -y --no-install-recommends fonts-noto-core fonts-noto-cjk fontconfig libgl1 && fc-cache -fv) || \
    echo "WARN: apt 装包失败（容器内 apt DNS 异常），已跳过；vlm-engine 不依赖这些包" ; \
    rm -rf /var/lib/apt/lists/* 2>/dev/null ; true

# 安装 mineru 3.4.x（阿里云 pip 源；锁区间 <3.5，避免意外大版本跳跃）
RUN python3 -m pip install -U 'mineru[core]>=3.4.5,<3.5' -i https://mirrors.aliyun.com/pypi/simple --break-system-packages && \
    python3 -m pip cache purge

# 下载全部模型（modelscope 国内源）
RUN /bin/bash -c "mineru-models-download -s modelscope -m all"

# 入口：注入 MINERU_MODEL_SOURCE=local 后执行后续命令
ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
