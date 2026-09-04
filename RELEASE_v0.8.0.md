# MinerU Web v0.8.0 发布说明

**发布日期**: 2026-09-04
**基础环境**: MinerU 3.4.5 · vllm 0.21.0 · mineru-base:3.4

## 概述

前端体验专项版本：修复文件名显示、失败原因不可见、工具栏按钮挤出屏幕三个显示问题，新增队列运行状态徽章，整体 UI 美化；同时将 MinerU 引擎从 3.3.x 升级到 3.4.5（PDF 文本提取与字体分析修复，无破坏性变更）。

## 主要变更

### 🐛 显示修复
- 文件名 URL 编码形态（`GB%2050736-2012%20…`）在 UI 中解码显示，后端存储与 API 契约不变
- 文件名中间截断控制显示长度，保留扩展名
- 失败任务卡片直接显示真实 `errorMessage`
- 输出目录工具栏按钮（刷新/全选/删除/打包下载）窄屏换行，不再溢出屏幕
- innerHTML 插入用户可控文本前统一转义（XSS 加固）

### ✨ 新功能
- header 队列状态徽章：转换中 / 空闲 / 已暂停 + 排队数，2 秒轮询实时更新

### 🎨 UI 美化
- header 品牌区重设计、控制面板分组卡片化、按钮体系语义化统一、表单 focus 态

### ⬆️ 升级
- MinerU 3.3.x → 3.4.5（pip 锁 `>=3.4.5,<3.5`），基础镜像 `mineru-base:3.4`
- VLM 模型不变（仍为 MinerU2.5-Pro-2605-1.2B），vlm-engine 后端不变，API 完全兼容

## 🔨 生产部署（192.168.0.71）

```bash
# 0) 同步代码
cd /opt/webapp/mineru_html && git pull

# 1) 重建基础镜像（mineru 3.4.5，需重新下载新增模型，约 20-40 分钟）
DOCKER_BUILDKIT=0 docker build -t mineru-base:3.4 -f docker/mineru-base.Dockerfile .

# 2) 重建定制镜像并重启
DOCKER_BUILDKIT=0 docker build -t mineru-web:latest -f docker/Dockerfile .
docker compose -f docker/compose.yaml up -d

# 3) 验证
curl http://192.168.0.71:5555/api/version
# 期望: {"version":"v0.8.0","mineru_version":"3.4.5"}
```

⚠️ 注意：
- 仍需 `DOCKER_BUILDKIT=0`（71 环境 buildkit 网络异常）
- 重建前停掉其他占显存的容器；vllm 预热约 3 分钟（healthcheck 已留 180s）
- 旧 tag `mineru-base:3.3` 镜像可保留作回滚（回滚 = `docker/Dockerfile` 改回 `FROM mineru-base:3.3` 重建）

## 兼容性

- API 路由 / 参数 / 返回值**零变更**，外部调用方无感
- `backend` 参数行为不变（任意值仍走 vlm-engine）
