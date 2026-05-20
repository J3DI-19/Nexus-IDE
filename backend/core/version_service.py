from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class SnapshotResult:
    operation_id: str
    snapshot_id: str | None
    snapshot_created: bool


class VersionService:
    def __init__(self) -> None:
        self._meta_dir_name = ".nexus"
        self._operations_path = "history_operations.jsonl"

    def ensure_local_repo(self, root: Path) -> None:
        if (root / ".git").exists():
            self._ensure_git_exclude(root)
            return
        self._run_git(root, ["init"])
        self._run_git(root, ["config", "user.name", "Nexus IDE"])
        self._run_git(root, ["config", "user.email", "nexus@local"])
        self._ensure_git_exclude(root)
        self._run_git(root, ["add", "-A"])
        self._run_git(root, ["commit", "--allow-empty", "-m", "nexus: baseline"])

    def snapshot(
        self,
        root: Path,
        action: str,
        paths: Iterable[str],
        actor: str = "user",
        result: str = "success",
        metadata: dict | None = None,
    ) -> SnapshotResult:
        self.ensure_local_repo(root)
        op_id = str(uuid.uuid4())
        changed = self._has_changes(root)
        commit_id = None
        if changed:
            self._run_git(root, ["add", "-A"])
            message = f"nexus:{action}:{op_id}"
            self._run_git(root, ["commit", "-m", message])
            commit_id = self._head(root)
        self._append_operation(root, op_id, commit_id, action, list(paths), actor, result=result, metadata=metadata)
        return SnapshotResult(operation_id=op_id, snapshot_id=commit_id, snapshot_created=bool(commit_id))

    def file_history(self, root: Path, rel_path: str, limit: int = 30) -> list[dict]:
        self.ensure_local_repo(root)
        output = self._run_git(root, ["log", f"-n{max(1, limit)}", "--pretty=format:%H|%ct|%s", "--", rel_path], capture=True)
        return self._parse_log(output, rel_path=rel_path)

    def project_history(self, root: Path, limit: int = 50) -> list[dict]:
        self.ensure_local_repo(root)
        output = self._run_git(root, ["log", f"-n{max(1, limit)}", "--pretty=format:%H|%ct|%s"], capture=True)
        return self._parse_log(output)

    def commit_details(self, root: Path, commit_id: str) -> dict:
        self.ensure_local_repo(root)
        meta = self._run_git(root, ["show", "-s", "--pretty=format:%H|%ct|%s", commit_id], capture=True).strip()
        diff = self._run_git(root, ["show", "--name-status", "--pretty=", commit_id], capture=True).strip()
        return {"commit": self._parse_log(meta)[0] if meta else None, "changes": diff.splitlines() if diff else []}

    def restore_file(self, root: Path, rel_path: str, commit_id: str) -> SnapshotResult:
        self.ensure_local_repo(root)
        self._run_git(root, ["checkout", commit_id, "--", rel_path])
        return self.snapshot(root, "restore_file", [rel_path], actor="user")

    def restore_project(self, root: Path, commit_id: str, paths: Iterable[str] | None = None) -> SnapshotResult:
        self.ensure_local_repo(root)
        target_paths = list(paths or [])
        if target_paths:
            self._run_git(root, ["checkout", commit_id, "--", *target_paths])
        else:
            self._run_git(root, ["checkout", commit_id, "--", "."])
        return self.snapshot(root, "restore_project", target_paths or ["."], actor="user")

    def undo(self, root: Path) -> tuple[SnapshotResult, str, str]:
        self.ensure_local_repo(root)
        head = self._head(root)
        parents = self._run_git(root, ["rev-list", "--parents", "-n", "1", head], capture=True).strip().split()
        if len(parents) <= 1:
            return SnapshotResult(operation_id=str(uuid.uuid4()), snapshot_id=None, snapshot_created=False), "noop", head
        op_id = str(uuid.uuid4())
        self._run_git(root, ["revert", "--no-edit", head])
        commit_id = self._head(root)
        self._append_operation(root, op_id, commit_id, "undo", ["."], "user", result="applied")
        return SnapshotResult(operation_id=op_id, snapshot_id=commit_id, snapshot_created=True), "revert_head", head

    def _append_operation(
        self,
        root: Path,
        operation_id: str,
        snapshot_id: str | None,
        action: str,
        paths: list[str],
        actor: str,
        result: str = "success",
        metadata: dict | None = None,
    ) -> None:
        meta_dir = root / self._meta_dir_name
        meta_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "operation_id": operation_id,
            "snapshot_id": snapshot_id,
            "action": action,
            "paths": paths,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
        if metadata:
            entry["metadata"] = metadata
        with open(meta_dir / self._operations_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def _has_changes(self, root: Path) -> bool:
        output = self._run_git(root, ["status", "--porcelain"], capture=True)
        return bool(output.strip())

    def has_workspace_changes(self, root: Path) -> bool:
        self.ensure_local_repo(root)
        return self._has_changes(root)

    def commit_exists(self, root: Path, commit_id: str) -> bool:
        self.ensure_local_repo(root)
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit_id}^{{commit}}"],
            cwd=str(root),
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def _head(self, root: Path) -> str:
        return self._run_git(root, ["rev-parse", "HEAD"], capture=True).strip()

    def _parse_log(self, output: str, rel_path: str | None = None) -> list[dict]:
        entries = []
        for row in output.splitlines():
            if not row.strip():
                continue
            parts = row.split("|", 2)
            if len(parts) != 3:
                continue
            commit, epoch, message = parts
            entries.append({
                "commit": commit,
                "timestamp": int(epoch),
                "message": message,
                "path": rel_path,
            })
        return entries

    def _run_git(self, root: Path, args: list[str], capture: bool = False) -> str:
        cmd = ["git", *args]
        result = subprocess.run(
            cmd,
            cwd=str(root),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git command failed: {' '.join(cmd)}")
        return result.stdout if capture else ""

    def _ensure_git_exclude(self, root: Path) -> None:
        exclude_path = root / ".git" / "info" / "exclude"
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if exclude_path.exists():
            existing = exclude_path.read_text(encoding="utf-8", errors="ignore")
        rule = ".nexus/history_operations.jsonl"
        if rule not in existing:
            with open(exclude_path, "a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(rule + "\n")


version_service = VersionService()
