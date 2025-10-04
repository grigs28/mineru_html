/**
 * MinerU 工具函数库
 * 包含通用的工具方法和辅助函数
 */

class MinerUUtils {
    /**
     * 格式化文件大小
     */
    static formatFileSize(bytes) {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * 格式化时间
     */
    static formatTime(time) {
        if (!time) return '未知';
        return new Date(time).toLocaleString('zh-CN');
    }

    /**
     * 获取文件图标
     */
    static getFileIcon(filename) {
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

    /**
     * 获取状态标签
     */
    static getStatusBadge(status) {
        const statusMap = {
            'pending': '⏳ 待处理',
            'queued': '📋 队列中',
            'processing': '⚙️ 处理中',
            'completed': '✅ 成功',
            'error': '❌ 失败'
        };
        return statusMap[status] || '❓ 未知状态';
    }

    /**
     * 计算处理时长
     */
    static calculateProcessingTime(startTime, endTime) {
        if (!startTime || !endTime) return '未知';
        const start = new Date(startTime);
        const end = new Date(endTime);
        const diff = end - start;
        const minutes = Math.floor(diff / 60000);
        const seconds = Math.floor((diff % 60000) / 1000);
        
        if (minutes > 0) {
            return `${minutes}分${seconds}秒`;
        } else {
            return `${seconds}秒`;
        }
    }

    /**
     * 获取当前时间戳
     */
    static getCurrentTimestamp() {
        return new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    }

    /**
     * 防抖函数
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * 节流函数
     */
    static throttle(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    /**
     * 深拷贝对象
     */
    static deepClone(obj) {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj.getTime());
        if (obj instanceof Array) return obj.map(item => this.deepClone(item));
        if (typeof obj === 'object') {
            const clonedObj = {};
            for (const key in obj) {
                if (obj.hasOwnProperty(key)) {
                    clonedObj[key] = this.deepClone(obj[key]);
                }
            }
            return clonedObj;
        }
    }

    /**
     * 验证文件类型
     */
    static isValidFileType(filename) {
        const ext = filename.toLowerCase().split('.').pop();
        return ['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'].includes(ext);
    }

    /**
     * 生成唯一ID
     */
    static generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    }

    /**
     * 安全的JSON解析
     */
    static safeJsonParse(str, defaultValue = null) {
        try {
            return JSON.parse(str);
        } catch (e) {
            return defaultValue;
        }
    }

    /**
     * 安全的JSON字符串化
     */
    static safeJsonStringify(obj, defaultValue = '{}') {
        try {
            return JSON.stringify(obj);
        } catch (e) {
            return defaultValue;
        }
    }
}

// 导出到全局作用域
window.MinerUUtils = MinerUUtils;
