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


