from pathlib import Path
import subprocess
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.version_service import version_service


def _git_available() -> bool:
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git is required")


def test_auto_init_and_snapshot(tmp_path: Path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("one", encoding="utf-8")
    snap = version_service.snapshot(tmp_path, "save", ["a.txt"])
    assert (tmp_path / ".git").exists()
    assert snap.operation_id


def test_file_history_and_restore(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("v1", encoding="utf-8")
    first = version_service.snapshot(tmp_path, "save", ["a.txt"])
    p.write_text("v2", encoding="utf-8")
    version_service.snapshot(tmp_path, "save", ["a.txt"])
    history = version_service.file_history(tmp_path, "a.txt", 10)
    assert len(history) >= 2
    version_service.restore_file(tmp_path, "a.txt", first.snapshot_id or history[-1]["commit"])
    assert p.read_text(encoding="utf-8") == "v1"


def test_undo(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("v1", encoding="utf-8")
    version_service.snapshot(tmp_path, "save", ["a.txt"])
    p.write_text("v2", encoding="utf-8")
    version_service.snapshot(tmp_path, "save", ["a.txt"])
    version_service.undo(tmp_path)
    assert p.read_text(encoding="utf-8") == "v1"
