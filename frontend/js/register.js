const form = document.getElementById('register-form');
const errorBox = document.getElementById('error-box');
const submitBtn = document.getElementById('submit-btn');

// Check if already logged in
apiFetch('/api/me').then(async res => {
  if (res.ok) {
    const user = await res.json();
    if (user.is_telegram_connected) {
        window.location.href = '/dashboard.html';
    } else {
        window.location.href = '/setup_telegram.html';
    }
  }
});

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove('success');
  errorBox.classList.add('visible');
}

function clearError() {
  errorBox.textContent = '';
  errorBox.classList.remove('visible');
  errorBox.classList.remove('success');
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearError();
  submitBtn.disabled = true;
  submitBtn.textContent = 'Creating…';

  const payload = {
    name: document.getElementById('name').value.trim(),
    email: document.getElementById('email').value.trim(),
    password: document.getElementById('password').value,
  };

  try {
    const res = await apiFetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      window.location.href = '/login.html?registered=1';
      return;
    }

    const data = await res.json().catch(() => ({}));
    if (Array.isArray(data.detail)) {
      // Pydantic validation errors
      showError(data.detail.map(d => d.msg).join(' '));
    } else {
      showError(data.detail || 'Something went wrong. Please try again.');
    }
  } catch (err) {
    showError('Could not reach the server. Please try again.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Create account';
  }
});
