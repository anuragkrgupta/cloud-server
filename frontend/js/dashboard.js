// Check Auth State on load
fetch('/api/me').then(async res => {
    if (!res.ok) {
        window.location.href = '/login.html';
        return;
    }
    const user = await res.json();
    
    if (!user.is_telegram_connected) {
        window.location.href = '/setup_telegram.html';
        return;
    }

    document.getElementById('main-container').classList.remove('hidden');

    document.getElementById('welcome-name').textContent = user.name;
    document.getElementById('display-name').textContent = user.name;
    document.getElementById('display-email').textContent = user.email;
    
    const tgStatus = document.getElementById('tg-status');
    tgStatus.textContent = 'Connected';
    tgStatus.className = 'px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs font-medium border border-green-500/30';
    
    if (user.channel_id) {
        document.getElementById('tg-channel-row').classList.remove('hidden');
        document.getElementById('tg-channel-id').textContent = user.channel_id;
    }

    loadFiles();
});

document.getElementById('logout-btn').addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/login.html';
});

const fileInput = document.getElementById('file-upload');
const fileNameDisplay = document.getElementById('file-name-display');
const uploadForm = document.getElementById('upload-form');
const btnUpload = document.getElementById('btn-upload');
const uploadMsg = document.getElementById('upload-msg');
const filesList = document.getElementById('files-list');

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        fileNameDisplay.textContent = e.target.files[0].name;
        fileNameDisplay.classList.add('text-indigo-300');
    } else {
        fileNameDisplay.textContent = "No file selected";
        fileNameDisplay.classList.remove('text-indigo-300');
    }
});

function showMsg(msg, isError=false) {
    uploadMsg.textContent = msg;
    uploadMsg.classList.remove('hidden', 'bg-red-500/20', 'border-red-500/50', 'text-red-200', 'bg-green-500/20', 'border-green-500/50', 'text-green-200');
    
    if (isError) {
        uploadMsg.classList.add('bg-red-500/20', 'border', 'border-red-500/50', 'text-red-200');
    } else {
        uploadMsg.classList.add('bg-green-500/20', 'border', 'border-green-500/50', 'text-green-200');
    }
}

// Fetch and display files
async function loadFiles() {
    try {
        const res = await fetch('/api/files');
        const files = await res.json();
        
        if (files.length === 0) {
            filesList.innerHTML = '<li class="text-slate-500 italic">No files uploaded yet. Upload a file above!</li>';
            return;
        }
        
        filesList.innerHTML = '';
        files.forEach(file => {
            const li = document.createElement('li');
            li.className = 'flex justify-between items-center bg-slate-800/50 p-3 rounded-lg border border-slate-700 transition-all hover:border-slate-500';
            li.id = `file-${file.id}`;
            
            const sizeStr = (file.file_size / 1024).toFixed(2) + ' KB';
            
            li.innerHTML = `
                <div class="flex-1 overflow-hidden pr-4">
                    <div class="font-medium text-slate-200 truncate">${file.original_name}</div>
                    <div class="text-xs text-slate-500">Size: ${sizeStr}</div>
                </div>
                <div class="flex space-x-2 shrink-0">
                    <button onclick="downloadFile(${file.id})" class="p-2 bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/30 rounded-lg transition-colors border border-indigo-500/30" title="Download">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    </button>
                    <button onclick="deleteFile(${file.id})" class="p-2 bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded-lg transition-colors border border-red-500/30" title="Delete">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                </div>
            `;
            filesList.appendChild(li);
        });
    } catch (err) {
        console.error("Failed to load files:", err);
    }
}

window.downloadFile = (id) => {
    window.location.href = `/api/download/${id}`;
};

window.deleteFile = async (id) => {
    if(!confirm("Are you sure you want to permanently delete this file from Telegram?")) return;
    
    try {
        const res = await fetch(`/api/files/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete file');
        
        const item = document.getElementById(`file-${id}`);
        if (item) item.remove();
        
        if (filesList.children.length === 0) {
            filesList.innerHTML = '<li class="text-slate-500 italic">No files uploaded yet. Upload a file above!</li>';
        }
    } catch (err) {
        alert(err.message);
    }
};

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (fileInput.files.length === 0) return;
    
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    btnUpload.disabled = true;
    btnUpload.textContent = "Uploading to Telegram...";
    uploadMsg.classList.add('hidden');

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData 
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || 'Upload failed');
        }
        
        showMsg('File successfully uploaded to Telegram!');
        fileInput.value = "";
        fileNameDisplay.textContent = "No file selected";
        fileNameDisplay.classList.remove('text-indigo-300');
        
        // Refresh list
        loadFiles();
        
    } catch (err) {
        showMsg(err.message, true);
    } finally {
        btnUpload.disabled = false;
        btnUpload.textContent = "Upload to Telegram";
    }
});
