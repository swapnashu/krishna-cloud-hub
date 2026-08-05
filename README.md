# ⚡ Advanced Cloud File Hub & Web IDE

A high-performance Python FastAPI application offering desktop-grade file management and text/code editing, optimized for multi-cloud deployment on **Render**, **Railway**, and **Fly.io**.

---

## ✨ Features

- **📂 Subdirectory & Nested Folder Navigation**: Create, navigate, and manage folder hierarchies with interactive breadcrumbs.
- **📝 In-Browser Code & Text Editor**: Edit `.py`, `.js`, `.css`, `.html`, `.json`, `.md`, `.txt`, `.toml`, and config files directly in the browser with live saving.
- **👁️ Multimedia Previewers**: Preview images (`.png`, `.jpg`, `.svg`, `.webp`), audio (`.mp3`, `.wav`), and video (`.mp4`, `.webm`) files.
- **📦 Dynamic ZIP Archive Generation**: Select multiple files or directories and compress them into a `.zip` download on the fly.
- **🗑️ Batch Operations**: Multi-select items for bulk download or batch deletion.
- **🔍 Search & Filtering**: Real-time filename search and category filters (Code, Images, Media, Documents, Archives).
- **🔲 Grid & List View Modes**: Toggle between compact row views and card grid views.
- **🔒 Path Traversal Security**: Built-in path validation preventing directory traversal attacks outside the storage root.
- **🚀 Multi-Cloud Deployment Ready**: Pre-configured for **Render** (`render.yaml`), **Railway** (`railway.json`), **Fly.io** (`fly.toml`), **Docker** (`Dockerfile`), and **Procfile**.

---

## 💻 Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Application
```bash
python main.py
```
Or with Uvicorn:
```bash
uvicorn main:app --reload --port 8000
```
Access the Web UI at `http://localhost:8000` or interactive API docs at `http://localhost:8000/docs`.

### 3. Run Test Suite
```bash
python test_app.py
```

---

## 🛠️ API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Web IDE & Advanced File Manager UI |
| `/healthz` | `GET` | Service health probe |
| `/api/info` | `GET` | System metrics & storage info |
| `/api/files` | `GET` | List files/folders (`?path=subfolder`) |
| `/api/folders` | `POST` | Create a new folder |
| `/api/files/create-text` | `POST` | Create a new text file |
| `/api/files/content` | `GET` | Get text file content for editor |
| `/api/files/content` | `PUT` | Save updated text file content |
| `/api/files/upload` | `POST` | Upload files (`?target_path=subfolder`) |
| `/api/files/rename` | `POST` | Rename file or folder |
| `/api/files/move` | `POST` | Move item to target directory |
| `/api/files/view/{path}` | `GET` | Stream raw media/document file |
| `/api/files/zip` | `POST` | Compress selected items to ZIP |
| `/api/files/batch-delete` | `POST` | Delete multiple selected items |
| `/api/files` | `DELETE` | Delete single item (`?path=item`) |

---

## ☁️ Deployment Guides

### 1. Render
Push your code to GitHub, open [Render Dashboard](https://dashboard.render.com), click **New Web Service**, select your repository, and Render will automatically detect `render.yaml`.

### 2. Railway
Deploy directly from your GitHub repository on [Railway](https://railway.app/). Railway will automatically read `railway.json` and `Dockerfile`.

### 3. Fly.io
Run `fly launch` followed by `fly deploy` in your project folder.
