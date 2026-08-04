fetch('/api/me').then(async res => {
    if (res.ok) {
        const user = await res.json();
        if (user.is_telegram_connected) {
            window.location.href = '/dashboard.html';
        } else {
            window.location.href = '/setup_telegram.html';
        }
    } else {
        window.location.href = '/login.html';
    }
}).catch(() => {
    window.location.href = '/login.html';
});
