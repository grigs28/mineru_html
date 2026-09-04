        /**
 * MinerU PDF转换工具 - 主应用JavaScript文件
 * 版本: 见 CHANGELOG.md（单一来源，由 /api/version 动态读取）
 * 功能: PDF文档解析与转换、文件管理、任务队列等
 * 
 * 主要功能模块:
 * - 文件上传和管理
 * - 任务队列处理
 * - 进度监控和状态更新
 * - 结果预览和下载
 * - 输出文件管理
 */

class MinerUApp {
            constructor() {
                this.uploadedFiles = [];
                this.processingFiles = new Set();
                this.results = new Map();
                this.isAutoUploading = false;
                this.isProcessing = false;
                this.currentProcessingIndex = -1;
                this.manualViewFile = null; // 用户手动查看的文件名（锁定预览）
                this.loadFromStorage();
                this.init();
            }

            init() {
                this.setupEventListeners();
                this.updateSliderValue();
                this.updateBackendOptions();
                this.refreshVersion();
                this.syncFileListFromServer();
                this.loadExamples();
                this.updateFileList();
            }

            async syncFileListFromServer() {
                // 从服务端获取共享文件列表，与本地合并（服务端为主）
                try {
                    const res = await fetch('/api/file_list');
                    if (!res.ok) return;
                    const serverFiles = await res.json();
                    if (Array.isArray(serverFiles)) {
                        // 正常化状态并以服务端为主替换（仅状态/元信息，File对象为空）
                        const normalizeStatus = (s) => {
                            if (!s) return 'pending';
                            const map = { failed: 'error', error: 'error', queued: 'queued', pending: 'pending', processing: 'processing', completed: 'completed' };
                            return map[s] || 'pending';
                        };
                        const merged = serverFiles.map(f => ({
                            file: null,
                            name: f.name,
                            size: f.size || 0,
                            status: normalizeStatus(f.status),
                            uploadTime: f.uploadTime || null,
                            startTime: f.startTime || null,
                            endTime: f.endTime || null,
                            processingTime: f.processingTime || null,
                            taskId: f.taskId || null,
                            progress: Number.isFinite(f.progress) ? f.progress : 0,
                            message: f.message || '',
                            errorMessage: f.errorMessage || null
                        }));
                        this.uploadedFiles = merged;
                        this.updateFileList();
                        this.saveToStorage();
                    }
                } catch (e) {
                    console.warn('syncFileListFromServer failed', e);
                }
            }

            async syncFileListToServer() {
                // 将当前文件列表推送到服务端共享（仅同步新增文件，不覆盖后端状态）
                try {
                    // 先获取服务端的文件列表
                    const res = await fetch('/api/file_list');
                    if (!res.ok) return;
                    const serverFiles = await res.json();
                    
                    // 构建服务端taskId到文件的映射
                    const serverTaskIdMap = new Map();
                    serverFiles.forEach(f => {
                        if (f.taskId) {
                            serverTaskIdMap.set(f.taskId, f);
                        }
                    });
                    
                    // 找出需要同步到服务端的文件
                    // 只同步本地有而服务端没有的文件，或本地状态更新的文件
                    const filesToSync = [];
                    
                    for (const f of this.uploadedFiles) {
                        if (!f.taskId) {
                            // 没有任务ID的文件跳过（这些可能是未上传的文件）
                            continue;
                        }
                        
                        const serverFile = serverTaskIdMap.get(f.taskId);
                        
                        if (!serverFile) {
                            // 服务端没有该任务ID，需要添加
                            filesToSync.push(f);
                        } else {
                            // 服务端有该任务ID，检查是否需要更新
                            // 如果本地状态更新，需要同步到服务端
                            if (f.status !== serverFile.status || 
                                f.progress !== serverFile.progress || 
                                f.message !== serverFile.message ||
                                f.errorMessage !== serverFile.errorMessage) {
                                filesToSync.push(f);
                            }
                        }
                    }
                    
                    if (filesToSync.length > 0) {
                        const payload = {
                            files: filesToSync.map(f => ({
                                name: f.name,
                                size: f.size || 0,
                                status: f.status || 'pending',
                                uploadTime: f.uploadTime || null,
                                startTime: f.startTime || null,
                                endTime: f.endTime || null,
                                processingTime: f.processingTime || null,
                                taskId: f.taskId || null,
                                progress: f.progress || 0,
                                message: f.message || '',
                                errorMessage: f.errorMessage || null,
                                outputDir: f.outputDir || null
                            }))
                        };
                        await fetch('/api/file_list', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        console.log(`同步了 ${filesToSync.length} 个文件到服务端`);
                    }
                } catch (e) {
                    console.warn('syncFileListToServer failed', e);
                }
            }

            async refreshVersion() {
                try {
                    const res = await fetch('/api/version');
                    if (!res.ok) return;
                    const data = await res.json();
                    const el = document.querySelector('.version-text');
                    if (el && data.version) {
                        const mineru = data.mineru_version ? ` · MinerU ${data.mineru_version}` : '';
                        el.textContent = data.version + mineru;
                        el.title = `MinerU ${data.mineru_version || '未知'}（点击查看更新日志）`;
                    }
                } catch (e) {
                    console.warn('获取版本失败', e);
                }
            }

            // 持久化存储方法
            saveToStorage() {
                const data = {
                    uploadedFiles: this.uploadedFiles.map(file => ({
                        name: file.name,
                        size: file.size,
                        type: file.type,
                        lastModified: file.lastModified,
                        status: file.status || 'pending',
                        startTime: file.startTime || null,
                        endTime: file.endTime || null,
                        processingTime: file.processingTime || null,
                        taskId: file.taskId || null,  // 保存任务ID
                        progress: file.progress || 0,  // 保存进度
                        message: file.message || '',   // 保存消息
                        errorMessage: file.errorMessage || null  // 保存错误信息
                    })),
                    results: Array.from(this.results.entries())
                };
                localStorage.setItem('mineru_files', JSON.stringify(data));
            }

            loadFromStorage() {
                try {
                    const data = localStorage.getItem('mineru_files');
                    if (data) {
                        const parsed = JSON.parse(data);
                        // 恢复文件列表（不包含File对象，需要重新创建）
                        this.uploadedFiles = parsed.uploadedFiles || [];
                        // 恢复结果
                        if (parsed.results) {
                            this.results = new Map(parsed.results);
                        }
                        
                        // 恢复数据后更新UI
                        this.updateFileList();
                        
                        // 如果有文件，显示第一个文件的预览
                        if (this.uploadedFiles.length > 0) {
                            this.showFirstFilePreview();
                        }
                        
                        // 如果有文件且有任务ID，检查是否需要启动全局状态轮询
                        const hasTasks = this.uploadedFiles.some(f => f.taskId);
                        if (hasTasks && !this.globalPollingInterval) {
                            // 检查是否有活跃任务（非完成状态）
                            const hasActiveTasks = this.uploadedFiles.some(f => 
                                f.taskId && f.status && f.status !== 'completed' && f.status !== 'failed'
                            );
                            if (hasActiveTasks) {
                                this.startGlobalStatusPolling();
                            }
                        }
                    }
                } catch (error) {
                    console.error('加载存储数据失败:', error);
                    this.uploadedFiles = [];
                    this.results = new Map();
                }
            }

            // 获取北京时区时间
            getBeijingTime() {
                return new Date().toLocaleString('zh-CN', {
                    timeZone: 'Asia/Shanghai',
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
            }

            // 计算处理时长
            calculateProcessingTime(startTime, endTime) {
                if (!startTime || !endTime) return null;
                const start = new Date(startTime);
                const end = new Date(endTime);
                const diffMs = end - start;
                const minutes = Math.floor(diffMs / 60000);
                const seconds = Math.floor((diffMs % 60000) / 1000);
                return `${minutes}分${seconds}秒`;
            }

            setupEventListeners() {
                // 文件上传
                const uploadArea = document.getElementById('uploadArea');
                const fileInput = document.getElementById('fileInput');

                uploadArea.addEventListener('click', () => fileInput.click());
                uploadArea.addEventListener('dragover', this.handleDragOver.bind(this));
                uploadArea.addEventListener('dragleave', this.handleDragLeave.bind(this));
                uploadArea.addEventListener('drop', this.handleDrop.bind(this));
                fileInput.addEventListener('change', this.handleFileSelect.bind(this));

                // 滑块
                document.getElementById('maxPages').addEventListener('input', this.updateSliderValue.bind(this));

                // 后端选择
                document.getElementById('backend').addEventListener('change', this.updateBackendOptions.bind(this));

                // 按钮
                document.getElementById('convertBtn').addEventListener('click', this.startConversion.bind(this));
                document.getElementById('clearBtn').addEventListener('click', this.clearAll.bind(this));

                // 标签页
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.addEventListener('click', this.switchTab.bind(this));
                });

                // 输出文件操作
                document.getElementById('refreshExamples').addEventListener('click', this.loadExamples.bind(this));
                document.getElementById('selectAllExamples').addEventListener('click', this.selectAllExamples.bind(this));
                document.getElementById('deleteSelected').addEventListener('click', this.deleteSelectedExamples.bind(this));
            }

            handleDragOver(e) {
                e.preventDefault();
                e.currentTarget.classList.add('dragover');
            }

            handleDragLeave(e) {
                e.preventDefault();
                e.currentTarget.classList.remove('dragover');
            }

            handleDrop(e) {
                e.preventDefault();
                e.currentTarget.classList.remove('dragover');
                const files = Array.from(e.dataTransfer.files);
                this.addFiles(files);
            }

            handleFileSelect(e) {
                const files = Array.from(e.target.files);
                this.addFiles(files);
            }

            async addFiles(files) {
                const validFiles = files.filter(file => {
                    const ext = file.name.toLowerCase().split('.').pop();
                    return ['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'].includes(ext);
                });

                validFiles.forEach(file => {
                    if (!this.uploadedFiles.find(f => f.name === file.name && f.size === file.size)) {
                        this.uploadedFiles.push({
                            file: file,
                            name: file.name,
                            size: file.size,
                            status: 'pending',
                            uploadTime: new Date(),
                            startTime: null,
                            endTime: null,
                            processingTime: null
                        });
                    }
                });

                this.updateFileList();
                this.saveToStorage();
                this.syncFileListToServer();
                
                // 批量上传后显示第一个文件的预览（若未手动锁定预览）
                if (validFiles.length > 0 && !this.manualViewFile) {
                    this.showFirstFilePreview();
                }

                // 如果队列正在运行，则自动上传新加入且为待处理的文件
                try {
                    const qs = await this.getQueueStatus();
                    if (qs && qs.queue_status === 'running') {
                        await this.uploadFilesWithProgress();
                        if (!this.globalPollingInterval) {
                            this.startGlobalStatusPolling();
                        }
                    }
                } catch (e) {
                    console.warn('auto enqueue check failed', e);
                }

                // 更新转换按钮状态
                await this.updateConvertButtonState();
            }

            updateFileList() {
                // 直接更新文件状态卡片
                this.updateFileStatusCards();
            }

            updateFileStatusCards() {
                const fileStatusCards = document.getElementById('fileStatusCards');
                const cardsContainer = document.getElementById('cardsContainer');
                const fileCountBadge = document.getElementById('fileCount');
                
                // 文件状态区域始终显示
                    fileStatusCards.style.display = 'block';
                
                // 如果有文件，显示文件卡片
                if (this.uploadedFiles.length > 0 || this.results.size > 0) {
                    cardsContainer.innerHTML = '';

                    // 按状态排序文件：正在处理、待处理、队列中、失败、已完成
                    const sortedFiles = this.sortFilesByStatus(this.uploadedFiles);

                    // 显示上传的文件（包括已上传和正在处理的）
                    sortedFiles.forEach((fileData, index) => {
                        const fileCard = this.createFileCard(fileData, index);
                        cardsContainer.appendChild(fileCard);
                    });

                    // 统计数量：显示“已完成/总文件数”格式
                    const completedCount = (this.uploadedFiles || []).filter(f => f && f.status === 'completed').length;
                    const totalCount = this.uploadedFiles.length;
                    if (fileCountBadge) fileCountBadge.textContent = `${completedCount}/${totalCount}`;

                } else {
                    // 显示空状态
                    cardsContainer.innerHTML = `
                        <div class="empty-state">
                            <div style="font-size: 48px; margin-bottom: 15px;">📋</div>
                            <p>暂无文件</p>
                            <p style="font-size: 14px; color: #999;">上传文件后将显示在这里</p>
                        </div>
                    `;
                    if (fileCountBadge) fileCountBadge.textContent = '0';
                }
            }

            createFileCard(fileData, index) {
                const card = document.createElement('div');
                card.className = 'file-card';

                // 添加data属性，便于后续更新单个卡片
                card.setAttribute('data-filename', fileData.name);
                card.setAttribute('data-taskid', fileData.taskId || '');

                const fileIcon = this.getFileIcon(fileData.name);
                const statusBadge = this.getStatusBadge(fileData.status);
                const progressBar = this.getProgressBar(fileData);
                const actions = this.getFileActions(fileData, index);

                // 构建状态和时间信息
                const timeInfo = this.getTimeInfo(fileData);

                // 展示用文件名：解码 URL 编码名 + 中间截断控制长度（原始名仍作数据键）
                const fullDisplayName = MinerUUtils.displayName(fileData.name);
                const shortDisplayName = MinerUUtils.escapeHtml(MinerUUtils.truncateFilename(fullDisplayName));

                // 失败原因直接展示在卡片上（后端 errorMessage 已下发，此前未渲染）
                const errorBlock = (fileData.status === 'error' && fileData.errorMessage)
                    ? `<div class="file-error-text" title="${MinerUUtils.escapeHtml(String(fileData.errorMessage))}">⚠️ ${MinerUUtils.escapeHtml(MinerUUtils.truncateFilename(String(fileData.errorMessage), 80))}</div>`
                    : '';

                card.innerHTML = `
                    <div class="file-card-header">
                        <div class="file-info">
                            <span class="file-icon">${fileIcon}</span>
                            <span class="file-name" title="${MinerUUtils.escapeHtml(fullDisplayName)}">${shortDisplayName}</span>
                        </div>
                        <div class="status-badge ${fileData.status}">${statusBadge}</div>
                    </div>
                    <div class="file-card-body">
                        ${progressBar}
                        ${errorBlock}
                    </div>
                    <div class="file-card-footer">
                        <div class="file-info-footer">
                            <span class="file-size">${this.formatFileSize(fileData.size)}</span>
                            <span class="file-duration">${this.getDurationOnly(fileData)}</span>
                            <div class="file-actions">
                                ${actions}
                            </div>
                        </div>
                    </div>
                `;

                // 点击卡片：预览该任务转换效果（左 PDF + 右 md rendering/text/输出文件），复用现有 showMarkdownResult
                card.addEventListener('click', (e) => {
                    if (e.target.closest('button')) return; // 忽略卡片内按钮（下载/删除等）
                    this.manualViewFile = fileData.name;
                    this.showMarkdownResult(fileData.name);
                });
                card.style.cursor = 'pointer';

                return card;
            }


            getFileIcon(filename) {
                const ext = filename.toLowerCase().split('.').pop();
                const iconMap = {
                    'pdf': '📄',
                    'png': '🖼️',
                    'jpg': '🖼️',
                    'jpeg': '🖼️',
                    'gif': '🖼️',
                    'webp': '🖼️',
                    'md': '📝',
                    'txt': '📄',
                    'zip': '📦'
                };
                return iconMap[ext] || '📁';
            }

            getStatusBadge(status) {
                const statusMap = {
                    'pending': '⏳ 待处理',
                    'queued': '📋 队列中',
                    'processing': '⚙️ 处理中',
                    'completed': '✅ 成功',
                    'error': '❌ 失败'
                };
                return statusMap[status] || '❓ 未知';
            }

            getProgressBar(fileData) {
                const progress = fileData.progress || 0;
                const status = fileData.status;
                
                if (status === 'processing') {
                    const progressColor = '#007bff';
                    return `
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%; background: ${progressColor};"></div>
                            <span class="progress-text">${progress}%</span>
                        </div>
                    `;
                } else if (status === 'pending' || status === 'queued') {
                    const progressColor = status === 'queued' ? '#ffc107' : '#007bff';
                    return `
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 0%; background: ${progressColor};"></div>
                            <span class="progress-text">0%</span>
                        </div>
                    `;
                } else if (status === 'completed') {
                    return `
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 100%; background: #28a745;"></div>
                            <span class="progress-text">100%</span>
                        </div>
                    `;
                } else if (status === 'error') {
                    return `
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 100%; background: #dc3545;"></div>
                            <span class="progress-text">错误</span>
                        </div>
                    `;
                }
                return '';
            }

            getFileActions(fileData, index) {
                // 查看按钮：任务完成时可用
                const viewBtn = fileData.status === 'completed'
                    ? `<button class="btn-card btn-view" onclick="app.viewResult('${fileData.name}')">👁️ 查看</button>`
                    : `<button class="btn-card btn-view" disabled>👁️ 查看</button>`;
                
                // 下载按钮：任务完成时可用
                const downloadBtn = fileData.status === 'completed'
                    ? `<button class="btn-card btn-download" onclick="app.downloadResult('${fileData.name}')">📥 下载</button>`
                    : `<button class="btn-card btn-download" disabled>📥 下载</button>`;
                
                // 删除按钮：始终可用，使用文件名而不是索引
                const deleteBtn = `<button class="btn-card btn-delete" onclick="app.removeFile('${fileData.name}')">🗑️ 删除</button>`;
                
                return viewBtn + downloadBtn + deleteBtn;
            }

            formatTime(date) {
                if (!date) return '';
                const now = new Date();
                const diff = now - date;
                const minutes = Math.floor(diff / 60000);
                const hours = Math.floor(diff / 3600000);
                const days = Math.floor(diff / 86400000);
                
                if (days > 0) return `${days}天前`;
                if (hours > 0) return `${hours}小时前`;
                if (minutes > 0) return `${minutes}分钟前`;
                return '刚刚';
            }
            
            formatTimeShort(dateStr) {
                if (!dateStr) return '';
                const date = new Date(dateStr);
                const now = new Date();
                const diff = now - date;
                const minutes = Math.floor(diff / 60000);
                const hours = Math.floor(diff / 3600000);
                const days = Math.floor(diff / 86400000);
                
                if (days > 0) return `${days}d`;
                if (hours > 0) return `${hours}h`;
                if (minutes > 0) return `${minutes}m`;
                return '刚刚';
            }
            
            formatTimeDetail(dateStr) {
                if (!dateStr) return '';
                // 以北京时间格式化显示
                try {
                    const d = new Date(dateStr);
                    const parts = new Intl.DateTimeFormat('zh-CN', {
                        timeZone: 'Asia/Shanghai',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false
                    }).formatToParts(d).reduce((acc, p) => (acc[p.type] = p.value, acc), {});
                    return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
                } catch (_) {
                    const date = new Date(dateStr);
                    const hours = date.getHours().toString().padStart(2, '0');
                    const minutes = date.getMinutes().toString().padStart(2, '0');
                    const month = (date.getMonth() + 1).toString().padStart(2, '0');
                    const day = date.getDate().toString().padStart(2, '0');
                    return `${month}-${day} ${hours}:${minutes}`;
                }
            }
            
            getTimeInfo(fileData) {
                switch (fileData.status) {
                    case 'pending':
                        return `📤 待处理`;
                    case 'queued':
                        const queuedAt = fileData.uploadTime || fileData.upload_time;
                        return `📋 队列中 | 加入: ${queuedAt ? this.formatTimeDetail(queuedAt) : '未知'}`;
                    case 'processing':
                        return `⚙️ 处理中`;
                    case 'completed':
                        const duration = this.getProcessingDuration(fileData);
                        return `✅ 完成 | 耗时: ${duration}`;
                    case 'error':
                        const errDuration = this.getProcessingDuration(fileData);
                        return `❌ 失败 | 耗时: ${errDuration}`;
                    default:
                        return `❓ 未知状态`;
                }
            }
            
            getDurationOnly(fileData) {
                switch (fileData.status) {
                    case 'completed':
                    case 'error':
                        const duration = this.getProcessingDuration(fileData);
                        return duration !== '未知' ? `耗时: ${duration}` : '';
                    default:
                        return '';
                }
            }
            
            getProcessingDuration(fileData) {
                if (!fileData.startTime || !fileData.endTime) return '未知';
                const start = new Date(fileData.startTime);
                const end = new Date(fileData.endTime);
                const diff = end - start;
                const minutes = Math.floor(diff / 60000);
                const seconds = Math.floor((diff % 60000) / 1000);
                
                if (minutes > 0) {
                    return `${minutes}分${seconds}秒`;
                } else {
                    return `${seconds}秒`;
                }
            }
            
            formatDuration(milliseconds) {
                const seconds = Math.floor(milliseconds / 1000);
                const minutes = Math.floor(seconds / 60);
                const hours = Math.floor(minutes / 60);
                
                if (hours > 0) {
                    return `${hours}小时${minutes % 60}分钟`;
                } else if (minutes > 0) {
                    return `${minutes}分${seconds % 60}秒`;
                } else {
                    return `${seconds}秒`;
                }
            }

            getStatusText(status) {
                const statusMap = {
                    'pending': '待处理',
                    'processing': '处理中',
                    'completed': '转换成功',
                    'error': '转换失败'
                };
                return statusMap[status] || status;
            }

            updateSingleFileCard(fileData) {
                // 查找对应的DOM卡片并更新
                const cardId = `file-card-${fileData.name.replace(/[^a-zA-Z0-9]/g, '_')}-${fileData.taskId || 'no-task'}`;
                const existingCard = document.querySelector(`[data-filename="${fileData.name}"][data-taskid="${fileData.taskId}"]`);
                
                if (existingCard) {
                    // 更新现有卡片的内容
                    const statusBadge = existingCard.querySelector('.status-badge');
                    const progressBarContainer = existingCard.querySelector('.file-card-body');
                    const durationSpan = existingCard.querySelector('.file-duration');
                    const actionsContainer = existingCard.querySelector('.file-actions');
                    
                    if (statusBadge) {
                        statusBadge.className = `status-badge ${fileData.status}`;
                        statusBadge.textContent = this.getStatusBadge(fileData.status);
                    }
                    
                    if (progressBarContainer) {
                        const errorBlock = (fileData.status === 'error' && fileData.errorMessage)
                            ? `<div class="file-error-text" title="${MinerUUtils.escapeHtml(String(fileData.errorMessage))}">⚠️ ${MinerUUtils.escapeHtml(MinerUUtils.truncateFilename(String(fileData.errorMessage), 80))}</div>`
                            : '';
                        progressBarContainer.innerHTML = this.getProgressBar(fileData) + errorBlock;
                    }
                    
                    if (durationSpan) {
                        durationSpan.textContent = this.getDurationOnly(fileData);
                    }
                    
                    if (actionsContainer) {
                        actionsContainer.innerHTML = this.getFileActions(fileData, -1); // -1表示不特定索引
                    }
                } else {
                    // 如果没有找到对应卡片，可能需要重新渲染整个列表
                    // 这种情况应该很少发生
                    this.updateFileList();
                }
            }

            async removeFile(filename) {
                // 从本地数组中删除文件
                const index = this.uploadedFiles.findIndex(f => f.name === filename);
                if (index !== -1) {
                    this.uploadedFiles.splice(index, 1);
                }
                
                // 同步到服务器
                try {
                    await fetch('/api/remove_file', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ filename: filename })
                    });
                } catch (e) {
                    console.warn('同步删除到服务器失败:', e);
                }
                
                // 更新本地存储和界面
                this.saveToStorage();
                this.updateFileList();
            }

            updateSliderValue() {
                const slider = document.getElementById('maxPages');
                const value = document.getElementById('maxPagesValue');
                value.textContent = slider.value;
            }

            updateBackendOptions() {
                const backend = document.getElementById('backend').value;
                const serverUrlGroup = document.getElementById('serverUrlGroup');
                const ocrOptions = document.getElementById('ocrOptions');

                if (backend === 'vlm-sglang-client') {
                    serverUrlGroup.style.display = 'block';
                    ocrOptions.style.display = 'none';
                } else if (backend === 'pipeline') {
                    serverUrlGroup.style.display = 'none';
                    ocrOptions.style.display = 'block';
                } else if (backend === 'vlm-sglang-engine' || backend === 'vlm-transformers') {
                    serverUrlGroup.style.display = 'none';
                    ocrOptions.style.display = 'none';
                } else {
                    serverUrlGroup.style.display = 'none';
                    ocrOptions.style.display = 'none';
                }
            }

            async startConversion() {
                if (this.uploadedFiles.length === 0) {
                    alert('请先上传文件');
                    return;
                }

                // 检查队列状态
                try {
                    const queueStatus = await this.getQueueStatus();
                    if (queueStatus && queueStatus.queue_status === 'running') {
                        alert('队列正在处理中，请等待当前任务完成后再开始新的转换');
                        // 确保按钮保持禁用状态
                        const convertBtn = document.getElementById('convertBtn');
                        convertBtn.disabled = true;
                        convertBtn.innerHTML = '<span class="icon">⏳</span><span class="btn-text">队列处理中</span>';
                        convertBtn.title = '队列正在处理中，请等待完成';
                        return;
                    }
                } catch (error) {
                    console.warn('检查队列状态失败:', error);
                    // 如果检查失败，继续执行（避免阻塞用户操作）
                }

                this.isProcessing = true;
                const convertBtn = document.getElementById('convertBtn');
                convertBtn.disabled = true;
                convertBtn.innerHTML = '<span class="icon">⏳</span><span class="btn-text">正在处理</span>';
                convertBtn.title = '正在处理文件';

                try {
                    // 上传文件并自动加入队列
                    const taskIds = await this.uploadFilesWithProgress();
                    
                    if (taskIds && taskIds.length > 0) {
                        // 启动队列
                        await this.startQueue();
                        
                        
                        // 开始全局轮询文件状态
                        this.startGlobalStatusPolling();
                        
                        alert('文件已上传并加入队列！您可以关闭浏览器，任务将在后台继续运行。');
                    }
                    
                } catch (error) {
                    console.error('处理文件时出现错误:', error);
                    alert('处理文件失败: ' + error.message);
                } finally {
                    this.isProcessing = false;
                    // 检查实际队列状态以确定按钮状态
                    await this.updateConvertButtonState();
                }
            }

            async uploadFilesWithProgress() {
                const taskIds = [];
                let lastUploadedFile = null;
                
                for (const fileData of this.uploadedFiles) {
                    // 只上传状态为pending且没有任务ID的文件
                    if (fileData.status === 'pending' && fileData.file instanceof Blob && !fileData.taskId) {
                        const formData = new FormData();
                        formData.append('files', fileData.file);
                        
                        try {
                            const response = await fetch('/api/upload_with_progress', {
                                method: 'POST',
                                body: formData
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                taskIds.push(...result.task_ids);
                                
                                // 更新文件状态，关联任务ID
                                fileData.status = 'pending';  // 先设置为pending状态
                                fileData.taskId = result.task_ids[0];
                                fileData.progress = 10;
                                fileData.message = "文件上传完成";
                                
                                // 记录最后一个上传的文件
                                lastUploadedFile = fileData;
                                
                                // 如果队列状态是running，启动全局轮询
                                if (result.queue_status === 'running') {
                                    // 确保全局轮询正在运行
                                    if (!this.globalPollingInterval) {
                                        this.startGlobalStatusPolling();
                                    }
                                }
                            } else {
                                throw new Error(`上传失败: ${response.statusText}`);
                            }
                        } catch (error) {
                            console.error(`上传文件 ${fileData.name} 失败:`, error);
                            fileData.status = 'error';
                        }
                    } else if (fileData.taskId) {
                        // 如果文件已经有任务ID，也添加到taskIds中，但不需要重新上传
                        taskIds.push(fileData.taskId);
                    }
                }
                
                // 批量上传完成后，显示最后一个文件的预览
                if (lastUploadedFile && !this.manualViewFile) {
                    this.showFirstFilePreview(lastUploadedFile);
                }
                
                return taskIds;
            }

            async autoUploadPendingIfQueueRunning() {
                if (this.isAutoUploading) return;
                const hasPendingWithBlob = this.uploadedFiles.some(f => f.status === 'pending' && f.file instanceof Blob);
                if (!hasPendingWithBlob) return;
                try {
                    const qs = await this.getQueueStatus();
                    if (qs && qs.queue_status === 'running') {
                        this.isAutoUploading = true;
                        await this.uploadFilesWithProgress();
                    }
                } catch (e) {
                    console.warn('autoUploadPendingIfQueueRunning failed', e);
                } finally {
                    this.isAutoUploading = false;
                }
            }

            async startQueue() {
                const response = await fetch('/api/queue/start', {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    throw new Error(`启动队列失败: ${response.statusText}`);
                }
                
                return await response.json();
            }

            async stopQueue() {
                const response = await fetch('/api/queue/stop', {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    throw new Error(`停止队列失败: ${response.statusText}`);
                }
                
                return await response.json();
            }

            async getQueueStatus() {
                const response = await fetch('/api/queue/status');
                
                if (!response.ok) {
                    throw new Error(`获取队列状态失败: ${response.statusText}`);
                }
                
                return await response.json();
            }

            async updateConvertButtonState() {
                try {
                    const queueStatus = await this.getQueueStatus();
                    const convertBtn = document.getElementById('convertBtn');
                    this.updateQueueBadge(queueStatus);

                    if (queueStatus && queueStatus.queue_status === 'running') {
                        // 队列正在运行，禁用按钮
                        convertBtn.disabled = true;
                        convertBtn.innerHTML = '<span class="icon">⏳</span><span class="btn-text">队列处理中</span>';
                        convertBtn.title = '队列正在处理中，请等待完成';
                    } else {
                        // 队列空闲，启用按钮
                        convertBtn.disabled = false;
                        convertBtn.innerHTML = '<span class="icon">🚀</span><span class="btn-text">开始转换</span>';
                        convertBtn.title = '开始转换';
                    }
                } catch (error) {
                    console.warn('更新转换按钮状态失败:', error);
                }
            }

            // 更新 header 的队列状态徽章（🔄 转换中 / ✅ 空闲 / ⏸️ 已暂停）
            updateQueueBadge(queueStatus) {
                const badge = document.getElementById('queueBadge');
                const text = document.getElementById('queueBadgeText');
                if (!badge || !text) return;

                const status = queueStatus && queueStatus.queue_status;
                const queued = (queueStatus && queueStatus.queued_count) || 0;
                const running = queueStatus && queueStatus.current_processing_task;

                badge.classList.remove('idle', 'running', 'paused');
                if (status === 'running') {
                    badge.classList.add('running');
                    text.textContent = running
                        ? `转换中${queued > 0 ? ` · ${queued} 排队` : ''}`
                        : `队列运行中${queued > 0 ? ` · ${queued} 排队` : ''}`;
                    badge.title = '有转换任务正在运行';
                } else if (status === 'paused') {
                    badge.classList.add('paused');
                    text.textContent = `已暂停${queued > 0 ? ` · ${queued} 排队` : ''}`;
                    badge.title = '转换队列已暂停';
                } else {
                    badge.classList.add('idle');
                    text.textContent = '队列空闲';
                    badge.title = '当前没有转换任务运行';
                }
            }


            startFileStatusPolling(taskIds) {
                this.filePollingInterval = setInterval(async () => {
                    try {
                        const allCompleted = await this.updateFileStatuses(taskIds);
                        if (allCompleted) {
                            clearInterval(this.filePollingInterval);
                        }
                    } catch (error) {
                        console.error('轮询文件状态失败:', error);
                    }
                }, 2000); // 每2秒轮询一次
            }
            
            startGlobalStatusPolling() {
                if (this.globalPollingInterval) {
                    clearInterval(this.globalPollingInterval);
                }
                
                this.globalPollingInterval = setInterval(async () => {
                    try {
                        await this.updateAllFileStatuses();
                        // 队列运行中时，自动把新增的待处理文件上传入队
                        await this.autoUploadPendingIfQueueRunning();
                        // 自动预览策略：根据当前状态切换展示
                        this.autoPreviewTick();
                        // 更新转换按钮状态
                        await this.updateConvertButtonState();
                    } catch (error) {
                        console.error('轮询所有文件状态失败:', error);
                    }
                }, 2000); // 每2秒轮询一次
            }

            async updateFileStatuses(taskIds) {
                let allCompleted = true;
                
                for (const taskId of taskIds) {
                    try {
                        const response = await fetch(`/api/task/${taskId}`);
                        if (response.ok) {
                            const task = await response.json();
                            
                            // 根据任务ID找到对应的文件并更新状态
                            const fileData = this.uploadedFiles.find(f => f.taskId === taskId);
                            if (fileData) {
                                this.updateFileDataFromTask(fileData, task);
                                
                                if (task.status !== 'completed' && task.status !== 'failed') {
                                    allCompleted = false;
                                }
                            }
                        }
                    } catch (error) {
                        console.error(`获取任务 ${taskId} 状态失败:`, error);
                    }
                }
                
                // 更新文件列表显示
                            this.updateFileList();
                            this.saveToStorage();
                            this.syncFileListToServer();
                            
                return allCompleted;
            }
            
            async updateAllFileStatuses() {
                try {
                    // 获取所有任务状态
                    const response = await fetch('/api/tasks');
                    if (response.ok) {
                        const allTasks = await response.json();
                        
                        // 记录更新前的状态，以检测变化
                        const prevStatusMap = new Map();
                        this.uploadedFiles.forEach(f => {
                            if (f.taskId) {
                                prevStatusMap.set(f.taskId, {
                                    status: f.status,
                                    progress: f.progress,
                                    message: f.message
                                });
                            }
                        });
                        
                        // 更新所有有任务ID的文件
                        let hasActiveTasks = false;
                        let hasProcessing = false;
                        let hasNewProcessing = false; // 检测是否新增了处理中任务
                        let hasCompletedTask = false; // 检测是否有任务完成
                        
                        for (const fileData of this.uploadedFiles) {
                            if (fileData.taskId) {
                                const task = allTasks.find(t => t.task_id === fileData.taskId);
                                if (task) {
                                    // 保存更新前的状态
                                    const prevStatus = {
                                        status: fileData.status,
                                        progress: fileData.progress,
                                        message: fileData.message,
                                        errorMessage: fileData.errorMessage
                                    };
                                    
                                    this.updateFileDataFromTask(fileData, task);
                                    
                                    // 检查是否有状态变化
                                    const hasStatusChanged = 
                                        prevStatus.status !== fileData.status ||
                                        prevStatus.progress !== fileData.progress ||
                                        prevStatus.message !== fileData.message ||
                                        prevStatus.errorMessage !== fileData.errorMessage;
                                    
                                    // 检查是否有活跃任务（非完成状态）
                                    if (task.status !== 'completed' && task.status !== 'failed') {
                                        hasActiveTasks = true;
                                    }
                                    if (task.status === 'processing') {
                                        hasProcessing = true;
                                        // 检查是否是新进入处理中的任务
                                        if (prevStatus.status !== 'processing') {
                                            hasNewProcessing = true;
                                        }
                                    }
                                    
                                    // 检查是否有任务完成
                                    if (prevStatus.status !== 'completed' && fileData.status === 'completed') {
                                        hasCompletedTask = true;
                                    }
                                    
                                    // 仅当状态发生变化时，才更新对应的文件卡片
                                    if (hasStatusChanged) {
                                        this.updateSingleFileCard(fileData);
                                    }
                                }
                            }
                        }
                        
                        // 检查是否有之前活跃的任务变为非活跃
                        const hasPrevActiveTasks = Array.from(prevStatusMap.values())
                            .some(s => s.status !== 'completed' && s.status !== 'failed');
                        
                        // 需要重绘整个文件列表的情况：
                        // 1. 活跃任务状态发生变化
                        // 2. 有任务完成（会影响统计信息和排序）
                        // 3. 有新任务进入处理中状态（会影响排序）
                        const needsFullListUpdate = 
                            hasActiveTasks !== hasPrevActiveTasks || 
                            hasCompletedTask || 
                            hasNewProcessing;
                        
                        if (needsFullListUpdate) {
                            this.updateFileList(); // 这会重新排序和显示文件卡片
                        }
                        
                        this.saveToStorage();
                        // 仅在有需要同步的新文件时才调用syncFileListToServer
                        await this.syncFileListToServer();
                        
                        // 如果有新进入处理中的任务，更新预览（但不自动切换）
                        if (hasNewProcessing && !this.manualViewFile) {
                            // 找到正在处理的文件并更新预览
                            const processing = this.uploadedFiles.find(f => f.status === 'processing');
                            if (processing) {
                                this.showProcessingPreview(processing);
                            }
                        } else if (hasCompletedTask && !this.manualViewFile) {
                            // 如果有任务完成且用户没有手动锁定预览，展示最新完成的文件
                            const completed = this.uploadedFiles
                                .filter(f => f.status === 'completed')
                                .sort((a, b) => new Date(b.endTime || 0) - new Date(a.endTime || 0));
                            if (completed.length > 0) {
                                this.showMarkdownResult(completed[0].name);
                            }
                        }
                        
                        // 如果所有任务都已完成，停止轮询
                        if (!hasActiveTasks && this.globalPollingInterval) {
                            console.log('所有任务已完成，停止状态轮询');
                            clearInterval(this.globalPollingInterval);
                            this.globalPollingInterval = null;
                            

                            // 任务结束后，若未手动锁定预览，展示最后一个文件结果
                            this.autoPreviewTick();
                        }
                    }
                } catch (error) {
                    console.error('更新所有文件状态失败:', error);
                }
            }

            // 自动预览策略
            autoPreviewTick() {
                // 若用户手动查看过某个文件，则不自动切换
                if (this.manualViewFile) {
                    return;
                }

                // 优先展示正在处理的文件
                const processing = this.uploadedFiles.find(f => f.status === 'processing');
                if (processing) {
                    this.showProcessingPreview(processing);
                    return;
                }

                // 如无处理，若有已完成文件，展示最后一个完成的文件结果
                const completed = this.uploadedFiles.filter(f => f.status === 'completed');
                if (completed.length > 0) {
                    const last = completed[completed.length - 1];
                    this.showMarkdownResult(last.name);
                    return;
                }

                // 否则展示第一个已上传的文件预览
                if (this.uploadedFiles.length > 0) {
                    this.showFirstFilePreview();
                }
            }

            updateFileDataFromTask(fileData, task) {
                // 更新文件数据
                fileData.progress = task.progress || 0;
                fileData.message = task.message || '';
                
                // 更新时间信息
                if (task.start_time) {
                    fileData.startTime = task.start_time;
                }
                if (task.end_time) {
                    fileData.endTime = task.end_time;
                }
                if (task.upload_time) {
                    fileData.upload_time = task.upload_time;
                }
                
                // 映射任务状态到文件状态
                switch (task.status) {
                    case 'pending':
                        fileData.status = 'pending';
                        break;
                    case 'queued':
                        fileData.status = 'queued';
                        break;
                    case 'processing':
                        fileData.status = 'processing';
                        break;
                    case 'completed':
                        fileData.status = 'completed';
                        // 设置输出目录（从任务信息中获取）
                        if (task.result_path) {
                            fileData.outputDir = task.result_path;
                        }
                        // 保存结果信息，确保查看和下载按钮可用
                        this.results.set(fileData.name, {
                            mdContent: '',
                            txtContent: '',
                            zipPath: '',
                            pdfPath: '',
                            filename: fileData.name.replace(/\.[^/.]+$/, '.md'),
                            originalName: fileData.name,
                            type: 'completed'
                        });
                        break;
                    case 'failed':
                        fileData.status = 'error';
                        fileData.errorMessage = task.error_message || '处理失败';
                        break;
                }
            }


            async processFile(fileData) {
                try {
                    // 检查文件类型，如果不是PDF，先转换为PDF
                    let fileToProcess = fileData.file;
                    const fileName = fileData.name.toLowerCase();
                    const isPdf = fileName.endsWith('.pdf');
                    
                    if (!isPdf) {
                        // 非PDF文件，需要先转换为PDF
                        console.log(`转换非PDF文件: ${fileData.name}`);
                        // 这里需要调用后端的to_pdf接口
                        const convertResponse = await fetch('/convert_to_pdf', {
                            method: 'POST',
                            body: fileData.file
                        });
                        
                        if (convertResponse.ok) {
                            const pdfBlob = await convertResponse.blob();
                            fileToProcess = new File([pdfBlob], fileData.name.replace(/\.[^/.]+$/, '.pdf'), { type: 'application/pdf' });
                        } else {
                            throw new Error('文件转换为PDF失败');
                        }
                    }
                    
                    const formData = new FormData();
                    // files must be Blob/File
                    formData.append('files', fileToProcess);
                    // Always send strings for non-file fields
                    formData.append('output_dir', './output');
                    const lang = (document.getElementById('language') && document.getElementById('language').value) || 'ch';
                    formData.append('lang_list', String(lang));
                    formData.append('backend', String(document.getElementById('backend').value));
                    const isOcrEnabled = !!(document.getElementById('isOcr') && document.getElementById('isOcr').checked);
                    formData.append('parse_method', isOcrEnabled ? 'ocr' : 'auto');
                    formData.append('formula_enable', String(!!document.getElementById('formulaEnable').checked));
                    formData.append('table_enable', String(!!document.getElementById('tableEnable').checked));
                    const serverUrlVal = (document.getElementById('serverUrl') && document.getElementById('serverUrl').value) || '';
                    if (serverUrlVal) {
                        formData.append('server_url', String(serverUrlVal));
                    }
                    formData.append('return_md', String(true));
                    formData.append('return_images', String(true));
                    formData.append('response_format_zip', String(false));
                    formData.append('start_page_id', String(0));
                    const endPage = Math.max(0, parseInt(document.getElementById('maxPages').value, 10) - 1);
                    formData.append('end_page_id', String(endPage));

                    const response = await fetch('/file_parse', {
                        method: 'POST',
                        body: formData
                    });

                    if (response.ok) {
                        // 检查响应类型
                        const contentType = response.headers.get('content-type');
                        
                        if (contentType && contentType.includes('application/json')) {
                            // 如果是JSON响应，直接解析
                            const result = await response.json();
                            this.handleJsonResponse(fileData, result);
                        } else {
                            // 如果是ZIP文件，直接存储blob
                            const blob = await response.blob();
                            this.handleZipResponse(fileData, blob);
                        }

                        fileData.status = 'completed';
                        fileData.endTime = new Date();
                        if (fileData.startTime) {
                            fileData.processingTime = fileData.endTime - fileData.startTime;
                        }
                    } else {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                } catch (error) {
                    console.error(`处理文件 ${fileData.name} 时出错:`, error);
                    fileData.status = 'error';
                    fileData.endTime = new Date();
                    if (fileData.startTime) {
                        fileData.processingTime = fileData.endTime - fileData.startTime;
                    }
                }
            }
            
            async handleJsonResponse(fileData, result) {
                // 直接使用后端返回的结果（与gradio_app.py.sample完全一致）
                const mdContent = result.md_content || '';
                const txtContent = result.txt_content || '';
                const zipPath = result.archive_zip_path || '';
                const pdfPath = result.new_pdf_path || '';
                
                // 使用后端生成的文件名
                const fileName = result.file_name || fileData.name.replace(/\.[^/.]+$/, '');
                
                this.results.set(fileData.name, {
                    mdContent: mdContent,
                    txtContent: txtContent,
                    zipPath: zipPath,
                    pdfPath: pdfPath,
                    filename: fileName + '.md',
                    originalName: fileData.name,
                    type: 'json'
                });
                
                // 立即显示结果
                this.showMarkdownResult(fileData.name, mdContent, txtContent);
            }
            
            handleZipResponse(fileData, blob) {
                // 直接存储后端返回的ZIP文件（与gradio_app.py.sample完全一致）
                const timestamp = this.getCurrentTimestamp();
                const baseName = this.safeStem(fileData.name);
                const fileName = `${baseName}_${timestamp}`;
                
                this.results.set(fileData.name, {
                    blob: blob,
                    filename: fileName + '.zip',
                    originalName: fileData.name,
                    type: 'zip'
                });
                
                // 显示处理完成消息
                this.showMarkdownResult(fileData.name, 
                    '## 转换完成\n\n文件已成功转换，请点击下载按钮获取完整的转换结果。', 
                    '转换完成\n\n文件已成功转换，请点击下载按钮获取完整的转换结果。'
                );
            }
            
            
            // 生成当前时间戳（格式：yymmdd_HHMMSS）
            getCurrentTimestamp() {
                const now = new Date();
                const year = now.getFullYear().toString().slice(-2);
                const month = (now.getMonth() + 1).toString().padStart(2, '0');
                const day = now.getDate().toString().padStart(2, '0');
                const hours = now.getHours().toString().padStart(2, '0');
                const minutes = now.getMinutes().toString().padStart(2, '0');
                const seconds = now.getSeconds().toString().padStart(2, '0');
                return `${year}${month}${day}_${hours}${minutes}${seconds}`;
            }
            
            // 安全文件名处理（保留中文、字母、数字、下划线和点）
            safeStem(filename) {
                const nameWithoutExt = filename.replace(/\.[^/.]+$/, '');
                return nameWithoutExt.replace(/[^\w.\u4e00-\u9fff]/g, '_');
            }
            
            
            async showMarkdownResult(filename, mdContent = null, txtContent = null) {
                // 切换到Markdown rendering标签页
                this.switchToTab('markdown-rendering');
                
                // 如果没有提供内容，从已存储的结果中获取
                if (!mdContent || !txtContent) {
                    const result = this.results.get(filename);
                    if (result && result.mdContent && result.txtContent) {
                        mdContent = result.mdContent;
                        txtContent = result.txtContent;
                    } else {
                        // results 无缓存（刷新后 / 点击卡片预览），从后端按 taskId 取最新转换结果
                        const fileData = this.uploadedFiles.find(f => f.name === filename);
                        const taskId = fileData && fileData.taskId;
                        if (taskId) {
                            try {
                                const resp = await fetch(`/api/task/${taskId}/markdown`);
                                if (resp.ok) {
                                    const data = await resp.json();
                                    mdContent = data.md_content || '';
                                    txtContent = data.txt_content || mdContent;
                                }
                            } catch (_) { /* 忽略，下方兜底提示 */ }
                        }
                        if (!mdContent) {
                            mdContent = '## 提示\n\n暂无Markdown内容，请先转换文件。';
                            txtContent = '暂无Markdown内容，请先转换文件。';
                        }
                    }
                }
                
                // 显示渲染后的Markdown
                document.getElementById('markdownPreview').innerHTML = 
                    `<div class="markdown-content">${this.markdownToHtml(mdContent)}</div>`;
                
                // 显示原始Markdown文本
                document.getElementById('markdownText').textContent = txtContent;
                
                // 如果是PDF文件，显示PDF预览
                if (filename.toLowerCase().endsWith('.pdf')) {
                    const fileData = this.uploadedFiles.find(f => f.name === filename);
                    if (fileData && fileData.file instanceof Blob) {
                        this.showPdfPreview(fileData.file);
                    } else {
                        // 刷新后自动向后端查询匹配的PDF
                        try {
                            const resp = await fetch(`/output/find_pdf?q=${encodeURIComponent(filename)}`);
                            if (resp.ok) {
                                const data = await resp.json();
                                if (data && data.path) {
                                    // 使用 encodeURI 保留路径中的斜杠，仅对中文等字符编码
                                    this.showPdfPreviewByUrl(`/output/raw/${encodeURI(data.path)}`);
                                } else {
                                    this.clearPdfPreview();
                                }
                            } else {
                                this.clearPdfPreview();
                            }
                        } catch (_) {
                            this.clearPdfPreview();
                        }
                    }
                } else {
                    // 清空PDF预览区域
                    this.clearPdfPreview();
                }
            }


            async downloadResult(filename) {
                // 显示进度弹窗
                this.showDownloadProgressModal();
                const displayName = MinerUUtils.displayName(filename);
                this.updateDownloadProgress(0, `开始下载 ${displayName}...`);
                
                try {
                    const res = await fetch(`/download_file/${encodeURIComponent(filename)}`);
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    
                    this.updateDownloadProgress(50, `正在处理 ${displayName}...`);
                    
                    const blob = await res.blob();
                    this.updateDownloadProgress(90, `准备下载 ${displayName}...`);
                    
                    const blobUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = blobUrl;
                    a.download = `${this.safeStem(filename)}.zip`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(blobUrl);
                    
                    this.updateDownloadProgress(100, `下载完成: ${displayName}`);
                    
                    // 延迟隐藏进度条
                    setTimeout(() => {
                        this.hideDownloadProgressModal();
                    }, 1000);
                    
                } catch (err) {
                    console.error('下载失败:', err);
                    this.updateDownloadProgress(0, `下载失败: ${err.message}`);
                    setTimeout(() => {
                        this.hideDownloadProgressModal();
                    }, 2000);
                    alert('下载失败，请稍后重试');
                }
            }

            async downloadAllResults() {
                // 显示进度弹窗
                this.showDownloadProgressModal();
                
                try {
                    // 从服务器获取所有已完成文件的信息
                    const fileListResponse = await fetch('/api/file_list');
                    if (!fileListResponse.ok) {
                        throw new Error('获取文件列表失败');
                    }
                    const fileList = await fileListResponse.json();
                    
                    // 筛选出已完成状态的文件
                    const completedFiles = fileList.filter(f => f.status === 'completed');
                    if (completedFiles.length === 0) {
                        this.hideDownloadProgressModal();
                        alert('暂无已完成的文件可打包');
                        return;
                    }
                    
                    // 启动打包任务
                    const response = await fetch('/download_all_with_progress', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ files: completedFiles.map(f => f.name) })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    
                    const taskInfo = await response.json();
                    
                    if (taskInfo.status === 'error') {
                        throw new Error(taskInfo.message || '启动打包任务失败');
                    }
                    
                    const taskId = taskInfo.task_id;
                    
                    // 轮询进度直到完成
                    let completed = false;
                    while (!completed) {
                        await new Promise(resolve => setTimeout(resolve, 1000)); // 等待1秒
                        
                        try {
                            const progressResponse = await fetch(`/download_progress/${taskId}`);
                            if (!progressResponse.ok) {
                                throw new Error(`HTTP ${progressResponse.status}`);
                            }
                            
                            const progressData = await progressResponse.json();
                            
                            // 更新进度
                            this.updateDownloadProgress(
                                progressData.progress || 0, 
                                progressData.message || '处理中...', 
                                {
                                    currentDir: progressData.current_dir || '-',
                                    packedCount: progressData.packed_count || 0,
                                    totalCount: progressData.total_count || 0
                                }
                            );
                            
                            // 检查是否完成
                            if (progressData.status === 'completed') {
                                completed = true;
                                
                                // 下载文件
                                const downloadUrl = `/download_file/${encodeURIComponent(progressData.filename)}`;
                                const downloadRes = await fetch(downloadUrl);
                                
                                if (downloadRes.ok) {
                                    const blob = await downloadRes.blob();
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    const ts = this.getCurrentTimestamp();
                                    a.href = url;
                                    a.download = `completed_${completedFiles.length}_all_results_${ts}.zip`;
                                    document.body.appendChild(a);
                                    a.click();
                                    document.body.removeChild(a);
                                    URL.revokeObjectURL(url);
                                    
                                    this.updateDownloadProgress(100, '所有结果文件下载完成', {
                                        currentDir: '完成',
                                        packedCount: completedFiles.length,
                                        totalCount: completedFiles.length
                                    });
                                } else {
                                    throw new Error('下载文件失败');
                                }
                                
                                break; // 完成后退出循环
                            } else if (progressData.status === 'error') {
                                throw new Error(progressData.message || '打包失败');
                            }
                        } catch (e) {
                            console.error('获取进度失败:', e);
                            throw e;
                        }
                    }
                    
                    // 最后更新进度为完成
                    setTimeout(() => {
                        this.hideDownloadProgressModal();
                    }, 1000);
                    
                } catch (e) {
                    console.error('全部下载失败:', e);
                    this.updateDownloadProgress(0, `下载失败: ${e.message}`, {
                        currentDir: '-',
                        packedCount: 0,
                        totalCount: 0
                    });
                    setTimeout(() => {
                        this.hideDownloadProgressModal();
                    }, 2000);
                    alert('全部下载失败，请稍后重试');
                }
            }
            

            async viewResult(filename) {
                // 从文件列表中找到对应的任务ID
                const fileData = this.uploadedFiles.find(f => f.name === filename);
                if (!fileData || !fileData.taskId) {
                    alert('找不到对应的任务信息');
                    return;
                }
                
                try {
                    // 从后端API获取Markdown内容
                    const response = await fetch(`/api/task/${fileData.taskId}/markdown`);
                    if (response.ok) {
                        const result = await response.json();
                        // 显示Markdown内容
                        await this.showMarkdownResult(filename, result.md_content, result.txt_content);
                        // 锁定为用户手动查看，避免自动切换
                        this.manualViewFile = filename;
                    } else {
                        const error = await response.json();
                        alert(`获取Markdown内容失败: ${error.error}`);
                    }
                } catch (error) {
                    console.error('获取Markdown内容失败:', error);
                    alert('获取Markdown内容失败，请稍后重试');
                }
            }

            // 显示下载进度弹窗
            showDownloadProgressModal() {
                // 创建进度弹窗HTML
                const modalHtml = `
                    <div id="downloadProgressModal" class="download-progress-modal">
                        <div class="download-progress-content">
                            <div class="download-progress-header">
                                <h3>📦 正在打包下载</h3>
                                <button class="close-btn" onclick="app.hideDownloadProgressModal()">×</button>
                            </div>
                            <div class="progress-details" id="downloadProgressDetails">
                                <div class="detail-item">
                                    <span class="detail-label">正在打包:</span>
                                    <span class="detail-value" id="currentDir" title="">-</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">已打包目录数:</span>
                                    <span class="detail-value" id="packedCount">0</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">总目录数:</span>
                                    <span class="detail-value" id="totalCount">0</span>
                                </div>
                            </div>
                            <div class="download-progress-body">
                                <div class="progress-info">
                                    <div class="progress-text" id="downloadProgressText" style="display: none;">准备中...</div>
                                </div>
                                <div class="progress-bar-container">
                                    <div class="progress-bar-fill" id="downloadProgressBar" style="width: 0%"></div>
                                </div>
                                <div class="progress-percentage" id="downloadProgressPercent">0%</div>
                            </div>
                        </div>
                    </div>
                `;
                
                // 添加到页面
                document.body.insertAdjacentHTML('beforeend', modalHtml);
            }

            // 隐藏下载进度弹窗
            hideDownloadProgressModal() {
                const modal = document.getElementById('downloadProgressModal');
                if (modal) {
                    modal.remove();
                }
            }

            // 简化目录名显示
            simplifyDirectoryName(dirName) {
                if (!dirName || dirName === '-' || dirName === '完成') {
                    return dirName;
                }
                
                // 前方去掉5个"_"，后面去掉2个"_"
                let simplified = dirName;
                
                // 前方去掉5个"_"
                for (let i = 0; i < 5; i++) {
                    const firstUnderscoreIndex = simplified.indexOf('_');
                    if (firstUnderscoreIndex !== -1) {
                        simplified = simplified.substring(firstUnderscoreIndex + 1);
                    } else {
                        break;
                    }
                }
                
                // 后面去掉2个"_"
                for (let i = 0; i < 2; i++) {
                    const lastUnderscoreIndex = simplified.lastIndexOf('_');
                    if (lastUnderscoreIndex !== -1) {
                        simplified = simplified.substring(0, lastUnderscoreIndex);
                    } else {
                        break;
                    }
                }
                
                return simplified;
            }

            // 更新下载进度
            updateDownloadProgress(percentage, message, details = {}) {
                const progressText = document.getElementById('downloadProgressText');
                const progressPercent = document.getElementById('downloadProgressPercent');
                const progressBar = document.getElementById('downloadProgressBar');
                const currentDir = document.getElementById('currentDir');
                const packedCount = document.getElementById('packedCount');
                const totalCount = document.getElementById('totalCount');
                
                if (progressText) progressText.textContent = message;
                if (progressPercent) progressPercent.textContent = `${Math.round(percentage)}%`;
                if (progressBar) progressBar.style.width = `${percentage}%`;
                if (currentDir && details.currentDir) {
                    const simplifiedName = this.simplifyDirectoryName(details.currentDir);
                    currentDir.textContent = simplifiedName;
                }
                if (packedCount && details.packedCount !== undefined) packedCount.textContent = details.packedCount;
                if (totalCount && details.totalCount !== undefined) totalCount.textContent = details.totalCount;
            }

            showProcessingPreview(fileData) {
                // 切换到Markdown rendering标签页
                this.switchToTab('markdown-rendering');
                
                // 显示处理中的预览
                const processingContent = `# 正在处理文件

## 📄 ${MinerUUtils.displayName(fileData.name)}

**状态**: ⚙️ 处理中  
**进度**: 正在转换中，请稍候...

---

### 处理信息
- **文件名**: ${MinerUUtils.displayName(fileData.name)}
- **文件大小**: ${this.formatFileSize(fileData.size)}
- **开始时间**: ${new Date().toLocaleString()}
- **处理状态**: 正在OCR识别和格式转换

> 💡 **提示**: 处理时间取决于文件大小和复杂度，请耐心等待。

---

<div style="text-align: center; margin: 20px 0;">
    <div style="display: inline-block; padding: 10px 20px; background: #f0f8ff; border: 1px solid #4a90e2; border-radius: 8px;">
        <div style="font-size: 24px; margin-bottom: 10px;">⚙️</div>
        <div style="color: #4a90e2; font-weight: bold;">正在处理中...</div>
                        </div>
                    </div>`;

                document.getElementById('markdownPreview').innerHTML = 
                    `<div class="markdown-content">${this.markdownToHtml(processingContent)}</div>`;
                document.getElementById('markdownText').textContent = processingContent;
                
                // 如果是PDF文件，显示PDF预览
                if (fileData.name.toLowerCase().endsWith('.pdf')) {
                    this.showPdfPreview(fileData.file);
                } else {
                    // 清空PDF预览区域
                    this.clearPdfPreview();
                }
            }

            async showCompletedPreview(fileData) {
                // 直接调用showMarkdownResult，它会从后端API获取最新的Markdown内容
                await this.showMarkdownResult(fileData.name);
            }

            showFirstFilePreview(specificFile = null) {
                const targetFile = specificFile || (this.uploadedFiles.length > 0 ? this.uploadedFiles[0] : null);
                if (targetFile) {
                    // 切换到Markdown rendering标签页
                    this.switchToTab('markdown-rendering');
                    
                    // 显示文件的预览
                    const filePreviewContent = `# 📁 文件已上传

## ${this.getFileIcon(targetFile.name)} ${MinerUUtils.displayName(targetFile.name)}

**文件信息**:
- **文件名**: ${MinerUUtils.displayName(targetFile.name)}
- **文件大小**: ${this.formatFileSize(targetFile.size)}
- **上传时间**: ${this.formatTime(targetFile.uploadTime)}
- **状态**: ${this.getStatusBadge(targetFile.status)}
- **时间信息**: ${this.getTimeInfo(targetFile)}

---

### 下一步操作

> 🚀 **准备转换**: 文件已成功上传，点击右侧的"**开始转换**"按钮开始处理文件。

**转换选项**:
- ✅ 公式识别: 已启用
- ✅ 表格识别: 已启用
- 📄 最大页数: ${document.getElementById('maxPages').value}页
- 🔧 后端: ${document.getElementById('backend').value}

---

<div style="text-align: center; margin: 20px 0;">
    <div style="display: inline-block; padding: 15px 25px; background: #e8f5e8; border: 1px solid #4caf50; border-radius: 8px;">
        <div style="font-size: 20px; margin-bottom: 8px;">📋</div>
        <div style="color: #2e7d32; font-weight: bold;">文件准备就绪</div>
        <div style="color: #666; font-size: 14px; margin-top: 5px;">点击开始转换按钮开始处理</div>
    </div>
                        </div>`;

                    document.getElementById('markdownPreview').innerHTML = 
                        `<div class="markdown-content">${this.markdownToHtml(filePreviewContent)}</div>`;
                    document.getElementById('markdownText').textContent = filePreviewContent;
                    
                    // 如果是PDF文件，显示PDF预览
                    if (targetFile.name.toLowerCase().endsWith('.pdf') && targetFile.file instanceof Blob) {
                        this.showPdfPreview(targetFile.file);
                    } else {
                        // 清空PDF预览区域
                        this.clearPdfPreview();
                    }
                }
            }

            async clearAll() {
                if (this.isProcessing) {
                    alert('转换进行中，无法清空文件列表');
                    return;
                }
                
                if (!confirm('确定要清空所有文件吗？此操作不可撤销。')) {
                    return;
                }
                
                try {
                    // 调用后端API清空所有任务
                    const response = await fetch('/api/clear_all', {
                        method: 'POST'
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        console.log('清空成功:', result.message);
                    } else {
                        const error = await response.json();
                        console.error('清空失败:', error.error);
                        alert('清空失败: ' + error.error);
                        return;
                    }
                } catch (error) {
                    console.error('清空请求失败:', error);
                    alert('清空请求失败，请稍后重试');
                    return;
                }
                
                // 清空前端数据
                this.uploadedFiles = [];
                this.processingFiles.clear();
                this.results.clear();
                
                // 清理URL对象
                this.results.forEach(result => {
                    if (result.url) {
                        URL.revokeObjectURL(result.url);
                    }
                });
                
                // 停止全局轮询
                if (this.globalPollingInterval) {
                    clearInterval(this.globalPollingInterval);
                    this.globalPollingInterval = null;
                }
                
                this.updateFileList();
                this.saveToStorage();
                
                // 清空预览
                const defaultContent = `# 📄 MinerU PDF转换工具

## 欢迎使用智能PDF文档解析与转换平台

### 功能特点
- 📄 **PDF转换**: 支持PDF文档转换为Markdown格式
- 🖼️ **图片识别**: 支持图片文件OCR识别
- 🧮 **公式识别**: 自动识别数学公式和化学式
- 📊 **表格识别**: 智能识别表格结构
- 🌐 **多语言支持**: 支持中文、英文等多种语言

### 使用步骤
1. **上传文件**: 拖拽或点击选择PDF/图片文件
2. **配置选项**: 设置转换参数（页数、语言等）
3. **开始转换**: 点击"开始转换"按钮
4. **查看结果**: 在右侧查看转换后的Markdown内容

---

<div style="text-align: center; margin: 40px 0;">
    <div style="display: inline-block; padding: 20px 30px; background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 12px;">
        <div style="font-size: 48px; margin-bottom: 15px;">📁</div>
        <div style="color: #6c757d; font-size: 18px; font-weight: bold;">请上传文件开始转换</div>
        <div style="color: #adb5bd; font-size: 14px; margin-top: 8px;">支持PDF和图片文件</div>
    </div>
</div>`;

                document.getElementById('markdownPreview').innerHTML = 
                    `<div class="markdown-content">${this.markdownToHtml(defaultContent)}</div>`;
                document.getElementById('markdownText').textContent = defaultContent;
                
                // 清空PDF预览
                this.clearPdfPreview();
            }

            switchTab(e) {
                const tabName = e.target.dataset.tab;
                this.switchToTab(tabName, e.target);
            }

            // 版本和CHANGELOG相关方法
            showChangelog() {
                const modal = document.getElementById('changelogModal');
                const content = document.getElementById('changelogContent');
                
                // 显示模态框
                modal.style.display = 'block';
                
                // 加载CHANGELOG内容
                this.loadChangelogContent(content);
            }

            closeChangelog() {
                const modal = document.getElementById('changelogModal');
                modal.style.display = 'none';
            }

            async loadChangelogContent(contentElement) {
                try {
                    const response = await fetch('/CHANGELOG.md');
                    if (response.ok) {
                        const markdown = await response.text();
                        // 简单的Markdown到HTML转换
                        const html = this.markdownToHtml(markdown);
                        contentElement.innerHTML = `<div class="changelog-content">${html}</div>`;
                    } else {
                        contentElement.innerHTML = '<div class="error">无法加载更新日志</div>';
                    }
                } catch (error) {
                    console.error('加载CHANGELOG失败:', error);
                    contentElement.innerHTML = '<div class="error">加载更新日志时出错</div>';
                }
            }

            markdownToHtml(markdown) {
                return markdown
                    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
                    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
                    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
                    .replace(/^#### (.*$)/gim, '<h4>$1</h4>')
                    .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
                    .replace(/\*(.*)\*/gim, '<em>$1</em>')
                    .replace(/`(.*)`/gim, '<code>$1</code>')
                    .replace(/^- (.*$)/gim, '<li>$1</li>')
                    .replace(/^\[(.*)\]\((.*)\)/gim, '<a href="$2">$1</a>')
                    .replace(/\n\n/gim, '</p><p>')
                    .replace(/\n/gim, '<br>')
                    .replace(/^(<li>.*<\/li>)$/gim, '<ul>$1</ul>')
                    .replace(/<\/ul><ul>/gim, '')
                    .replace(/^(?!<[h|u|p|a|s|e|d])/gim, '<p>')
                    .replace(/(<li>.*<\/li><\/ul>)/gim, '<ul>$1</ul>');
            }
                
            switchToTab(tabName, targetElement = null) {
                // 更新标签页状态
                document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                
                // 如果提供了目标元素，激活它；否则找到对应的标签页
                if (targetElement) {
                    targetElement.classList.add('active');
                } else {
                    const tabElement = document.querySelector(`[data-tab="${tabName}"]`);
                    if (tabElement) {
                        tabElement.classList.add('active');
                    }
                }
                
                // 激活对应的内容区域
                const contentElement = document.getElementById(tabName + 'Tab');
                if (contentElement) {
                    contentElement.classList.add('active');
                }

                // 如果是示例标签页，刷新列表
                if (tabName === 'examples') {
                    this.loadExamples();
                }
            }

            async loadExamples() {
                try {
                    const response = await fetch('/list_output_files');
                    const files = await response.json();
                    
                    const examplesList = document.getElementById('examplesList');
                    const examplesCount = document.getElementById('examplesCount');
                    examplesList.innerHTML = '';

                    if (examplesCount) examplesCount.textContent = String(Array.isArray(files) ? files.length : 0);
                    if (files.length === 0) {
                        examplesList.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">输出目录为空</p>';
                        return;
                    }

                    files.forEach(file => {
                        const exampleItem = document.createElement('div');
                        exampleItem.className = 'example-item';
                        exampleItem.innerHTML = `
                            <input type="checkbox" class="example-checkbox" data-filename="${MinerUUtils.escapeHtml(file.name)}">
                            <div class="example-name" title="${MinerUUtils.escapeHtml(MinerUUtils.displayName(file.name))}">${MinerUUtils.escapeHtml(MinerUUtils.truncateFilename(MinerUUtils.displayName(file.name), 50))}</div>
                            <div class="example-type">${file.type}</div>
                        `;
                        examplesList.appendChild(exampleItem);
                    });
                } catch (error) {
                    console.error('加载输出文件失败:', error);
                    document.getElementById('examplesList').innerHTML = 
                        '<p style="text-align: center; color: #f44336; padding: 20px;">加载失败</p>';
                    const examplesCount = document.getElementById('examplesCount');
                    if (examplesCount) examplesCount.textContent = '0';
                }
            }

            async downloadAllOutputs() {
                // 获取用户选择的文件
                const selectedCheckboxes = document.querySelectorAll('.example-checkbox:checked');
                if (selectedCheckboxes.length === 0) {
                    alert('请先选择要下载的输出文件');
                    return;
                }
                
                const selectedFiles = Array.from(selectedCheckboxes).map(cb => cb.dataset.filename);
                
                // 显示进度弹窗
                this.showDownloadProgressModal();
                this.updateDownloadProgress(0, `开始打包 ${selectedFiles.length} 个选择的输出文件...`, {
                    currentDir: '-',
                    packedCount: 0,
                    totalCount: selectedFiles.length
                });
                
                try {
                    // 启动打包任务
                    const response = await fetch('/download_all_with_progress', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ files: selectedFiles })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    
                    const taskInfo = await response.json();
                    
                    if (taskInfo.status === 'error') {
                        throw new Error(taskInfo.message || '启动打包任务失败');
                    }
                    
                    const taskId = taskInfo.task_id;
                    
                    // 轮询进度直到完成
                    let completed = false;
                    while (!completed) {
                        await new Promise(resolve => setTimeout(resolve, 1000)); // 等待1秒
                        
                        try {
                            const progressResponse = await fetch(`/download_progress/${taskId}`);
                            if (!progressResponse.ok) {
                                throw new Error(`HTTP ${progressResponse.status}`);
                            }
                            
                            const progressData = await progressResponse.json();
                            
                            // 更新进度
                            this.updateDownloadProgress(
                                progressData.progress || 0, 
                                progressData.message || '处理中...', 
                                {
                                    currentDir: progressData.current_dir || '-',
                                    packedCount: progressData.packed_count || 0,
                                    totalCount: progressData.total_count || 0
                                }
                            );
                            
                            // 检查是否完成
                            if (progressData.status === 'completed') {
                                completed = true;
                                
                                // 下载文件
                                const downloadUrl = `/download_file/${encodeURIComponent(progressData.filename)}`;
                                const downloadRes = await fetch(downloadUrl);
                                
                                if (downloadRes.ok) {
                                    const blob = await downloadRes.blob();
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    const ts = this.getCurrentTimestamp();
                                    a.href = url;
                                    a.download = `selected_outputs_${ts}.zip`;
                                    document.body.appendChild(a);
                                    a.click();
                                    document.body.removeChild(a);
                                    URL.revokeObjectURL(url);
                                    
                                    this.updateDownloadProgress(100, '选择的输出文件下载完成', {
                                        currentDir: '完成',
                                        packedCount: selectedFiles.length,
                                        totalCount: selectedFiles.length
                                    });
                                } else {
                                    throw new Error('下载文件失败');
                                }
                                
                                break; // 完成后退出循环
                            } else if (progressData.status === 'error') {
                                throw new Error(progressData.message || '打包失败');
                            }
                        } catch (e) {
                            console.error('获取进度失败:', e);
                            throw e;
                        }
                    }
                    
                    // 最后更新进度为完成
                    setTimeout(() => {
                        this.hideDownloadProgressModal();
                    }, 1000);
                    
                } catch (e) {
                    console.error('打包选择的输出失败:', e);
                    this.updateDownloadProgress(0, `打包失败: ${e.message}`, {
                        currentDir: '-',
                        packedCount: 0,
                        totalCount: selectedFiles.length
                    });
                    setTimeout(() => {
                        this.hideDownloadProgressModal();
                    }, 2000);
                    alert('打包选择的输出失败，请稍后重试');
                }
            }

            selectAllExamples() {
                const checkboxes = document.querySelectorAll('.example-checkbox');
                const allChecked = Array.from(checkboxes).every(cb => cb.checked);
                
                checkboxes.forEach(cb => {
                    cb.checked = !allChecked;
                });
            }

            async deleteSelectedExamples() {
                const selectedFiles = Array.from(document.querySelectorAll('.example-checkbox:checked'))
                    .map(cb => cb.dataset.filename);

                if (selectedFiles.length === 0) {
                    alert('请选择要删除的文件');
                    return;
                }

                if (!confirm(`确定要删除选中的 ${selectedFiles.length} 个文件吗？`)) {
                    return;
                }

                try {
                    const response = await fetch('/delete_output_files', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ files: selectedFiles })
                    });

                    if (response.ok) {
                        alert('删除成功');
                        this.loadExamples();
                    } else {
                        throw new Error('删除失败');
                    }
                } catch (error) {
                    console.error('删除文件失败:', error);
                    alert('删除失败: ' + error.message);
                }
            }

            /**
             * 按照指定顺序对文件进行排序：正在处理、待处理、队列中、失败、已完成
             */
            sortFilesByStatus(files) {
                // 定义排序优先级
                const statusPriority = {
                    'processing': 0,  // 正在处理
                    'pending': 1,     // 待处理
                    'queued': 2,      // 队列中
                    'error': 3,       // 失败
                    'completed': 4    // 已完成
                };
                
                // 按照状态优先级排序，相同状态按文件名排序
                return files.slice().sort((a, b) => {
                    const priorityA = statusPriority[a.status] !== undefined ? statusPriority[a.status] : 5;
                    const priorityB = statusPriority[b.status] !== undefined ? statusPriority[b.status] : 5;
                    
                    // 如果状态优先级不同，按优先级排序
                    if (priorityA !== priorityB) {
                        return priorityA - priorityB;
                    }
                    
                    // 如果状态相同，按文件名排序
                    return a.name.localeCompare(b.name);
                });
            }

            formatFileSize(bytes) {
                if (bytes === 0) return '0 Bytes';
                const k = 1024;
                const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }

            markdownToHtml(markdown) {
                if (!markdown) return '';
                
                // 使用marked.js进行Markdown渲染
                if (typeof marked !== 'undefined') {
                    // 配置marked选项
                    marked.setOptions({
                        breaks: true,
                        gfm: true,
                        tables: true,
                        sanitize: false
                    });
                    
                    let html = marked.parse(markdown);
                    
                    // 渲染数学公式
                    this.renderMath(html);
                    
                    return html;
                } else {
                    // 降级到简单的Markdown渲染
                    return this.simpleMarkdownToHtml(markdown);
                }
            }
            
            renderMath(html) {
                // 延迟渲染数学公式，确保DOM已更新
                setTimeout(() => {
                    if (typeof renderMathInElement !== 'undefined') {
                        const element = document.getElementById('markdownPreview');
                        if (element) {
                            renderMathInElement(element, {
                                delimiters: [
                                    {left: '$$', right: '$$', display: true},
                                    {left: '$', right: '$', display: false},
                                    {left: '\\(', right: '\\)', display: false},
                                    {left: '\\[', right: '\\]', display: true}
                                ],
                                throwOnError: false
                            });
                        }
                    }
                }, 100);
            }
            
            simpleMarkdownToHtml(markdown) {
                // 简单的Markdown渲染作为降级方案
                let html = markdown;
                
                // 处理代码块
                html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
                html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
                
                // 处理标题
                html = html.replace(/^#{6}\s+(.*)$/gm, '<h6>$1</h6>');
                html = html.replace(/^#{5}\s+(.*)$/gm, '<h5>$1</h5>');
                html = html.replace(/^#{4}\s+(.*)$/gm, '<h4>$1</h4>');
                html = html.replace(/^#{3}\s+(.*)$/gm, '<h3>$1</h3>');
                html = html.replace(/^#{2}\s+(.*)$/gm, '<h2>$1</h2>');
                html = html.replace(/^#{1}\s+(.*)$/gm, '<h1>$1</h1>');
                
                // 处理其他格式
                html = html.replace(/^[-*]{3,}$/gm, '<hr>');
                html = html.replace(/^>\s+(.*)$/gm, '<blockquote>$1</blockquote>');
                html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width: 100%; height: auto;">');
                html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
                html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
                html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
                html = html.replace(/_(.*?)_/g, '<em>$1</em>');
                html = html.replace(/~~(.*?)~~/g, '<del>$1</del>');
                
                return html;
            }
            
            // 复制功能
            copyMarkdown() {
                const markdownPreview = document.getElementById('markdownPreview');
                if (markdownPreview) {
                    // 复制渲染后的HTML内容
                    const htmlContent = markdownPreview.innerHTML;
                    this.copyToClipboard(htmlContent);
                    this.showCopySuccess('copyMarkdownBtn');
                }
            }
            
            copyText() {
                const markdownText = document.getElementById('markdownText');
                if (markdownText && markdownText.textContent) {
                    this.copyToClipboard(markdownText.textContent);
                    this.showCopySuccess('copyTextBtn');
                }
            }
            
            copyToClipboard(text) {
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(text).then(() => {
                        console.log('复制成功');
                    }).catch(err => {
                        console.error('复制失败:', err);
                        this.fallbackCopyToClipboard(text);
                    });
                } else {
                    this.fallbackCopyToClipboard(text);
                }
            }
            
            fallbackCopyToClipboard(text) {
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                
                try {
                    document.execCommand('copy');
                    console.log('复制成功');
                } catch (err) {
                    console.error('复制失败:', err);
                }
                
                document.body.removeChild(textArea);
            }
            
            showCopySuccess(buttonId) {
                const button = document.getElementById(buttonId);
                const originalText = button.textContent;
                button.textContent = '✅ 已复制';
                button.style.background = '#28a745';
                button.style.color = 'white';
                
                setTimeout(() => {
                    button.textContent = originalText;
                    button.style.background = '#f6f8fa';
                    button.style.color = '#586069';
                }, 2000);
            }

            showPdfPreview(file) {
                const pdfPreviewContainer = document.getElementById('pdfPreviewContainer');
                if (!file) {
                    this.clearPdfPreview();
                    return;
                }

                // 仅在提供的是Blob/File时预览
                if (!(file instanceof Blob)) {
                    // 刷新后本地无Blob时给出友好提示
                    pdfPreviewContainer.innerHTML = `
                        <div class="pdf-preview-placeholder">
                            <div style="font-size: 48px; margin-bottom: 15px;">📄</div>
                            <p>无法显示PDF预览</p>
                            <p style="font-size: 14px; color: #999;">刷新后无法恢复文件数据，请重新上传 PDF 以查看预览</p>
                        </div>
                    `;
                    return;
                }

                const url = URL.createObjectURL(file);
                pdfPreviewContainer.innerHTML = `
                    <iframe src="${url}" 
                            class="pdf-preview-iframe"
                            title="PDF预览">
                    </iframe>
                `;
            }

            showPdfPreviewByUrl(url) {
                const pdfPreviewContainer = document.getElementById('pdfPreviewContainer');
                if (!url) {
                    this.clearPdfPreview();
                    return;
                }
                pdfPreviewContainer.innerHTML = `
                    <iframe src="${url}" 
                            class="pdf-preview-iframe"
                            title="PDF预览">
                    </iframe>
                `;
            }

            clearPdfPreview() {
                const pdfPreviewContainer = document.getElementById('pdfPreviewContainer');
                pdfPreviewContainer.innerHTML = `
                    <div class="pdf-preview-placeholder">
                        <div style="font-size: 48px; margin-bottom: 15px;">📄</div>
                        <p>PDF预览</p>
                        <p style="font-size: 14px; color: #999;">上传PDF文件后将显示预览</p>
                    </div>
                `;
            }
        }

        // 注意：全局轮询会在需要时自动启动（有活跃任务时）
        // 不需要在这里无条件启动

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new MinerUApp();
});
