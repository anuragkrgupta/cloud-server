// ============================================================
// config.js — Global Backend API Configuration
// ============================================================

if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    // Local development: use relative paths so requests go to the FastAPI server on localhost
    window.API_BASE_URL = '';
} else {
    // Production (Vercel, Netlify, etc.): point to the deployed Render backend
    window.API_BASE_URL = 'https://cloud-server-eazn.onrender.com';
}
