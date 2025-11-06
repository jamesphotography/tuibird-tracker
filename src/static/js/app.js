// ==================== 全局工具函数 ====================

/**
 * 显示加载动画
 * @param {string} mainText - 主要提示文本
 * @param {string} subText - 副提示文本
 */
function showLoading(mainText = '正在查询中...', subText = '请稍候，正在从eBird数据库获取数据') {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    const loadingSubtext = document.getElementById('loadingSubtext');

    if (overlay) {
        if (loadingText) loadingText.textContent = mainText;
        if (loadingSubtext) loadingSubtext.textContent = subText;
        overlay.classList.add('active');
        // 防止页面滚动
        document.body.style.overflow = 'hidden';
    }
}

/**
 * 隐藏加载动画
 */
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.remove('active');
        // 恢复页面滚动
        document.body.style.overflow = '';
    }
}

/**
 * 显示通知消息
 */
function showNotification(message, type = 'info') {
    // 创建通知容器
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;

    // 创建消息文本
    const messageSpan = document.createElement('span');
    messageSpan.textContent = message;
    messageSpan.style.cssText = 'flex: 1; word-wrap: break-word;';

    // 创建关闭按钮
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '×';
    closeBtn.style.cssText = `
        background: none;
        border: none;
        color: white;
        font-size: 1.5rem;
        cursor: pointer;
        padding: 0;
        margin-left: 1rem;
        line-height: 1;
        opacity: 0.8;
    `;
    closeBtn.onmouseover = () => closeBtn.style.opacity = '1';
    closeBtn.onmouseout = () => closeBtn.style.opacity = '0.8';
    closeBtn.onclick = () => removeNotification(notification);

    notification.appendChild(messageSpan);
    notification.appendChild(closeBtn);

    // 样式
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        z-index: 9999;
        animation: slideIn 0.3s ease;
        max-width: 500px;
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
    `;

    // 根据类型设置颜色
    const colors = {
        'success': '#27AE60',
        'error': '#E74C3C',
        'warning': '#F39C12',
        'info': '#4A90E2'
    };

    notification.style.background = colors[type] || colors.info;
    notification.style.color = 'white';

    document.body.appendChild(notification);

    // 错误和警告消息需要手动关闭，其他消息5秒后自动移除
    if (type === 'error' || type === 'warning') {
        // 不自动关闭，只能手动点击 × 关闭
        notification.setAttribute('data-persistent', 'true');
    } else {
        // 成功和信息消息5秒后自动移除
        setTimeout(() => {
            removeNotification(notification);
        }, 5000);
    }
}

/**
 * 移除通知
 */
function removeNotification(notification) {
    if (notification && notification.parentElement) {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            if (notification.parentElement) {
                document.body.removeChild(notification);
            }
        }, 300);
    }
}

/**
 * 获取本地存储的 API Key
 */
function getLocalApiKey() {
    return localStorage.getItem('ebird_api_key');
}

/**
 * 保存 API Key 到本地存储和 Cookie
 */
function saveLocalApiKey(apiKey) {
    // 保存到 localStorage
    localStorage.setItem('ebird_api_key', apiKey);

    // 同时保存到 Cookie（支持页面导航时传递 API Key）
    // 设置 Cookie 有效期为 1 年
    const expires = new Date();
    expires.setFullYear(expires.getFullYear() + 1);
    document.cookie = `ebird_api_key=${apiKey}; expires=${expires.toUTCString()}; path=/; SameSite=Lax`;
}

/**
 * 删除本地存储的 API Key 和 Cookie
 */
function removeLocalApiKey() {
    // 删除 localStorage
    localStorage.removeItem('ebird_api_key');

    // 删除 Cookie
    document.cookie = 'ebird_api_key=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
}

/**
 * API 请求封装
 * 自动从 localStorage 读取 API Key 并添加到请求头
 */
async function apiRequest(url, options = {}) {
    try {
        // 从本地存储获取 API Key
        const apiKey = getLocalApiKey();

        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(apiKey && { 'X-eBird-API-Key': apiKey }),  // 如果有 API Key，添加到请求头
                'X-CSRFToken': csrfToken,  // 添加 CSRF Token
                ...options.headers
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '请求失败');
        }

        return data;
    } catch (error) {
        console.error('API Error:', error);
        showNotification(error.message, 'error');
        throw error;
    }
}

/**
 * 格式化日期时间
 */
function formatDateTime(dateString) {
    if (!dateString) return '未知';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN');
}

/**
 * 防抖函数
 */
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

// ==================== 页面加载完成后执行 ====================
document.addEventListener('DOMContentLoaded', function() {
    // 生产环境已移除调试日志

    // 同步 localStorage 中的 API Key 到 Cookie
    const apiKey = getLocalApiKey();
    if (apiKey) {
        // 检查 Cookie 中是否已有 API Key
        const cookieApiKey = document.cookie
            .split('; ')
            .find(row => row.startsWith('ebird_api_key='))
            ?.split('=')[1];

        // 如果 Cookie 中没有或者与 localStorage 不一致，则更新
        if (!cookieApiKey || cookieApiKey !== apiKey) {
            saveLocalApiKey(apiKey);
        }
    }

    // 添加动画样式
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
});
