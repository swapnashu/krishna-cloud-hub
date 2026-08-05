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


def test_system_info():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "total_files" in data
    assert "total_storage_mb" in data


def test_file_upload_list_download_delete():
    # 1. Upload a test file
    test_filename = "test_sample.txt"
    file_content = b"Hello from FastAPI Cloud Test!"
    
    response = client.post(
        "/api/files/upload",
        files={"files": (test_filename, file_content, "text/plain")}
    )
    assert response.status_code == 200
    upload_data = response.json()
    assert len(upload_data["files"]) == 1
    assert upload_data["files"][0]["filename"] == test_filename

    # 2. List files and check test file is present
    response = client.get("/api/files")
    assert response.status_code == 200
    files_list = response.json()["files"]
    assert any(f["name"] == test_filename for f in files_list)

    # 3. Download test file
    response = client.get(f"/api/files/{test_filename}")
    assert response.status_code == 200
    assert response.content == file_content

    # 4. Delete test file
    response = client.delete(f"/api/files/{test_filename}")
    assert response.status_code == 200

    # 5. Verify deletion
    response = client.get(f"/api/files/{test_filename}")
    assert response.status_code == 404


if __name__ == "__main__":
    test_healthz()
    test_system_info()
    test_file_upload_list_download_delete()
    print("All automated tests passed successfully!")
