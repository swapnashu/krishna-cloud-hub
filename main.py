import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import config

app = FastAPI(
    title=config.APP_NAME,
    description="Advanced Cloud File Manager & Web IDE with multi-cloud support",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = config.BASE_DIR / "static"
templates_path = config.BASE_DIR / "templates"
static_path.mkdir(parents=True, exist_ok=True)
templates_path.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

START_TIME = time.time()


# Request Models
class CreateFolderRequest(BaseModel):
    folder_path: str = Field(..., description="Relative path for new folder")

class CreateFileRequest(BaseModel):
    file_path: str = Field(..., description="Relative path for new file")
    content: Optional[str] = ""

class SaveFileContentRequest(BaseModel):
    file_path: str = Field(..., description="Relative path of file to edit")
    content: str

class RenameItemRequest(BaseModel):
    old_path: str
    new_name: str

class MoveItemRequest(BaseModel):
    source_path: str
    target_folder: str

class BatchPathRequest(BaseModel):
    paths: List[str]


def get_safe_path(relative_path: str = "") -> Path:
    """Resolve and validate path to prevent directory traversal outside UPLOAD_DIR."""
    clean_rel = relative_path.lstrip("/\\")
    resolved = (config.UPLOAD_DIR / clean_rel).resolve()
    
    if not str(resolved).startswith(str(config.UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path: Directory traversal detected")
    return resolved


def format_bytes(size: int) -> str:
    """Format bytes into human readable string."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{round(size / 1024, 1)} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{round(size / (1024 * 1024), 2)} MB"
    else:
        return f"{round(size / (1024 * 1024 * 1024), 2)} GB"


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "app_name": config.APP_NAME})


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "service": config.APP_NAME,
        "environment_port": config.PORT
    }


@app.get("/api/info")
async def get_system_info():
    all_files = [p for p in config.UPLOAD_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    total_size = sum(f.stat().st_size for f in all_files)
    
    return {
        "app_name": config.APP_NAME,
        "status": "online",
        "total_files": len(all_files),
        "total_storage_bytes": total_size,
        "total_storage_formatted": format_bytes(total_size),
        "port": config.PORT,
        "uptime": f"{round(time.time() - START_TIME, 1)}s"
    }


@app.get("/api/files")
async def list_directory_contents(path: str = Query("", description="Relative path in uploads folder")):
    target_dir = get_safe_path(path)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    items = []
    for item in target_dir.iterdir():
        if item.name == ".gitkeep":
            continue
            
        rel_item_path = str(item.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
        ext = item.suffix.lstrip(".").lower() if item.is_file() else ""
        
        stat_info = item.stat()
        items.append({
            "name": item.name,
            "path": rel_item_path,
            "is_dir": item.is_dir(),
            "size_bytes": stat_info.st_size if item.is_file() else 0,
            "size_formatted": format_bytes(stat_info.st_size) if item.is_file() else "--",
            "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat_info.st_mtime)),
            "extension": ext,
            "is_text": ext in config.TEXT_EXTENSIONS,
            "is_image": ext in config.IMAGE_EXTENSIONS,
            "is_audio": ext in config.AUDIO_EXTENSIONS,
            "is_video": ext in config.VIDEO_EXTENSIONS,
            "is_archive": ext in config.ARCHIVE_EXTENSIONS
        })

    # Directories first, then files sorted alphabetically
    sorted_items = sorted(items, key=lambda x: (not x["is_dir"], x["name"].lower()))
    
    rel_current = str(target_dir.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
    if rel_current == ".":
        rel_current = ""

    return {
        "current_path": rel_current,
        "items": sorted_items
    }


@app.post("/api/folders")
async def create_folder(req: CreateFolderRequest):
    target_path = get_safe_path(req.folder_path)
    if target_path.exists():
        raise HTTPException(status_code=400, detail="Folder already exists")
    
    target_path.mkdir(parents=True, exist_ok=True)
    return {"message": "Folder created successfully", "path": req.folder_path}


@app.post("/api/files/create-text")
async def create_text_file(req: CreateFileRequest):
    target_path = get_safe_path(req.file_path)
    if target_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")
    
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(req.content or "", encoding="utf-8")
    return {"message": f"File '{target_path.name}' created successfully"}


@app.get("/api/files/content")
async def read_file_content(path: str = Query(..., description="Relative path of file")):
    target_path = get_safe_path(path)
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = target_path.suffix.lstrip(".").lower()
    if ext not in config.TEXT_EXTENSIONS and target_path.stat().st_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is not editable text or exceeds 5MB")
        
    try:
        content = target_path.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "filename": target_path.name, "content": content, "extension": ext}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@app.put("/api/files/content")
async def save_file_content(req: SaveFileContentRequest):
    target_path = get_safe_path(req.file_path)
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    target_path.write_text(req.content, encoding="utf-8")
    return {"message": f"Saved changes to '{target_path.name}'"}


@app.post("/api/files/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    target_path: Optional[str] = Query("", description="Target subfolder relative path")
):
    upload_dir = get_safe_path(target_path)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded = []
    for file in files:
        if not file.filename:
            continue
        safe_filename = os.path.basename(file.filename)
        dest = upload_dir / safe_filename
        
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        uploaded.append({"filename": safe_filename, "size": dest.stat().st_size})
        
    return {"message": f"Uploaded {len(uploaded)} file(s)", "files": uploaded}


@app.post("/api/files/rename")
async def rename_item(req: RenameItemRequest):
    source_path = get_safe_path(req.old_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Item not found")
        
    clean_new_name = os.path.basename(req.new_name.strip())
    if not clean_new_name:
        raise HTTPException(status_code=400, detail="Invalid new name")
        
    destination_path = source_path.parent / clean_new_name
    if destination_path.exists():
        raise HTTPException(status_code=400, detail="Target name already exists")
        
    source_path.rename(destination_path)
    return {"message": f"Renamed to '{clean_new_name}'"}


@app.post("/api/files/move")
async def move_item(req: MoveItemRequest):
    source_path = get_safe_path(req.source_path)
    target_dir = get_safe_path(req.target_folder)
    
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source item not found")
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Target directory not found")
        
    destination_path = target_dir / source_path.name
    if destination_path.exists():
        raise HTTPException(status_code=400, detail="An item with the same name exists in target folder")
        
    shutil.move(str(source_path), str(destination_path))
    return {"message": f"Moved '{source_path.name}' to target directory"}


@app.get("/api/files/view/{file_path:path}")
async def view_raw_file(file_path: str):
    target_path = get_safe_path(file_path)
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=target_path)


@app.post("/api/files/zip")
async def create_zip_archive(req: BatchPathRequest):
    if not req.paths:
        raise HTTPException(status_code=400, detail="No paths provided")
        
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip_path = Path(temp_zip.name)
    temp_zip.close()
    
    with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for rel_p in req.paths:
            full_p = get_safe_path(rel_p)
            if not full_p.exists():
                continue
            if full_p.is_file():
                zip_file.write(full_p, arcname=full_p.name)
            elif full_p.is_dir():
                for sub_item in full_p.rglob("*"):
                    arc_name = sub_item.relative_to(full_p.parent)
                    zip_file.write(sub_item, arcname=str(arc_name))
                    
    return FileResponse(
        path=temp_zip_path,
        filename=f"archive_{int(time.time())}.zip",
        media_type="application/zip"
    )


@app.post("/api/files/batch-delete")
async def batch_delete_items(req: BatchPathRequest):
    deleted_count = 0
    for rel_p in req.paths:
        full_p = get_safe_path(rel_p)
        if full_p.exists() and full_p.name != ".gitkeep":
            if full_p.is_dir():
                shutil.rmtree(full_p)
            else:
                full_p.unlink()
            deleted_count += 1
            
    return {"message": f"Successfully deleted {deleted_count} item(s)"}


@app.delete("/api/files")
async def delete_single_item(path: str = Query(...)):
    full_p = get_safe_path(path)
    if not full_p.exists():
        raise HTTPException(status_code=404, detail="Item not found")
        
    if full_p.is_dir():
        shutil.rmtree(full_p)
    else:
        full_p.unlink()
        
    return {"message": f"Successfully deleted '{full_p.name}'"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
