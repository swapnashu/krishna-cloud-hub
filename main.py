import os
import shutil
import time
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config

app = FastAPI(
    title=config.APP_NAME,
    description="A high-performance Python web application deployable on Render, Railway, and Fly.io",
    version="1.0.0"
)

# Enable CORS for cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup directories
static_path = config.BASE_DIR / "static"
templates_path = config.BASE_DIR / "templates"
static_path.mkdir(parents=True, exist_ok=True)
templates_path.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

START_TIME = time.time()


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve web dashboard UI."""
    return templates.TemplateResponse("index.html", {"request": request, "app_name": config.APP_NAME})


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint for Render, Railway, and Fly.io health probes."""
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "service": config.APP_NAME,
        "environment_port": config.PORT
    }


@app.get("/api/info")
async def get_system_info():
    """Returns platform runtime stats and storage metrics."""
    files = list(config.UPLOAD_DIR.glob("*"))
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    
    return {
        "app_name": config.APP_NAME,
        "status": "online",
        "total_files": len([f for f in files if f.is_file()]),
        "total_storage_bytes": total_size,
        "total_storage_mb": round(total_size / (1024 * 1024), 2),
        "port": config.PORT,
        "uptime": f"{round(time.time() - START_TIME, 1)}s"
    }


@app.get("/api/files")
async def list_files():
    """List all stored files with details."""
    file_list = []
    for f in config.UPLOAD_DIR.iterdir():
        if f.is_file():
            stat_info = f.stat()
            file_list.append({
                "name": f.name,
                "size_bytes": stat_info.st_size,
                "size_kb": round(stat_info.st_size / 1024, 2),
                "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat_info.st_mtime))
            })
    return {"files": sorted(file_list, key=lambda x: x["name"])}


@app.post("/api/files/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload one or multiple files."""
    uploaded = []
    for file in files:
        if not file.filename:
            continue
        
        # Sanitize filename
        safe_filename = os.path.basename(file.filename)
        destination = config.UPLOAD_DIR / safe_filename
        
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        uploaded.append({
            "filename": safe_filename,
            "size": destination.stat().st_size
        })
        
    return {"message": f"Successfully uploaded {len(uploaded)} file(s)", "files": uploaded}


@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """Download a file by filename."""
    file_path = config.UPLOAD_DIR / os.path.basename(filename)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """Delete a file by filename."""
    file_path = config.UPLOAD_DIR / os.path.basename(filename)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path.unlink()
    return {"message": f"File '{filename}' deleted successfully"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
