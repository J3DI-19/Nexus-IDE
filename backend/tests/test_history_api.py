from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app  # noqa: E402
from utils.security import set_project_root  # noqa: E402


def _git_available() -> bool:
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git is required")


def test_history_endpoints_roundtrip(tmp_path: Path):
    set_project_root(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")

    client = TestClient(app)
    save = client.post("/file/save", json={"path": "a.txt", "content": "v1"})
    assert save.status_code == 200
    assert save.json().get("operation_id")

    h = client.get("/history/file", params={"path": "a.txt"})
    assert h.status_code == 200
    assert h.json().get("status") == "success"
    entries = h.json().get("entries", [])
    assert entries

    c = entries[0]["commit"]
    preview = client.post("/history/restore/preview", json={"commit_id": c, "path": "a.txt", "has_dirty_conflict": True})
    assert preview.status_code == 200
    assert preview.json().get("can_apply") is False


def test_undo_baseline_noop(tmp_path: Path):
    set_project_root(str(tmp_path))
    client = TestClient(app)
    resp = client.post("/history/undo")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert "snapshot_created" in body
    assert "undo_mode" in body
    assert "undo_target" in body


def test_restore_preview_invalid_commit_reports_conflict(tmp_path: Path):
    set_project_root(str(tmp_path))
    client = TestClient(app)
    preview = client.post("/history/restore/preview", json={"commit_id": "deadbeef", "path": "a.txt", "scope": "file"})
    assert preview.status_code == 200
    data = preview.json()
    assert data["status"] == "success"
    reasons = [c.get("reason") for c in data.get("conflicts", [])]
    assert "commit_not_found" in reasons


def test_file_save_contract_fields(tmp_path: Path):
    set_project_root(str(tmp_path))
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    client = TestClient(app)
    resp = client.post("/file/save", json={"path": "a.txt", "content": "hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "request_id" in data
    assert "operation_id" in data
    assert "snapshot_created" in data
