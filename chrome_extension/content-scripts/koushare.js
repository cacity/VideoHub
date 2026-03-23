// Koushare页面内容脚本
(function() {
    'use strict';

    let downloadButton = null;
    let currentVideoUrl = null;

    function init() {
        console.log('Koushare下载助手已加载');

        const observer = new MutationObserver(() => {
            checkAndInjectButton();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        checkAndInjectButton();

        let lastUrl = location.href;
        new MutationObserver(() => {
            const currentUrl = location.href;
            if (currentUrl !== lastUrl) {
                lastUrl = currentUrl;
                setTimeout(checkAndInjectButton, 500);
            }
        }).observe(document, { subtree: true, childList: true });
    }

    function checkAndInjectButton() {
        if (!isSupportedVideoPage()) {
            currentVideoUrl = null;
            if (downloadButton) {
                downloadButton.remove();
                downloadButton = null;
            }
            return;
        }

        const videoUrl = getCanonicalVideoUrl();
        if (!videoUrl || videoUrl === currentVideoUrl) {
            return;
        }

        currentVideoUrl = videoUrl;

        if (downloadButton) {
            downloadButton.remove();
            downloadButton = null;
        }

        setTimeout(() => {
            injectDownloadButton();
        }, 1000);
    }

    function isSupportedVideoPage() {
        const url = new URL(window.location.href);
        const path = url.pathname;

        if (/^\/video\/(details|videodetail)\/[^/]+$/.test(path)) {
            return true;
        }

        if (/^\/live\/details\/[^/]+$/.test(path)) {
            return Boolean(url.searchParams.get('vid') || url.searchParams.get('videoId'));
        }

        return false;
    }

    function getCanonicalVideoUrl() {
        const url = new URL(window.location.href);
        const path = url.pathname;

        if (/^\/video\/(details|videodetail)\/[^/]+$/.test(path)) {
            url.hash = '';
            return url.toString();
        }

        if (/^\/live\/details\/[^/]+$/.test(path)) {
            const videoId = url.searchParams.get('vid') || url.searchParams.get('videoId');
            if (!videoId) {
                return null;
            }

            url.search = '';
            url.searchParams.set('vid', videoId);
            url.hash = '';
            return url.toString();
        }

        return null;
    }

    function getVideoTitle() {
        const titleSelectors = [
            'h1',
            '.video-title',
            '.detail-title',
            '.live-title',
            '.playback-title',
            '[class*="title"]'
        ];

        for (const selector of titleSelectors) {
            const titleElement = document.querySelector(selector);
            if (titleElement) {
                const text = titleElement.textContent?.trim();
                if (text) {
                    return text;
                }
            }
        }

        const pageTitle = document.title || '';
        const cleanedTitle = pageTitle
            .replace(/[-|_｜].*寇享.*$/, '')
            .replace(/[-|_｜].*Koushare.*$/i, '')
            .trim();

        return cleanedTitle || '寇享视频';
    }

    function injectDownloadButton() {
        const targetSelectors = [
            '.video-actions',
            '.detail-actions',
            '.playback-actions',
            '.video-info',
            '.detail-info',
            '.live-info',
            '.main-content',
            'main'
        ];

        let targetElement = null;
        for (const selector of targetSelectors) {
            targetElement = document.querySelector(selector);
            if (targetElement) {
                break;
            }
        }

        if (!targetElement) {
            console.log('Koushare下载助手: 未找到合适的注入位置');
            return;
        }

        downloadButton = document.createElement('button');
        downloadButton.className = 'video-downloader-btn';
        downloadButton.textContent = '添加到下载队列';
        downloadButton.title = '点击将寇享视频添加到闲时下载队列';

        const tooltip = document.createElement('div');
        tooltip.className = 'video-downloader-tooltip';
        tooltip.textContent = '添加到闲时下载队列';
        downloadButton.appendChild(tooltip);

        downloadButton.addEventListener('click', handleDownloadClick);
        targetElement.appendChild(downloadButton);

        console.log('Koushare下载助手: 按钮已注入');
    }

    function handleDownloadClick(event) {
        event.preventDefault();
        event.stopPropagation();

        const button = event.currentTarget;
        const videoUrl = getCanonicalVideoUrl();
        const videoTitle = getVideoTitle();

        if (!videoUrl) {
            alert('当前页面不是受支持的寇享视频页面');
            return;
        }

        button.className = 'video-downloader-btn loading';
        button.textContent = '正在添加...';

        chrome.runtime.sendMessage({
            action: 'addToDownloadQueue',
            platform: 'koushare',
            data: {
                url: videoUrl,
                title: videoTitle
            }
        }, (response) => {
            if (response && response.success) {
                button.className = 'video-downloader-btn success';
                button.textContent = '已添加到队列';

                setTimeout(() => {
                    button.className = 'video-downloader-btn';
                    button.textContent = '添加到下载队列';
                }, 3000);
            } else {
                button.className = 'video-downloader-btn error';
                button.textContent = '添加失败';
                alert('添加到下载队列失败: ' + (response?.error || '未知错误'));

                setTimeout(() => {
                    button.className = 'video-downloader-btn';
                    button.textContent = '添加到下载队列';
                }, 3000);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
