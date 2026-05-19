from pathlib import Path

import pytest

from core.runtime_installer import RuntimeInstaller
from core.runtime_registry import RuntimeConfig


def test_rejects_non_allowlisted_host(tmp_path: Path):
    installer = RuntimeInstaller()
    installer.manifest_path = tmp_path / "manifest.json"
    installer.manifest_path.write_text(
        '{"runtimes":{"python":{"label":"Python","version":"1","windows":{"url":"https://example.com/x.zip","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}}',
        encoding="utf-8",
    )

    job_id = installer.create_install_job(["python"], reinstall=True)
    # run synchronously by querying until settled in this lightweight test
    for _ in range(100):
      job = installer.get_job(job_id)
      if job.get("status") in {"failed", "completed"}:
          break
    assert job["status"] == "failed"
    assert "allowlisted" in (job.get("error") or "").lower()


def test_checksum_validation_fails(tmp_path: Path, monkeypatch):
    installer = RuntimeInstaller()
    installer.manifest_path = tmp_path / "manifest.json"
    installer.manifest_path.write_text(
        '{"runtimes":{"python":{"label":"Python","version":"1","windows":{"url":"https://www.python.org/ftp/python/3.12.4/python-3.12.4-embed-amd64.zip","sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}}}',
        encoding="utf-8",
    )

    # Avoid real network: inject download payload.
    def fake_download(_url: str, out: Path):
        out.write_bytes(b"fake-binary")

    monkeypatch.setattr(installer, "_download_to", fake_download)
    job_id = installer.create_install_job(["python"], reinstall=True)
    for _ in range(100):
      job = installer.get_job(job_id)
      if job.get("status") in {"failed", "completed"}:
          break
    assert job["status"] == "failed"
    assert "checksum mismatch" in (job.get("error") or "").lower()


def test_auto_writes_runtime_path_when_not_configured(tmp_path: Path, monkeypatch):
    installer = RuntimeInstaller()
    monkeypatch.setattr("core.runtime_installer.runtime_registry.bundle_root", tmp_path / "runtimes")
    monkeypatch.setattr("core.runtime_installer.runtime_registry.load", lambda: RuntimeConfig())
    saved = {}

    def fake_save(config: RuntimeConfig):
        saved["python"] = config.python

    monkeypatch.setattr("core.runtime_installer.runtime_registry.save", fake_save)
    monkeypatch.setattr(
        "core.runtime_installer.runtime_registry.runtime_status",
        lambda: {"python": {"source": "missing"}},
    )

    target = (tmp_path / "runtimes" / "python")
    target.mkdir(parents=True, exist_ok=True)
    exe = target / "python.exe"
    exe.write_bytes(b"x")
    installer._update_runtime_config("python")
    assert saved["python"].endswith("python/python.exe")
