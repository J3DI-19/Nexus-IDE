from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

from core.runtime_registry import RuntimeConfig, runtime_registry
from utils.security import get_project_root


@dataclass
class RuntimeJobItem:
    runtime: str
    status: str = "queued"
    progress: int = 0
    message: str = ""
    installed_version: Optional[str] = None
    target_version: Optional[str] = None


@dataclass
class RuntimeInstallJob:
    job_id: str
    status: str = "running"
    items: dict[str, RuntimeJobItem] | None = None
    error: Optional[str] = None


class RuntimeInstaller:
    # Windows-first v1 map. URLs/checksums are strict inputs for secure installs.
    # Replace checksum values as part of release process.
    ALLOWED_HOSTS = {
        "www.python.org",
        "nodejs.org",
        "download.oracle.com",
        "aka.ms",
        "github.com",
        "www.7-zip.org",
    }
    PORTABLE_7ZR_URL = "https://www.7-zip.org/a/7zr.exe"

    RUNTIME_EXECUTABLES = {
        "python": "python/python.exe",
        "node": "node/node.exe",
        "java": "java/bin/java.exe",
        "gcc": "gcc/bin/gcc.exe",
        "gpp": "gcc/bin/g++.exe",
        "dotnet": "dotnet/dotnet.exe",
        "bash": "bash/usr/bin/bash.exe",
        "powershell": "powershell/pwsh.exe",
    }

    def __init__(self):
        self.root = get_project_root()
        self.manifest_path = self.root / "backend" / "config" / "runtime_manifest.json"
        self.tools_dir = self.root / "backend" / "tools"
        self.jobs: dict[str, RuntimeInstallJob] = {}
        self._lock = threading.Lock()

    def _load_manifest(self) -> dict[str, Any]:
        # Accept UTF-8 files with or without BOM (PowerShell may emit BOM by default).
        data = json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or "runtimes" not in data:
            raise ValueError("Invalid runtime manifest format")
        return data

    def _runtime_status_label(self, key: str, pinned_version: str) -> str:
        status = runtime_registry.runtime_status().get(key, {})
        if status.get("bundled_installed"):
            return "installed"
        return "not_installed"

    def get_catalog(self) -> dict[str, Any]:
        manifest = self._load_manifest()
        runtimes = manifest.get("runtimes", {})
        out: list[dict[str, Any]] = []
        status_map = runtime_registry.runtime_status()
        for key, spec in runtimes.items():
            pinned = str(spec.get("version", ""))
            current = status_map.get(key, {})
            out.append({
                "key": key,
                "label": str(spec.get("label", key.title())),
                "version": pinned,
                "status": self._runtime_status_label(key, pinned),
                "resolved": current.get("resolved"),
                "source": current.get("source"),
                "bundled_installed": bool(current.get("bundled_installed")),
            })
        return {"runtimes": out}

    def get_preflight(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        missing_hosts: list[str] = []
        manifest_ok = True
        manifest_error: Optional[str] = None
        try:
            manifest = self._load_manifest()
            runtimes = manifest.get("runtimes", {})
            for key, spec in runtimes.items():
                url = str(((spec.get("windows") or {}).get("url")) or "")
                host = (urlparse(url).hostname or "").lower()
                if host and host not in self.ALLOWED_HOSTS:
                    missing_hosts.append(f"{key}:{host}")
        except Exception as exc:
            manifest_ok = False
            manifest_error = str(exc)

        checks["manifest"] = {"ok": manifest_ok, "message": "Manifest readable" if manifest_ok else f"Manifest error: {manifest_error}"}
        checks["allowlist"] = {
            "ok": len(missing_hosts) == 0,
            "message": "All manifest hosts are allowlisted" if len(missing_hosts) == 0 else f"Non-allowlisted hosts: {', '.join(missing_hosts)}",
        }
        checks["extractor"] = {
            "ok": bool(shutil.which("7z") or shutil.which("7zr") or shutil.which("7za") or shutil.which("tar")),
            "message": "Archive extractor found" if bool(shutil.which("7z") or shutil.which("7zr") or shutil.which("7za") or shutil.which("tar")) else "No system extractor found (portable 7zr bootstrap will be attempted)",
        }
        node_root = runtime_registry.bundle_root / "node"
        candidates = [node_root, node_root / "node-install"]
        has_node = any((c / "node.exe").exists() for c in candidates)
        tsx = any((c / "node_modules" / ".bin" / "tsx.cmd").exists() for c in candidates)
        ts_node = any((c / "node_modules" / ".bin" / "ts-node.cmd").exists() for c in candidates)
        ts_ok = True
        checks["typescript"] = {
            "ok": ts_ok,
            "message": "TypeScript runner is available" if (tsx or ts_node) else "TypeScript runner not found; IDE will run .ts with Node direct mode unless tsx/ts-node is installed.",
        }
        all_ok = checks["manifest"]["ok"] and checks["allowlist"]["ok"]
        return {"ok": all_ok, "checks": checks}

    def create_install_job(self, runtimes: list[str], reinstall: bool = False) -> str:
        manifest = self._load_manifest()
        available = set((manifest.get("runtimes") or {}).keys())
        selected = [r for r in runtimes if r in available]
        if not selected:
            selected = list(available)
        job_id = uuid.uuid4().hex
        items = {
            rt: RuntimeJobItem(runtime=rt, status="queued", target_version=str(manifest["runtimes"][rt].get("version", "")))
            for rt in selected
        }
        job = RuntimeInstallJob(job_id=job_id, status="running", items=items)
        with self._lock:
            self.jobs[job_id] = job

        thread = threading.Thread(target=self._run_install_job, args=(job_id, selected, reinstall), daemon=True)
        thread.start()
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.jobs.get(job_id)
        if not job:
            return {"error": "job_not_found"}
        return {
            "job_id": job.job_id,
            "status": job.status,
            "error": job.error,
            "items": {k: asdict(v) for k, v in (job.items or {}).items()},
        }

    def _run_install_job(self, job_id: str, runtimes: list[str], reinstall: bool):
        try:
            manifest = self._load_manifest()
            for runtime_key in runtimes:
                self._run_single_runtime(job_id, runtime_key, manifest["runtimes"][runtime_key], reinstall)
            with self._lock:
                job = self.jobs[job_id]
                failures = [i for i in (job.items or {}).values() if i.status == "failed"]
                job.status = "failed" if failures else "completed"
        except Exception as exc:
            with self._lock:
                job = self.jobs[job_id]
                job.status = "failed"
                job.error = str(exc)

    def _run_single_runtime(self, job_id: str, runtime_key: str, spec: dict[str, Any], reinstall: bool):
        self._update_item(job_id, runtime_key, status="installing", progress=5, message="Starting install")
        status_map = runtime_registry.runtime_status()
        if status_map.get(runtime_key, {}).get("bundled_installed") and not reinstall:
            self._update_item(job_id, runtime_key, status="installed", progress=100, message="Already installed")
            return

        package = (spec.get("windows") or {})
        url = str(package.get("url", ""))
        checksum = str(package.get("sha256", ""))
        if not url.startswith("https://"):
            raise ValueError(f"{runtime_key}: URL must use https")
        host = (urlparse(url).hostname or "").lower()
        if host not in self.ALLOWED_HOSTS:
            raise ValueError(f"{runtime_key}: host {host} is not allowlisted")
        if len(checksum) != 64:
            raise ValueError(f"{runtime_key}: sha256 checksum is required")

        bundle_root = runtime_registry.bundle_root
        runtime_target = bundle_root / runtime_key
        bundle_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=f"nexus-{runtime_key}-") as td:
            temp_dir = Path(td)
            archive_name = Path(urlparse(url).path).name or "runtime.bin"
            archive_path = temp_dir / archive_name
            self._update_item(job_id, runtime_key, progress=20, message="Downloading")
            self._download_to(url, archive_path)
            self._update_item(job_id, runtime_key, progress=45, message="Verifying checksum")
            self._verify_sha256(archive_path, checksum)
            extract_dir = temp_dir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            self._update_item(job_id, runtime_key, progress=65, message="Extracting")
            self._extract_archive(archive_path, extract_dir)
            installed_dir = self._pick_runtime_root(extract_dir)
            staging_target = bundle_root / f".staging-{runtime_key}"
            if staging_target.exists():
                shutil.rmtree(staging_target, ignore_errors=True)
            shutil.move(str(installed_dir), str(staging_target))
            if runtime_target.exists():
                shutil.rmtree(runtime_target, ignore_errors=True)
            shutil.move(str(staging_target), str(runtime_target))

        self._update_runtime_config(runtime_key)
        smoke_ok, smoke_message = self._run_smoke_test(runtime_key)
        if not smoke_ok:
            self._update_item(job_id, runtime_key, status="failed", progress=100, message=f"Installed, smoke test failed: {smoke_message}")
            return
        if runtime_key == "node":
            self._ensure_typescript_runner()
        self._update_item(job_id, runtime_key, status="installed", progress=100, message=f"Installed ({smoke_message})", installed_version=str(spec.get("version", "")))

    def _run_smoke_test(self, runtime_key: str) -> tuple[bool, str]:
        rel = self.RUNTIME_EXECUTABLES.get(runtime_key)
        if not rel:
            return True, "No smoke test defined"
        exe = runtime_registry.bundle_root / rel
        if not exe.exists():
            return False, "Executable missing after install"
        probes = {
            "python": [[str(exe), "--version"]],
            "node": [[str(exe), "--version"]],
            "java": [[str(exe), "-version"]],
            "gcc": [[str(exe), "--version"]],
            "gpp": [[str(exe), "--version"]],
            "dotnet": [[str(exe), "--info"]],
            "bash": [[str(exe), "--version"]],
            "powershell": [[str(exe), "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]],
        }
        for cmd in probes.get(runtime_key, [[str(exe), "--version"]]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
                if result.returncode == 0:
                    output = (result.stdout or result.stderr or "").strip().splitlines()
                    return True, (output[0] if output else "smoke test ok")[:120]
            except Exception as exc:
                return False, str(exc)
        return False, "command exited non-zero"

    def _ensure_typescript_runner(self):
        node_root = runtime_registry.bundle_root / "node"
        for node_dir in (node_root, node_root / "node-install"):
            node_exe = node_dir / "node.exe"
            if not node_exe.exists():
                continue
            tsx_cmd = node_dir / "node_modules" / ".bin" / "tsx.cmd"
            ts_node_cmd = node_dir / "node_modules" / ".bin" / "ts-node.cmd"
            if tsx_cmd.exists() or ts_node_cmd.exists():
                return
            npm_cmd = node_dir / "npm.cmd"
            if npm_cmd.exists():
                try:
                    subprocess.run(
                        [str(npm_cmd), "install", "--no-audit", "--no-fund", "--prefix", str(node_dir), "tsx", "ts-node", "typescript"],
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                    )
                except Exception:
                    pass
            npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if npm_cli.exists():
                try:
                    subprocess.run(
                        [str(node_exe), str(npm_cli), "install", "--no-audit", "--no-fund", "--prefix", str(node_dir), "tsx", "ts-node", "typescript"],
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                    )
                except Exception:
                    pass

    def _pick_runtime_root(self, extract_dir: Path) -> Path:
        entries = [p for p in extract_dir.iterdir()]
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return extract_dir

    def _extract_archive(self, archive_path: Path, extract_dir: Path):
        suffix = archive_path.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_dir)
            return

        # 7z/exe self-extracting archives: try common extractors first.
        # This keeps installs seamless for MinGW/w64devkit style payloads.
        for tool in ("7z", "7zr", "7za"):
            executable = shutil.which(tool)
            if not executable:
                continue
            result = subprocess.run(
                [executable, "x", "-y", f"-o{extract_dir}", str(archive_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return

        portable = self._ensure_portable_7zr()
        if portable:
            result = subprocess.run(
                [str(portable), "x", "-y", f"-o{extract_dir}", str(archive_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return

        # Fallback: bsdtar on Windows can unpack several formats.
        tar_bin = shutil.which("tar")
        if tar_bin:
            result = subprocess.run(
                [tar_bin, "-xf", str(archive_path), "-C", str(extract_dir)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return

        raise ValueError(
            f"Unsupported archive format for {archive_path.name}. "
            "Install 7-Zip (7z/7zr) or provide a .zip runtime package."
        )

    def _ensure_portable_7zr(self) -> Optional[Path]:
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        target = self.tools_dir / "7zr.exe"
        if target.exists():
            return target
        host = (urlparse(self.PORTABLE_7ZR_URL).hostname or "").lower()
        if host not in self.ALLOWED_HOSTS:
            return None
        try:
            self._download_to(self.PORTABLE_7ZR_URL, target)
            if target.exists() and target.stat().st_size > 0:
                return target
        except Exception:
            pass
        return None

    def _update_runtime_config(self, runtime_key: str):
        rel = self.RUNTIME_EXECUTABLES.get(runtime_key)
        if not rel:
            return
        path = runtime_registry.bundle_root / rel
        config = runtime_registry.load()
        if path.exists():
            setattr(config, runtime_key, str(path))
            runtime_registry.save(config)

    def _download_to(self, url: str, output: Path):
        with urlopen(url, timeout=120) as resp:
            data = resp.read()
        output.write_bytes(data)

    def _verify_sha256(self, path: Path, expected: str):
        digest = hashlib.sha256(path.read_bytes()).hexdigest().lower()
        if digest != expected.lower():
            raise ValueError(f"Checksum mismatch for {path.name}")

    def _update_item(self, job_id: str, runtime_key: str, **kwargs: Any):
        with self._lock:
            job = self.jobs[job_id]
            item = job.items[runtime_key]
            for k, v in kwargs.items():
                setattr(item, k, v)


runtime_installer = RuntimeInstaller()
