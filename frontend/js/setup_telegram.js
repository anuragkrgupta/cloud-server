// Check auth state
apiFetch('/api/me').then(async res => {
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

const mismatchWrapper = document.getElementById('mismatch-wrapper');
const btnOverrideMismatch = document.getElementById('btn-override-mismatch');
const btnCancelMismatch = document.getElementById('btn-cancel-mismatch');

// Phone login elements
const btnTabQr = document.getElementById('btn-tab-qr');
const btnTabPhone = document.getElementById('btn-tab-phone');
const phoneWrapper = document.getElementById('phone-wrapper');
const phoneStep1 = document.getElementById('phone-step-1');
const phoneStep2 = document.getElementById('phone-step-2');
const phoneNumberInput = document.getElementById('phone-number');
const phoneCodeInput = document.getElementById('phone-code');
const btnSendCode = document.getElementById('btn-send-code');
const btnVerifyCode = document.getElementById('btn-verify-code');

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
        const res = await apiFetch('/api/telegram/qr-start', {
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
        const res = await apiFetch(`/api/telegram/qr-status?token=${token}`);
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
        } else if (data.status === 'account_mismatch') {
            clearInterval(pollInterval);
            qrWrapper.classList.add('hidden');
            qrWrapper.classList.remove('flex');
            faWrapper.classList.add('hidden');
            faWrapper.classList.remove('flex');
            mismatchWrapper.classList.remove('hidden');
            mismatchWrapper.classList.add('flex');
        } else if (data.status === 'failed' || data.status === 'not_found') {
            clearInterval(pollInterval);
            showError('QR Login failed or expired. Please refresh the page.');
        }
        // If pending, do nothing (keep polling)
    } catch (err) {
        console.error("Poll error:", err);
    }
}

// ---- Tab Switching ----
btnTabQr.addEventListener('click', () => {
    btnTabQr.classList.add('border-indigo-500', 'text-indigo-400');
    btnTabQr.classList.remove('border-transparent', 'text-slate-400');
    btnTabPhone.classList.remove('border-indigo-500', 'text-indigo-400');
    btnTabPhone.classList.add('border-transparent', 'text-slate-400');
    
    phoneWrapper.classList.add('hidden');
    phoneWrapper.classList.remove('flex');
    qrWrapper.classList.remove('hidden');
    qrWrapper.classList.add('flex');
});

btnTabPhone.addEventListener('click', () => {
    btnTabPhone.classList.add('border-indigo-500', 'text-indigo-400');
    btnTabPhone.classList.remove('border-transparent', 'text-slate-400');
    btnTabQr.classList.remove('border-indigo-500', 'text-indigo-400');
    btnTabQr.classList.add('border-transparent', 'text-slate-400');
    
    qrWrapper.classList.add('hidden');
    qrWrapper.classList.remove('flex');
    phoneWrapper.classList.remove('hidden');
    phoneWrapper.classList.add('flex');
});

// ---- Phone Login Logic ----
btnSendCode.addEventListener('click', async () => {
    const phone = phoneNumberInput.value.trim();
    if (!phone) {
        showError("Please enter your phone number.");
        return;
    }
    
    btnSendCode.disabled = true;
    btnSendCode.textContent = "Sending...";
    
    try {
        const res = await apiFetch('/api/telegram/phone-start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_number: phone })
        });
        const data = await res.json();
        
        if (!res.ok) throw new Error(data.detail || 'Failed to send code');
        
        currentToken = data.token;
        phoneStep1.classList.add('hidden');
        phoneStep2.classList.remove('hidden');
        
        // Stop QR polling if it was running
        if (pollInterval) clearInterval(pollInterval);
        
    } catch (err) {
        showError(err.message);
        btnSendCode.disabled = false;
        btnSendCode.textContent = "Send Code";
    }
});

btnVerifyCode.addEventListener('click', async () => {
    const code = phoneCodeInput.value.trim();
    if (!code) {
        showError("Please enter the code.");
        return;
    }
    
    btnVerifyCode.disabled = true;
    btnVerifyCode.textContent = "Verifying...";
    
    try {
        const res = await apiFetch('/api/telegram/phone-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: currentToken, phone_code: code })
        });
        const data = await res.json();
        
        if (!res.ok && data.status !== 'account_mismatch') throw new Error(data.detail || data.message || 'Failed to verify code');
        
        if (data.status === 'success') {
            showSuccess('Telegram connected! Redirecting to dashboard...');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 1500);
        } else if (data.status === '2fa_required') {
            phoneWrapper.classList.add('hidden');
            phoneWrapper.classList.remove('flex');
            faWrapper.classList.remove('hidden');
            faWrapper.classList.add('flex');
        } else if (data.status === 'account_mismatch') {
            phoneWrapper.classList.add('hidden');
            phoneWrapper.classList.remove('flex');
            mismatchWrapper.classList.remove('hidden');
            mismatchWrapper.classList.add('flex');
        } else {
            throw new Error(data.message || 'Verification failed');
        }
    } catch (err) {
        showError(err.message);
        btnVerifyCode.disabled = false;
        btnVerifyCode.textContent = "Verify Code";
    }
});

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
        const res = await apiFetch('/api/telegram/2fa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: currentToken, password: password })
        });
        
        const data = await res.json();
        
        if (!res.ok && data.status !== 'account_mismatch') {
            throw new Error(data.detail || data.message || 'Failed to verify password');
        }
        
        if (data.status === 'success') {
            showSuccess('Telegram connected! Redirecting to dashboard...');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 1500);
        } else if (data.status === 'account_mismatch') {
            loadingMsg.classList.add('hidden');
            mismatchWrapper.classList.remove('hidden');
            mismatchWrapper.classList.add('flex');
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

btnOverrideMismatch.addEventListener('click', async () => {
    mismatchWrapper.classList.add('hidden');
    mismatchWrapper.classList.remove('flex');
    loadingMsg.textContent = "Creating new storage channel...";
    loadingMsg.classList.remove('hidden');
    
    try {
        const res = await apiFetch('/api/telegram/override-mismatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: currentToken })
        });
        
        const data = await res.json();
        
        if (data.status === 'success') {
            showSuccess('Mismatched account accepted! Redirecting...');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 1500);
        } else {
            throw new Error(data.message || 'Failed to override mismatch');
        }
    } catch (err) {
        showError(err.message);
    }
});

btnCancelMismatch.addEventListener('click', () => {
    window.location.reload();
});

btnLogout.addEventListener('click', async () => {
    if (pollInterval) clearInterval(pollInterval);
    await apiFetch('/api/logout', { method: 'POST' });
    clearAuthToken();
    window.location.href = '/login.html';
});
