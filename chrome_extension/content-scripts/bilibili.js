// Bilibili页面内容脚本
(function() {
    'use strict';

    let downloadButton = null;
    let currentVideoUrl = null;

    // 初始化函数
    function init() {
        console.log('Bilibili下载助手已加载');
        
        // 监听页面变化
        const observer = new MutationObserver(() => {
            checkAndInjectButton();
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        // 立即检查当前页面
        checkAndInjectButton();
        
        // 监听URL变化
        let lastUrl = location.href;
        new MutationObserver(() => {
            const currentUrl = location.href;
            if (currentUrl !== lastUrl) {
                lastUrl = currentUrl;
                setTimeout(checkAndInjectButton, 500);
            }
        }).observe(document, {subtree: true, childList: true});
    }

    // 检查并注入下载按钮
    function checkAndInjectButton() {
        if (!isVideoPage()) {
            return;
        }

        const videoUrl = getVideoUrl();
        if (!videoUrl || videoUrl === currentVideoUrl) {
            return;
        }

        currentVideoUrl = videoUrl;
        
        // 移除旧按钮
        if (downloadButton) {
            downloadButton.remove();
            downloadButton = null;
        }

        // 等待页面元素加载完成
        setTimeout(() => {
            injectDownloadButton();
        }, 1000);
    }

    // 检查是否在视频页面
    function isVideoPage() {
        return window.location.pathname.includes('/video/') || 
               window.location.pathname.includes('/bangumi/play/') ||
               window.location.href.includes('bilibili.com/video/') ||
               window.location.href.includes('bilibili.com/bangumi/play/');
    }

    // 获取视频URL
    function getVideoUrl() {
        return window.location.href;
    }

    // 获取BV号或AV号
    function getVideoId() {
        const url = window.location.href;
        
        // 匹配BV号
        const bvMatch = url.match(/BV[a-zA-Z0-9]+/);
        if (bvMatch) {
            return bvMatch[0];
        }
        
        // 匹配AV号
        const avMatch = url.match(/av(\d+)/);
        if (avMatch) {
            return 'av' + avMatch[1];
        }
        
        // 匹配番剧
        const bangumiMatch = url.match(/ep(\d+)/);
        if (bangumiMatch) {
            return 'ep' + bangumiMatch[1];
        }
        
        return null;
    }

    // 获取视频标题
    function getVideoTitle() {
        // 尝试多个可能的标题选择器
        const titleSelectors = [
            'h1[title]', // 新版页面
            '.video-title', // 旧版页面
            'h1.tit', // 另一种旧版页面
            '.media-title', // 番剧页面
            'h1' // 通用h1标签
        ];

        for (const selector of titleSelectors) {
            const titleElement = document.querySelector(selector);
            if (titleElement) {
                return titleElement.textContent.trim() || titleElement.title || '未知标题';
            }
        }

        // 如果都找不到，尝试从页面title获取
        const pageTitle = document.title;
        if (pageTitle && pageTitle !== 'bilibili') {
            return pageTitle.replace(/_哔哩哔哩.*$/, '').trim();
        }

        return '未知标题';
    }

    // 获取UP主信息
    function getUploaderInfo() {
        const uploaderSelectors = [
            '.up-info .up-name', // 新版页面
            '.username', // 旧版页面
            '.up-detail .up-name', // 另一种新版页面
            '.media-info .media-author' // 番剧页面
        ];

        for (const selector of uploaderSelectors) {
            const uploaderElement = document.querySelector(selector);
            if (uploaderElement) {
                return uploaderElement.textContent.trim();
            }
        }

        return '未知UP主';
    }

    // 注入下载按钮
    function injectDownloadButton() {
        // 查找合适的位置注入按钮
        const targetSelectors = [
            '.video-toolbar-right', // 新版页面右侧工具栏
            '.video-toolbar .ops', // 旧版页面操作区
            '.tool-bar', // 通用工具栏
            '.media-tool', // 番剧页面工具栏
            '.video-info .video-toolbar', // 备选位置
        ];

        let targetElement = null;
        for (const selector of targetSelectors) {
            targetElement = document.querySelector(selector);
            if (targetElement) {
                break;
            }
        }

        if (!targetElement) {
            // 如果找不到工具栏，尝试找到视频标题区域并在其下方插入
            const titleArea = document.querySelector('.video-info, .media-info');
            if (titleArea) {
                targetElement = titleArea;
            } else {
                console.log('Bilibili下载助手: 未找到合适的注入位置');
                return;
            }
        }

        // 创建下载按钮
        downloadButton = document.createElement('button');
        downloadButton.className = 'video-downloader-btn';
        downloadButton.textContent = '添加到下载队列';
        downloadButton.title = '点击将视频添加到闲时下载队列';

        // 创建提示文本
        const tooltip = document.createElement('div');
        tooltip.className = 'video-downloader-tooltip';
        tooltip.textContent = '添加到闲时下载队列';
        downloadButton.appendChild(tooltip);

        // 添加点击事件
        downloadButton.addEventListener('click', handleDownloadClick);

        // 插入按钮
        targetElement.appendChild(downloadButton);

        console.log('Bilibili下载助手: 按钮已注入');
    }

    // 处理下载按钮点击
    function handleDownloadClick(event) {
        event.preventDefault();
        event.stopPropagation();

        const button = event.target;
        const videoUrl = getVideoUrl();
        const videoTitle = getVideoTitle();
        const videoId = getVideoId();
        const uploader = getUploaderInfo();

        if (!videoId) {
            alert('无法获取视频信息');
            return;
        }

        // 设置按钮为加载状态
        button.className = 'video-downloader-btn loading';
        button.textContent = '正在添加...';

        // 发送消息到background script
        chrome.runtime.sendMessage({
            action: 'addToDownloadQueue',
            platform: 'bilibili',
            data: {
                url: videoUrl,
                title: videoTitle,
                videoId: videoId,
                uploader: uploader
            }
        }, (response) => {
            if (response && response.success) {
                // 显示成功状态
                button.className = 'video-downloader-btn success';
                button.textContent = '已添加到队列';
                
                // 3秒后恢复原状态
                setTimeout(() => {
                    button.className = 'video-downloader-btn';
                    button.textContent = '添加到下载队列';
                }, 3000);
            } else {
                // 显示错误状态
                button.className = 'video-downloader-btn error';
                button.textContent = '添加失败';
                alert('添加到下载队列失败: ' + (response?.error || '未知错误'));
                
                // 3秒后恢复原状态
                setTimeout(() => {
                    button.className = 'video-downloader-btn';
                    button.textContent = '添加到下载队列';
                }, 3000);
            }
        });
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();