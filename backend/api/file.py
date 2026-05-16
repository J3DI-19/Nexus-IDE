from fastapi import APIRouter, Query, Body
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from core.file_manager import get_file_content, save_file_content, create_new_file, create_new_folder, rename_path, delete_path, move_path

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
async def save_file(req: SaveFileRequest):
    """Saves content to a file."""
    save_file_content(req.path, req.content)
    
    # 2. Trigger Background Diagnostics (Linter-like behavior)
    try:
        _run_live_diagnostics(req.path, req.content)
    except Exception as e:
        print(f"[Diagnostics] Failed for {req.path}: {e}")

    return {"status": "success", "message": "File saved and diagnostics completed."}

@router.post("/file/diagnostics")
async def run_live_file_diagnostics(req: DiagnosticsRequest):
    """Runs diagnostics against the unsaved editor buffer and updates runtime artifacts."""
    try:
        diagnostics, applied = _run_live_diagnostics(req.path, req.content, version=req.version)
        return {
            "status": "success",
            "applied": applied,
            "version": req.version,
            "diagnostics": [artifact.dict() for artifact in diagnostics]
        }
    except Exception as e:
        print(f"[Diagnostics] Failed for {req.path}: {e}")
        return {"status": "error", "diagnostics": [], "message": str(e)}

@router.post("/file/create")
async def create_file(req: CreatePathRequest):
    """Creates a new empty file."""
    create_new_file(req.path)
    return {"status": "success", "message": "File created."}

@router.post("/folder/create")
async def create_folder(req: CreatePathRequest):
    """Creates a new folder."""
    create_new_folder(req.path)
    return {"status": "success", "message": "Folder created."}

@router.post("/file/rename")
async def rename_file_or_folder(req: RenameRequest):
    """Renames a file or folder."""
    rename_path(req.old_path, req.new_path)
    return {"status": "success", "message": "Path renamed."}

@router.post("/file/move")
async def move_file_or_folder(req: MoveRequest):
    """Moves a file or folder to a new destination."""
    move_path(req.source_path, req.dest_path)
    return {"status": "success", "message": "Path moved."}

@router.post("/file/delete")
async def delete_file_or_folder(req: DeleteRequest):
    """Deletes a file or folder."""
    delete_path(req.path)
    return {"status": "success", "message": "Path deleted."}

