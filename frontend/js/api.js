// ============================================================
// api.js — Unified API Client & Authentication Helpers
// ============================================================

/**
 * Returns the fully qualified URL for any API endpoint path.
 * If window.API_BASE_URL is set (e.g. on Vercel), it prepends the backend URL.
 * Otherwise, it uses the relative path (for local dev or same-origin backend hosting).
 */
function getApiUrl(path) {
    var base = (window.API_BASE_URL || localStorage.getItem('api_base_url') || '').trim();
    base = base.replace(/\/+$/, '');
    if (!path.startsWith('/')) {
        path = '/' + path;
    }
    return base ? base + path : path;
}

/**
 * Token management helpers
 */
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function setAuthToken(token) {
    if (token) {
        localStorage.setItem('access_token', token);
    } else {
        localStorage.removeItem('access_token');
    }
}

function clearAuthToken() {
    localStorage.removeItem('access_token');
}

/**
 * Unified fetch wrapper that automatically:
 * 1. Prepends the backend API base URL
 * 2. Adds Bearer token in Authorization header (essential for cross-origin Vercel -> Render)
 * 3. Adds credentials: 'include' for cross-origin cookies
 */
function apiFetch(path, options) {
    options = options || {};
    options.headers = options.headers || {};

    var token = getAuthToken();
    if (token) {
        if (typeof Headers !== 'undefined' && options.headers instanceof Headers) {
            if (!options.headers.has('Authorization')) {
                options.headers.set('Authorization', 'Bearer ' + token);
            }
        } else {
            if (!options.headers['Authorization'] && !options.headers['authorization']) {
                options.headers['Authorization'] = 'Bearer ' + token;
            }
        }
    }

    if (!options.credentials) {
        options.credentials = 'include';
    }

    return fetch(getApiUrl(path), options);
}

// Global server configuration banner for Vercel users (if API URL is missing)
(function initBackendConfigPrompt() {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;

    var isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    var hasApiUrl = !!(window.API_BASE_URL || localStorage.getItem('api_base_url'));

    // If running on a remote host (e.g. *.vercel.app) and no backend URL is set, show a prompt bar
    if (!isLocalhost && !hasApiUrl) {
        document.addEventListener('DOMContentLoaded', function() {
            if (document.getElementById('api-config-banner')) return;
            var banner = document.createElement('div');
            banner.id = 'api-config-banner';
            banner.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:9999;background:#1e293b;border:1px solid #6366f1;color:#f8fafc;padding:16px;border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,0.5);max-width:360px;font-family:sans-serif;font-size:13px;';
            banner.innerHTML = 
                '<div style="font-weight:600;margin-bottom:6px;color:#a5b4fc;">Backend API URL Required</div>' +
                '<p style="margin:0 0 10px;color:#94a3b8;font-size:12px;">Enter your deployed Render backend URL (e.g. <code>https://your-service.onrender.com</code>):</p>' +
                '<input id="api-url-input" type="url" placeholder="https://your-service.onrender.com" style="width:100%;box-sizing:border-box;padding:8px 10px;border-radius:6px;background:#0f172a;border:1px solid #475569;color:#fff;font-size:12px;margin-bottom:10px;outline:none;" />' +
                '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
                    '<button id="api-url-save-btn" style="background:#6366f1;color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px;">Save & Connect</button>' +
                '</div>';
            document.body.appendChild(banner);

            var saveBtn = document.getElementById('api-url-save-btn');
            var input = document.getElementById('api-url-input');
            saveBtn.addEventListener('click', function() {
                var val = (input.value || '').trim();
                if (val) {
                    val = val.replace(/\/+$/, '');
                    localStorage.setItem('api_base_url', val);
                    window.API_BASE_URL = val;
                    banner.remove();
                    window.location.reload();
                }
            });
        });
    }
})();
