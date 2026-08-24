function el(id) { return document.getElementById(id); }

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    var k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

document.addEventListener('DOMContentLoaded', function() {
    var params = new URLSearchParams(window.location.search);
    var token = params.get('token');

    if (!token) {
        showError('No share token provided in URL.');
        return;
    }

    // Fetch file info
    fetch('/api/shared/' + token)
    .then(function(res) {
        if (!res.ok) throw new Error('File not found or link expired.');
        return res.json();
    })
    .then(function(fileInfo) {
        el('loading').style.display = 'none';
        el('file-info').style.display = 'block';
        el('filename').textContent = fileInfo.original_name;
        el('filesize').textContent = formatBytes(fileInfo.file_size);
        el('ownername').textContent = fileInfo.owner_name;

        checkAuth(token);
    })
    .catch(function(e) {
        showError(e.message);
    });
});

function showError(msg) {
    el('loading').style.display = 'none';
    el('file-info').style.display = 'none';
    el('error-info').style.display = 'block';
    if(msg) el('error-msg').textContent = msg;
}

function checkAuth(token) {
    fetch('/api/me')
    .then(function(r) { return r.ok ? r.json() : Promise.reject('unauth'); })
    .then(function(user) {
        if (!user.is_telegram_connected) {
            // Logged in but not connected
            showSaveError('Please connect your Telegram account in the dashboard first.', true);
        } else {
            el('save-section').classList.remove('hidden');
            el('save-btn').onclick = function() {
                saveFile(token);
            };
        }
    })
    .catch(function() {
        // Not logged in
        el('auth-check').classList.remove('hidden');
        // Save current url to redirect back after login (could be implemented in login.js)
        localStorage.setItem('redirect_after_login', window.location.href);
    });
}

function saveFile(token) {
    var btn = el('save-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="animate-pulse">Transferring...</span>';
    
    fetch('/api/shared/' + token + '/save', { method: 'POST' })
    .then(function(res) {
        return res.json().then(function(data) {
            if (!res.ok) throw new Error(data.detail || 'Failed to save file');
            return data;
        });
    })
    .then(function(data) {
        btn.style.display = 'none';
        var msg = el('save-msg');
        msg.textContent = data.message || 'File transfer started successfully! Check your dashboard.';
        msg.className = 'mt-4 text-sm p-3 bg-emerald-500/20 text-emerald-200 border border-emerald-500/50 rounded-lg';
        msg.style.display = 'block';
        
        setTimeout(function() {
            window.location.href = '/dashboard.html';
        }, 3000);
    })
    .catch(function(e) {
        btn.disabled = false;
        btn.innerHTML = 'Try Again';
        showSaveError(e.message, false);
    });
}

function showSaveError(msg, showAsAuth) {
    if (showAsAuth) {
        el('auth-check').classList.remove('hidden');
        el('auth-check').innerHTML = '<p class="text-red-400 mb-4">' + msg + '</p>' + 
            '<a href="/dashboard.html" class="block w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-colors text-center border border-indigo-500 shadow-[0_0_15px_rgba(79,70,229,0.3)]">Go to Dashboard</a>';
    } else {
        var errEl = el('save-msg');
        errEl.textContent = msg;
        errEl.className = 'mt-4 text-sm p-3 bg-red-500/20 text-red-200 border border-red-500/50 rounded-lg';
        errEl.style.display = 'block';
    }
}
