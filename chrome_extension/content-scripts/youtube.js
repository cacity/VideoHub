// YouTube页面内容脚本
(function() {
    'use strict';

    let downloadButton = null;
    let currentVideoId = null;
    let injectionRetryTimer = null;

    // 初始化函数
    function init() {
        console.log('YouTube下载助手已加载');
        
        // 监听页面变化（YouTube是SPA）
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
                setTimeout(checkAndInjectButton, 500); // 延迟执行，等待页面加载
            }
        }).observe(document, {subtree: true, childList: true});
    }

    // 检查并注入下载按钮
    function checkAndInjectButton() {
        // 检查是否在视频页面
        if (!isVideoPage()) {
            removeDownloadButton();
            currentVideoId = null;
            return;
        }

        const videoId = getVideoId();
        if (!videoId) {
            return;
        }

        if (downloadButton && downloadButton.isConnected && videoId === currentVideoId) {
            return;
        }

        if (videoId !== currentVideoId) {
            currentVideoId = videoId;
            removeDownloadButton();
        }

        // 等待页面元素加载完成
        scheduleInjectDownloadButton(0);
    }

    // 检查是否在视频页面
    function isVideoPage() {
        return window.location.pathname === '/watch' && window.location.search.includes('v=');
    }

    // 获取视频ID
    function getVideoId() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('v');
    }

    // 获取视频标题
    function getVideoTitle() {
        const titleElement = document.querySelector('h1.ytd-video-primary-info-renderer, h1.ytd-watch-metadata');
        return titleElement ? titleElement.textContent.trim() : '未知标题';
    }

    // 获取视频URL
    function getVideoUrl() {
        return window.location.href;
    }

    function removeDownloadButton() {
        if (injectionRetryTimer) {
            clearTimeout(injectionRetryTimer);
            injectionRetryTimer = null;
        }

        document.querySelectorAll('.videohub-youtube-download-wrapper, .video-downloader-btn[data-videohub-platform="youtube"]').forEach(element => {
            element.remove();
        });

        downloadButton = null;
    }

    function scheduleInjectDownloadButton(attempt) {
        if (injectionRetryTimer) {
            return;
        }

        const delay = attempt === 0 ? 500 : Math.min(1000 * attempt, 3000);
        injectionRetryTimer = setTimeout(() => {
            injectionRetryTimer = null;
            const injected = injectDownloadButton();
            if (!injected && attempt < 10 && isVideoPage()) {
                scheduleInjectDownloadButton(attempt + 1);
            }
        }, delay);
    }

    // 注入下载按钮
    function injectDownloadButton() {
        if (!isVideoPage()) {
            return false;
        }

        const existingButton = document.querySelector('.video-downloader-btn[data-videohub-platform="youtube"]');
        if (existingButton) {
            downloadButton = existingButton;
            return true;
        }

        // 查找合适的位置注入按钮
        const targetSelectors = [
            'ytd-watch-metadata #title',
            'ytd-watch-metadata #top-row',
            'ytd-watch-metadata #owner',
            '#above-the-fold #title',
            '#above-the-fold',
            'ytd-watch-metadata #actions-inner',
            'ytd-watch-metadata #actions',
            '#above-the-fold #actions-inner',
            '#above-the-fold #actions',
            '#top-row #actions',
            'div#menu-container',
            'div#top-level-buttons-computed',
            'ytd-video-primary-info-renderer',
            'ytd-video-secondary-info-renderer'
        ];

        let targetElement = null;
        for (const selector of targetSelectors) {
            targetElement = document.querySelector(selector);
            if (targetElement) {
                break;
            }
        }

        if (!targetElement) {
            console.log('YouTube下载助手: 未找到合适的注入位置');
            return false;
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'videohub-youtube-download-wrapper';
        wrapper.style.cssText = [
            'display: flex',
            'align-items: center',
            'gap: 8px',
            'margin: 12px 0',
            'width: 100%'
        ].join(';');

        // 创建下载按钮
        downloadButton = document.createElement('button');
        downloadButton.className = 'video-downloader-btn';
        downloadButton.dataset.videohubPlatform = 'youtube';
        downloadButton.textContent = '下载视频';
        downloadButton.title = '点击将视频添加到闲时下载队列';
        downloadButton.style.minWidth = '160px';
        downloadButton.style.height = '36px';

        // 创建提示文本
        const tooltip = document.createElement('div');
        tooltip.className = 'video-downloader-tooltip';
        tooltip.textContent = '添加到闲时下载队列';
        downloadButton.appendChild(tooltip);

        // 添加点击事件
        downloadButton.addEventListener('click', handleDownloadClick);
        wrapper.appendChild(downloadButton);

        // 插入按钮
        if (targetElement.id === 'actions' || targetElement.id === 'actions-inner' || targetElement.id === 'top-level-buttons-computed' || targetElement.id === 'menu-container') {
            targetElement.appendChild(downloadButton);
        } else if (targetElement.parentNode) {
            targetElement.parentNode.insertBefore(wrapper, targetElement.nextSibling);
        } else {
            targetElement.appendChild(wrapper);
        }

        console.log('YouTube下载助手: 按钮已注入');
        return true;
    }

    // 处理下载按钮点击
    function handleDownloadClick(event) {
        event.preventDefault();
        event.stopPropagation();

        const button = event.currentTarget || event.target;
        if (!button || !button.classList) {
            console.warn('YouTube下载助手: 未能定位到按钮元素');
            return;
        }
        const videoUrl = getVideoUrl();
        const videoTitle = getVideoTitle();
        const videoId = getVideoId();

        if (!videoId) {
            alert('无法获取视频信息');
            return;
        }

        const resetButtonState = (text = '下载视频', stateClass = '') => {
            button.className = stateClass || 'video-downloader-btn';
            button.textContent = text;
            button.dataset.videohubPlatform = 'youtube';
        };

        // 设置按钮为加载状态
        resetButtonState('正在添加...', 'video-downloader-btn loading');

        // 超时回退，避免一直停留在加载状态
        const timeoutId = setTimeout(() => {
            console.warn('YouTube下载助手: 添加请求超时');
            resetButtonState('连接超时', 'video-downloader-btn error');
            setTimeout(() => resetButtonState(), 3000);
        }, 15000);

        // 发送消息到background script
        console.log('YouTube下载助手: 发送添加到队列请求', {
            url: videoUrl,
            title: videoTitle,
            videoId: videoId
        });
        
        chrome.runtime.sendMessage({
            action: 'addToDownloadQueue',
            platform: 'youtube',
            data: {
                url: videoUrl,
                title: videoTitle,
                videoId: videoId
            }
        }, (response) => {
            clearTimeout(timeoutId);
            console.log('YouTube下载助手: 收到响应', response);
            
            // 检查是否有运行时错误
            if (chrome.runtime.lastError) {
                console.error('YouTube下载助手: 运行时错误', chrome.runtime.lastError);
                resetButtonState('连接失败', 'video-downloader-btn error');
                
                setTimeout(() => {
                    resetButtonState();
                }, 3000);
                return;
            }
            
            // 检查响应有效性
            if (!response) {
                console.error('YouTube下载助手: 响应为空');
                resetButtonState('无响应', 'video-downloader-btn error');
                
                setTimeout(() => {
                    resetButtonState();
                }, 3000);
                return;
            }

            if (response.success) {
                // 显示成功状态
                console.log('YouTube下载助手: 添加成功');
                resetButtonState('已添加到队列', 'video-downloader-btn success');
                
                // 显示详细信息（如果有）
                if (response.message) {
                    console.log('YouTube下载助手: ' + response.message);
                }

                // 3秒后恢复原状态
                setTimeout(() => {
                    resetButtonState();
                }, 3000);
            } else {
                // 显示错误状态
                console.error('YouTube下载助手: 添加失败', response.error);
                resetButtonState('添加失败', 'video-downloader-btn error');
                
                // 显示具体错误信息
                const errorMsg = response.error || '未知错误';
                console.error('YouTube下载助手: 错误详情:', errorMsg);

                // 3秒后恢复原状态
                setTimeout(() => {
                    resetButtonState();
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
