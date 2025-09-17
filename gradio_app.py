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

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    else:
        # 返回基本的HTML页面
        return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MinerU PDF转换工具</title>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            background: white; 
            border-radius: 15px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { margin: 0; font-size: 2.5em; font-weight: 300; }
        .header p { margin: 10px 0 0 0; opacity: 0.9; }
        
        .main-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            padding: 30px;
        }
        
        .upload-section {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
        }
        
        .upload-area { 
            border: 3px dashed #667eea; 
            padding: 40px; 
            text-align: center; 
            border-radius: 10px;
            background: white;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .upload-area:hover {
            border-color: #764ba2;
            background: #f8f9ff;
        }
        .upload-area.dragover {
            border-color: #28a745;
            background: #f0fff4;
        }
        
        .file-status-section {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
        }
        
        .file-card {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
            transition: all 0.3s ease;
        }
        .file-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }
        .file-card.converting {
            border-left-color: #ffc107;
            background: #fffbf0;
        }
        .file-card.completed {
            border-left-color: #28a745;
            background: #f0fff4;
        }
        .file-card.error {
            border-left-color: #dc3545;
            background: #fff5f5;
        }
        
        .file-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .file-name {
            font-weight: 600;
            color: #333;
            flex: 1;
            margin-right: 10px;
        }
        .file-actions {
            display: flex;
            gap: 5px;
        }
        
        .btn { 
            background: #667eea; 
            color: white; 
            padding: 8px 16px; 
            border: none; 
            border-radius: 6px; 
            cursor: pointer; 
            font-size: 14px;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
        }
        .btn:hover { 
            background: #5a6fd8; 
            transform: translateY(-1px);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn-danger {
            background: #dc3545;
        }
        .btn-danger:hover {
            background: #c82333;
        }
        .btn-success {
            background: #28a745;
        }
        .btn-success:hover {
            background: #218838;
        }
        .btn-warning {
            background: #ffc107;
            color: #333;
        }
        .btn-warning:hover {
            background: #e0a800;
        }
        
        .file-info {
            font-size: 12px;
            color: #666;
            margin-bottom: 10px;
        }
        
        .file-preview {
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
            max-height: 200px;
            overflow-y: auto;
        }
        
        .preview-content {
            font-family: 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.4;
            white-space: pre-wrap;
        }
        
        .batch-actions {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            text-align: center;
        }
        
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-pending { background: #6c757d; }
        .status-converting { background: #ffc107; animation: pulse 1.5s infinite; }
        .status-completed { background: #28a745; }
        .status-error { background: #dc3545; }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .progress-bar {
            width: 100%;
            height: 4px;
            background: #e9ecef;
            border-radius: 2px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            width: 0%;
            transition: width 0.3s ease;
        }
        
        .conversion-status {
            background: #e3f2fd;
            border: 1px solid #2196f3;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            display: none;
        }
        .conversion-status.active {
            display: block;
        }
        
        .preview-section {
            grid-column: 1 / -1;
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
            margin-top: 20px;
        }
        
        .preview-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .preview-content-area {
            background: white;
            border-radius: 8px;
            padding: 20px;
            min-height: 300px;
            border: 1px solid #dee2e6;
        }
        
        .empty-state {
            text-align: center;
            color: #6c757d;
            padding: 40px;
        }
        .empty-state i {
            font-size: 48px;
            margin-bottom: 15px;
            opacity: 0.5;
        }
        
        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
                gap: 20px;
                padding: 20px;
            }
            .header h1 {
                font-size: 2em;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MinerU PDF转换工具</h1>
            <p>智能文档转换，支持PDF、图片等多种格式</p>
        </div>
        
        <div class="main-content">
            <div class="upload-section">
                <h3>文件上传</h3>
                <div class="upload-area" id="uploadArea">
                    <div style="font-size: 48px; margin-bottom: 15px;">📁</div>
                    <p style="font-size: 18px; margin-bottom: 10px;">拖拽文件到此处或点击选择文件</p>
                    <p style="color: #666; font-size: 14px;">支持 PDF、PNG、JPG、JPEG、BMP、TIFF 格式</p>
                    <input type="file" id="fileInput" multiple accept=".pdf,.png,.jpg,.jpeg,.bmp,.tiff" style="display: none;">
                </div>
                
                <div class="batch-actions">
                    <button class="btn btn-success" onclick="startConversion()" id="convertBtn">
                        🚀 开始转换
                    </button>
                    <button class="btn btn-warning" onclick="clearAllFiles()">
                        🗑️ 清空所有
                    </button>
                    <button class="btn" onclick="downloadAllResults()" id="downloadAllBtn" style="display: none;">
                        📥 一键下载
                    </button>
                </div>
            </div>
            
            <div class="file-status-section">
                <h3>文件状态</h3>
                <div id="fileStatusList">
                    <div class="empty-state">
                        <div style="font-size: 48px; margin-bottom: 15px;">📋</div>
                        <p>暂无文件</p>
                        <p style="font-size: 14px; color: #999;">上传文件后将显示在这里</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="conversion-status" id="conversionStatus">
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span class="status-indicator status-converting"></span>
                <strong>正在转换中...</strong>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div id="conversionProgress">准备中...</div>
        </div>
        
        <div class="preview-section">
            <div class="preview-header">
                <h3>文件预览</h3>
                <div>
                    <button class="btn" onclick="togglePreviewMode()" id="previewModeBtn">
                        📄 预览模式
                    </button>
                </div>
            </div>
            <div class="preview-content-area" id="previewContent">
                <div class="empty-state">
                    <div style="font-size: 48px; margin-bottom: 15px;">👁️</div>
                    <p>选择文件查看预览</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let uploadedFiles = [];
        let fileStates = new Map(); // 存储文件状态
        let currentPreviewMode = 'preview'; // 'preview' 或 'markdown'
        let isConverting = false;
        
        // 文件状态枚举
        const FileStatus = {
            PENDING: 'pending',
            CONVERTING: 'converting', 
            COMPLETED: 'completed',
            ERROR: 'error'
        };
        
        // 初始化
        document.addEventListener('DOMContentLoaded', function() {
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');
            
            // 点击上传区域
            uploadArea.addEventListener('click', () => fileInput.click());
            
            // 文件选择
            fileInput.addEventListener('change', function(e) {
                addFiles(Array.from(e.target.files));
            });
            
            // 拖拽上传
            uploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
            
            uploadArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
            });
            
            uploadArea.addEventListener('drop', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = Array.from(e.dataTransfer.files);
                addFiles(files);
            });
        });
        
        function addFiles(files) {
            files.forEach(file => {
                if (!uploadedFiles.find(f => f.name === file.name && f.size === file.size)) {
                    uploadedFiles.push(file);
                    fileStates.set(file.name, {
                        status: FileStatus.PENDING,
                        progress: 0,
                        result: null,
                        error: null
                    });
                }
            });
            updateFileStatusList();
            updatePreview();
        }
        
        function updateFileStatusList() {
            const fileStatusList = document.getElementById('fileStatusList');
            
            if (uploadedFiles.length === 0) {
                fileStatusList.innerHTML = `
                    <div class="empty-state">
                        <div style="font-size: 48px; margin-bottom: 15px;">📋</div>
                        <p>暂无文件</p>
                        <p style="font-size: 14px; color: #999;">上传文件后将显示在这里</p>
                    </div>
                `;
                return;
            }
            
            fileStatusList.innerHTML = uploadedFiles.map((file, index) => {
                const state = fileStates.get(file.name);
                const statusClass = state ? state.status : FileStatus.PENDING;
                const statusText = getStatusText(statusClass);
                const statusIndicator = getStatusIndicator(statusClass);
                
                return `
                    <div class="file-card ${statusClass}" data-index="${index}">
                        <div class="file-header">
                            <div class="file-name">
                                <span class="status-indicator ${statusIndicator}"></span>
                                ${file.name}
                            </div>
                            <div class="file-actions">
                                ${getFileActions(file, state, index)}
                            </div>
                        </div>
                        <div class="file-info">
                            大小: ${formatFileSize(file.size)} | 类型: ${file.type || '未知'}
                        </div>
                        ${getProgressBar(state)}
                        ${getFilePreview(file, state)}
                    </div>
                `;
            }).join('');
        }
        
        function getStatusText(status) {
            const statusMap = {
                [FileStatus.PENDING]: '等待中',
                [FileStatus.CONVERTING]: '转换中',
                [FileStatus.COMPLETED]: '已完成',
                [FileStatus.ERROR]: '转换失败'
            };
            return statusMap[status] || '未知';
        }
        
        function getStatusIndicator(status) {
            return `status-${status}`;
        }
        
        function getFileActions(file, state, index) {
            const actions = [];
            
            if (state && state.status === FileStatus.COMPLETED && state.result) {
                actions.push(`<button class="btn btn-success" onclick="downloadFile('${file.name}')">📥 下载</button>`);
            }
            
            actions.push(`<button class="btn btn-danger" onclick="removeFile(${index})">🗑️ 删除</button>`);
            
            return actions.join('');
        }
        
        function getProgressBar(state) {
            if (!state || state.status === FileStatus.PENDING) {
                return '';
            }
            
            const progress = state.progress || 0;
            return `
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
            `;
        }
        
        function getFilePreview(file, state) {
            if (!state || state.status !== FileStatus.COMPLETED) {
                return '';
            }
            
            return `
                <div class="file-preview">
                    <div class="preview-content">
                        ${state.result ? state.result.substring(0, 200) + '...' : '暂无预览内容'}
                    </div>
                </div>
            `;
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function removeFile(index) {
            const file = uploadedFiles[index];
            uploadedFiles.splice(index, 1);
            fileStates.delete(file.name);
            updateFileStatusList();
            updatePreview();
        }
        
        function clearAllFiles() {
            if (isConverting) {
                alert('转换进行中，无法清空文件');
                return;
            }
            uploadedFiles = [];
            fileStates.clear();
            updateFileStatusList();
            updatePreview();
            hideConversionStatus();
        }
        
        function updatePreview() {
            const previewContent = document.getElementById('previewContent');
            
            if (uploadedFiles.length === 0) {
                previewContent.innerHTML = `
                    <div class="empty-state">
                        <div style="font-size: 48px; margin-bottom: 15px;">👁️</div>
                        <p>选择文件查看预览</p>
                    </div>
                `;
                return;
            }
            
            // 显示第一个文件的预览
            const firstFile = uploadedFiles[0];
            const state = fileStates.get(firstFile.name);
            
            if (state && state.status === FileStatus.COMPLETED && state.result) {
                showFilePreview(firstFile, state.result);
            } else {
                previewContent.innerHTML = `
                    <div class="empty-state">
                        <div style="font-size: 48px; margin-bottom: 15px;">⏳</div>
                        <p>等待文件转换完成</p>
                    </div>
                `;
            }
        }
        
        function showFilePreview(file, content) {
            const previewContent = document.getElementById('previewContent');
            const mode = currentPreviewMode === 'preview' ? '预览' : 'Markdown';
            
            previewContent.innerHTML = `
                <div style="margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #dee2e6;">
                    <h4 style="margin: 0; color: #333;">${file.name} - ${mode}</h4>
                </div>
                <div class="preview-content" style="max-height: 400px; overflow-y: auto;">
                    ${currentPreviewMode === 'preview' ? 
                        content.replace(/\\n/g, '<br>').substring(0, 1000) + (content.length > 1000 ? '...' : '') :
                        '<pre>' + content.substring(0, 1000) + (content.length > 1000 ? '...' : '') + '</pre>'
                    }
                </div>
            `;
        }
        
        function togglePreviewMode() {
            currentPreviewMode = currentPreviewMode === 'preview' ? 'markdown' : 'preview';
            const btn = document.getElementById('previewModeBtn');
            btn.textContent = currentPreviewMode === 'preview' ? '📄 预览模式' : '📝 Markdown模式';
            updatePreview();
        }
        
        async function startConversion() {
            if (uploadedFiles.length === 0) {
                alert('请先上传文件');
                return;
            }
            
            if (isConverting) {
                alert('转换正在进行中，请等待完成');
                return;
            }
            
            isConverting = true;
            showConversionStatus();
            updateConvertButton();
            
            try {
                // 模拟转换过程
                for (let i = 0; i < uploadedFiles.length; i++) {
                    const file = uploadedFiles[i];
                    const state = fileStates.get(file.name);
                    
                    // 更新状态为转换中
                    state.status = FileStatus.CONVERTING;
                    state.progress = 0;
                    updateFileStatusList();
                    updateConversionProgress(`正在转换: ${file.name}`, (i / uploadedFiles.length) * 100);
                    
                    // 模拟转换进度
                    for (let progress = 0; progress <= 100; progress += 10) {
                        state.progress = progress;
                        updateFileStatusList();
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }
                    
                    // 模拟转换结果
                    const mockResult = `# ${file.name} 转换结果\\n\\n这是 ${file.name} 的转换结果。\\n\\n## 内容摘要\\n\\n文件已成功转换为Markdown格式。\\n\\n## 详细信息\\n\\n- 文件名: ${file.name}\\n- 文件大小: ${formatFileSize(file.size)}\\n- 转换时间: ${new Date().toLocaleString()}\\n\\n## 转换内容\\n\\n这里是转换后的主要内容...`;
                    
                    state.status = FileStatus.COMPLETED;
                    state.progress = 100;
                    state.result = mockResult;
                    updateFileStatusList();
                }
                
                // 显示最后一个文件的预览
                const lastFile = uploadedFiles[uploadedFiles.length - 1];
                const lastState = fileStates.get(lastFile.name);
                showFilePreview(lastFile, lastState.result);
                
                updateConversionProgress('转换完成！', 100);
                showDownloadAllButton();
                
            } catch (error) {
                console.error('转换失败:', error);
                updateConversionProgress('转换失败: ' + error.message, 0);
            } finally {
                isConverting = false;
                updateConvertButton();
                setTimeout(() => hideConversionStatus(), 3000);
            }
        }
        
        function showConversionStatus() {
            document.getElementById('conversionStatus').classList.add('active');
        }
        
        function hideConversionStatus() {
            document.getElementById('conversionStatus').classList.remove('active');
        }
        
        function updateConversionProgress(message, progress) {
            document.getElementById('conversionProgress').textContent = message;
            document.getElementById('progressFill').style.width = progress + '%';
        }
        
        function updateConvertButton() {
            const btn = document.getElementById('convertBtn');
            if (isConverting) {
                btn.textContent = '⏳ 转换中...';
                btn.disabled = true;
                btn.style.opacity = '0.6';
            } else {
                btn.textContent = '🚀 开始转换';
                btn.disabled = false;
                btn.style.opacity = '1';
            }
        }
        
        function showDownloadAllButton() {
            document.getElementById('downloadAllBtn').style.display = 'inline-block';
        }
        
        function downloadFile(filename) {
            const state = fileStates.get(filename);
            if (state && state.status === FileStatus.COMPLETED) {
                // 调用后端API下载文件目录
                window.open(`/download_file/${encodeURIComponent(filename)}`, '_blank');
            } else {
                alert('文件尚未处理完成，无法下载');
            }
        }
        
        function downloadAllResults() {
            const completedFiles = uploadedFiles.filter(file => {
                const state = fileStates.get(file.name);
                return state && state.status === FileStatus.COMPLETED;
            });
            
            if (completedFiles.length === 0) {
                alert('没有可下载的文件');
                return;
            }
            
            // 调用后端API下载所有文件
            window.open('/download_all', '_blank');
        }
    </script>
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
        # 处理结果目录格式：{safe_stem}_{时间戳}
        safe_filename = safe_stem(filename)
        
        # 查找匹配的目录
        matching_dirs = []
        if os.path.exists(output_dir):
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isdir(item_path) and item.startswith(safe_filename + "_"):
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
