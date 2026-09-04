# MinerU Web API 调用说明

> **服务地址**: `http://192.168.0.71:5555`  
> **版本**: v0.7.1（MinerU 3.3.x + vllm 0.21.0）
> **框架**: FastAPI  
> **功能**: PDF / 图片 → Markdown 转换，支持 OCR、公式识别、表格识别

在线交互式文档（启动服务后可用）：
- Swagger UI: `http://192.168.0.71:5555/docs`
- ReDoc: `http://192.168.0.71:5555/redoc`

---

## 目录

1. [快速开始（推荐流程）](#快速开始推荐流程)
2. [核心 API](#核心-api)
3. [任务管理 API](#任务管理-api)
4. [队列控制 API](#队列控制-api)
5. [文件管理 API](#文件管理-api)
6. [下载 API](#下载-api)
7. [辅助 API](#辅助-api)
8. [完整调用示例](#完整调用示例)
9. [错误处理](#错误处理)
10. [支持的参数说明](#支持的参数说明)

---

## 快速开始（推荐流程）

使用异步队列方式，上传后立即返回，后台处理，轮询获取结果：

```bash
# 第一步：上传文件（自动创建任务并入队）
curl -X POST http://192.168.0.71:5555/api/upload_with_progress \
  -F "files=@/path/to/your.pdf"

# 返回示例：
# {
#   "task_ids": ["7d7f43e0-7028-4744-8d54-0665a38d7d90"],
#   "queue_status": "running",
#   "message": "成功上传 1 个文件，已自动加入队列"
# }

# 第二步：轮询任务状态（处理中会显示 progress 百分比）
curl -s http://192.168.0.71:5555/api/task/{task_id}

# 返回示例（处理中）：
# {
#   "task_id": "7d7f43e0-...",
#   "filename": "example.pdf",
#   "status": "processing",
#   "progress": 45,
#   "message": "正在处理PDF内容... (45%)"
# }

# 返回示例（完成）：
# {
#   "task_id": "7d7f43e0-...",
#   "filename": "example.pdf",
#   "status": "completed",
#   "progress": 100,
#   "message": "转换完成",
#   "result_path": "./output/7d7f43e0_.../vlm"
# }

# 第三步：获取 Markdown 结果
curl -s http://192.168.0.71:5555/api/task/{task_id}/markdown

# 返回示例：
# {
#   "task_id": "...",
#   "filename": "example.pdf",
#   "md_content": "# 标题\n\n正文内容...",
#   "status": "completed"
# }
```

---

## 核心 API

### POST /api/upload_with_progress — 上传文件（推荐）

上传 PDF 或图片文件，自动创建任务并加入处理队列。队列运行时自动开始处理。

**请求**：`multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `files` | File[] | 是 | 上传的文件列表，支持 PDF / PNG / JPG / JPEG / BMP / TIFF |

**响应 200**：
```json
{
  "task_ids": ["uuid1", "uuid2"],
  "queue_status": "running",
  "message": "成功上传 2 个文件，已自动加入队列"
}
```

> **注意**：同名文件如果存在未完成的任务（pending/queued/processing），不会重复创建，而是复用现有任务并重置为 pending 状态。

---

### POST /file_parse — 直接解析文件

同步提交文件并等待解析完成。适合单个文件、需要立即获取结果的场景。

**请求**：`multipart/form-data`

| 参数 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `files` | File[] | — | 是 | 上传文件列表 |
| `output_dir` | string | `"./output"` | 否 | 输出目录 |
| `lang_list` | string[] | `["ch"]` | 否 | OCR 语言列表 |
| `backend` | string | `"vlm-engine"` | 否 | 后端引擎，**可选**（兼容 `pipeline` / `vlm-sglang-engine` / `vlm-engine` 等历史值，已有外部程序在用），**无论传何值，内部一律固定走 `vlm-engine`（vllm）** |
| `parse_method` | string | `"auto"` | 否 | 解析方式 `auto`/`txt`/`ocr`；**vlm-engine 下实际统一为 `vlm`**（传其他值会被覆盖，由 VLM 模型统一处理） |
| `formula_enable` | boolean | `true` | 否 | 启用公式识别 |
| `table_enable` | boolean | `true` | 否 | 启用表格识别 |
| `server_url` | string | `null` | 否 | vlm-engine（in-process）下不使用，保留仅为兼容 |
| `return_md` | boolean | `true` | 否 | 返回 Markdown 内容 |
| `return_images` | boolean | `true` | 否 | 返回图片（base64） |
| `response_format_zip` | boolean | `true` | 否 | `true` 返回 ZIP 文件，`false` 返回 JSON |
| `start_page_id` | int | `0` | 否 | 起始页码（从 0 开始） |
| `end_page_id` | int | `99999` | 否 | 结束页码 |

**响应**：JSON（当 `response_format_zip=false`）或 ZIP 文件（默认）。

ZIP 模式下返回文件下载，JSON 模式下返回：
```json
{
  "backend": "vlm-engine",
  "version": "v0.7.1",
  "results": {
    "example": {
      "md_content": "# 标题\n内容...",
      "images": {
        "image_001.jpg": "data:image/jpeg;base64,/9j/4AAQ..."
      }
    }
  }
}
```

---

### POST /convert_to_pdf — 非 PDF 转 PDF

将图片文件（PNG/JPG 等）转为 PDF 格式。

**请求**：`multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 上传的文件 |

**响应 200**：返回转换后的 PDF 文件。

---

## 任务管理 API

### GET /api/tasks — 获取所有任务

```bash
curl http://192.168.0.71:5555/api/tasks
```

**响应**：
```json
[
  {
    "task_id": "uuid",
    "filename": "example.pdf",
    "upload_time": "2026-06-15T01:37:13.886654",
    "status": "completed",
    "progress": 100,
    "message": "转换完成",
    "start_time": "2026-06-15T01:37:13.909599",
    "end_time": "2026-06-15T01:37:29.639587",
    "result_path": "./output/xxx/vlm",
    "error_message": null
  }
]
```

任务状态（`status`）枚举：
| 状态 | 说明 |
|------|------|
| `pending` | 待处理 |
| `queued` | 已加入队列 |
| `processing` | 处理中 |
| `completed` | 已完成 |
| `failed` | 失败 |

---

### GET /api/task/{task_id} — 获取单个任务状态

```bash
curl http://192.168.0.71:5555/api/task/{task_id}
```

返回格式同 `/api/tasks` 中的单个元素。处理中时会返回 `progress` 百分比（0–100）。

---

### GET /api/task/{task_id}/markdown — 获取 Markdown 结果

任务完成后，获取解析出的 Markdown 文本内容。

```bash
curl http://192.168.0.71:5555/api/task/{task_id}/markdown
```

**响应 200**（任务已完成）：
```json
{
  "task_id": "uuid",
  "filename": "example.pdf",
  "md_content": "# 解析出的标题\n\n正文内容...",
  "txt_content": "纯文本版本...",
  "status": "completed"
}
```

**响应 400**：任务尚未完成  
**响应 404**：任务不存在

---

### POST /api/start_background_processing — 手动启动后台处理

```bash
curl -X POST http://192.168.0.71:5555/api/start_background_processing \
  -F "task_ids=uuid1" \
  -F "task_ids=uuid2"
```

**响应 200**：
```json
{
  "message": "已启动 2 个任务的后台处理，您可以关闭浏览器"
}
```

---

## 队列控制 API

### GET /api/queue/status — 获取队列状态

```bash
curl http://192.168.0.71:5555/api/queue/status
```

**响应**：
```json
{
  "queue_status": "running",
  "current_processing_task": "uuid or null",
  "queued_tasks": ["uuid1", "uuid2"],
  "queued_count": 2
}
```

`queue_status` 取值：`idle` / `running` / `stopped`

---

### POST /api/queue/start — 启动队列

```bash
curl -X POST http://192.168.0.71:5555/api/queue/start
```

**响应 200**：
```json
{
  "message": "任务队列已启动",
  "queue_status": "running"
}
```

---

### POST /api/queue/stop — 停止队列

```bash
curl -X POST http://192.168.0.71:5555/api/queue/stop
```

**响应 200**：
```json
{
  "message": "任务队列已停止",
  "queue_status": "stopped"
}
```

---

## 文件管理 API

### GET /api/file_list — 获取共享文件列表

多 PC 间共享的文件列表。

```bash
curl http://192.168.0.71:5555/api/file_list
```

---

### POST /api/file_list — 设置文件列表

合并（而非覆盖）文件列表。

```bash
curl -X POST http://192.168.0.71:5555/api/file_list \
  -H "Content-Type: application/json" \
  -d '{"files": [{"name": "a.pdf", "status": "pending"}]}'
```

---

### POST /api/remove_file — 删除单个文件

```bash
curl -X POST http://192.168.0.71:5555/api/remove_file \
  -H "Content-Type: application/json" \
  -d '{"filename": "example.pdf"}'
```

---

### POST /api/clear_all — 清空所有任务

```bash
curl -X POST http://192.168.0.71:5555/api/clear_all
```

---

## 下载 API

### GET /download_file/{filename} — 下载单个文件结果

将指定文件处理结果目录打包为 ZIP 下载。

```bash
curl -O http://192.168.0.71:5555/download_file/example.pdf
```

---

### GET /download_all — 下载全部成功结果

打包所有处理成功（status=completed）的文件结果。

```bash
curl -O http://192.168.0.71:5555/download_all
```

---

### POST /download_all — 按列表下载

指定文件列表打包下载。

```bash
curl -X POST http://192.168.0.71:5555/download_all \
  -H "Content-Type: application/json" \
  -d '{"files": ["a.pdf", "b.pdf", "output_dir/"]}'
```

---

### POST /download_all_with_progress — 带进度的批量下载

```bash
curl -X POST http://192.168.0.71:5555/download_all_with_progress \
  -H "Content-Type: application/json" \
  -d '{"files": ["a.pdf", "b.pdf"]}'

# 返回：{"task_id": "download-xxx", "message": "下载任务已创建"}（非阻塞）

# 查询下载进度：
curl http://192.168.0.71:5555/download_progress/{task_id}
```

---

### GET /api/download_zip — 直接获取 ZIP（同步，推荐）

同步直接返回 ZIP 文件，**压缩内容与「输出文件」中的打包下载完全一致**（含 `.md` / `_layout.pdf` / `_origin.pdf` / `images/` / json 等）。原有下载接口（`/download_file`、`/download_all` 等）逻辑与参数**不变**。

**参数（可选，优先级：task_id > files > 全部）**

| 参数 | 说明 | 示例 |
|------|------|------|
| `task_id` | 打包指定任务的产物 | `?task_id=7d7f43e0-...` |
| `files` | 文件名列表（逗号分隔） | `?files=a.pdf,b.pdf` |
| 无参 | 打包所有已完成文件 | `/api/download_zip` |

```bash
# 1) 按 task_id 获取单个任务 ZIP（最常用）
curl -o result.zip "http://192.168.0.71:5555/api/download_zip?task_id=7d7f43e0-7028-4744-8d54-0665a38d7d90"

# 2) 按文件名获取（多个逗号分隔）
curl -o files.zip "http://192.168.0.71:5555/api/download_zip?files=a.pdf,b.pdf"

# 3) 获取全部已完成文件
curl -o all.zip "http://192.168.0.71:5555/api/download_zip"
```

**返回**：`application/zip`（`FileResponse`），HTTP 200。zip 内结构：`<产物目录>/vlm/{*.md, *_layout.pdf, *_origin.pdf, *_content_list.json, ...}` + `images/`。

**与 `/download_all_with_progress` 的区别**：本接口**同步**直接返回 zip（一次请求即拿到），后者为**异步**（启动任务→轮询 `/download_progress`→再取 zip），适合大批量/需进度的场景。

**错误**：无匹配产物 → `404 {"error":"未找到匹配的处理结果"}`。

---

## 辅助 API

### GET /api/version — 获取版本号

返回项目版本（CHANGELOG.md 单一来源）+ MinerU 引擎版本。

```bash
curl http://192.168.0.71:5555/api/version
# → {"version": "v0.7.1", "mineru_version": "3.3.1"}
```

---

### GET /api/backend_options — 获取后端引擎选项

固定返回 `vlm-engine`（v0.7.0 起唯一后端）。

```bash
curl http://192.168.0.71:5555/api/backend_options
# → {"backend_options":[{"value":"vlm-engine","label":"VLM Engine"}],"default_backend":"vlm-engine"}
```

---

### GET /output/find_pdf?q= — 查找输出 PDF

```bash
curl "http://192.168.0.71:5555/output/find_pdf?q=供暖说明"
```

---

### GET /output/raw/{filename} — 直接获取输出文件

```bash
curl -O "http://192.168.0.71:5555/output/raw/xxx/example.md"
```

---

### GET /list_output_files — 列出输出目录文件

```bash
curl http://192.168.0.71:5555/list_output_files
```

---

### POST /delete_output_files — 删除输出目录文件

```bash
curl -X POST http://192.168.0.71:5555/delete_output_files \
  -H "Content-Type: application/json" \
  -d '{"files": ["filename.pdf", "dirname/"]}'
```

---

## 完整调用示例

### Shell 脚本

```bash
#!/bin/bash
# 上传并等待解析完成，输出 Markdown

HOST="http://192.168.0.71:5555"
PDF="$1"

if [ ! -f "$PDF" ]; then
    echo "用法: $0 <pdf文件路径>"
    exit 1
fi

# 1. 上传
echo "📤 上传文件: $PDF"
RESP=$(curl -s -X POST "$HOST/api/upload_with_progress" -F "files=@$PDF")
TASK_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_ids'][0])")
echo "✅ 任务ID: $TASK_ID"

# 2. 轮询状态
echo "⏳ 等待处理..."
while true; do
    STATUS=$(curl -s "$HOST/api/task/$TASK_ID")
    STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    PROGRESS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('progress',0))")
    echo "   状态: $STATE ($PROGRESS%)"

    if [ "$STATE" = "completed" ]; then
        echo "✅ 处理完成"
        break
    elif [ "$STATE" = "failed" ]; then
        echo "❌ 处理失败"
        echo "$STATUS"
        exit 1
    fi
    sleep 2
done

# 3. 获取 Markdown
echo "📄 Markdown 结果:"
curl -s "$HOST/api/task/$TASK_ID/markdown" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('md_content', '无内容'))
"
```

### Python 脚本

```python
import requests
import time
import sys

HOST = "http://192.168.0.71:5555"

def parse_pdf(filepath: str) -> str:
    """上传 PDF 并返回 Markdown 内容"""
    # 1. 上传
    with open(filepath, "rb") as f:
        resp = requests.post(f"{HOST}/api/upload_with_progress",
                             files={"files": (filepath, f)})
    resp.raise_for_status()
    task_id = resp.json()["task_ids"][0]
    print(f"✅ 任务ID: {task_id}")

    # 2. 轮询直到完成
    while True:
        resp = requests.get(f"{HOST}/api/task/{task_id}")
        data = resp.json()
        status = data["status"]
        progress = data.get("progress", 0)
        print(f"   {status} ({progress}%)")

        if status == "completed":
            break
        elif status == "failed":
            raise RuntimeError(f"处理失败: {data.get('error_message')}")
        time.sleep(2)

    # 3. 获取结果
    resp = requests.get(f"{HOST}/api/task/{task_id}/markdown")
    return resp.json()["md_content"]


if __name__ == "__main__":
    md = parse_pdf(sys.argv[1])
    print(md)
```

---

## 错误处理

所有 API 在出错时返回 JSON 格式错误信息：

```json
{
  "error": "错误描述信息"
}
```

常见 HTTP 状态码：

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误（文件类型不支持、任务未完成等） |
| 404 | 任务或文件不存在 |
| 422 | 请求参数校验失败 |
| 500 | 服务器内部错误 |

---

## 支持的参数说明

### 后端引擎（backend）

| 传入值 | 实际处理 |
|--------|----------|
| `vlm-engine` / `pipeline` / `vlm-sglang-engine` / `vlm-sglang-client` / …（任意） | **一律按 `vlm-engine`（vllm，底层 vllm-async-engine）处理** |

> **向后兼容**：为不破坏已有 API 调用，`backend` 仍接受历史值（`pipeline` / `vlm-sglang-engine` 等），但 v0.7.1 起内部统一固定为 `vlm-engine`，**传入值不影响实际引擎**。推荐新调用直接传 `vlm-engine`。

### 解析方式（parse_method）

| 值 | 说明 |
|----|------|
| `auto` | 自动判断（默认） |
| `txt` | 文本提取方式 |
| `ocr` | OCR 方式（适合图片型 PDF） |

### OCR 语言（lang_list）

| 值 | 语言 |
|----|------|
| `ch` | 中文（默认） |
| `en` | 英文 |
| `korean` | 韩文 |
| `japan` | 日文 |
| `chinese_cht` | 繁体中文 |
| `latin` | 拉丁语系 |
| `arabic` | 阿拉伯语 |
| `devanagari` | 天城文 |
| 等 | … |

### 支持的文件格式

- **PDF**: `.pdf`
- **图片**: `.png` `.jpg` `.jpeg` `.bmp` `.tiff` `.webp` `.gif`

---

> 文档生成日期：2026-06-17
> 基于 MinerU Web Interface v0.7.1（MinerU 3.3.x + vllm 0.21.0）
