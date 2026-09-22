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


