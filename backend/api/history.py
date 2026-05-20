from __future__ import annotations

from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.version_service import version_service
from utils.security import get_project_root
from utils.api_response import err, log_route_end, log_route_start, ok, request_id_from

router = APIRouter()


class RestoreFileRequest(BaseModel):
    path: str
    commit_id: str
    has_dirty_conflict: bool = False
    force: bool = False


class RestoreProjectRequest(BaseModel):
    commit_id: str
    paths: Optional[List[str]] = None

class RestorePreviewRequest(BaseModel):
    commit_id: str
    path: Optional[str] = None
    has_dirty_conflict: bool = False
    scope: str = "file"


@router.get("/history/file")
async def get_file_history(request: Request, path: str = Query(...), limit: int = Query(30)):
    rid = request_id_from(request)
    started = log_route_start("/history/file", rid)
    try:
        root = get_project_root()
        payload = ok({"entries": version_service.file_history(root, path, limit)}, request_id=rid)
        log_route_end("/history/file", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/file", rid, started, False)
        return err("history_file_failed", "Failed to fetch file history", details=str(e), request_id=rid)


@router.get("/history/project")
async def get_project_history(request: Request, limit: int = Query(50)):
    rid = request_id_from(request)
    started = log_route_start("/history/project", rid)
    try:
        root = get_project_root()
        payload = ok({"entries": version_service.project_history(root, limit)}, request_id=rid)
        log_route_end("/history/project", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/project", rid, started, False)
        return err("history_project_failed", "Failed to fetch project history", details=str(e), request_id=rid)


@router.get("/history/commit/{commit_id}")
async def get_commit_details(request: Request, commit_id: str):
    rid = request_id_from(request)
    started = log_route_start("/history/commit", rid)
    try:
        root = get_project_root()
        payload = ok(version_service.commit_details(root, commit_id), request_id=rid)
        log_route_end("/history/commit", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/commit", rid, started, False)
        return err("history_commit_failed", "Failed to fetch commit details", details=str(e), request_id=rid)


@router.post("/history/restore/file")
async def restore_file(request: Request, req: RestoreFileRequest):
    rid = request_id_from(request)
    started = log_route_start("/history/restore/file", rid)
    try:
        if req.has_dirty_conflict and not req.force:
            log_route_end("/history/restore/file", rid, started, False)
            return err("restore_conflict", "Restore blocked by conflicts", details={"conflicts": [{"path": req.path, "reason": "dirty_buffer"}]}, request_id=rid)
        root = get_project_root()
        result = version_service.restore_file(root, req.path, req.commit_id)
        payload = ok(result.__dict__, request_id=rid)
        log_route_end("/history/restore/file", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/restore/file", rid, started, False)
        return err("restore_file_failed", "Failed to restore file", details=str(e), request_id=rid)

@router.post("/history/restore/preview")
async def restore_preview(request: Request, req: RestorePreviewRequest):
    rid = request_id_from(request)
    started = log_route_start("/history/restore/preview", rid)
    try:
        root = get_project_root()
        if not version_service.commit_exists(root, req.commit_id):
            return ok({
                "commit_id": req.commit_id,
                "impacted_files": [],
                "conflicts": [{"path": req.path or ".", "reason": "commit_not_found"}],
                "can_apply": False,
            }, request_id=rid)
        details = version_service.commit_details(root, req.commit_id)
        raw_changes = details.get("changes", [])
        impacted_files = []
        for row in raw_changes:
            parts = row.split("\t", 1)
            if len(parts) == 2:
                impacted_files.append(parts[1])
        if req.path:
            impacted_files = [p for p in impacted_files if p == req.path]
        conflicts = []
        if req.scope == "file" and not req.path:
            conflicts.append({"path": ".", "reason": "restore_scope_mismatch"})
        if version_service.has_workspace_changes(root):
            conflicts.append({"path": ".", "reason": "workspace_diverged"})
        if req.path and not (root / req.path).exists():
            conflicts.append({"path": req.path, "reason": "missing_path"})
        if req.path and (root / req.path).exists() and not (root / req.path).is_file():
            conflicts.append({"path": req.path, "reason": "path_type_mismatch"})
        if req.has_dirty_conflict and req.path:
            conflicts.append({"path": req.path, "reason": "dirty_buffer"})
        payload = ok({
            "commit_id": req.commit_id,
            "impacted_files": impacted_files,
            "conflicts": conflicts,
            "can_apply": len(conflicts) == 0,
            "can_force_apply": any(c.get("reason") in {"dirty_buffer", "workspace_diverged"} for c in conflicts),
        }, request_id=rid)
        log_route_end("/history/restore/preview", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/restore/preview", rid, started, False)
        return err("restore_preview_failed", "Failed to generate restore preview", details=str(e), request_id=rid)


@router.post("/history/restore/project")
async def restore_project(request: Request, req: RestoreProjectRequest):
    rid = request_id_from(request)
    started = log_route_start("/history/restore/project", rid)
    try:
        root = get_project_root()
        result = version_service.restore_project(root, req.commit_id, req.paths)
        payload = ok(result.__dict__, request_id=rid)
        log_route_end("/history/restore/project", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/restore/project", rid, started, False)
        return err("restore_project_failed", "Failed to restore project scope", details=str(e), request_id=rid)


@router.post("/history/undo")
async def undo_latest(request: Request):
    rid = request_id_from(request)
    started = log_route_start("/history/undo", rid)
    try:
        root = get_project_root()
        result, undo_mode, undo_target = version_service.undo(root)
        payload = ok({**result.__dict__, "undo_mode": undo_mode, "undo_target": undo_target}, request_id=rid)
        log_route_end("/history/undo", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/history/undo", rid, started, False)
        return err("undo_failed", "Failed to undo latest operation", details=str(e), request_id=rid)
