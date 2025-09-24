// Chrome插件后台脚本
console.log('Background script 开始加载');

const DEFAULT_API_URL = 'http://127.0.0.1:8765';

/**
 * 规范化用户配置的API基础地址，确保不会重复 /api 路径
 * @param {string} rawUrl 原始输入
 * @returns {string} 清理后的基础地址
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
        pathname = pathname.replace(/\/+$/, ''); // 移除末尾斜杠

        // 如果路径以 /api 开头则移除，避免出现 /api/api/... 的情况
        if (pathname.toLowerCase().startsWith('/api')) {
            pathname = '';
        }

        parsed.pathname = pathname;
        parsed.search = '';
        parsed.hash = '';

        const normalized = parsed.toString().replace(/\/+$/, '');
        return normalized || DEFAULT_API_URL;
    } catch (error) {
        console.error('Background: 无效的API地址，已使用默认值', rawUrl, error);
        return DEFAULT_API_URL;
    }
}

// Service Worker保持活跃
self.addEventListener('install', event => {
    console.log('Service Worker 安装中');
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    console.log('Service Worker 激活中');
    event.waitUntil(self.clients.claim());
});

chrome.runtime.onInstalled.addListener((details) => {
    console.log('视频下载助手已安装/更新', details);
    
    // 初始化存储
    chrome.storage.local.get(['downloadQueue'], (result) => {
        if (!result.downloadQueue) {
            chrome.storage.local.set({
                downloadQueue: [],
                settings: {
                    idleStartTime: '23:00',
                    idleEndTime: '07:00',
                    guiAppPath: '',
                    apiUrl: DEFAULT_API_URL
                }
            });
            console.log('初始化存储完成');
        } else {
            console.log('存储已存在，队列长度:', result.downloadQueue.length);
        }
    });
});

chrome.runtime.onStartup.addListener(() => {
    console.log('Chrome扩展启动');
});

// 添加服务工作器保持活跃的机制
chrome.runtime.onConnect.addListener((port) => {
    console.log('建立连接:', port.name);
});

console.log('Background script 加载完成');

// 监听来自content script的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log('Background: 收到消息', request.action, request);
    
    try {
        if (request.action === 'addToDownloadQueue') {
            console.log('Background: 处理添加到队列请求');
            handleAddToDownloadQueue(request, sendResponse);
            return true; // 异步响应
        } else if (request.action === 'getDownloadQueue') {
            handleGetDownloadQueue(sendResponse);
            return true;
        } else if (request.action === 'clearDownloadQueue') {
            handleClearDownloadQueue(sendResponse);
            return true;
        } else if (request.action === 'exportToFile') {
            handleExportToFile(sendResponse);
            return true;
        } else if (request.action === 'checkApiConnection') {
            checkApiConnection(sendResponse);
            return true;
        } else {
            console.log('Background: 未知消息类型:', request.action);
            sendResponse({ success: false, error: '未知消息类型' });
            return false;
        }
    } catch (error) {
        console.error('Background: 消息处理出错:', error);
        sendResponse({ success: false, error: '消息处理出错: ' + error.message });
        return false;
    }
});

// 添加到下载队列
function handleAddToDownloadQueue(request, sendResponse) {
    console.log('Background: 收到添加到队列请求', request);
    
    const { platform, data } = request;
    
    try {
        // 创建任务对象
        const task = createTask(platform, data);
        console.log('Background: 创建任务对象', task);
        
        // 获取当前队列
        chrome.storage.local.get(['downloadQueue'], (result) => {
            const queue = result.downloadQueue || [];
            console.log('Background: 当前队列长度', queue.length);
            
            // 检查是否已存在相同的任务
            const existingTaskIndex = queue.findIndex(t => 
                t.params.youtube_url === task.params.youtube_url ||
                t.params.url === task.params.url
            );
            
            if (existingTaskIndex >= 0) {
                console.log('Background: 任务已存在，跳过');
                sendResponse({ success: false, error: '该视频已在下载队列中' });
                return;
            }
            
            // 直接调用API添加到GUI应用
            console.log('Background: 开始同步到GUI应用');
            syncToGuiApp(task, (success, errorMessage) => {
                if (success) {
                    // API成功，也保存到本地存储作为备份
                    queue.push(task);
                    chrome.storage.local.set({ downloadQueue: queue }, () => {
                        console.log('Background: 任务已通过API添加到GUI应用并保存到本地');
                        sendResponse({ 
                            success: true, 
                            message: '已添加到GUI应用队列',
                            queueLength: queue.length
                        });
                        console.log('Background: 已向content script发送成功响应 (API)');
                    });
                } else {
                    // API失败，保存到本地存储
                    console.log('Background: API调用失败，保存到本地队列', errorMessage);
                    queue.push(task);
                    chrome.storage.local.set({ downloadQueue: queue }, () => {
                        sendResponse({ 
                            success: true, 
                            message: '已添加到本地队列（无法连接GUI应用）',
                            queueLength: queue.length,
                            warning: errorMessage
                        });
                        console.log('Background: 已向content script发送成功响应 (本地队列)');
                    });
                }
            });
        });
    } catch (error) {
        console.error('Background: 处理请求时出错', error);
        sendResponse({ 
            success: false, 
            error: '处理请求时出错: ' + error.message 
        });
        console.log('Background: 已向content script发送失败响应');
    }
}

// 创建任务对象
function createTask(platform, data) {
    const baseParams = {
        model: null,
        api_key: null,
        base_url: null,
        whisper_model_size: "small",
        stream: true,
        summary_dir: "summaries",
        download_video: true,
        custom_prompt: null,
        template_path: null,
        generate_subtitles: true,
        translate_to_chinese: false,
        embed_subtitles: true,
        cookies_file: null,
        enable_transcription: false,
        generate_article: false
    };

    let task;
    
    switch (platform) {
        case 'youtube':
            task = {
                type: "youtube",
                params: {
                    ...baseParams,
                    youtube_url: data.url
                },
                title: `视频: ${data.title}`
            };
            break;
            
        case 'twitter':
            task = {
                type: "twitter", 
                params: {
                    ...baseParams,
                    url: data.url,
                    author: data.author,
                    text: data.text
                },
                title: `Twitter: ${data.title}`
            };
            break;
            
        case 'bilibili':
            task = {
                type: "bilibili",
                params: {
                    ...baseParams,
                    url: data.url,
                    uploader: data.uploader,
                    videoId: data.videoId
                },
                title: `B站: ${data.title}`
            };
            break;
            
        default:
            throw new Error('不支持的平台: ' + platform);
    }
    
    // 添加时间戳
    task.addedTime = new Date().toISOString();
    task.platform = platform;
    
    return task;
}

// 获取下载队列
function handleGetDownloadQueue(sendResponse) {
    chrome.storage.local.get(['downloadQueue'], (result) => {
        sendResponse({ success: true, queue: result.downloadQueue || [] });
    });
}

// 清空下载队列
function handleClearDownloadQueue(sendResponse) {
    chrome.storage.local.set({ downloadQueue: [] }, () => {
        sendResponse({ success: true });
    });
}

// 导出到文件
function handleExportToFile(sendResponse) {
    chrome.storage.local.get(['downloadQueue', 'settings'], (result) => {
        const queue = result.downloadQueue || [];
        const settings = result.settings || {};
        
        const exportData = {
            tasks: queue,
            idle_start_time: settings.idleStartTime || "23:00",
            idle_end_time: settings.idleEndTime || "07:00",
            exported_time: new Date().toISOString()
        };
        
        // 创建Blob并下载
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { 
            type: 'application/json' 
        });
        
        const url = URL.createObjectURL(blob);
        const filename = `idle_queue_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
        
        chrome.downloads.download({
            url: url,
            filename: filename
        }, (downloadId) => {
            if (chrome.runtime.lastError) {
                sendResponse({ success: false, error: chrome.runtime.lastError.message });
            } else {
                sendResponse({ success: true, downloadId, filename });
            }
        });
    });
}

// 同步到GUI应用
function syncToGuiApp(task, callback) {
    console.log('Background: syncToGuiApp 开始');
    // 获取设置
    chrome.storage.local.get(['settings'], (result) => {
        const settings = result.settings || {};
        const rawApiUrl = settings.apiUrl || DEFAULT_API_URL;
        const apiUrl = normalizeApiBaseUrl(rawApiUrl);

        if (apiUrl !== rawApiUrl) {
            chrome.storage.local.set({
                settings: {
                    ...settings,
                    apiUrl
                }
            }, () => {
                console.log('Background: 已规范化API地址:', apiUrl);
            });
        } else {
            console.log('Background: 使用API URL:', apiUrl);
        }
        
        // 优先使用HTTP API
        attemptApiCall(task, apiUrl, (success, errorMessage) => {
            console.log('Background: API调用结果:', success, errorMessage);
            if (success) {
                callback(true);
            } else {
                // API失败时使用备用方案（本地存储）
                callback(false, errorMessage);
            }
        });
    });
}

// 调用GUI应用API
function attemptApiCall(task, apiUrl, callback) {
    const url = `${apiUrl}/api/queue/add`;
    
    // 准备API请求数据
    const requestData = {
        platform: task.platform,
        url: task.params.youtube_url || task.params.url,
        title: task.title.replace(/^(视频|Twitter|B站): /, ''),
        videoId: task.params.videoId,
        uploader: task.params.uploader,
        author: task.params.author,
        text: task.params.text
    };
    
    console.log('Background: 调用GUI应用API:', url);
    console.log('Background: 请求数据:', requestData);
    
    // 添加超时处理
    const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('请求超时')), 10000); // 10秒超时
    });
    
    const fetchPromise = fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData)
    });
    
    Promise.race([fetchPromise, timeoutPromise])
    .then(response => {
        console.log('Background: 收到HTTP响应:', response.status, response.statusText);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Background: API响应数据:', data);
        if (data.success) {
            console.log('Background: API调用成功');
            callback(true, null);
        } else {
            console.error('Background: API返回错误:', data.error);
            callback(false, data.error || '服务器返回错误');
        }
    })
    .catch(error => {
        console.error('Background: API调用失败:', error);
        let errorMessage = 'API调用失败';
        if (error.message.includes('Failed to fetch')) {
            errorMessage = '无法连接到GUI应用，请确认应用是否正在运行';
        } else if (error.message.includes('请求超时')) {
            errorMessage = 'API请求超时';
        } else {
            errorMessage = error.message;
        }
        callback(false, errorMessage);
    });
}

// 检查API连接状态
function checkApiConnection(callback) {
    chrome.storage.local.get(['settings'], (result) => {
        const settings = result.settings || {};
        const apiUrl = normalizeApiBaseUrl(settings.apiUrl || DEFAULT_API_URL);
        
        fetch(`${apiUrl}/api/health`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => {
            if (response.ok) {
                return response.json();
            }
            throw new Error(`HTTP ${response.status}`);
        })
        .then(data => {
            callback({
                connected: true,
                message: data.message || 'API服务器正常',
                timestamp: data.timestamp
            });
        })
        .catch(error => {
            callback({
                connected: false,
                message: '无法连接到GUI应用',
                error: error.message
            });
        });
    });
}

// 定期清理旧的任务（可选）
chrome.alarms.create('cleanupOldTasks', { periodInMinutes: 60 });

chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'cleanupOldTasks') {
        cleanupOldTasks();
    }
});

function cleanupOldTasks() {
    chrome.storage.local.get(['downloadQueue'], (result) => {
        const queue = result.downloadQueue || [];
        const now = new Date();
        const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        
        // 保留最近24小时内的任务
        const filteredQueue = queue.filter(task => {
            const addedTime = new Date(task.addedTime);
            return addedTime > oneDayAgo;
        });
        
        if (filteredQueue.length !== queue.length) {
            chrome.storage.local.set({ downloadQueue: filteredQueue });
            console.log(`已清理 ${queue.length - filteredQueue.length} 个旧任务`);
        }
    });
}
