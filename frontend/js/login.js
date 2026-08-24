const params = new URLSearchParams(window.location.search);
const form = document.getElementById('login-form');
const errorBox = document.getElementById('error-box');
const submitBtn = document.getElementById('submit-btn');

// Check if already logged in
fetch('/api/me').then(async res => {
  if (res.ok) {
    const user = await res.json();
    
    const redirectUrl = localStorage.getItem('redirect_after_login');
    if (redirectUrl) {
        localStorage.removeItem('redirect_after_login');
        window.location.href = redirectUrl;
        return;
    }
    
    if (user.is_telegram_connected) {
        window.location.href = '/dashboard.html';
    } else {
        window.location.href = '/setup_telegram.html';
    }
  }
});

if (params.get('registered') === '1') {
  errorBox.textContent = 'Account created. You can log in now.';
  errorBox.classList.add('success');
  errorBox.classList.add('visible');
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove('success');
  errorBox.classList.add('visible');
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  submitBtn.textContent = 'Logging in…';

  const payload = {
    email: document.getElementById('email').value.trim(),
    password: document.getElementById('password').value,
  };

  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const meRes = await fetch('/api/me');
      if (meRes.ok) {
         const user = await meRes.json();
         
         const redirectUrl = localStorage.getItem('redirect_after_login');
         if (redirectUrl) {
             localStorage.removeItem('redirect_after_login');
             window.location.href = redirectUrl;
             return;
         }
         
         if (user.is_telegram_connected) {
             window.location.href = '/dashboard.html';
         } else {
             window.location.href = '/setup_telegram.html';
         }
      }
      return;
    }

    const data = await res.json().catch(() => ({}));
    showError(data.detail || 'Login failed. Please try again.');
  } catch (err) {
    showError('Could not reach the server. Please try again.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Log in';
  }
});
