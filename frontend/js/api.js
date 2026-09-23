// ============================================================
// api.js — Unified API Client & Authentication Helpers
// ============================================================

function getApiUrl(path) {
    // Auto-detect environment:
    var hostname = window.location.hostname;
    var isLocal = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '';
    var base = isLocal ? 'http://127.0.0.1:8000' : 'https://cloud-server-eazn.onrender.com';
    
    base = base.replace(/\/+$/, '');
    if (!path.startsWith('/')) {
        path = '/' + path;
    }
    return base ? base + path : path;
}

/**
 * Unified fetch wrapper that automatically:
 * 1. Prepends the backend API base URL
 * 2. Adds credentials: 'include' for cross-origin cookies
 * 3. Adds X-Requested-With for CSRF protection
 */
function apiFetch(path, options) {
    options = options || {};
    options.headers = options.headers || {};

    // Add CSRF mitigation header (requires CORS preflight for cross-origin requests)
    if (typeof Headers !== 'undefined' && options.headers instanceof Headers) {
        options.headers.set('X-Requested-With', 'XMLHttpRequest');
    } else {
        options.headers['X-Requested-With'] = 'XMLHttpRequest';
    }

    if (!options.credentials) {
        options.credentials = 'include';
    }

    return fetch(getApiUrl(path), options).then(function(res) {
        if (res.status === 400 || res.status === 401 || res.status === 403) {
            var clone = res.clone();
            clone.json().then(function(data) {
                if (data && data.detail && typeof data.detail === 'string') {
                    var lower = data.detail.toLowerCase();
                    if (lower.includes('telegram session expired') || lower.includes('revoked') || lower.includes('unregistered')) {
                        window.location.href = '/setup_telegram.html';
                    }
                }
            }).catch(function(){});
        }
        return res;
    });
}


