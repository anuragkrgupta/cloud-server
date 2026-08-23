// Check auth state
fetch('/api/me').then(async res => {
    if (!res.ok) {
        window.location.href = '/login.html';
    } else {
        const user = await res.json();
        if (user.is_telegram_connected) {
            window.location.href = '/dashboard.html';
        } else {
            startQRLogin();
        }
    }
});

const errorMsg = document.getElementById('error-msg');
const successMsg = document.getElementById('success-msg');
const loadingMsg = document.getElementById('loading-msg');
const qrWrapper = document.getElementById('qr-wrapper');
const qrContainer = document.getElementById('qr-container');
const btnLogout = document.getElementById('btn-logout');
const faWrapper = document.getElementById('2fa-wrapper');
const btnSubmit2fa = document.getElementById('btn-submit-2fa');
const faPassword = document.getElementById('2fa-password');

let pollInterval = null;
let currentToken = null;

function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove('hidden');
    successMsg.classList.add('hidden');
    loadingMsg.classList.add('hidden');
    qrWrapper.classList.add('hidden');
}

function showSuccess(msg) {
    successMsg.textContent = msg;
    successMsg.classList.remove('hidden');
    errorMsg.classList.add('hidden');
    loadingMsg.classList.add('hidden');
    qrWrapper.classList.add('hidden');
}

async function startQRLogin() {
    try {
        const res = await fetch('/api/telegram/qr-start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || 'Failed to start QR login');
        }

        // Render QR code
        loadingMsg.classList.add('hidden');
        qrWrapper.classList.remove('hidden');
        qrWrapper.classList.add('flex');
        
        qrContainer.innerHTML = "";
        new QRCode(qrContainer, {
            text: data.url,
            width: 200,
            height: 200,
            colorDark : "#000000",
            colorLight : "#ffffff",
            correctLevel : QRCode.CorrectLevel.L
        });

        // Start polling status
        currentToken = data.token;
        pollInterval = setInterval(() => checkStatus(data.token), 2000);
        
    } catch (err) {
        showError(err.message);
    }
}

async function checkStatus(token) {
    try {
        const res = await fetch(`/api/telegram/qr-status?token=${token}`);
        const data = await res.json();

        if (data.status === 'success') {
            clearInterval(pollInterval);
            showSuccess('Telegram connected! Redirecting to dashboard...');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 1500);
        } else if (data.status === '2fa_required') {
            clearInterval(pollInterval);
            qrWrapper.classList.add('hidden');
            qrWrapper.classList.remove('flex');
            faWrapper.classList.remove('hidden');
            faWrapper.classList.add('flex');
        } else if (data.status === 'failed' || data.status === 'not_found') {
            clearInterval(pollInterval);
            showError('QR Login failed or expired. Please refresh the page.');
        }
        // If pending, do nothing (keep polling)
    } catch (err) {
        console.error("Poll error:", err);
    }
}

btnSubmit2fa.addEventListener('click', async () => {
    const password = faPassword.value;
    if (!password) {
        showError("Please enter your password.");
        return;
    }
    
    faWrapper.classList.add('hidden');
    faWrapper.classList.remove('flex');
    loadingMsg.textContent = "Verifying password...";
    loadingMsg.classList.remove('hidden');
    
    try {
        const res = await fetch('/api/telegram/2fa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: currentToken, password: password })
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || data.message || 'Failed to verify password');
        }
        
        if (data.status === 'success') {
            showSuccess('Telegram connected! Redirecting to dashboard...');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 1500);
        } else {
            throw new Error(data.message || 'Verification failed');
        }
    } catch (err) {
        showError(err.message);
        // Show input again if failed
        setTimeout(() => {
            errorMsg.classList.add('hidden');
            faWrapper.classList.remove('hidden');
            faWrapper.classList.add('flex');
        }, 3000);
    }
});

btnLogout.addEventListener('click', async () => {
    if (pollInterval) clearInterval(pollInterval);
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/login.html';
});
