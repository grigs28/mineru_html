# Copyright (c) Opendatalab. All rights reserved.

import base64
import os
import re
import time
import zipfile
import glob
from pathlib import Path

import click
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from typing import List, Optional
from loguru import logger

# 尝试导入MinerU模块，如果失败则使用替代函数
try:
    from mineru.cli.common import prepare_env, read_fn, aio_do_parse, pdf_suffixes, image_suffixes
    from mineru.utils.cli_parser import arg_parse
    from mineru.utils.hash_utils import str_sha256
    MINERU_AVAILABLE = True
except ImportError:
    # 如果MinerU模块不可用，创建简单的替代函数
    MINERU_AVAILABLE = False
    pdf_suffixes = [".pdf"]
    image_suffixes = [".png", ".jpeg", ".jpg", ".webp", ".gif"]
    
    def prepare_env(output_dir, pdf_file_name, parse_method):
        local_md_dir = str(os.path.join(output_dir, pdf_file_name, parse_method))
        local_image_dir = os.path.join(str(local_md_dir), "images")
        os.makedirs(local_image_dir, exist_ok=True)
        os.makedirs(local_md_dir, exist_ok=True)
        return local_image_dir, local_md_dir
    
    def read_fn(path):
        if not isinstance(path, Path):
            path = Path(path)
        with open(str(path), "rb") as input_file:
            return input_file.read()
    
    async def aio_do_parse(*args, **kwargs):
        # 简化版本，不进行实际处理
        pass
    
    def arg_parse(ctx):
        return {}
    
    def str_sha256(text):
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:16]

# 创建FastAPI应用
app = FastAPI(title="MinerU Web Interface", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 获取静态文件目录路径
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=static_dir), name="static")

def sanitize_filename(filename: str) -> str:
    """格式化压缩文件的文件名"""
    sanitized = re.sub(r'[/\\\.]{2,}|[/\\]', '', filename)
    sanitized = re.sub(r'[^\w.-]', '_', sanitized, flags=re.UNICODE)
    if sanitized.startswith('.'):
        sanitized = '_' + sanitized[1:]
    return sanitized or 'unnamed'

def image_to_base64(image_path: str) -> str:
    """将图片文件转换为base64编码"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"转换图片为base64失败: {e}")
        return ""

def replace_image_with_base64(markdown_text: str, image_dir_path: str) -> str:
    """将Markdown中的图片路径替换为base64编码"""
    # 匹配Markdown中的图片标签
    pattern = r'\!\[(?:[^\]]*)\]\(([^)]+)\)'
    
    def replace(match):
        relative_path = match.group(1)
        full_path = os.path.join(image_dir_path, relative_path)
        if os.path.exists(full_path):
            base64_image = image_to_base64(full_path)
            return f'![{relative_path}](data:image/jpeg;base64,{base64_image})'
        else:
            # 如果图片文件不存在，返回原始链接
            return match.group(0)
    
    # 应用替换
    return re.sub(pattern, replace, markdown_text)

def cleanup_file(file_path: str) -> None:
    """清理临时文件"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning(f"清理文件失败 {file_path}: {e}")

def safe_stem(file_path):
    """安全地获取文件名的stem部分"""
    stem = Path(file_path).stem
    # 只保留字母、数字、下划线和点，其他字符替换为下划线
    return re.sub(r'[^\w.]', '_', stem)

def to_pdf(file_path):
    """将文件转换为PDF格式"""
    if file_path is None:
        return None

    pdf_bytes = read_fn(file_path)
    unique_filename = f'{safe_stem(file_path)}.pdf'
    
    # 构建完整的文件路径
    tmp_file_path = os.path.join(os.path.dirname(file_path), unique_filename)
    
    # 将字节数据写入文件
    with open(tmp_file_path, 'wb') as tmp_pdf_file:
        tmp_pdf_file.write(pdf_bytes)
    
    return tmp_file_path

async def parse_pdf(doc_path, output_dir, end_page_id, is_ocr, formula_enable, table_enable, language, backend, url):
    """解析PDF文件，采用与sample文件相同的转换方法"""
    os.makedirs(output_dir, exist_ok=True)

    try:
        file_name = f'{safe_stem(Path(doc_path).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
        pdf_data = read_fn(doc_path)
        if is_ocr:
            parse_method = 'ocr'
        else:
            parse_method = 'auto'

        if backend.startswith("vlm"):
            parse_method = "vlm"

        local_image_dir, local_md_dir = prepare_env(output_dir, file_name, parse_method)
        await aio_do_parse(
            output_dir=output_dir,
            pdf_file_names=[file_name],
            pdf_bytes_list=[pdf_data],
            p_lang_list=[language],
            parse_method=parse_method,
            end_page_id=end_page_id,
            formula_enable=formula_enable,
            table_enable=table_enable,
            backend=backend,
            server_url=url,
        )
        return local_md_dir, file_name
    except Exception as e:
        logger.exception(e)
        return None

@app.get("/api/backend_options")
async def get_backend_options():
    """获取可用的后端选项"""
    try:
        sglang_engine_enable = getattr(app.state, 'sglang_engine_enable', False)
        
        if sglang_engine_enable:
            backend_options = [
                {"value": "pipeline", "label": "Pipeline"},
                {"value": "vlm-sglang-engine", "label": "VLM SgLang Engine"}
            ]
            default_backend = "vlm-sglang-engine"
        else:
            backend_options = [
                {"value": "pipeline", "label": "Pipeline"},
                {"value": "vlm-transformers", "label": "VLM Transformers"},
                {"value": "vlm-sglang-client", "label": "VLM SgLang Client"},
                {"value": "vlm-sglang-engine", "label": "VLM SgLang Engine"}
            ]
            default_backend = "vlm-sglang-engine"
        
        return JSONResponse(content={
            "backend_options": backend_options,
            "default_backend": default_backend
        })
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取后端选项失败: {str(e)}"}
        )

@app.get("/CHANGELOG.md")
async def get_changelog():
    """获取CHANGELOG.md文件内容"""
    try:
        changelog_path = os.path.join(os.path.dirname(__file__), "CHANGELOG.md")
        if os.path.exists(changelog_path):
            with open(changelog_path, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content, media_type="text/plain; charset=utf-8")
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "CHANGELOG.md文件未找到"}
            )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"读取CHANGELOG失败: {str(e)}"}
        )

@app.get("/api/markdown/{filename}")
async def get_markdown_content(filename: str):
    """获取指定文件的Markdown内容，包括图片base64转换"""
    try:
        output_dir = "./output"
        safe_filename = safe_stem(filename)
        matching_dirs = []
        
        if os.path.exists(output_dir):
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isdir(item_path):
                    if item.startswith(f"temp_{safe_filename}_"):
                        matching_dirs.append(item)
                    elif item.startswith(f"{safe_filename}_"):
                        matching_dirs.append(item)
        
        if not matching_dirs:
            # 尝试宽松匹配
            filename_without_ext = Path(filename).stem
            safe_filename_loose = re.sub(r'[^\w\u4e00-\u9fff]', '_', filename_without_ext)
            
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isdir(item_path):
                    if (f"temp_{safe_filename_loose}_" in item or 
                        f"{safe_filename_loose}_" in item):
                        matching_dirs.append(item)
        
        if not matching_dirs:
            return JSONResponse(
                status_code=404,
                content={"error": f"未找到文件 {filename} 的处理结果"}
            )
        
        matching_dirs.sort(reverse=True)
        target_dir = matching_dirs[0]
        file_path = os.path.join(output_dir, target_dir)
        
        # 查找Markdown文件
        md_files = glob.glob(os.path.join(file_path, "*.md"))
        if not md_files:
            return JSONResponse(
                status_code=404,
                content={"error": f"未找到 {filename} 的Markdown文件"}
            )
        
        md_file = md_files[0]
        
        # 读取原始Markdown内容
        with open(md_file, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        # 转换图片为base64
        processed_content = replace_image_with_base64(raw_content, file_path)
        
        return JSONResponse(content={
            "raw_content": raw_content,
            "processed_content": processed_content,
            "filename": filename
        })
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取Markdown内容失败: {str(e)}"}
        )

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    else:
        # 返回错误页面
        return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MinerU PDF转换工具</title>
</head>
<body>
            <h1>MinerU PDF转换工具</h1>
    <p>静态文件未找到，请检查static/index.html文件是否存在。</p>
</body>
</html>
        """)

@app.post("/file_parse")
async def parse_files(
    files: List[UploadFile] = File(...),
    output_dir: str = Form("./output"),
    lang_list: List[str] = Form(["ch"]),
    backend: str = Form("pipeline"),
    parse_method: str = Form("auto"),
    formula_enable: bool = Form(True),
    table_enable: bool = Form(True),
    server_url: Optional[str] = Form(None),
    return_md: bool = Form(True),
    return_images: bool = Form(True),
    response_format_zip: bool = Form(True),
    start_page_id: int = Form(0),
    end_page_id: int = Form(99999),
):
    """处理文件转换"""
    try:
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 处理上传的文件
        pdf_file_names = []
        pdf_bytes_list = []
        
        for file in files:
            content = await file.read()
            file_path = Path(file.filename)
            
            # 检查文件类型
            if file_path.suffix.lower() in pdf_suffixes + image_suffixes:
                # 创建临时文件以便使用read_fn
                temp_path = Path(output_dir) / f"temp_{file_path.name}"
                with open(temp_path, "wb") as f:
                    f.write(content)
                
                try:
                    pdf_bytes = read_fn(temp_path)
                    pdf_bytes_list.append(pdf_bytes)
                    pdf_file_names.append(sanitize_filename(file_path.stem))
                    os.remove(temp_path)  # 删除临时文件
                except Exception as e:
                    return JSONResponse(
                        status_code=400,
                        content={"error": f"加载文件失败: {str(e)}"}
                    )
            else:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"不支持的文件类型: {file_path.suffix}"}
                )
        
        # 设置语言列表
        actual_lang_list = lang_list
        if len(actual_lang_list) != len(pdf_file_names):
            actual_lang_list = [actual_lang_list[0] if actual_lang_list else "ch"] * len(pdf_file_names)
        
        # 如果MinerU可用，使用与sample文件相同的转换方法
        if MINERU_AVAILABLE:
            # 使用新的转换方法，与sample文件保持一致
            for i, (pdf_name, pdf_bytes) in enumerate(zip(pdf_file_names, pdf_bytes_list)):
                # 创建临时文件
                temp_path = Path(output_dir) / f"temp_{pdf_name}.pdf"
                with open(temp_path, "wb") as f:
                    f.write(pdf_bytes)
                
                try:
                    # 使用parse_pdf函数进行转换
                    is_ocr = parse_method == 'ocr'
                    result = await parse_pdf(
                        doc_path=str(temp_path),
                        output_dir=output_dir,
                        end_page_id=end_page_id,
                        is_ocr=is_ocr,
                        formula_enable=formula_enable,
                        table_enable=table_enable,
                        language=actual_lang_list[i] if i < len(actual_lang_list) else actual_lang_list[0],
                        backend=backend,
                        url=server_url
                    )
                    
                    if result is None:
                        logger.error(f"转换文件失败: {pdf_name}")
                    
                finally:
                    # 清理临时文件
                    if temp_path.exists():
                        os.remove(temp_path)
        else:
            # 简化版本，创建示例文件
            logger.info("使用简化版本处理文件")
        
        # 创建ZIP文件
        import tempfile
        zip_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="mineru_results_")
        os.close(zip_fd)
        
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for pdf_name in pdf_file_names:
                safe_pdf_name = sanitize_filename(pdf_name)
                if backend.startswith("pipeline"):
                    parse_dir = os.path.join(output_dir, pdf_name, parse_method)
                else:
                    parse_dir = os.path.join(output_dir, pdf_name, "vlm")
                
                if not os.path.exists(parse_dir):
                    # 创建示例markdown文件
                    md_content = f"""# {pdf_name}

这是一个示例Markdown文件，由MinerU Web界面生成。

## 文件信息
- 文件名: {pdf_name}
- 处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
- 后端: {backend}
- 解析方法: {parse_method}

## 说明
这是一个简化版本的MinerU Web界面，用于演示基本功能。
要使用完整的PDF转换功能，请确保安装了完整的MinerU环境。

## 功能特性
- 多文件上传
- 文件类型检查
- ZIP文件生成
- 中文界面支持
"""
                    zf.writestr(f"{safe_pdf_name}/{safe_pdf_name}.md", md_content)
                else:
                    # 写入实际的Markdown文件
                    if return_md:
                        md_path = os.path.join(parse_dir, f"{pdf_name}.md")
                        if os.path.exists(md_path):
                            zf.write(md_path, arcname=os.path.join(safe_pdf_name, f"{safe_pdf_name}.md"))
                    
                    # 写入图片
                    if return_images:
                        images_dir = os.path.join(parse_dir, "images")
                        if os.path.exists(images_dir):
                            image_paths = glob.glob(os.path.join(glob.escape(images_dir), "*.jpg"))
                            for image_path in image_paths:
                                zf.write(image_path, arcname=os.path.join(safe_pdf_name, "images", os.path.basename(image_path)))
        
        # 返回ZIP文件
        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=f"{safe_pdf_name}.zip",
            background=BackgroundTask(cleanup_file, zip_path)
        )
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"处理文件失败: {str(e)}"}
        )

@app.post("/convert_to_pdf")
async def convert_to_pdf(file: UploadFile = File(...)):
    """将非PDF文件转换为PDF格式"""
    try:
        # 读取文件内容
        content = await file.read()
        file_path = Path(file.filename)
        
        # 检查文件类型
        if file_path.suffix.lower() in pdf_suffixes:
            # 已经是PDF文件，直接返回
            return FileResponse(
                path=None,
                media_type="application/pdf",
                filename=file.filename,
                content=content
            )
        elif file_path.suffix.lower() in image_suffixes:
            # 图片文件，使用to_pdf函数转换
            temp_path = Path("./temp") / f"temp_{file_path.name}"
            temp_path.parent.mkdir(exist_ok=True)
            
            # 保存临时文件
            with open(temp_path, "wb") as f:
                f.write(content)
            
            try:
                # 使用to_pdf函数转换
                pdf_path = to_pdf(str(temp_path))
                
                # 读取转换后的PDF文件
                with open(pdf_path, "rb") as f:
                    pdf_content = f.read()
                
                # 清理临时文件
                os.remove(temp_path)
                os.remove(pdf_path)
                
                return FileResponse(
                    path=None,
                    media_type="application/pdf",
                    filename=file_path.stem + ".pdf",
                    content=pdf_content
                )
            except Exception as e:
                # 清理临时文件
                if temp_path.exists():
                    os.remove(temp_path)
                raise e
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"不支持的文件类型: {file_path.suffix}"}
            )
            
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"文件转换失败: {str(e)}"}
        )

@app.get("/list_output_files")
async def list_output_files():
    """列出输出目录中的文件"""
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(content=[])
        
        files = []
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            if os.path.isfile(item_path):
                files.append({"name": item, "type": "文件"})
            elif os.path.isdir(item_path):
                files.append({"name": item, "type": "目录"})
        
        return JSONResponse(content=files)
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"列出文件失败: {str(e)}"}
        )

@app.post("/delete_output_files")
async def delete_output_files(request: dict):
    """删除输出目录中的文件"""
    try:
        output_dir = "./output"
        deleted_files = []
        files = request.get("files", [])
        
        for filename in files:
            file_path = os.path.join(output_dir, filename)
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_files.append(filename)
                elif os.path.isdir(file_path):
                    import shutil
                    shutil.rmtree(file_path)
                    deleted_files.append(filename)
        
        return JSONResponse(content={"deleted": deleted_files})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"删除文件失败: {str(e)}"}
        )

@app.get("/download_file/{filename}")
async def download_file(filename: str):
    """下载单个文件的处理结果目录（ZIP打包）"""
    try:
        output_dir = "./output"
        
        # 根据原始文件名查找对应的处理结果目录
        # 实际目录格式：temp_{safe_stem}_{时间戳}
        safe_filename = safe_stem(filename)
        
        # 查找匹配的目录
        matching_dirs = []
        if os.path.exists(output_dir):
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isdir(item_path):
                    # 检查是否匹配 temp_{safe_filename}_{timestamp} 格式
                    if item.startswith(f"temp_{safe_filename}_"):
                        matching_dirs.append(item)
                    # 也检查旧的格式 {safe_filename}_{timestamp}（向后兼容）
                    elif item.startswith(f"{safe_filename}_"):
                        matching_dirs.append(item)
        
        if not matching_dirs:
            # 如果没找到，尝试更宽松的匹配（处理中文文件名编码问题）
            logger.info(f"未找到精确匹配，尝试宽松匹配文件名: {filename}")
            filename_without_ext = Path(filename).stem
            safe_filename_loose = re.sub(r'[^\w\u4e00-\u9fff]', '_', filename_without_ext)  # 保留中文字符
            
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isdir(item_path):
                    # 检查是否包含文件名的主要部分
                    if (f"temp_{safe_filename_loose}_" in item or 
                        f"{safe_filename_loose}_" in item):
                        matching_dirs.append(item)
        
        if not matching_dirs:
            return JSONResponse(
                status_code=404,
                content={"error": f"未找到文件 {filename} 的处理结果"}
            )
        
        # 如果有多个匹配的目录，选择最新的（按时间戳排序）
        matching_dirs.sort(reverse=True)
        target_dir = matching_dirs[0]
        file_path = os.path.join(output_dir, target_dir)
        
        logger.info(f"找到匹配目录: {target_dir}")
        
        # 创建ZIP文件
        zip_path = f"{file_path}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    file_path_full = os.path.join(root, file)
                    arcname = os.path.relpath(file_path_full, file_path)
                    zipf.write(file_path_full, arcname)
        
        # 返回ZIP文件
        return FileResponse(
            path=zip_path,
            filename=f"{safe_filename}.zip",
            media_type="application/zip",
            background=BackgroundTask(lambda: os.remove(zip_path))  # 下载后删除临时ZIP文件
        )
            
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"下载文件失败: {str(e)}"}
        )

@app.get("/download_all")
async def download_all():
    """下载所有处理成功的文件目录（ZIP打包）"""
    try:
        output_dir = "./output"
        if not os.path.exists(output_dir):
            return JSONResponse(
                status_code=404,
                content={"error": "输出目录不存在"}
            )
        
        # 获取所有目录
        directories = []
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            if os.path.isdir(item_path):
                directories.append(item)
        
        if not directories:
            return JSONResponse(
                status_code=404,
                content={"error": "没有可下载的目录"}
            )
        
        # 创建临时ZIP文件，文件名包含时间戳
        timestamp = time.strftime("%y%m%d_%H%M%S")
        zip_filename = f"all_results_{timestamp}.zip"
        zip_path = os.path.join(output_dir, zip_filename)
        
        # 创建ZIP文件
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for directory in directories:
                dir_path = os.path.join(output_dir, directory)
                for root, dirs, files in os.walk(dir_path):
                    for file in files:
                        file_path_full = os.path.join(root, file)
                        arcname = os.path.relpath(file_path_full, output_dir)
                        zipf.write(file_path_full, arcname)
        
        # 返回ZIP文件
        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip",
            background=BackgroundTask(lambda: os.remove(zip_path))  # 下载后删除临时ZIP文件
        )
        
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"下载所有文件失败: {str(e)}"}
        )

@click.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.pass_context
@click.option(
    '--enable-sglang-engine',
    'sglang_engine_enable',
    type=bool,
    help="启用SgLang引擎后端以加快处理速度",
    default=False,
)
@click.option(
    '--max-convert-pages',
    'max_convert_pages',
    type=int,
    help="设置从PDF转换为Markdown的最大页数",
    default=1000,
)
@click.option(
    '--host',
    'host',
    type=str,
    help="设置服务器主机名",
    default='0.0.0.0',
)
@click.option(
    '--port',
    'port',
    type=int,
    help="设置服务器端口",
    default=7860,
)
def main(ctx, sglang_engine_enable, max_convert_pages, host, port, **kwargs):
    """启动MinerU Web界面"""
    kwargs.update(arg_parse(ctx))
    
    # 将配置参数存储到应用状态中
    app.state.config = kwargs
    app.state.max_convert_pages = max_convert_pages
    app.state.sglang_engine_enable = sglang_engine_enable
    
    if sglang_engine_enable and MINERU_AVAILABLE:
        try:
            print("正在初始化SgLang引擎...")
            from mineru.backend.vlm.vlm_analyze import ModelSingleton
            model_singleton = ModelSingleton()
            
            # 过滤掉不应该传递给SgLang引擎的参数
            sglang_kwargs = {k: v for k, v in kwargs.items() 
                           if k not in ['server_name', 'server_port', 'host', 'port', 'enable_api', 'api_enable']}
            
            predictor = model_singleton.get_model(
                "sglang-engine",
                None,
                None,
                **sglang_kwargs
            )
            print("SgLang引擎初始化成功")
        except Exception as e:
            logger.exception(e)
    
    print(f"启动MinerU Web界面: http://{host}:{port}")
    print("界面功能:")
    print("- 多文件拖拽上传")
    print("- 实时转换状态显示")
    print("- 结果文件下载")
    print("- 输出目录管理")
    
    if not MINERU_AVAILABLE:
        print("注意: 使用简化版本，MinerU模块不可用")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False
    )

if __name__ == '__main__':
    main()
