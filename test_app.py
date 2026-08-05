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
    assert data["version"] == "2.0.0"


def test_system_info():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "total_files" in data
    assert "total_storage_formatted" in data


def test_directory_traversal_prevention():
    response = client.get("/api/files?path=../../")
    assert response.status_code == 400
    assert "Directory traversal" in response.json()["detail"]


def test_advanced_file_operations():
    # 1. Create a subfolder
    subfolder_name = "test_subfolder"
    response = client.post("/api/folders", json={"folder_path": subfolder_name})
    assert response.status_code == 200

    # 2. Create a text file inside subfolder
    file_path = f"{subfolder_name}/hello.py"
    initial_code = "print('Hello Cloud!')"
    response = client.post("/api/files/create-text", json={"file_path": file_path, "content": initial_code})
    assert response.status_code == 200

    # 3. Read file content
    response = client.get(f"/api/files/content?path={file_path}")
    assert response.status_code == 200
    assert response.json()["content"] == initial_code

    # 4. Save edited content
    updated_code = "print('Hello Advanced Cloud File Manager!')"
    response = client.put("/api/files/content", json={"file_path": file_path, "content": updated_code})
    assert response.status_code == 200

    # 5. List directory items
    response = client.get(f"/api/files?path={subfolder_name}")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "hello.py"

    # 6. Rename file
    response = client.post("/api/files/rename", json={"old_path": file_path, "new_name": "app.py"})
    assert response.status_code == 200

    # 7. Compress folder to ZIP
    renamed_file_path = f"{subfolder_name}/app.py"
    response = client.post("/api/files/zip", json={"paths": [renamed_file_path]})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # 8. Batch delete subfolder
    response = client.post("/api/files/batch-delete", json={"paths": [subfolder_name]})
    assert response.status_code == 200


if __name__ == "__main__":
    test_healthz()
    test_system_info()
    test_directory_traversal_prevention()
    test_advanced_file_operations()
    print("All advanced automated tests passed successfully!")
