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
 * Store the access token as a session-scoped fallback for browsers
 * that block cross-site cookies (e.g. mobile Safari ITP).
 * The httpOnly cookie remains the primary auth mechanism — this is
 * only used when the cookie is not stored by the browser.
 */
function setAuthToken(token) {
    if (token) {
        try { sessionStorage.setItem('_auth_token', token); } catch(e) {}
    }
}

function getAuthToken() {
    try { return sessionStorage.getItem('_auth_token'); } catch(e) { return null; }
}

function clearAuthToken() {
    try { sessionStorage.removeItem('_auth_token'); } catch(e) {}
}

/**
 * Unified fetch wrapper that automatically:
 * 1. Prepends the backend API base URL
 * 2. Adds credentials: 'include' for cross-origin cookies
 * 3. Adds X-Requested-With for CSRF protection
 * 4. Falls back to Bearer token auth when cookies are blocked
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

    // Always include credentials so httpOnly cookies are sent when available
    if (!options.credentials) {
        options.credentials = 'include';
    }

    // Fallback: attach Bearer token for browsers that block cross-site cookies
    var token = getAuthToken();
    if (token) {
        if (typeof Headers !== 'undefined' && options.headers instanceof Headers) {
            if (!options.headers.has('Authorization')) {
                options.headers.set('Authorization', 'Bearer ' + token);
            }
        } else {
            if (!options.headers['Authorization']) {
                options.headers['Authorization'] = 'Bearer ' + token;
            }
        }
    }

    return fetch(getApiUrl(path), options).then(function (res) {
        if (res.status === 400 || res.status === 401 || res.status === 403) {
            var clone = res.clone();
            clone.json().then(function (data) {
                if (data && data.detail && typeof data.detail === 'string') {
                    var lower = data.detail.toLowerCase();
                    if (lower.includes('telegram session expired') || lower.includes('revoked') || lower.includes('unregistered')) {
                        window.location.href = '/setup_telegram.html';
                    }
                }
            }).catch(function () { });
        }
        return res;
    });
}


