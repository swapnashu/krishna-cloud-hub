import asyncio
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path
from typing import List, Optional

import httpx
import psutil
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
    description="Ultimate Web IDE & Cloud Suite v3.3 - Telegram Unlimited Storage Enabled",
    version="3.3.0"
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
TELEGRAM_INDEX_FILE = config.UPLOAD_DIR / "telegram_index.json"


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

class TelegramConfigRequest(BaseModel):
    bot_token: str = Field(..., description="Telegram Bot Token from @BotFather")
    chat_id: Optional[str] = Field("", description="Telegram Channel / Group / User Chat ID")

class SqlQueryRequest(BaseModel):
    db_path: str = Field(..., description="Relative path of sqlite database")
    query: str = Field(..., description="SQL Query to execute")


# Helper Functions
def get_safe_path(relative_path: str = "") -> Path:
    clean_rel = relative_path.lstrip("/\\")
    resolved = (config.UPLOAD_DIR / clean_rel).resolve()
    if not str(resolved).startswith(str(config.UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path: Directory traversal detected")
    return resolved


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{round(size / 1024, 1)} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{round(size / (1024 * 1024), 2)} MB"
    else:
        return f"{round(size / (1024 * 1024 * 1024), 2)} GB"


def load_telegram_index() -> dict:
    if TELEGRAM_INDEX_FILE.exists():
        try:
            return json.loads(TELEGRAM_INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_telegram_index(data: dict):
    try:
        TELEGRAM_INDEX_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# Telegram API Helpers
async def upload_file_to_telegram(file_bytes: bytes, filename: str) -> Optional[dict]:
    token = config.TELEGRAM_BOT_TOKEN.strip()
    chat_id = config.TELEGRAM_CHAT_ID.strip()
    if not token:
        return None
        
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    
    # If chat_id is empty, send to bot's own chat or getUpdates
    target_chat = chat_id if chat_id else None
    if not target_chat:
        # Try getting bot's own user ID or chat
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                if r.status_code == 200:
                    target_chat = str(r.json()["result"]["id"])
        except Exception:
            pass

    if not target_chat:
        target_chat = "@me"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"document": (filename, file_bytes)}
            data = {"chat_id": target_chat, "caption": f"☁️ Cloud IDE Upload: {filename}"}
            resp = await client.post(url, data=data, files=files)
            
            if resp.status_code == 200:
                result = resp.json().get("result", {})
                doc = result.get("document", {})
                return {
                    "file_id": doc.get("file_id"),
                    "file_unique_id": doc.get("file_unique_id"),
                    "file_name": doc.get("file_name", filename),
                    "file_size": doc.get("file_size", len(file_bytes)),
                    "message_id": result.get("message_id")
                }
    except Exception as e:
        print(f"Telegram upload error: {e}")
    return None


async def download_file_from_telegram(file_id: str) -> Optional[bytes]:
    token = config.TELEGRAM_BOT_TOKEN.strip()
    if not token or not file_id:
        return None
        
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Get file path
            r = await client.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}")
            if r.status_code != 200:
                return None
                
            tg_file_path = r.json()["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{token}/{tg_file_path}"
            
            # 2. Download raw content
            r_down = await client.get(download_url)
            if r_down.status_code == 200:
                return r_down.content
    except Exception as e:
        print(f"Telegram download error: {e}")
    return None


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
        "version": "3.3.0",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "service": config.APP_NAME,
        "telegram_connected": bool(config.TELEGRAM_BOT_TOKEN)
    }


@app.get("/api/info")
async def get_system_info():
    all_files = [p for p in config.UPLOAD_DIR.rglob("*") if p.is_file() and p.name not in [".gitkeep", "telegram_index.json"]]
    upload_storage_bytes = sum(f.stat().st_size for f in all_files)
    
    # Include Telegram Index count
    tg_index = load_telegram_index()
    tg_file_count = len(tg_index)

    # Disk Usage Metrics
    total_disk, used_disk, free_disk = shutil.disk_usage(config.UPLOAD_DIR)
    used_percent = round((used_disk / total_disk) * 100, 1)
    
    # CPU & RAM Metrics via psutil
    cpu_usage = psutil.cpu_percent(interval=0.1)
    virtual_mem = psutil.virtual_memory()
    
    return {
        "app_name": config.APP_NAME,
        "status": "online",
        "total_files": len(all_files) + tg_file_count,
        "upload_storage_bytes": upload_storage_bytes,
        "upload_storage_formatted": format_bytes(upload_storage_bytes),
        "telegram_cloud": {
            "connected": bool(config.TELEGRAM_BOT_TOKEN),
            "files_stored": tg_file_count,
            "bot_configured": "Yes" if config.TELEGRAM_BOT_TOKEN else "No"
        },
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


# Telegram Cloud Config Endpoints
@app.get("/api/telegram/status")
async def get_telegram_status():
    token = config.TELEGRAM_BOT_TOKEN.strip()
    if not token:
        return {"connected": False, "bot_name": "", "message": "No Telegram Bot Token configured"}
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if res.status_code == 200:
                bot_info = res.json()["result"]
                return {
                    "connected": True,
                    "bot_name": bot_info.get("first_name", ""),
                    "username": f"@{bot_info.get('username', '')}",
                    "chat_id": config.TELEGRAM_CHAT_ID
                }
    except Exception as e:
        return {"connected": False, "message": f"Connection error: {str(e)}"}
        
    return {"connected": False, "message": "Invalid Bot Token"}


@app.post("/api/telegram/config")
async def save_telegram_config(req: TelegramConfigRequest):
    config.TELEGRAM_BOT_TOKEN = req.bot_token.strip()
    config.TELEGRAM_CHAT_ID = req.chat_id.strip()
    
    # Save to .env file for persistence across server restarts
    env_file = config.BASE_DIR / ".env"
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
        
    new_lines = []
    has_token = False
    has_chat = False
    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={config.TELEGRAM_BOT_TOKEN}")
            has_token = True
        elif line.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={config.TELEGRAM_CHAT_ID}")
            has_chat = True
        else:
            new_lines.append(line)
            
    if not has_token:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={config.TELEGRAM_BOT_TOKEN}")
    if not has_chat:
        new_lines.append(f"TELEGRAM_CHAT_ID={config.TELEGRAM_CHAT_ID}")
        
    env_file.write_text("\n".join(new_lines), encoding="utf-8")
    
    # Validate connection
    status_info = await get_telegram_status()
    if status_info.get("connected"):
        return {"message": f"Connected to Telegram Bot: {status_info.get('username')}", "status": status_info}
    else:
        return {"message": "Credentials saved, but bot connection failed.", "status": status_info}


@app.get("/api/files")
async def list_directory_contents(
    path: str = Query("", description="Relative path in uploads folder"),
    sort_by: str = Query("name", description="Sort by: name, size, date"),
    sort_order: str = Query("asc", description="Sort order: asc, desc")
):
    target_dir = get_safe_path(path)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    tg_index = load_telegram_index()
    items = []
    seen_names = set()
    
    for item in target_dir.iterdir():
        if item.name in [".gitkeep", "telegram_index.json"]:
            continue
            
        rel_item_path = str(item.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
        seen_names.add(rel_item_path)
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
            "is_db": ext in config.DATABASE_EXTENSIONS,
            "in_telegram": rel_item_path in tg_index
        })

    # Include Telegram Cloud files that may have been wiped locally on server restart
    rel_current = str(target_dir.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
    if rel_current == ".":
        rel_current = ""

    for tg_path, meta in tg_index.items():
        # Check if file belongs to current subdirectory
        parent_path = str(Path(tg_path).parent).replace("\\", "/")
        if parent_path == ".":
            parent_path = ""
            
        if parent_path == rel_current and tg_path not in seen_names:
            filename = Path(tg_path).name
            ext = Path(tg_path).suffix.lstrip(".").lower()
            items.append({
                "name": filename,
                "path": tg_path,
                "is_dir": False,
                "size_bytes": meta.get("size_bytes", 0),
                "size_formatted": format_bytes(meta.get("size_bytes", 0)),
                "modified_timestamp": meta.get("timestamp", time.time()),
                "modified": meta.get("date", "Telegram Cloud"),
                "extension": ext,
                "is_text": ext in config.TEXT_EXTENSIONS,
                "is_image": ext in config.IMAGE_EXTENSIONS,
                "is_audio": ext in config.AUDIO_EXTENSIONS,
                "is_video": ext in config.VIDEO_EXTENSIONS,
                "is_archive": ext in config.ARCHIVE_EXTENSIONS,
                "is_db": ext in config.DATABASE_EXTENSIONS,
                "in_telegram": True
            })

    # Sort Logic
    reverse_flag = (sort_order.lower() == "desc")
    if sort_by == "size":
        items.sort(key=lambda x: x["size_bytes"], reverse=reverse_flag)
    elif sort_by == "date":
        items.sort(key=lambda x: x["modified_timestamp"], reverse=reverse_flag)
    else: # name
        items.sort(key=lambda x: x["name"].lower(), reverse=reverse_flag)

    sorted_items = sorted(items, key=lambda x: not x["is_dir"])

    return {
        "current_path": rel_current,
        "items": sorted_items
    }


@app.post("/api/files/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    target_path: Optional[str] = Query("", description="Target subfolder relative path")
):
    upload_dir = get_safe_path(target_path)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    tg_index = load_telegram_index()
    uploaded = []
    
    for file in files:
        if not file.filename:
            continue
        safe_filename = os.path.basename(file.filename)
        dest = upload_dir / safe_filename
        
        file_bytes = await file.read()
        dest.write_bytes(file_bytes)
        
        rel_path = str(dest.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
        
        # Upload to Telegram Cloud for 100% permanent storage if Bot Token is set
        tg_res = await upload_file_to_telegram(file_bytes, safe_filename)
        if tg_res:
            tg_index[rel_path] = {
                "file_id": tg_res["file_id"],
                "size_bytes": len(file_bytes),
                "timestamp": time.time(),
                "date": time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        uploaded.append({"filename": safe_filename, "size": len(file_bytes), "in_telegram": bool(tg_res)})

    save_telegram_index(tg_index)
    return {"message": f"Uploaded {len(uploaded)} file(s) safely", "files": uploaded}


@app.get("/api/files/view/{file_path:path}")
async def view_raw_file(file_path: str):
    target_path = get_safe_path(file_path)
    
    # 1. If local file exists, serve it
    if target_path.exists() and target_path.is_file():
        return FileResponse(path=target_path)
        
    # 2. Fallback to Telegram Cloud if wiped locally from server sleep
    tg_index = load_telegram_index()
    if file_path in tg_index:
        file_id = tg_index[file_path]["file_id"]
        file_bytes = await download_file_from_telegram(file_id)
        if file_bytes:
            # Restore local file cache
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(file_bytes)
            return FileResponse(path=target_path)
            
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/files/content")
async def read_file_content(path: str = Query(..., description="Relative path of file")):
    target_path = get_safe_path(path)
    
    # Restore from Telegram Cloud if missing locally
    if not target_path.exists():
        tg_index = load_telegram_index()
        if path in tg_index:
            file_bytes = await download_file_from_telegram(tg_index[path]["file_id"])
            if file_bytes:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(file_bytes)

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
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(req.content, encoding="utf-8")
    
    # Sync update to Telegram Cloud
    rel_path = str(target_path.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
    file_bytes = req.content.encode("utf-8")
    tg_res = await upload_file_to_telegram(file_bytes, target_path.name)
    if tg_res:
        tg_index = load_telegram_index()
        tg_index[rel_path] = {
            "file_id": tg_res["file_id"],
            "size_bytes": len(file_bytes),
            "timestamp": time.time(),
            "date": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_telegram_index(tg_index)
        
    return {"message": f"Saved changes to '{target_path.name}'"}


# 1-Click ZIP / Tar Extraction Endpoint
@app.post("/api/files/extract")
async def extract_archive(req: ExtractArchiveRequest):
    archive_file = get_safe_path(req.archive_path)
    
    if not archive_file.exists():
        tg_index = load_telegram_index()
        if req.archive_path in tg_index:
            file_bytes = await download_file_from_telegram(tg_index[req.archive_path]["file_id"])
            if file_bytes:
                archive_file.parent.mkdir(parents=True, exist_ok=True)
                archive_file.write_bytes(file_bytes)

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
        if not file_path.is_file() or file_path.name in [".gitkeep", "telegram_index.json"]:
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
                        if len(results) >= 200:
                            break
        except Exception:
            continue
            
    return {"query": query, "total_matches": len(results), "results": results}


# Git Client Endpoints
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


# SQLite DB Browser Endpoints
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
            rows = cursor.fetchmany(100)
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
    
    # Sync creation to Telegram Cloud if Bot Token is set
    rel_path = str(target_path.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
    file_bytes = (req.content or "").encode("utf-8")
    tg_res = await upload_file_to_telegram(file_bytes, target_path.name)
    if tg_res:
        tg_index = load_telegram_index()
        tg_index[rel_path] = {
            "file_id": tg_res["file_id"],
            "size_bytes": len(file_bytes),
            "timestamp": time.time(),
            "date": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_telegram_index(tg_index)
        
    return {"message": f"File '{target_path.name}' created successfully"}


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
    
    # Update Telegram Index if applicable
    tg_index = load_telegram_index()
    if req.old_path in tg_index:
        new_rel_path = str(destination_path.relative_to(config.UPLOAD_DIR)).replace("\\", "/")
        tg_index[new_rel_path] = tg_index.pop(req.old_path)
        save_telegram_index(tg_index)
        
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
    else:
        copy_name = f"{source_path.name}_copy"
        copy_path = parent_dir / copy_name
        counter = 1
        while copy_path.exists():
            copy_name = f"{source_path.name}_copy_{counter}"
            copy_path = parent_dir / copy_name
            counter += 1
            
        shutil.copytree(str(source_path), str(copy_path))
        
    return {"message": f"Created duplicate '{copy_name}'", "new_name": copy_name}


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
                # Attempt download from Telegram Cloud
                tg_index = load_telegram_index()
                if rel_p in tg_index:
                    f_bytes = await download_file_from_telegram(tg_index[rel_p]["file_id"])
                    if f_bytes:
                        full_p.parent.mkdir(parents=True, exist_ok=True)
                        full_p.write_bytes(f_bytes)

            if full_p.exists():
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
    tg_index = load_telegram_index()
    
    for rel_p in req.paths:
        full_p = get_safe_path(rel_p)
        if full_p.exists() and full_p.name not in [".gitkeep", "telegram_index.json"]:
            if full_p.is_dir():
                shutil.rmtree(full_p)
            else:
                full_p.unlink()
            deleted_count += 1
            
        if rel_p in tg_index:
            tg_index.pop(rel_p)
            deleted_count += 1

    save_telegram_index(tg_index)
    return {"message": f"Successfully deleted {deleted_count} item(s)"}


@app.delete("/api/files")
async def delete_single_item(path: str = Query(...)):
    full_p = get_safe_path(path)
    tg_index = load_telegram_index()
    
    if full_p.exists() and full_p.name not in [".gitkeep", "telegram_index.json"]:
        if full_p.is_dir():
            shutil.rmtree(full_p)
        else:
            full_p.unlink()

    if path in tg_index:
        tg_index.pop(path)
        save_telegram_index(tg_index)
        
    return {"message": f"Successfully deleted '{path.split('/')[-1]}'"}


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
