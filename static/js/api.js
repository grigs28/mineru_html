/**
 * MinerU API 客户端
 * 处理与后端的所有API通信
 */

class MinerUAPI {
    /**
     * 基础API请求方法
     */
    static async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const config = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers,
            },
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            
            return await response.text();
        } catch (error) {
            console.error(`API请求失败 [${url}]:`, error);
            throw error;
        }
    }

    /**
     * 获取版本信息
     */
    static async getVersion() {
        return await this.request('/api/version');
    }

    /**
     * 获取文件列表
     */
    static async getFileList() {
        return await this.request('/api/file_list');
    }

    /**
     * 更新文件列表
     */
    static async updateFileList(files) {
        return await this.request('/api/file_list', {
            method: 'POST',
            body: JSON.stringify({ files }),
        });
    }

    /**
     * 获取队列状态
     */
    static async getQueueStatus() {
        return await this.request('/api/queue_status');
    }

    /**
     * 启动队列
     */
    static async startQueue() {
        return await this.request('/api/start_queue', {
            method: 'POST',
        });
    }

    /**
     * 停止队列
     */
    static async stopQueue() {
        return await this.request('/api/stop_queue', {
            method: 'POST',
        });
    }

    /**
     * 上传文件（带进度）
     */
    static async uploadFilesWithProgress(files) {
        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file);
        });

        return await this.request('/api/upload_with_progress', {
            method: 'POST',
            headers: {}, // 让浏览器自动设置Content-Type
            body: formData,
        });
    }

    /**
     * 获取任务状态
     */
    static async getTaskStatus(taskId) {
        return await this.request(`/api/task_status/${taskId}`);
    }

    /**
     * 获取所有任务状态
     */
    static async getAllTasksStatus() {
        return await this.request('/api/all_tasks_status');
    }

    /**
     * 删除任务
     */
    static async deleteTask(taskId) {
        return await this.request(`/api/delete_task/${taskId}`, {
            method: 'DELETE',
        });
    }

    /**
     * 获取输出文件列表
     */
    static async getOutputFiles() {
        return await this.request('/list_output_files');
    }

    /**
     * 删除输出文件
     */
    static async deleteOutputFiles(files) {
        return await this.request('/delete_output_files', {
            method: 'POST',
            body: JSON.stringify({ files }),
        });
    }

    /**
     * 下载文件
     */
    static async downloadFile(filename) {
        return await this.request(`/download_file/${encodeURIComponent(filename)}`);
    }

    /**
     * 下载所有选择的文件
     */
    static async downloadAllSelected(files) {
        return await this.request('/download_all', {
            method: 'POST',
            body: JSON.stringify({ files }),
        });
    }

    /**
     * 下载所有选择的文件（带进度）
     */
    static async downloadAllSelectedWithProgress(files) {
        return await this.request('/download_all_with_progress', {
            method: 'POST',
            body: JSON.stringify({ files }),
        });
    }

    /**
     * 获取下载进度
     */
    static async getDownloadProgress(taskId) {
        return await this.request(`/download_progress/${taskId}`);
    }

    /**
     * 获取Markdown内容
     */
    static async getMarkdownContent(filename) {
        return await this.request(`/api/markdown_content/${encodeURIComponent(filename)}`);
    }

    /**
     * 转换PDF为Markdown
     */
    static async convertToMarkdown(files, options = {}) {
        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file);
        });

        // 添加转换选项
        Object.keys(options).forEach(key => {
            formData.append(key, options[key]);
        });

        return await this.request('/convert_to_markdown', {
            method: 'POST',
            headers: {},
            body: formData,
        });
    }

    /**
     * 获取PDF预览
     */
    static async getPdfPreview(filename) {
        const response = await fetch(`/output/raw/${encodeURIComponent(filename)}`);
        if (response.ok) {
            return response.blob();
        }
        throw new Error(`PDF预览获取失败: ${response.statusText}`);
    }

    /**
     * 健康检查
     */
    static async healthCheck() {
        try {
            const response = await fetch('/api/health');
            return response.ok;
        } catch (error) {
            return false;
        }
    }

    /**
     * 批量API调用
     */
    static async batchRequest(requests) {
        const promises = requests.map(request => 
            this.request(request.url, request.options).catch(error => ({
                error: error.message,
                url: request.url
            }))
        );
        
        return await Promise.all(promises);
    }
}

// 导出到全局作用域
window.MinerUAPI = MinerUAPI;
