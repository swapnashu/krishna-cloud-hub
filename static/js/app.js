// State Management
let currentPath = "";
let currentItems = [];
let selectedPaths = new Set();
let viewMode = "list";
let activeFilter = "all";
let searchQuery = "";
let sortBy = "name";
let sortOrder = "asc";
let currentEditingPath = "";

// Terminal State
let terminalHistory = [];
let terminalHistoryIdx = -1;

document.addEventListener('DOMContentLoaded', () => {
    fetchSystemInfo();
    fetchDirectoryContents(currentPath);
    setupUploadHandlers();
});

async function fetchSystemInfo() {
    try {
        const res = await fetch('/api/info');
        if (!res.ok) throw new Error('Failed system info request');
        const data = await res.json();
        
        document.getElementById('stat-status').textContent = 'Online 🟢';
        document.getElementById('stat-files').textContent = data.total_files;
        
        if (data.disk) {
            document.getElementById('storage-percent').textContent = `${data.disk.used_percent}%`;
            document.getElementById('storage-fill').style.width = `${Math.min(data.disk.used_percent, 100)}%`;
            document.getElementById('stat-disk-subtext').textContent = `Free: ${data.disk.free_formatted} / Total: ${data.disk.total_formatted}`;
        }
        
        document.getElementById('stat-uptime').textContent = `:${data.port} | ${data.uptime}`;
    } catch (err) {
        document.getElementById('stat-status').textContent = 'Offline 🔴';
        document.getElementById('stat-status').style.color = '#EF4444';
    }
}

async function fetchDirectoryContents(path = "") {
    currentPath = path;
    selectedPaths.clear();
    updateBatchBar();
    document.getElementById('select-all-checkbox').checked = false;
    
    // Update Terminal CWD Badge
    const cwdBadge = document.getElementById('terminal-cwd-badge');
    if (cwdBadge) cwdBadge.textContent = path ? `uploads/${path}` : 'uploads/';

    const container = document.getElementById('explorer-body');
    container.innerHTML = '<div class="empty-state">Loading directory...</div>';
    renderBreadcrumbs();

    try {
        const url = `/api/files?path=${encodeURIComponent(path)}&sort_by=${sortBy}&sort_order=${sortOrder}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Directory fetch failed');
        const data = await res.json();
        
        currentItems = data.items;
        renderExplorer();
        fetchSystemInfo();
    } catch (err) {
        container.innerHTML = `<div class="empty-state">Error loading directory contents (${escapeHtml(err.message)})</div>`;
    }
}

function renderBreadcrumbs() {
    const container = document.getElementById('breadcrumbs');
    const parts = currentPath ? currentPath.split('/') : [];
    
    let html = `<span class="crumb-item" onclick="fetchDirectoryContents('')">🏠 Root</span>`;
    let accumulatedPath = "";

    parts.forEach((part, index) => {
        if (!part) return;
        accumulatedPath += (accumulatedPath ? '/' : '') + part;
        const isLast = index === parts.length - 1;
        
        html += ` <span class="crumb-separator">/</span> `;
        if (isLast) {
            html += `<span class="crumb-current">${escapeHtml(part)}</span>`;
        } else {
            const navPath = accumulatedPath;
            html += `<span class="crumb-item" onclick="fetchDirectoryContents('${escapeHtml(navPath)}')">${escapeHtml(part)}</span>`;
        }
    });

    container.innerHTML = html;
}

function renderExplorer() {
    const container = document.getElementById('explorer-body');
    
    let filtered = currentItems.filter(item => {
        if (searchQuery && !item.name.toLowerCase().includes(searchQuery.toLowerCase())) {
            return false;
        }
        if (activeFilter === "code") return item.is_dir || item.is_text;
        if (activeFilter === "images") return item.is_dir || item.is_image;
        if (activeFilter === "media") return item.is_dir || item.is_audio || item.is_video;
        if (activeFilter === "docs") return item.is_dir || (item.is_text && !["py","js","html","css","json"].includes(item.extension));
        if (activeFilter === "archives") return item.is_dir || item.is_archive;
        return true;
    });

    if (filtered.length === 0) {
        container.className = "explorer-body";
        container.innerHTML = `<div class="empty-state">No files or folders found.</div>`;
        return;
    }

    if (viewMode === "list") {
        container.className = "file-list-view";
        container.innerHTML = filtered.map(item => `
            <div class="file-item-row">
                <input type="checkbox" ${selectedPaths.has(item.path) ? 'checked' : ''} onchange="toggleItemSelect('${escapeHtml(item.path)}', this)">
                <span class="item-icon">${getItemIcon(item)}</span>
                <span class="item-title" onclick="handleItemClick('${escapeHtml(item.path)}', ${item.is_dir}, ${item.is_text}, ${item.is_image}, ${item.is_audio}, ${item.is_video})">
                    ${escapeHtml(item.name)}
                </span>
                <span class="item-size">${item.size_formatted}</span>
                <span class="item-date">${item.modified}</span>
                <div class="item-actions">
                    ${getItemActionButtons(item)}
                </div>
            </div>
        `).join('');
    } else {
        container.className = "file-grid-view";
        container.innerHTML = filtered.map(item => `
            <div class="file-grid-card">
                <input type="checkbox" class="grid-checkbox" ${selectedPaths.has(item.path) ? 'checked' : ''} onchange="toggleItemSelect('${escapeHtml(item.path)}', this)">
                <div class="grid-icon">${getItemIcon(item)}</div>
                <div class="grid-title" onclick="handleItemClick('${escapeHtml(item.path)}', ${item.is_dir}, ${item.is_text}, ${item.is_image}, ${item.is_audio}, ${item.is_video})">
                    ${escapeHtml(item.name)}
                </div>
                <div class="grid-subtext">${item.is_dir ? 'Folder' : item.size_formatted}</div>
                <div class="grid-actions">
                    ${getItemActionButtons(item, true)}
                </div>
            </div>
        `).join('');
    }
}

function getItemIcon(item) {
    if (item.is_dir) return '📁';
    if (item.is_image) return '🖼️';
    if (item.is_audio) return '🎵';
    if (item.is_video) return '🎬';
    if (item.is_archive) return '📦';
    if (item.is_text) return '📝';
    return '📄';
}

function getItemActionButtons(item, isGrid = false) {
    let btns = '';
    
    if (item.is_dir) {
        btns += `<button class="btn btn-secondary btn-small" onclick="fetchDirectoryContents('${escapeHtml(item.path)}')">Open</button>`;
    } else {
        if (item.is_text) {
            btns += `<button class="btn btn-primary btn-small" onclick="openEditor('${escapeHtml(item.path)}')">✏️ Edit</button>`;
            if (["py", "js", "sh", "bat"].includes(item.extension)) {
                btns += `<button class="btn btn-accent btn-small" onclick="runScriptFile('${escapeHtml(item.path)}', '${item.extension}')" title="Run Script">▶️</button>`;
            }
        }
        if (item.is_image || item.is_audio || item.is_video) {
            btns += `<button class="btn btn-accent btn-small" onclick="openPreview('${escapeHtml(item.path)}', ${item.is_image}, ${item.is_audio}, ${item.is_video})">👁️ Preview</button>`;
        }
        btns += `<button class="btn btn-secondary btn-small" onclick="copyDirectLink('${escapeHtml(item.path)}')" title="Copy Direct Link">🔗</button>`;
        btns += `<a href="/api/files/view/${encodeURIComponent(item.path)}" download class="btn btn-secondary btn-small">⬇️</a>`;
    }
    
    btns += `<button class="btn btn-secondary btn-small" onclick="duplicateItem('${escapeHtml(item.path)}')" title="Duplicate Item">📋</button>`;
    btns += `<button class="btn btn-secondary btn-small" onclick="openRenameModal('${escapeHtml(item.path)}', '${escapeHtml(item.name)}')">✏️</button>`;
    btns += `<button class="btn btn-danger btn-small" onclick="deleteSingleItem('${escapeHtml(item.path)}')">🗑️</button>`;
    
    return btns;
}

function handleItemClick(path, isDir, isText, isImage, isAudio, isVideo) {
    if (isDir) {
        fetchDirectoryContents(path);
    } else if (isText) {
        openEditor(path);
    } else if (isImage || isAudio || isVideo) {
        openPreview(path, isImage, isAudio, isVideo);
    } else {
        window.open(`/api/files/view/${encodeURIComponent(path)}`, '_blank');
    }
}

// Code Editor Modal
async function openEditor(path) {
    try {
        const res = await fetch(`/api/files/content?path=${encodeURIComponent(path)}`);
        if (!res.ok) throw new Error('Could not read file content');
        const data = await res.json();
        
        currentEditingPath = path;
        document.getElementById('editor-title').textContent = `Editing: ${data.filename}`;
        document.getElementById('editor-path').textContent = path;
        document.getElementById('code-editor').value = data.content;
        
        const runBtn = document.getElementById('run-script-btn');
        if (["py", "js", "sh", "bat"].includes(data.extension)) {
            runBtn.style.display = 'inline-flex';
        } else {
            runBtn.style.display = 'none';
        }
        
        openModal('editor-modal');
    } catch (err) {
        showToast(`Failed to load file: ${err.message}`, 'error');
    }
}

async function saveEditorContent() {
    if (!currentEditingPath) return;
    const content = document.getElementById('code-editor').value;
    
    try {
        const res = await fetch('/api/files/content', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: currentEditingPath, content: content })
        });
        if (!res.ok) throw new Error('Save failed');
        const data = await res.json();
        
        showToast(data.message);
        closeModal('editor-modal');
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast(`Error saving file: ${err.message}`, 'error');
    }
}

async function runCurrentScript() {
    if (!currentEditingPath) return;
    await saveEditorContent();
    const ext = currentEditingPath.split('.').pop().toLowerCase();
    runScriptFile(currentEditingPath, ext);
}

function runScriptFile(path, ext) {
    const filename = path.split('/').pop();
    let runnerCmd = "";
    if (ext === "py") runnerCmd = `python "${filename}"`;
    else if (ext === "js") runnerCmd = `node "${filename}"`;
    else if (ext === "sh") runnerCmd = `bash "${filename}"`;
    else runnerCmd = `"${filename}"`;
    
    // Open terminal drawer and execute
    const terminalDrawer = document.getElementById('terminal-drawer');
    terminalDrawer.style.display = 'block';
    terminalDrawer.scrollIntoView({ behavior: 'smooth' });
    
    const parentFolder = path.includes('/') ? path.substring(0, path.lastIndexOf('/')) : "";
    executeTerminalCommand(runnerCmd, parentFolder);
}

// Web Terminal Operations
function toggleTerminal() {
    const terminalDrawer = document.getElementById('terminal-drawer');
    if (terminalDrawer.style.display === 'none' || !terminalDrawer.style.display) {
        terminalDrawer.style.display = 'block';
        terminalDrawer.scrollIntoView({ behavior: 'smooth' });
        document.getElementById('terminal-cmd-input').focus();
    } else {
        terminalDrawer.style.display = 'none';
    }
}

function runQuickCommand(cmd) {
    const terminalDrawer = document.getElementById('terminal-drawer');
    terminalDrawer.style.display = 'block';
    executeTerminalCommand(cmd, currentPath);
}

function submitTerminalCommand() {
    const input = document.getElementById('terminal-cmd-input');
    const cmd = input.value.trim();
    if (!cmd) return;
    
    terminalHistory.push(cmd);
    terminalHistoryIdx = terminalHistory.length;
    input.value = '';
    
    executeTerminalCommand(cmd, currentPath);
}

function handleTerminalKeyDown(event) {
    if (event.key === 'Enter') {
        submitTerminalCommand();
    } else if (event.key === 'ArrowUp') {
        if (terminalHistoryIdx > 0) {
            terminalHistoryIdx--;
            event.target.value = terminalHistory[terminalHistoryIdx];
        }
    } else if (event.key === 'ArrowDown') {
        if (terminalHistoryIdx < terminalHistory.length - 1) {
            terminalHistoryIdx++;
            event.target.value = terminalHistory[terminalHistoryIdx];
        } else {
            terminalHistoryIdx = terminalHistory.length;
            event.target.value = '';
        }
    }
}

async function executeTerminalCommand(cmd, cwdOverride = null) {
    const consoleDiv = document.getElementById('terminal-console');
    const targetCwd = cwdOverride !== null ? cwdOverride : currentPath;
    const cwdDisplay = targetCwd ? `uploads/${targetCwd}` : 'uploads/';
    
    // Append command line
    const cmdLine = document.createElement('div');
    cmdLine.className = 'terminal-line log-cmd';
    cmdLine.textContent = `$ ${cwdDisplay}> ${cmd}`;
    consoleDiv.appendChild(cmdLine);
    consoleDiv.scrollTop = consoleDiv.scrollHeight;

    if (cmd.toLowerCase() === 'clear') {
        clearTerminalLogs();
        return;
    }

    try {
        const res = await fetch('/api/terminal/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmd, cwd: targetCwd })
        });
        
        if (!res.ok) throw new Error('Command execution API error');
        const data = await res.json();
        
        if (data.stdout) {
            const stdoutLine = document.createElement('div');
            stdoutLine.className = 'terminal-line log-stdout';
            stdoutLine.textContent = data.stdout;
            consoleDiv.appendChild(stdoutLine);
        }
        
        if (data.stderr) {
            const stderrLine = document.createElement('div');
            stderrLine.className = 'terminal-line log-stderr';
            stderrLine.textContent = data.stderr;
            consoleDiv.appendChild(stderrLine);
        }
        
        const infoLine = document.createElement('div');
        infoLine.className = data.exit_code === 0 ? 'terminal-line log-success' : 'terminal-line log-stderr';
        infoLine.textContent = `[Process finished with exit code ${data.exit_code} (${data.duration_ms}ms)]`;
        consoleDiv.appendChild(infoLine);
        
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    } catch (err) {
        const errLine = document.createElement('div');
        errLine.className = 'terminal-line log-stderr';
        errLine.textContent = `Execution Error: ${err.message}`;
        consoleDiv.appendChild(errLine);
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    }
}

function clearTerminalLogs() {
    const consoleDiv = document.getElementById('terminal-console');
    consoleDiv.innerHTML = '<div class="terminal-line log-system">Terminal cleared. Type a command or run a script above.</div>';
}

// Media Preview Modal
function openPreview(path, isImage, isAudio, isVideo) {
    const title = document.getElementById('preview-title');
    const contentBody = document.getElementById('preview-content-body');
    const rawUrl = `/api/files/view/${encodeURIComponent(path)}`;
    
    title.textContent = `Preview: ${path.split('/').pop()}`;
    
    if (isImage) {
        contentBody.innerHTML = `<img src="${rawUrl}" class="preview-img" alt="Preview">`;
    } else if (isAudio) {
        contentBody.innerHTML = `<audio controls src="${rawUrl}" class="preview-media"></audio>`;
    } else if (isVideo) {
        contentBody.innerHTML = `<video controls src="${rawUrl}" class="preview-media"></video>`;
    }
    
    openModal('preview-modal');
}

// File Duplication
async function duplicateItem(path) {
    try {
        const res = await fetch('/api/files/copy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_path: path })
        });
        if (!res.ok) throw new Error('Duplicate failed');
        const data = await res.json();
        
        showToast(data.message);
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast(`Duplicate error: ${err.message}`, 'error');
    }
}

function copyDirectLink(path) {
    const fullUrl = `${window.location.origin}/api/files/view/${encodeURIComponent(path)}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
        showToast('Direct URL copied to clipboard! 🔗');
    }).catch(() => {
        showToast('Failed to copy URL', 'error');
    });
}

// Folder & File Creation
async function submitCreateFolder() {
    const input = document.getElementById('new-folder-name');
    const folderName = input.value.trim();
    if (!folderName) return;
    
    const targetFolder = currentPath ? `${currentPath}/${folderName}` : folderName;
    
    try {
        const res = await fetch('/api/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: targetFolder })
        });
        if (!res.ok) throw new Error('Failed to create folder');
        
        showToast('Folder created!');
        input.value = '';
        closeModal('new-folder-modal');
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast(`Error creating folder: ${err.message}`, 'error');
    }
}

async function submitCreateFile() {
    const input = document.getElementById('new-file-name');
    const fileName = input.value.trim();
    if (!fileName) return;
    
    const targetFile = currentPath ? `${currentPath}/${fileName}` : fileName;
    
    try {
        const res = await fetch('/api/files/create-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: targetFile, content: "" })
        });
        if (!res.ok) throw new Error('Failed to create file');
        
        showToast('File created!');
        input.value = '';
        closeModal('new-file-modal');
        fetchDirectoryContents(currentPath);
        openEditor(targetFile);
    } catch (err) {
        showToast(`Error creating file: ${err.message}`, 'error');
    }
}

// Rename
function openRenameModal(path, currentName) {
    document.getElementById('rename-old-path').value = path;
    document.getElementById('rename-new-name').value = currentName;
    openModal('rename-modal');
}

async function submitRename() {
    const oldPath = document.getElementById('rename-old-path').value;
    const newName = document.getElementById('rename-new-name').value.trim();
    if (!newName) return;

    try {
        const res = await fetch('/api/files/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_path: oldPath, new_name: newName })
        });
        if (!res.ok) throw new Error('Rename failed');
        const data = await res.json();
        
        showToast(data.message);
        closeModal('rename-modal');
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast(`Rename error: ${err.message}`, 'error');
    }
}

// Deletion
async function deleteSingleItem(path) {
    if (!confirm(`Are you sure you want to delete "${path}"?`)) return;

    try {
        const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        
        showToast('Deleted item');
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast(`Delete error: ${err.message}`, 'error');
    }
}

// Upload Setup
function setupUploadHandlers() {
    const dropZone = document.getElementById('drop-zone-wrapper');
    const fileInput = document.getElementById('file-input');

    ['dragenter', 'dragover'].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        });
    });

    dropZone.addEventListener('drop', (e) => {
        if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
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

    try {
        showToast('Uploading files...');
        const res = await fetch(`/api/files/upload?target_path=${encodeURIComponent(currentPath)}`, {
            method: 'POST',
            body: formData
        });
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        
        showToast(data.message);
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast('Upload error', 'error');
    }
}

// Batch Actions
function toggleItemSelect(path, checkbox) {
    if (checkbox.checked) {
        selectedPaths.add(path);
    } else {
        selectedPaths.delete(path);
    }
    updateBatchBar();
}

function toggleSelectAll(masterCheckbox) {
    if (masterCheckbox.checked) {
        currentItems.forEach(item => selectedPaths.add(item.path));
    } else {
        selectedPaths.clear();
    }
    renderExplorer();
    updateBatchBar();
}

function updateBatchBar() {
    const batchBar = document.getElementById('batch-bar');
    const countSpan = document.getElementById('batch-count');
    
    if (selectedPaths.size > 0) {
        batchBar.style.display = 'flex';
        countSpan.textContent = `${selectedPaths.size} item(s) selected`;
    } else {
        batchBar.style.display = 'none';
    }
}

async function downloadSelectedZip() {
    if (selectedPaths.size === 0) return;
    
    try {
        showToast('Compressing ZIP archive...');
        const res = await fetch('/api/files/zip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths: Array.from(selectedPaths) })
        });
        if (!res.ok) throw new Error('ZIP generation failed');
        
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `cloud_archive_${Date.now()}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast('Download started!');
    } catch (err) {
        showToast(`ZIP error: ${err.message}`, 'error');
    }
}

async function deleteSelectedItems() {
    if (selectedPaths.size === 0) return;
    if (!confirm(`Delete ${selectedPaths.size} selected item(s)?`)) return;

    try {
        const res = await fetch('/api/files/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths: Array.from(selectedPaths) })
        });
        if (!res.ok) throw new Error('Batch delete failed');
        const data = await res.json();
        
        showToast(data.message);
        fetchDirectoryContents(currentPath);
    } catch (err) {
        showToast(`Batch delete error: ${err.message}`, 'error');
    }
}

// UI Filters & Sorting
function handleSortChange() {
    sortBy = document.getElementById('sort-by-select').value;
    fetchDirectoryContents(currentPath);
}

function toggleSortOrder() {
    sortOrder = (sortOrder === 'asc') ? 'desc' : 'asc';
    document.getElementById('sort-order-btn').textContent = (sortOrder === 'asc') ? '⬇️' : '⬆️';
    fetchDirectoryContents(currentPath);
}

function setViewMode(mode) {
    viewMode = mode;
    document.getElementById('view-list-btn').classList.toggle('active', mode === 'list');
    document.getElementById('view-grid-btn').classList.toggle('active', mode === 'grid');
    renderExplorer();
}

function setFilter(filter, button) {
    activeFilter = filter;
    document.querySelectorAll('.filter-pill').forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');
    renderExplorer();
}

function handleSearch() {
    searchQuery = document.getElementById('search-input').value.trim();
    renderExplorer();
}

// Modal Helpers
function openModal(id) {
    document.getElementById(id).classList.add('open');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('open');
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
    if (!text) return '';
    const div = document.createElement('div');
    div.innerText = text;
    return div.innerHTML;
}
