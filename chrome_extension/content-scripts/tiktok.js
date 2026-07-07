// TikTok页面内容脚本
(function() {
    'use strict';

    const injectedKeys = new Set();
    let observer = null;
    let scanTimer = null;

    function init() {
        console.log('TikTok下载助手已加载');
        startObserver();
        scanAndInjectButtons();

        let lastUrl = location.href;
        new MutationObserver(() => {
            if (location.href !== lastUrl) {
                lastUrl = location.href;
                setTimeout(scanAndInjectButtons, 800);
            }
        }).observe(document, { subtree: true, childList: true });
    }

    function startObserver() {
        if (observer) {
            observer.disconnect();
        }

        observer = new MutationObserver(() => {
            if (scanTimer) {
                return;
            }
            scanTimer = setTimeout(() => {
                scanTimer = null;
                scanAndInjectButtons();
            }, 600);
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    function scanAndInjectButtons() {
        const videoContainers = findVideoContainers();
        videoContainers.forEach(container => {
            const info = getVideoInfo(container);
            if (!info.url || injectedKeys.has(info.url)) {
                return;
            }
            injectDownloadButton(container, info);
        });

        if (isStandaloneVideoPage()) {
            const pageInfo = getPageVideoInfo();
            if (pageInfo.url && !injectedKeys.has(pageInfo.url)) {
                injectFixedDownloadButton(pageInfo);
            }
        }
    }

    function findVideoContainers() {
        const selectors = [
            'article:has(video)',
            '[data-e2e="recommend-list-item-container"]:has(video)',
            '[data-e2e="user-post-item"]:has(video)',
            '[class*="DivItemContainer"]:has(video)',
            '[class*="DivVideoWrapper"]:has(video)',
            'div:has(> video)'
        ];

        const containers = [];
        selectors.forEach(selector => {
            try {
                document.querySelectorAll(selector).forEach(element => containers.push(element));
            } catch (error) {
                // :has() is supported in current Chromium; keep a fallback below.
            }
        });

        if (containers.length === 0) {
            document.querySelectorAll('video').forEach(video => {
                const container = video.closest('article, [data-e2e], [class*="DivItemContainer"], [class*="DivVideoWrapper"], div');
                if (container) {
                    containers.push(container);
                }
            });
        }

        return Array.from(new Set(containers));
    }

    function isStandaloneVideoPage() {
        return /\/@[^/]+\/video\/\d+/.test(location.pathname);
    }

    function getPageVideoInfo() {
        const title = getBestTitle(document.body);
        return {
            url: location.href,
            title: title || document.title || 'TikTok视频',
            author: getAuthorFromUrl(location.href)
        };
    }

    function getVideoInfo(container) {
        const videoLink = container.querySelector('a[href*="/video/"]') || document.querySelector('a[href*="/video/"]');
        const url = videoLink ? videoLink.href : (isStandaloneVideoPage() ? location.href : '');
        return {
            url,
            title: getBestTitle(container) || document.title || 'TikTok视频',
            author: getAuthorFromUrl(url)
        };
    }

    function getBestTitle(container) {
        const textSelectors = [
            '[data-e2e="video-desc"]',
            '[data-e2e="browse-video-desc"]',
            '[class*="DivDescriptionContent"]',
            'h1',
            'span[dir="auto"]'
        ];

        for (const selector of textSelectors) {
            const element = container.querySelector(selector);
            const text = element ? element.textContent.trim() : '';
            if (text) {
                return text.length > 80 ? `${text.substring(0, 80)}...` : text;
            }
        }

        const ariaLabel = container.getAttribute('aria-label');
        if (ariaLabel) {
            return ariaLabel.length > 80 ? `${ariaLabel.substring(0, 80)}...` : ariaLabel;
        }

        return '';
    }

    function getAuthorFromUrl(url) {
        const match = (url || '').match(/tiktok\.com\/@([^/]+)/);
        return match ? `@${decodeURIComponent(match[1])}` : '';
    }

    function injectDownloadButton(container, info) {
        const target = findInjectionTarget(container);
        if (!target) {
            return;
        }

        const button = createDownloadButton(info);
        button.style.margin = '8px 0';
        target.appendChild(button);
        injectedKeys.add(info.url);
        console.log('TikTok下载助手: 按钮已注入', info.url);
    }

    function injectFixedDownloadButton(info) {
        const button = createDownloadButton(info);
        button.style.position = 'fixed';
        button.style.right = '24px';
        button.style.bottom = '88px';
        button.style.minWidth = '160px';
        button.style.height = '42px';
        document.body.appendChild(button);
        injectedKeys.add(info.url);
        console.log('TikTok下载助手: 固定按钮已注入', info.url);
    }

    function findInjectionTarget(container) {
        const targetSelectors = [
            '[data-e2e="browse-share-group"]',
            '[data-e2e="video-actions"]',
            '[class*="DivActionItemContainer"]',
            '[class*="DivActionContainer"]',
            '[class*="DivVideoInfoContainer"]',
            '[class*="DivContentContainer"]'
        ];

        for (const selector of targetSelectors) {
            const target = container.querySelector(selector);
            if (target) {
                return target;
            }
        }

        return container;
    }

    function createDownloadButton(info) {
        const button = document.createElement('button');
        button.className = 'video-downloader-btn';
        button.dataset.videohubPlatform = 'tiktok';
        button.textContent = '下载视频';
        button.title = '点击将TikTok视频添加到闲时下载队列';

        const tooltip = document.createElement('div');
        tooltip.className = 'video-downloader-tooltip';
        tooltip.textContent = '添加到闲时下载队列';
        button.appendChild(tooltip);

        button.addEventListener('click', event => {
            handleDownloadClick(event, button, info);
        });

        return button;
    }

    function handleDownloadClick(event, button, info) {
        event.preventDefault();
        event.stopPropagation();

        if (!info.url) {
            alert('无法获取TikTok视频链接');
            return;
        }

        const resetButtonState = (text = '下载视频', stateClass = '') => {
            button.className = stateClass || 'video-downloader-btn';
            button.dataset.videohubPlatform = 'tiktok';
            button.textContent = text;
        };

        resetButtonState('正在添加...', 'video-downloader-btn loading');

        const timeoutId = setTimeout(() => {
            console.warn('TikTok下载助手: 添加请求超时');
            resetButtonState('连接超时', 'video-downloader-btn error');
            setTimeout(() => resetButtonState(), 3000);
        }, 15000);

        chrome.runtime.sendMessage({
            action: 'addToDownloadQueue',
            platform: 'tiktok',
            data: {
                url: info.url,
                title: info.title,
                author: info.author
            }
        }, response => {
            clearTimeout(timeoutId);

            if (chrome.runtime.lastError) {
                console.error('TikTok下载助手: 运行时错误', chrome.runtime.lastError);
                resetButtonState('连接失败', 'video-downloader-btn error');
                setTimeout(() => resetButtonState(), 3000);
                return;
            }

            if (!response) {
                console.error('TikTok下载助手: 响应为空');
                resetButtonState('无响应', 'video-downloader-btn error');
                setTimeout(() => resetButtonState(), 3000);
                return;
            }

            if (response.success) {
                resetButtonState('已添加', 'video-downloader-btn success');
                setTimeout(() => resetButtonState(), 3000);
            } else {
                console.error('TikTok下载助手: 添加失败', response.error);
                resetButtonState('添加失败', 'video-downloader-btn error');
                setTimeout(() => resetButtonState(), 3000);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
