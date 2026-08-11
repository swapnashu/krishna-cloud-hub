import os
import sqlite3
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient

import config
from main import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "3.3.0"


def test_system_info_with_cpu_ram():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "disk" in data
    assert "system" in data
    assert "cpu_percent" in data["system"]
    assert "ram_percent" in data["system"]


def test_grep_code_search():
    # Create test code file
    test_file = "sample_grep.py"
    client.post("/api/files/create-text", json={"file_path": test_file, "content": "def calculate_total_sales():\n    return 42"})
    
    response = client.get(f"/api/search/grep?query=calculate_total_sales")
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] >= 1
    assert any(r["filename"] == test_file for r in data["results"])
    
    # Cleanup
    client.delete(f"/api/files?path={test_file}")


def test_archive_extraction():
    # 1. Create a zip archive containing a file
    zip_path = config.UPLOAD_DIR / "sample_test.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("unzipped_demo.txt", "Extracted content working!")
        
    # 2. Extract archive via API
    response = client.post("/api/files/extract", json={"archive_path": "sample_test.zip"})
    assert response.status_code == 200
    
    # 3. Check extracted file exists
    extracted_file = config.UPLOAD_DIR / "unzipped_demo.txt"
    assert extracted_file.exists()
    assert extracted_file.read_text() == "Extracted content working!"
    
    # Cleanup
    zip_path.unlink(missing_ok=True)
    extracted_file.unlink(missing_ok=True)


def test_sqlite_db_browser():
    # 1. Create a test SQLite database
    db_file = config.UPLOAD_DIR / "test_demo.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob');")
    conn.commit()
    conn.close()
    
    # 2. Fetch tables via API
    response = client.get("/api/db/tables?db_path=test_demo.db")
    assert response.status_code == 200
    assert "users" in response.json()["tables"]
    
    # 3. Execute SQL Query
    response = client.post("/api/db/query", json={"db_path": "test_demo.db", "query": "SELECT * FROM users;"})
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert len(data["rows"]) == 2
    
    # Cleanup
    db_file.unlink(missing_ok=True)


if __name__ == "__main__":
    test_healthz()
    test_system_info_with_cpu_ram()
    test_grep_code_search()
    test_archive_extraction()
    test_sqlite_db_browser()
    print("All v3.0 Ultimate IDE automated tests passed successfully!")
