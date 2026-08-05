import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = os.getenv("APP_NAME", "Advanced Cloud File Manager")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 50))

# Extension classifications
TEXT_EXTENSIONS = {
    "txt", "py", "js", "ts", "html", "css", "json", "md", "csv", "xml", 
    "yaml", "yml", "sh", "bat", "c", "cpp", "h", "java", "sql", "env", "ini", "dockerfile", "toml"
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mkv", "mov"}
ARCHIVE_EXTENSIONS = {"zip", "tar", "gz", "7z", "rar"}
