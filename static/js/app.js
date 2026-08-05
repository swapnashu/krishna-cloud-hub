document.addEventListener('DOMContentLoaded', () => {
    fetchSystemInfo();
    fetchFiles();
    setupUpload();
});

async function fetchSystemInfo() {
    try {
        const res = await fetch('/api/info');
        if (!res.ok) throw new Error('Failed to fetch system info');
        const data = await res.json();
        
        document.getElementById('stat-status').textContent = 'Online 🟢';
        document.getElementById('stat-files').textContent = data.total_files;
        document.getElementById('stat-storage').textContent = `${data.total_storage_mb} MB`;
        document.getElementById('stat-uptime').textContent = `:${data.port} | ${data.uptime}`;
    } catch (err) {
        document.getElementById('stat-status').textContent = 'Offline 🔴';
        document.getElementById('stat-status').className = 'stat-value';
        document.getElementById('stat-status').style.color = '#EF4444';
    }
}

async function fetchFiles() {
    const container = document.getElementById('file-list-container');
    container.innerHTML = '<div class="empty-state">Refreshing files...</div>';
    
    try {
        const res = await fetch('/api/files');
        const data = await res.json();
        
        if (!data.files || data.files.length === 0) {
            container.innerHTML = '<div class="empty-state">No files uploaded yet. Drag & drop files above to start!</div>';
            return;
        }
        
        container.innerHTML = data.files.map(file => `
            <div class="file-item">
                <div class="file-meta">
                    <span class="file-icon">${getFileIcon(file.name)}</span>
                    <div>
                        <div class="file-name">${escapeHtml(file.name)}</div>
                        <div class="file-subtext">${file.size_kb} KB • Modified ${file.modified}</div>
                    </div>
                </div>
                <div class="file-actions">
                    <a href="/api/files/${encodeURIComponent(file.name)}" class="action-btn action-download" download>Download</a>
                    <button onclick="deleteFile('${escapeHtml(file.name)}')" class="action-btn action-delete">Delete</button>
                </div>
            </div>
        `).join('');
        
        fetchSystemInfo();
    } catch (err) {
        container.innerHTML = '<div class="empty-state">Error loading file list.</div>';
    }
}

function setupUpload() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) uploadFiles(files);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) uploadFiles(e.target.files);
    });
}

async function uploadFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    const progressBar = document.getElementById('progress-bar');
    const progressContainer = document.getElementById('upload-progress');
    progressContainer.style.display = 'block';
    progressBar.style.width = '50%';

    try {
        const res = await fetch('/api/files/upload', {
            method: 'POST',
            body: formData
        });
        
        progressBar.style.width = '100%';
        
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        
        showToast(data.message || 'Upload complete!');
        fetchFiles();
    } catch (err) {
        showToast('Error uploading files', 'error');
    } finally {
        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressBar.style.width = '0%';
        }, 800);
    }
}

async function deleteFile(filename) {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) return;

    try {
        const res = await fetch(`/api/files/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Delete failed');
        
        showToast(`Deleted ${filename}`);
        fetchFiles();
    } catch (err) {
        showToast('Failed to delete file', 'error');
    }
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        pdf: '📄', txt: '📝', doc: '📄', docx: '📄',
        jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', svg: '🖼️',
        mp3: '🎵', wav: '🎵', mp4: '🎬', avi: '🎬',
        zip: '📦', rar: '📦', tar: '📦', gz: '📦',
        py: '🐍', js: '⚡', html: '🌐', css: '🎨', json: '⚙️'
    };
    return icons[ext] || '📁';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'error') toast.style.borderLeftColor = '#EF4444';
    toast.textContent = message;
    
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.innerText = text;
    return div.innerHTML;
}
