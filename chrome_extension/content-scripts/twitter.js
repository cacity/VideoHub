// Twitter/X页面内容脚本
(function() {
    'use strict';

    let injectedButtons = new Set(); // 记录已注入按钮的推文ID
    let observer = null;

    // 初始化函数
    function init() {
        console.log('Twitter下载助手已加载');

        // 启动观察器
        startObserver();

        // 立即扫描现有内容
        scanAndInjectButtons();

        // 监听页面导航变化
        let lastUrl = location.href;
        const navigationObserver = new MutationObserver(() => {
            const currentUrl = location.href;
            if (currentUrl !== lastUrl) {
                lastUrl = currentUrl;
                setTimeout(() => {
                    scanAndInjectButtons();
                }, 1000);
            }
        });

        navigationObserver.observe(document, {subtree: true, childList: true});
    }

    // 启动DOM观察器
    function startObserver() {
        if (observer) {
            observer.disconnect();
        }

        observer = new MutationObserver((mutations) => {
            let shouldScan = false;
            mutations.forEach(mutation => {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    shouldScan = true;
                }
            });

            if (shouldScan) {
                debounce(scanAndInjectButtons, 500)();
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // 防抖函数
    function debounce(func, wait) {
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

    // 扫描并注入下载按钮
    function scanAndInjectButtons() {
        // 查找包含视频的推文
        const videoTweets = document.querySelectorAll('[data-testid="tweet"]:has(video), [data-testid="tweet"]:has([data-testid="videoPlayer"])');

        videoTweets.forEach(tweet => {
            const tweetId = getTweetId(tweet);
            if (!tweetId || injectedButtons.has(tweetId)) {
                return;
            }

            injectDownloadButton(tweet, tweetId);
        });
    }

    // 获取推文ID
    function getTweetId(tweetElement) {
        // 尝试从链接中提取推文ID
        const tweetLink = tweetElement.querySelector('a[href*="/status/"]');
        if (tweetLink) {
            const match = tweetLink.href.match(/\/status\/(\d+)/);
            return match ? match[1] : null;
        }

        // 如果找不到链接，使用时间戳作为唯一标识
        const timeElement = tweetElement.querySelector('time');
        if (timeElement) {
            return timeElement.getAttribute('datetime') || Date.now().toString();
        }

        return Date.now().toString();
    }

    // 获取推文内容和URL
    function getTweetInfo(tweetElement) {
        const tweetLink = tweetElement.querySelector('a[href*="/status/"]');
        const tweetUrl = tweetLink ? tweetLink.href : window.location.href;

        // 获取推文文本
        const tweetTextElement = tweetElement.querySelector('[data-testid="tweetText"], [lang]');
        const tweetText = tweetTextElement ? tweetTextElement.textContent.trim() : '推文内容';

        // 获取作者信息
        const authorElement = tweetElement.querySelector('[data-testid="User-Name"] span, [data-testid="User-Names"] span');
        const author = authorElement ? authorElement.textContent.trim() : '未知用户';

        return {
            url: tweetUrl,
            text: tweetText,
            author: author,
            title: `${author}: ${tweetText.substring(0, 50)}${tweetText.length > 50 ? '...' : ''}`
        };
    }

    // 注入下载按钮
    function injectDownloadButton(tweetElement, tweetId) {
        // 查找操作按钮栏
        const actionBar = tweetElement.querySelector('[role="group"], [data-testid="reply"], [data-testid="retweet"]');
        if (!actionBar) {
            return;
        }

        // 创建下载按钮
        const downloadButton = document.createElement('button');
        downloadButton.className = 'video-downloader-btn';
        downloadButton.textContent = '下载视频';
        downloadButton.title = '添加到闲时下载队列';
        downloadButton.style.marginLeft = '12px';

        // 创建提示文本
        const tooltip = document.createElement('div');
        tooltip.className = 'video-downloader-tooltip';
        tooltip.textContent = '添加到下载队列';
        downloadButton.appendChild(tooltip);

        // 添加点击事件
        downloadButton.addEventListener('click', (event) => {
            handleDownloadClick(event, tweetElement, tweetId);
        });

        // 插入按钮到操作栏
        const parentContainer = actionBar.parentElement || actionBar;
        parentContainer.appendChild(downloadButton);

        // 记录已注入的按钮
        injectedButtons.add(tweetId);

        console.log(`Twitter下载助手: 已为推文 ${tweetId} 注入下载按钮`);
    }

    // 处理下载按钮点击
    function handleDownloadClick(event, tweetElement, tweetId) {
        event.preventDefault();
        event.stopPropagation();

        const button = event.target.closest('.video-downloader-btn') || event.target;
        if (!button || !button.classList) {
            console.warn('Twitter下载助手: 未能定位到按钮元素');
            return;
        }

        const tweetInfo = getTweetInfo(tweetElement);

        if (!tweetInfo.url) {
            alert('无法获取推文信息');
            return;
        }

        const resetButtonState = (text = '下载视频', stateClass = '') => {
            button.className = stateClass || 'video-downloader-btn';
            button.textContent = text;
        };

        // 设置按钮为加载状态
        resetButtonState('正在添加...', 'video-downloader-btn loading');

        // 超时回退，避免一直停留在加载状态
        const timeoutId = setTimeout(() => {
            console.warn('Twitter下载助手: 添加请求超时');
            resetButtonState('连接超时', 'video-downloader-btn error');
            setTimeout(() => resetButtonState(), 3000);
        }, 15000);

        // 发送消息到background script
        console.log('Twitter下载助手: 发送添加到队列请求', {
            url: tweetInfo.url,
            title: tweetInfo.title,
            text: tweetInfo.text,
            author: tweetInfo.author,
            tweetId: tweetId
        });

        chrome.runtime.sendMessage({
            action: 'addToDownloadQueue',
            platform: 'twitter',
            data: {
                url: tweetInfo.url,
                title: tweetInfo.title,
                text: tweetInfo.text,
                author: tweetInfo.author,
                tweetId: tweetId
            }
        }, (response) => {
            clearTimeout(timeoutId);
            console.log('Twitter下载助手: 收到响应', response);

            // 检查是否有运行时错误
            if (chrome.runtime.lastError) {
                console.error('Twitter下载助手: 运行时错误', chrome.runtime.lastError);
                resetButtonState('连接失败', 'video-downloader-btn error');

                setTimeout(() => {
                    resetButtonState();
                }, 3000);
                return;
            }

            // 检查响应有效性
            if (!response) {
                console.error('Twitter下载助手: 响应为空');
                resetButtonState('无响应', 'video-downloader-btn error');

                setTimeout(() => {
                    resetButtonState();
                }, 3000);
                return;
            }

            if (response.success) {
                // 显示成功状态
                console.log('Twitter下载助手: 添加成功');
                resetButtonState('已添加', 'video-downloader-btn success');

                // 显示详细信息（如果有）
                if (response.message) {
                    console.log('Twitter下载助手: ' + response.message);
                }

                // 3秒后恢复原状态
                setTimeout(() => {
                    resetButtonState();
                }, 3000);
            } else {
                // 显示错误状态
                console.error('Twitter下载助手: 添加失败', response.error);
                resetButtonState('添加失败', 'video-downloader-btn error');

                // 显示具体错误信息
                const errorMsg = response.error || '未知错误';
                console.error('Twitter下载助手: 错误详情:', errorMsg);

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

    // 页面离开时清理
    window.addEventListener('beforeunload', () => {
        if (observer) {
            observer.disconnect();
        }
    });

})();
