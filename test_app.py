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
    assert data["version"] == "2.2.0"


def test_system_info_with_disk_metrics():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "disk" in data
    assert "total_bytes" in data["disk"]
    assert "free_bytes" in data["disk"]


def test_terminal_command_execution():
    # Test simple command execution
    response = client.post("/api/terminal/execute", json={"command": "python --version"})
    assert response.status_code == 200
    data = response.json()
    assert data["exit_code"] == 0
    assert "Python" in data["stdout"] or "Python" in data["stderr"]

    # Test executing a Python script
    script_name = "test_script.py"
    client.post("/api/files/create-text", json={"file_path": script_name, "content": "print('Terminal Execution Working!')"})
    
    response = client.post("/api/terminal/execute", json={"command": f"python {script_name}"})
    assert response.status_code == 200
    exec_data = response.json()
    assert exec_data["exit_code"] == 0
    assert "Terminal Execution Working!" in exec_data["stdout"]

    # Clean up script
    client.delete(f"/api/files?path={script_name}")


if __name__ == "__main__":
    test_healthz()
    test_system_info_with_disk_metrics()
    test_terminal_command_execution()
    print("All v2.2 automated tests passed successfully!")
