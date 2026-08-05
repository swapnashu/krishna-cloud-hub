import os
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
    assert data["version"] == "2.1.0"


def test_system_info_with_disk_metrics():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "disk" in data
    assert "total_bytes" in data["disk"]
    assert "free_bytes" in data["disk"]
    assert "used_percent" in data["disk"]


def test_directory_traversal_prevention():
    response = client.get("/api/files?path=../../")
    assert response.status_code == 400
    assert "Directory traversal" in response.json()["detail"]


def test_copy_duplicate_file():
    # 1. Create original file
    original_path = "original_doc.py"
    client.post("/api/files/create-text", json={"file_path": original_path, "content": "print('Original')" if True else ""})
    
    # 2. Duplicate file
    response = client.post("/api/files/copy", json={"source_path": original_path})
    assert response.status_code == 200
    new_name = response.json()["new_name"]
    assert "original_doc_copy" in new_name
    
    # 3. Clean up created files
    client.delete(f"/api/files?path={original_path}")
    client.delete(f"/api/files?path={new_name}")


if __name__ == "__main__":
    test_healthz()
    test_system_info_with_disk_metrics()
    test_directory_traversal_prevention()
    test_copy_duplicate_file()
    print("All v2.1 automated tests passed successfully!")
