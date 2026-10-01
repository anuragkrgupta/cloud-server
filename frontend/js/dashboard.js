// ============================================================
// dashboard.js — Upload & Download with live speed display
// ============================================================

// ---- Toast Notifications ----------------------------------------------
window.showToast = function(msg, type = 'success') {
    var container = document.getElementById('toast-container');
    if (!container) {
        alert(msg);
        return;
    }
    
    var el = document.createElement('div');
    var bgColor = type === 'error' ? 'bg-red-500/90' : 'bg-emerald-500/90';
    el.className = bgColor + ' text-white px-4 py-2 rounded-full shadow-lg text-sm font-medium transition-all duration-300 opacity-0 translate-y-4';
    el.innerText = msg;
    
    // Add icon if success or error
    var icon = type === 'error' ? '⚠️ ' : '✅ ';
    el.innerText = icon + msg;
    
    container.appendChild(el);
    
    // Animate in
    setTimeout(() => {
        el.classList.remove('opacity-0', 'translate-y-4');
        el.classList.add('opacity-100', 'translate-y-0');
    }, 10);
    
    // Animate out after 3 seconds
    setTimeout(() => {
        el.classList.remove('opacity-100', 'translate-y-0');
        el.classList.add('opacity-0', 'translate-y-4');
        setTimeout(() => el.remove(), 300);
    }, 3000);
};


// ---- Formatters --------------------------------------------------------

function formatBytes(b) {
    if (b === 0) return '0 B';
    var k = 1024, s = ['B','KB','MB','GB'];
    var i = Math.min(Math.floor(Math.log(b)/Math.log(k)), 3);
    return (b/Math.pow(k,i)).toFixed(i===0?0:2)+' '+s[i];
}

function formatSpeed(bps) {
    if (!bps || !isFinite(bps)) return '0 B/s';
    var k = 1024;
    if (bps >= k*k) return (bps/(k*k)).toFixed(2)+' MB/s';
    if (bps >= k)   return (bps/k).toFixed(1)+' KB/s';
    return Math.round(bps)+' B/s';
}

function formatETA(sec) {
    if (!isFinite(sec) || sec <= 0) return '';
    if (sec < 60)   return Math.round(sec)+'s left';
    if (sec < 3600) return Math.floor(sec/60)+'m '+Math.round(sec%60)+'s left';
    return Math.floor(sec/3600)+'h '+Math.floor((sec%3600)/60)+'m left';
}

function el(id) { return document.getElementById(id); }

// ---- Upload speed tracker ---------------------------------------------

var _upTotal = 0, _upSent = 0, _upSamples = [];

function upReset(total) {
    _upTotal = total; _upSent = 0;
    _upSamples = [[performance.now(), 0]];
    el('upload-speed-panel').style.display = 'block';
    el('upload-progress-bar').style.width  = '0%';
    el('upload-speed').textContent         = '0 B/s';
    el('upload-transferred').textContent   = '0 B';
    el('upload-percent').textContent       = '0%';
    el('upload-eta').textContent           = '';
}

function upTick(bytes) {
    _upSent += bytes;
    var now = performance.now();
    _upSamples.push([now, _upSent]);
    _upSamples = _upSamples.filter(function(s){ return now - s[0] <= 5000; });
    var speed = 0;
    if (_upSamples.length >= 2) {
        var a = _upSamples[0], b = _upSamples[_upSamples.length-1];
        var dt = (b[0]-a[0])/1000;
        speed = dt > 0 ? (b[1]-a[1])/dt : 0;
    }
    var pct = _upTotal > 0 ? Math.min(_upSent/_upTotal*100, 100) : 0;
    var eta = speed > 0 ? (_upTotal-_upSent)/speed : Infinity;
    el('upload-progress-bar').style.width  = pct.toFixed(1)+'%';
    el('upload-speed').textContent         = formatSpeed(speed);
    el('upload-transferred').textContent   = formatBytes(_upSent);
    el('upload-percent').textContent       = pct.toFixed(1)+'%';
    el('upload-eta').textContent           = formatETA(eta);
}

function upDone() {
    el('upload-progress-bar').style.width = '100%';
    el('upload-eta').textContent          = 'Complete';
    el('upload-percent').textContent      = '100%';
    setTimeout(function(){ el('upload-speed-panel').style.display = 'none'; }, 3000);
}

// ---- Auth check -------------------------------------------------------

apiFetch('/api/me')
.then(function(r){ return r.ok ? r.json() : Promise.reject('unauth'); })
.then(function(user) {
    if (window.hideLoadingScreen) window.hideLoadingScreen();
    if (!user.is_telegram_connected) { location.href='/setup_telegram.html'; return; }
    el('main-container').style.display = 'block';
    el('welcome-name').textContent     = user.name;
    el('display-name').textContent     = user.name;
    el('display-email').textContent    = user.email;
    var s = el('tg-status');
    s.textContent = 'Connected';
    s.className = 'px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs font-medium border border-green-500/30';
    if (user.channel_id) {
        el('tg-channel-row').style.display = '';
        el('tg-channel-id').textContent = user.channel_id;
    }
    loadFiles();
})
.catch(function(){ 
    if (window.hideLoadingScreen) window.hideLoadingScreen();
    location.href='/login.html'; 
});

el('logout-btn').addEventListener('click', function(){
    apiFetch('/api/logout',{method:'POST'}).finally(function(){
        clearAuthToken();
        location.href='/login.html'; 
    });
});

// ---- File input -------------------------------------------------------

el('file-upload').addEventListener('change', function(e){
    var d = el('file-name-display');
    d.textContent = e.target.files.length ? e.target.files[0].name : 'No file selected';
    d.className   = e.target.files.length ? 'text-xs text-indigo-300' : 'text-xs text-slate-500';
});

// ---- Status message ---------------------------------------------------

function showMsg(msg, isErr) {
    var m = el('upload-msg');
    m.textContent    = msg;
    m.style.display  = 'block';
    var blue = msg.indexOf('Upload')>=0||msg.indexOf('Final')>=0||msg.indexOf('Prepar')>=0||msg.indexOf('Resum')>=0;
    m.className = 'p-3 text-sm rounded-lg '+(isErr
        ? 'bg-red-500/20 border border-red-500/50 text-red-200'
        : blue
            ? 'bg-blue-500/20 border border-blue-500/50 text-blue-200'
            : 'bg-green-500/20 border border-green-500/50 text-green-200');
}

function hideMsg(){ el('upload-msg').style.display='none'; }

// ---- Load file list ---------------------------------------------------

function loadFiles() {
    apiFetch('/api/files').then(function(r){ return r.json(); }).then(function(files){
        var list = el('files-list');
        if (!files.length) {
            list.innerHTML = '<li class="text-slate-500 italic">No files uploaded yet. Upload a file above!</li>';
            return;
        }
        list.innerHTML = '';
        files.forEach(function(f){
            var li = document.createElement('li');
            li.id = 'file-'+f.id;
            li.className = 'bg-slate-800/50 p-3 rounded-lg border border-slate-700 hover:border-slate-500 transition-all';
            li.innerHTML =
                '<div class="flex justify-between items-center">'
              +   '<div class="flex-1 overflow-hidden pr-3">'
              +     '<div class="font-medium text-slate-200 truncate file-name">'+f.original_name+'</div>'
              +     '<div class="text-xs text-slate-500">'+formatBytes(f.file_size)+'</div>'
              +   '</div>'
              +   '<div class="flex gap-2 shrink-0">'
              +     '<button onclick="shareFile('+f.id+')"'
              +       ' class="p-2 bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-lg border border-emerald-500/30" title="Share">'
              +       '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
              +         '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />'
              +       '</svg>'
              +     '</button>'
              +     '<button id="dl-btn-'+f.id+'" onclick="dlFile('+f.id+')"'
              +       ' class="p-2 bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/30 rounded-lg border border-indigo-500/30" title="Download">'
              +       '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
              +         '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>'
              +       '</svg>'
              +     '</button>'
              +     '<button onclick="delFile('+f.id+')"'
              +       ' class="p-2 bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded-lg border border-red-500/30" title="Delete">'
              +       '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
              +         '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>'
              +       '</svg>'
              +     '</button>'
              +   '</div>'
              + '</div>'
              // Download speed strip
              + '<div id="dls-'+f.id+'" style="display:none;margin-top:8px">'
              +   '<div style="background:#1e293b;border-radius:4px;height:4px;overflow:hidden;margin-bottom:4px">'
              +     '<div id="dlb-'+f.id+'" style="height:4px;width:0%;background:linear-gradient(to right,#06b6d4,#3b82f6);transition:width 0.3s"></div>'
              +   '</div>'
              +   '<div style="display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;margin-top:2px">'
              +     '<span id="dlspd-'+f.id+'" style="color:#22d3ee;font-weight:600">0 B/s</span>'
              +     '<span id="dlxfr-'+f.id+'">0 B</span>'
              +   '</div>'
              + '</div>';
            list.appendChild(li);
        });
    }).catch(function(e){ console.error('loadFiles error:', e); });
}

window.shareFile = function(id) {
    apiFetch('/api/files/'+id+'/share', { method: 'POST' })
    .then(function(res){
        if (!res.ok) throw new Error('Share failed');
        return res.json();
    })
    .then(function(data){
        var url = window.location.origin + data.url;
        navigator.clipboard.writeText(url).then(function(){
            showToast('Share link copied to clipboard!');
        }).catch(function(){
            prompt('Copy this link:', url);
        });
    })
    .catch(function(e){
        showToast('Failed to share file.', 'error');
    });
};

// ---- Download with live speed -----------------------------------------

window.dlFile = function(id) {
    var btn    = el('dl-btn-'+id);
    var strip  = el('dls-'+id);
    var bar    = el('dlb-'+id);
    var spdEl  = el('dlspd-'+id);
    var xfrEl  = el('dlxfr-'+id);

    if (btn) btn.disabled = true;
    strip.style.display = 'block';
    bar.style.width     = '0%';
    spdEl.textContent   = 'Starting…';
    xfrEl.textContent   = '';

    // Stream large files directly to disk via native browser download.
    // Authentication cookies (access_token) are sent automatically on
    // same-site requests, so no manual header injection is needed.
    // The backend sets Content-Disposition: attachment so the browser
    // triggers a Save-As dialog / download bar natively.
    var downloadUrl = getApiUrl('/api/download/' + id);

    // Use a temporary <a> link instead of a hidden iframe.
    // Mobile browsers block downloads from iframes because they don't
    // consider them user-gesture-initiated. A programmatic click on an
    // <a> tag within the same call stack as the user's tap is treated
    // as a trusted gesture and works on both desktop and mobile.
    var a = document.createElement('a');
    a.href = downloadUrl;
    a.download = '';          // hint to browser: treat as download
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    bar.style.width   = '100%';
    spdEl.textContent = '↓ Download started';
    xfrEl.textContent = 'Check your browser downloads';

    setTimeout(function(){
        strip.style.display = 'none';
        if (btn) btn.disabled = false;
    }, 5000);
};

// ---- Delete -----------------------------------------------------------

window.delFile = function(id) {
    if (!confirm('Permanently delete this file from Cloud?')) return;
    apiFetch('/api/files/'+id, {method:'DELETE'})
    .then(function(r){
        if (!r.ok) throw new Error('Delete failed');
        var li = el('file-'+id);
        if (li) li.remove();
        var list = el('files-list');
        if (!list.children.length)
            list.innerHTML = '<li class="text-slate-500 italic">No files uploaded yet.</li>';
    })
    .catch(function(e){ alert(e.message); });
};

// ---- Upload -----------------------------------------------------------

el('upload-form').addEventListener('submit', function(e){
    e.preventDefault();
    var inp = el('file-upload');
    if (!inp.files.length) return;

    var file = inp.files[0];
    var btn  = el('btn-upload');
    btn.disabled    = true;
    btn.textContent = 'Uploading...';
    hideMsg();

    var CHUNK  = 1.5*1024*1024;        // 1.5 MB per HTTP POST
    var PART   = 512*1024;            // 512 KB Telegram part
    var MAXVOL = 3890*512*1024;       // ~1.90 GB volume limit (exact integer, aligned to 512 KB parts)
    var nvols  = Math.ceil(file.size/MAXVOL) || 1;
    var msgIds = [];

    upReset(file.size);

    function doVol(vi) {
        if (vi >= nvols) {
            // All volumes done
            showMsg('Completing upload...');
            return apiFetch('/api/upload/complete', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                    filename:    file.name,
                    file_size:   file.size,
                    mime_type:   file.type || 'application/octet-stream',
                    message_ids: msgIds
                })
            }).then(function(r){
                if (!r.ok) return r.json().then(function(d){ throw new Error(d.detail||'Complete failed'); });
                showMsg('File uploaded successfully!');
                upDone();
                inp.value = '';
                el('file-name-display').textContent = 'No file selected';
                el('file-name-display').className   = 'text-xs text-slate-500';
                loadFiles();
            });
        }

        var vs  = Math.floor(vi*MAXVOL);
        var ve  = Math.min(vs+MAXVOL, file.size);
        var vsz = Math.floor(ve-vs);
        var volumeSlice = file.slice(vs, ve);
        showMsg('Uploading volume '+(vi+1)+'/'+nvols+'...');

        return new Promise(function(resolve, reject) {
            var xhr = new XMLHttpRequest();
            var url = getApiUrl('/api/upload/stream?filename=' + encodeURIComponent(file.name) + '&filesize=' + vsz);
            xhr.open('POST', url, true);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            var _t = getAuthToken();
            if (_t) xhr.setRequestHeader('Authorization', 'Bearer ' + _t);
            xhr.withCredentials = true;
            
            var lastLoaded = 0;
            xhr.upload.onprogress = function(e) {
                if (e.lengthComputable) {
                    var delta = e.loaded - lastLoaded;
                    lastLoaded = e.loaded;
                    upTick(delta);
                }
            };
            
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    var diff = vsz - lastLoaded;
                    if (diff > 0) upTick(diff);
                    try {
                        var d = JSON.parse(xhr.responseText);
                        msgIds.push(d.message_id);
                        resolve(doVol(vi+1));
                    } catch(err) {
                        reject(new Error('Invalid JSON response from server'));
                    }
                } else {
                    try {
                        var d = JSON.parse(xhr.responseText);
                        reject(new Error(d.detail || 'Upload failed'));
                    } catch(e) {
                        reject(new Error('HTTP ' + xhr.status));
                    }
                }
            };
            
            xhr.onerror = function() { reject(new Error('Network Error')); };
            xhr.send(volumeSlice);
        }).catch(function(err){
            throw err; // bubble to doVol(0).catch
        });
    }

    doVol(0)
    .catch(function(err){
        if (err.message && err.message.toLowerCase().includes('session expired')) {
            location.href = '/setup_telegram.html';
            return;
        }
        showMsg(err.message || 'Upload failed', true);
        el('upload-speed-panel').style.display = 'none';
    })
    .finally(function(){
        btn.disabled    = false;
        btn.textContent = 'Upload to Cloud';
    });
});

