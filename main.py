import asyncio
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import List, Optional

import psutil
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import config

app = FastAPI(
    title=config.APP_NAME,
    description="Ultimate Web IDE & Cloud Suite v3.0",
    version="3.0.0"
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

class CopyItemRequest(BaseModel):
    source_path: str

class ExtractArchiveRequest(BaseModel):
    archive_path: str = Field(..., description="Relative path of archive to extract")

class BatchPathRequest(BaseModel):
    paths: List[str]

class ExecuteCommandRequest(BaseModel):
    command: str = Field(..., description="Shell command to execute")
    cwd: Optional[str] = Field("", description="Working directory relative to upload root")

class GitCommitRequest(BaseModel):
    message: str = Field(..., description="Commit message")

class SqlQueryRequest(BaseModel):
    db_path: str = Field(..., description="Relative path of sqlite database")
    query: str = Field(..., description="SQL Query to execute")


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
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": config.APP_NAME}
    )


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "version": "3.0.0",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "service": config.APP_NAME,
        "environment_port": config.PORT
    }


@app.get("/api/info")
async def get_system_info():
    all_files = [p for p in config.UPLOAD_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    upload_storage_bytes = sum(f.stat().st_size for f in all_files)
    
    # Disk Usage Metrics
    total_disk, used_disk, free_disk = shutil.disk_usage(config.UPLOAD_DIR)
    used_percent = round((used_disk / total_disk) * 100, 1)
    
    # CPU & RAM Metrics via psutil
    cpu_usage = psutil.cpu_percent(interval=0.1)
    virtual_mem = psutil.virtual_memory()
    
    return {
        "app_name": config.APP_NAME,
        "status": "online",
        "total_files": len(all_files),
        "upload_storage_bytes": upload_storage_bytes,
        "upload_storage_formatted": format_bytes(upload_storage_bytes),
        "disk": {
            "total_bytes": total_disk,
            "used_bytes": used_disk,
            "free_bytes": free_disk,
            "total_formatted": format_bytes(total_disk),
            "used_formatted": format_bytes(used_disk),
            "free_formatted": format_bytes(free_disk),
            "used_percent": used_percent
        },
        "system": {
            "cpu_percent": cpu_usage,
            "ram_total_formatted": format_bytes(virtual_mem.total),
            "ram_used_formatted": format_bytes(virtual_mem.used),
            "ram_percent": virtual_mem.percent
        },
        "port": config.PORT,
        "uptime": f"{round(time.time() - START_TIME, 1)}s"
    }


@app.get("/api/files")
async def list_directory_contents(
    path: str = Query("", description="Relative path in uploads folder"),
    sort_by: str = Query("name", description="Sort by: name, size, date"),
    sort_order: str = Query("asc", description="Sort order: asc, desc")
):
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
            "modified_timestamp": stat_info.st_mtime,
            "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat_info.st_mtime)),
            "extension": ext,
            "is_text": ext in config.TEXT_EXTENSIONS,
            "is_image": ext in config.IMAGE_EXTENSIONS,
            "is_audio": ext in config.AUDIO_EXTENSIONS,
            "is_video": ext in config.VIDEO_EXTENSIONS,
            "is_archive": ext in config.ARCHIVE_EXTENSIONS,
            "is_db": ext in config.DATABASE_EXTENSIONS
        })

    # Sort Logic
    reverse_flag = (sort_order.lower() == "desc")
    if sort_by == "size":
        items.sort(key=lambda x: x["size_bytes"], reverse=reverse_flag)
    elif sort_by == "date":
        items.sort(key=lambda x: x["modified_timestamp"], reverse=reverse_flag)
    else: # name
        items.sort(key=lambda x: x["name"].lower(), reverse=reverse_flag)

    # Directories stay grouped first
    sorted_items = sorted(items, key=lambda x: not x["is_dir"])
    
    rel_current = str(target_dir.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
    if rel_current == ".":
        rel_current = ""

    return {
        "current_path": rel_current,
        "items": sorted_items
    }


# 1-Click ZIP / Tar Extraction Endpoint
@app.post("/api/files/extract")
async def extract_archive(req: ExtractArchiveRequest):
    archive_file = get_safe_path(req.archive_path)
    if not archive_file.exists() or not archive_file.is_file():
        raise HTTPException(status_code=404, detail="Archive file not found")
        
    extract_target = archive_file.parent
    filename = archive_file.name.lower()
    
    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(archive_file, 'r') as zip_ref:
                zip_ref.extractall(extract_target)
        elif filename.endswith((".tar.gz", ".tgz", ".tar")):
            mode = "r:gz" if (filename.endswith(".tar.gz") or filename.endswith(".tgz")) else "r"
            with tarfile.open(archive_file, mode) as tar_ref:
                tar_ref.extractall(extract_target)
        else:
            raise HTTPException(status_code=400, detail="Unsupported archive format")
            
        return {"message": f"Successfully extracted '{archive_file.name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(e)}")


# Full-Text Grep Code Search Endpoint
@app.get("/api/search/grep")
async def grep_code_search(
    query: str = Query(..., description="Keyword or regex to search"),
    path: str = Query("", description="Relative path subfolder to search in")
):
    if not query.strip():
        return {"results": []}
        
    target_dir = get_safe_path(path)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Search directory not found")
        
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    
    for file_path in target_dir.rglob("*"):
        if not file_path.is_file() or file_path.name == ".gitkeep":
            continue
        ext = file_path.suffix.lstrip(".").lower()
        if ext not in config.TEXT_EXTENSIONS:
            continue
            
        rel_path = str(file_path.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for line_num, line_content in enumerate(f, 1):
                    if pattern.search(line_content):
                        results.append({
                            "path": rel_path,
                            "filename": file_path.name,
                            "line_num": line_num,
                            "line_content": line_content.strip()[:200]
                        })
                        if len(results) >= 200: # Limit max results
                            break
        except Exception:
            continue
            
    return {"query": query, "total_matches": len(results), "results": results}


# In-Browser Git Client Endpoints
@app.get("/api/git/status")
async def get_git_status():
    try:
        proc = await asyncio.create_subprocess_shell(
            "git status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(config.BASE_DIR)
        )
        stdout, stderr = await proc.communicate()
        return {
            "status_output": stdout.decode("utf-8", errors="replace"),
            "error": stderr.decode("utf-8", errors="replace")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/git/log")
async def get_git_log():
    try:
        proc = await asyncio.create_subprocess_shell(
            "git log -n 10 --pretty=format:'%h - %an, %ar : %s'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(config.BASE_DIR)
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode("utf-8", errors="replace").split("\n")
        return {"commits": [l for l in lines if l.strip()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# SQLite Database Browser Endpoints
@app.get("/api/db/tables")
async def get_db_tables(db_path: str = Query(..., description="Relative path of db file")):
    file_p = get_safe_path(db_path)
    if not file_p.exists() or not file_p.is_file():
        raise HTTPException(status_code=404, detail="Database file not found")
        
    try:
        conn = sqlite3.connect(str(file_p))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {"db_path": db_path, "tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQLite Error: {str(e)}")


@app.post("/api/db/query")
async def run_sql_query(req: SqlQueryRequest):
    file_p = get_safe_path(req.db_path)
    if not file_p.exists() or not file_p.is_file():
        raise HTTPException(status_code=404, detail="Database file not found")
        
    try:
        conn = sqlite3.connect(str(file_p))
        cursor = conn.cursor()
        cursor.execute(req.query)
        
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchmany(100) # Max 100 rows preview
            conn.close()
            return {"columns": columns, "rows": rows, "count": len(rows)}
        else:
            conn.commit()
            conn.close()
            return {"columns": ["Status"], "rows": [["Query executed successfully"]], "count": 1}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL Query Error: {str(e)}")


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


@app.post("/api/files/copy")
async def copy_item(req: CopyItemRequest):
    source_path = get_safe_path(req.source_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source item not found")
        
    parent_dir = source_path.parent
    base_name = source_path.stem
    ext = source_path.suffix
    
    if source_path.is_file():
        copy_name = f"{base_name}_copy{ext}"
        copy_path = parent_dir / copy_name
        counter = 1
        while copy_path.exists():
            copy_name = f"{base_name}_copy_{counter}{ext}"
            copy_path = parent_dir / copy_name
            counter += 1
            
        shutil.copy2(str(source_path), str(copy_path))
    else: # directory
        copy_name = f"{source_path.name}_copy"
        copy_path = parent_dir / copy_name
        counter = 1
        while copy_path.exists():
            copy_name = f"{source_path.name}_copy_{counter}"
            copy_path = parent_dir / copy_name
            counter += 1
            
        shutil.copytree(str(source_path), str(copy_path))
        
    return {"message": f"Created duplicate '{copy_name}'", "new_name": copy_name}


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


# Web Terminal Command Execution Endpoint
@app.post("/api/terminal/execute")
async def execute_terminal_command(req: ExecuteCommandRequest):
    cmd = req.command.strip()
    if not cmd:
        raise HTTPException(status_code=400, detail="Empty command")
        
    working_dir = get_safe_path(req.cwd or "")
    if not working_dir.exists() or not working_dir.is_dir():
        working_dir = config.UPLOAD_DIR

    start_time = time.time()
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir)
        )
        
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "command": cmd,
                "stdout": "",
                "stderr": "Execution timed out after 30 seconds.",
                "exit_code": -1,
                "duration_ms": 30000
            }

        duration_ms = round((time.time() - start_time) * 1000, 2)
        stdout_str = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr_str = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        
        if len(stdout_str) > 50000:
            stdout_str = stdout_str[:50000] + "\n... [Output truncated at 50KB]"
        if len(stderr_str) > 50000:
            stderr_str = stderr_str[:50000] + "\n... [Output truncated at 50KB]"

        return {
            "command": cmd,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": process.returncode,
            "duration_ms": duration_ms
        }
    except Exception as e:
        return {
            "command": cmd,
            "stdout": "",
            "stderr": f"System Error executing command: {str(e)}",
            "exit_code": 1,
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
