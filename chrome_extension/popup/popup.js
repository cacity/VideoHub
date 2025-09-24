// Popup界面脚本
document.addEventListener('DOMContentLoaded', () => {
    initializePopup();
});

const DEFAULT_API_URL = 'http://127.0.0.1:8765';

/**
 * 规范化API基础地址，避免用户将 /api 部分写入配置
 * @param {string} rawUrl 原始输入
 * @returns {string} 清理后的地址
 */
function normalizeApiBaseUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== 'string') {
        return DEFAULT_API_URL;
    }

    let url = rawUrl.trim();
    if (!url) {
        return DEFAULT_API_URL;
    }

    if (!/^https?:\/\//i.test(url)) {
        url = `http://${url}`;
    }

    try {
        const parsed = new URL(url);
        let pathname = parsed.pathname || '';
        pathname = pathname.replace(/\/+$/, '');

        if (pathname.toLowerCase().startsWith('/api')) {
            pathname = '';
        }

        parsed.pathname = pathname;
        parsed.search = '';
        parsed.hash = '';

        const normalized = parsed.toString().replace(/\/+$/, '');
        return normalized || DEFAULT_API_URL;
    } catch (error) {
        console.error('Popup: 无效的API地址，已重置为默认值', rawUrl, error);
        return DEFAULT_API_URL;
    }
}

// 初始化弹窗
function initializePopup() {
    loadSettings();
    loadQueue();
    bindEvents();
    updateStatus();
    checkApiStatus();
}

// 绑定事件监听器
function bindEvents() {
    // 选项卡切换
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', (e) => {
            switchTab(e.target.dataset.tab);
        });
    });

    // 队列操作按钮
    document.getElementById('exportBtn').addEventListener('click', exportQueue);
    document.getElementById('clearBtn').addEventListener('click', clearQueue);
    document.getElementById('refreshBtn').addEventListener('click', loadQueue);

    // 设置按钮
    document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
    document.getElementById('resetSettingsBtn').addEventListener('click', resetSettings);
    
    // API测试按钮
    document.getElementById('testApiBtn').addEventListener('click', testApiConnection);
}

// 选项卡切换
function switchTab(tabName) {
    // 切换选项卡按钮状态
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // 切换面板显示
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.getElementById(`${tabName}-panel`).classList.add('active');
}

// 加载队列
function loadQueue() {
    setStatus('loading', '加载中...');
    
    chrome.runtime.sendMessage({
        action: 'getDownloadQueue'
    }, (response) => {
        if (response && response.success) {
            displayQueue(response.queue);
            updateQueueCount(response.queue.length);
            setStatus('ready', '就绪');
        } else {
            setStatus('error', '加载失败');
            console.error('加载队列失败:', response);
        }
    });
}

// 显示队列
function displayQueue(queue) {
    const queueList = document.getElementById('queueList');
    const emptyState = document.getElementById('emptyState');
    
    if (!queue || queue.length === 0) {
        queueList.innerHTML = '';
        queueList.appendChild(emptyState);
        return;
    }
    
    // 隐藏空状态
    if (emptyState.parentNode) {
        emptyState.parentNode.removeChild(emptyState);
    }
    
    // 生成队列项目
    queueList.innerHTML = '';
    queue.forEach((task, index) => {
        const queueItem = createQueueItem(task, index);
        queueList.appendChild(queueItem);
    });
}

// 创建队列项目
function createQueueItem(task, index) {
    const div = document.createElement('div');
    div.className = 'queue-item';
    
    const platform = task.platform || 'unknown';
    const title = task.title || '未知标题';
    const url = task.params?.youtube_url || task.params?.url || '无URL';
    const addedTime = task.addedTime ? new Date(task.addedTime).toLocaleString() : '未知时间';
    
    div.innerHTML = `
        <div class="queue-item-header">
            <span class="platform-badge ${platform}">${platform.toUpperCase()}</span>
            <div class="queue-item-title">${escapeHtml(title)}</div>
            <span class="queue-item-time">${addedTime}</span>
        </div>
        <div class="queue-item-url">${escapeHtml(url)}</div>
    `;
    
    return div;
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 更新队列数量
function updateQueueCount(count) {
    document.getElementById('queueCount').textContent = count;
}

// 导出队列
function exportQueue() {
    setStatus('loading', '导出中...');
    
    chrome.runtime.sendMessage({
        action: 'exportToFile'
    }, (response) => {
        if (response && response.success) {
            setStatus('ready', '导出成功');
            showNotification(`队列已导出为 ${response.filename}`, 'success');
        } else {
            setStatus('error', '导出失败');
            showNotification('导出失败: ' + (response?.error || '未知错误'), 'error');
        }
    });
}

// 清空队列
function clearQueue() {
    if (!confirm('确定要清空下载队列吗？此操作不可撤销。')) {
        return;
    }
    
    setStatus('loading', '清空中...');
    
    chrome.runtime.sendMessage({
        action: 'clearDownloadQueue'
    }, (response) => {
        if (response && response.success) {
            loadQueue(); // 重新加载队列
            setStatus('ready', '已清空');
            showNotification('队列已清空', 'success');
        } else {
            setStatus('error', '清空失败');
            showNotification('清空失败', 'error');
        }
    });
}

// 加载设置
function loadSettings() {
    chrome.storage.local.get(['settings'], (result) => {
        const settings = result.settings || {};
        
        document.getElementById('idleStartTime').value = settings.idleStartTime || '23:00';
        document.getElementById('idleEndTime').value = settings.idleEndTime || '07:00';
        const normalizedApiUrl = normalizeApiBaseUrl(settings.apiUrl || DEFAULT_API_URL);

        if (!settings.apiUrl || settings.apiUrl !== normalizedApiUrl) {
            chrome.storage.local.set({
                settings: {
                    ...settings,
                    apiUrl: normalizedApiUrl
                }
            });
        }

        document.getElementById('apiUrl').value = normalizedApiUrl;
    });
}

// 保存设置
function saveSettings() {
    const settings = {
        idleStartTime: document.getElementById('idleStartTime').value,
        idleEndTime: document.getElementById('idleEndTime').value,
        apiUrl: normalizeApiBaseUrl(document.getElementById('apiUrl').value)
    };
    
    chrome.storage.local.set({ settings }, () => {
        showNotification('设置已保存', 'success');
        checkApiStatus(); // 保存后重新检查API连接
    });
}

// 重置设置
function resetSettings() {
    if (!confirm('确定要重置所有设置吗？')) {
        return;
    }
    
    document.getElementById('idleStartTime').value = '23:00';
    document.getElementById('idleEndTime').value = '07:00';
    document.getElementById('apiUrl').value = DEFAULT_API_URL;

    saveSettings();
    showNotification('设置已重置', 'success');
}

// 设置状态
function setStatus(type, text) {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    
    statusDot.className = `status-dot ${type}`;
    statusText.textContent = text;
}

// 更新状态
function updateStatus() {
    // 检查当前标签页是否支持
    chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
        if (tabs[0]) {
            const url = tabs[0].url;
            const supportedSites = [
                'youtube.com',
                'twitter.com',
                'x.com',
                'bilibili.com'
            ];
            
            const isSupported = supportedSites.some(site => url.includes(site));
            
            if (isSupported) {
                setStatus('ready', '支持的网站');
            } else {
                setStatus('error', '不支持的网站');
            }
        }
    });
}

// 显示通知
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 10px;
        right: 10px;
        padding: 12px 16px;
        background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#17a2b8'};
        color: white;
        border-radius: 4px;
        font-size: 12px;
        z-index: 10000;
        opacity: 0;
        transition: opacity 0.3s;
        max-width: 250px;
        word-wrap: break-word;
    `;
    notification.textContent = message;
    
    // 添加到页面
    document.body.appendChild(notification);
    
    // 显示动画
    setTimeout(() => {
        notification.style.opacity = '1';
    }, 100);
    
    // 自动移除
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// 监听存储变化以实时更新队列
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes.downloadQueue) {
        const newQueue = changes.downloadQueue.newValue || [];
        displayQueue(newQueue);
        updateQueueCount(newQueue.length);
    }
});

// 检查API连接状态
function checkApiStatus() {
    setApiStatus('checking', '检查连接中...');
    
    chrome.runtime.sendMessage({
        action: 'checkApiConnection'
    }, (response) => {
        if (response && response.connected) {
            setApiStatus('connected', 'GUI应用已连接');
        } else {
            setApiStatus('disconnected', response ? response.message : '连接失败');
        }
    });
}

// 测试API连接
function testApiConnection() {
    checkApiStatus();
}

// 设置API状态
function setApiStatus(type, text) {
    const apiDot = document.getElementById('apiDot');
    const apiText = document.getElementById('apiText');
    
    apiDot.className = `api-dot ${type}`;
    apiText.textContent = text;
}

// 页面可见性变化时刷新状态
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        updateStatus();
        loadQueue();
        checkApiStatus();
    }
});
