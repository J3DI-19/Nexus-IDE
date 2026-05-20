from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from core.file_manager import get_file_content, save_file_content, create_new_file, create_new_folder, rename_path, delete_path, move_path
from core.version_service import version_service
from utils.security import get_project_root
from utils.api_response import err, log_route_end, log_route_start, ok, request_id_from

router = APIRouter()

class SaveFileRequest(BaseModel):
    path: str
    content: str

class DiagnosticsRequest(BaseModel):
    path: str
    content: str
    version: int = 0

class CreatePathRequest(BaseModel):
    path: str

class RenameRequest(BaseModel):
    old_path: str
    new_path: str

class MoveRequest(BaseModel):
    source_path: str
    dest_path: str

class DeleteRequest(BaseModel):
    path: str

@router.get("/file")
async def read_file(path: str = Query(..., description="Relative path to file")):
    """Returns the content of a file."""
    content = get_file_content(path)
    return PlainTextResponse(content)

from context_engine.core.pipeline import pipeline

def _run_live_diagnostics(path: str, content: str, version: int = 0):
    diagnostics = pipeline.diagnostics.run_diagnostics(path, content)
    applied = pipeline.runtime.replace_diagnostics_for_file(path, diagnostics, version=version)
    return diagnostics, applied

@router.post("/file/save")
async def save_file(request: Request, req: SaveFileRequest):
    """Saves content to a file."""
    rid = request_id_from(request)
    started = log_route_start("/file/save", rid)
    try:
        save_file_content(req.path, req.content)
    
    # 2. Trigger Background Diagnostics (Linter-like behavior)
        try:
            _run_live_diagnostics(req.path, req.content)
        except Exception as e:
            print(f"[Diagnostics] Failed for {req.path}: {e}")

        snap = version_service.snapshot(get_project_root(), "save", [req.path], actor="user")
        payload = ok({
        "message": "File saved and diagnostics completed.",
        "operation_id": snap.operation_id,
        "snapshot_id": snap.snapshot_id,
        "snapshot_created": snap.snapshot_created,
        }, request_id=rid)
        log_route_end("/file/save", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/file/save", rid, started, False)
        return err("file_save_failed", "Failed to save file", details=str(e), request_id=rid)

@router.post("/file/diagnostics")
async def run_live_file_diagnostics(request: Request, req: DiagnosticsRequest):
    """Runs diagnostics against the unsaved editor buffer and updates runtime artifacts."""
    rid = request_id_from(request)
    started = log_route_start("/file/diagnostics", rid)
    try:
        diagnostics, applied = _run_live_diagnostics(req.path, req.content, version=req.version)
        payload = ok({
            "applied": applied,
            "version": req.version,
            "diagnostics": [artifact.dict() for artifact in diagnostics]
        }, request_id=rid)
        log_route_end("/file/diagnostics", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/file/diagnostics", rid, started, False)
        return err("file_diagnostics_failed", "Failed to run diagnostics", details=str(e), request_id=rid)

@router.post("/file/create")
async def create_file(request: Request, req: CreatePathRequest):
    """Creates a new empty file."""
    rid = request_id_from(request)
    started = log_route_start("/file/create", rid)
    try:
        create_new_file(req.path)
        snap = version_service.snapshot(get_project_root(), "create_file", [req.path], actor="user")
        payload = ok({"message": "File created.", "operation_id": snap.operation_id, "snapshot_id": snap.snapshot_id, "snapshot_created": snap.snapshot_created}, request_id=rid)
        log_route_end("/file/create", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/file/create", rid, started, False)
        return err("file_create_failed", "Failed to create file", details=str(e), request_id=rid)

@router.post("/folder/create")
async def create_folder(request: Request, req: CreatePathRequest):
    """Creates a new folder."""
    rid = request_id_from(request)
    started = log_route_start("/folder/create", rid)
    try:
        create_new_folder(req.path)
        snap = version_service.snapshot(get_project_root(), "create_folder", [req.path], actor="user")
        payload = ok({"message": "Folder created.", "operation_id": snap.operation_id, "snapshot_id": snap.snapshot_id, "snapshot_created": snap.snapshot_created}, request_id=rid)
        log_route_end("/folder/create", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/folder/create", rid, started, False)
        return err("folder_create_failed", "Failed to create folder", details=str(e), request_id=rid)

@router.post("/file/rename")
async def rename_file_or_folder(request: Request, req: RenameRequest):
    """Renames a file or folder."""
    rid = request_id_from(request)
    started = log_route_start("/file/rename", rid)
    try:
        rename_path(req.old_path, req.new_path)
        snap = version_service.snapshot(get_project_root(), "rename", [req.old_path, req.new_path], actor="user")
        payload = ok({"message": "Path renamed.", "operation_id": snap.operation_id, "snapshot_id": snap.snapshot_id, "snapshot_created": snap.snapshot_created}, request_id=rid)
        log_route_end("/file/rename", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/file/rename", rid, started, False)
        return err("file_rename_failed", "Failed to rename path", details=str(e), request_id=rid)

@router.post("/file/move")
async def move_file_or_folder(request: Request, req: MoveRequest):
    """Moves a file or folder to a new destination."""
    rid = request_id_from(request)
    started = log_route_start("/file/move", rid)
    try:
        move_path(req.source_path, req.dest_path)
        snap = version_service.snapshot(get_project_root(), "move", [req.source_path, req.dest_path], actor="user")
        payload = ok({"message": "Path moved.", "operation_id": snap.operation_id, "snapshot_id": snap.snapshot_id, "snapshot_created": snap.snapshot_created}, request_id=rid)
        log_route_end("/file/move", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/file/move", rid, started, False)
        return err("file_move_failed", "Failed to move path", details=str(e), request_id=rid)

@router.post("/file/delete")
async def delete_file_or_folder(request: Request, req: DeleteRequest):
    """Deletes a file or folder."""
    rid = request_id_from(request)
    started = log_route_start("/file/delete", rid)
    try:
        delete_path(req.path)
        snap = version_service.snapshot(get_project_root(), "delete", [req.path], actor="user")
        payload = ok({"message": "Path deleted.", "operation_id": snap.operation_id, "snapshot_id": snap.snapshot_id, "snapshot_created": snap.snapshot_created}, request_id=rid)
        log_route_end("/file/delete", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/file/delete", rid, started, False)
        return err("file_delete_failed", "Failed to delete path", details=str(e), request_id=rid)

