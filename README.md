# 🐍 Cloud File Manager & API Service

A modern, high-performance Python FastAPI application designed for seamless multi-cloud deployment on **Render**, **Railway**, and **Fly.io**, featuring dynamic `$PORT` handling, health monitoring, REST API, and a dark glassmorphism dashboard UI.

---

## 🚀 Features

- **FastAPI + Uvicorn/Gunicorn**: Blazing fast Python web backend.
- **Glassmorphism Web Dashboard**: Responsive UI for drag-and-drop file upload, file management, and system metrics.
- **RESTful API**: File upload (`POST`), list (`GET`), download (`GET`), and delete (`DELETE`).
- **Health Check Probes**: Pre-configured `/healthz` and `/api/info` endpoints.
- **Multi-Cloud Deployment Ready**: Includes configuration files for **Render** (`render.yaml`), **Railway** (`railway.json`), **Fly.io** (`fly.toml`), **Docker** (`Dockerfile`), and **Procfile**.

---

## 💻 Local Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Application
```bash
python main.py
```
Or directly using Uvicorn:
```bash
uvicorn main:app --reload --port 8000
```
Open your browser at `http://localhost:8000` to access the Web UI dashboard, or `http://localhost:8000/docs` for interactive API documentation.

### 3. Run Automated Tests
```bash
python test_app.py
```

---

## 🐙 Push to GitHub as a New Repository

### Option A: Using GitHub CLI (`gh`)
1. Log in to your GitHub account:
   ```bash
   gh auth login
   ```
2. Create and push your new repository in one step:
   ```bash
   gh repo create cloud-file-manager --public --source=. --remote=origin --push
   ```

### Option B: Using Git & GitHub Website
1. Go to [GitHub New Repository](https://github.new) and create a repository named `cloud-file-manager`.
2. Link your local repository and push:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/cloud-file-manager.git
   git branch -M main
   git push -u origin main
   ```

---

## ☁️ Cloud Deployment Guides

### 1. Deploying on Render
1. Go to [Render Dashboard](https://dashboard.render.com/) -> **New** -> **Web Service**.
2. Connect your GitHub repository (`cloud-file-manager`).
3. Render automatically detects `render.yaml` or set:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/healthz`

---

### 2. Deploying on Railway
1. Go to [Railway Dashboard](https://railway.app/) -> **New Project** -> **Deploy from GitHub repo**.
2. Select your `cloud-file-manager` repository.
3. Railway will automatically pick up `railway.json` / `Dockerfile` and set `$PORT` dynamically.

---

### 3. Deploying on Fly.io
1. Install [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/).
2. Run `fly launch` in the project root:
   ```bash
   fly launch
   ```
3. Deploy the application:
   ```bash
   fly deploy
   ```

---

## 🛠️ API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves Web Dashboard UI |
| `/healthz` | `GET` | Cloud health check probe |
| `/api/info` | `GET` | System metrics & storage info |
| `/api/files` | `GET` | List all uploaded files |
| `/api/files/upload` | `POST` | Upload single or multiple files |
| `/api/files/{filename}` | `GET` | Download file |
| `/api/files/{filename}` | `DELETE` | Delete file |
| `/docs` | `GET` | Interactive Swagger API docs |

---

## 📁 Directory Structure

```
├── main.py              # FastAPI server entrypoint
├── config.py            # Dynamic settings & environment variables
├── requirements.txt     # Python dependencies
├── test_app.py          # Automated test suite
├── Dockerfile           # Multi-stage production container setup
├── Procfile             # Process manager file
├── render.yaml          # Render Blueprint deployment config
├── fly.toml             # Fly.io deployment config
├── railway.json         # Railway deployment config
├── .gitignore           # Git ignore rules
├── .dockerignore        # Docker ignore rules
├── templates/
│   └── index.html       # Glassmorphism HTML dashboard
├── static/
│   ├── css/style.css    # Modern UI styles
│   └── js/app.js        # Client-side API integration
└── uploads/             # Managed files directory
```
