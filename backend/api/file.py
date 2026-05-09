from fastapi import APIRouter, Query, Body
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from core.file_manager import get_file_content, save_file_content, create_new_file, create_new_folder, rename_path, delete_path, move_path

router = APIRouter()

class SaveFileRequest(BaseModel):
    path: str
    content: str

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

@router.post("/file/save")
async def save_file(req: SaveFileRequest):
    """Saves content to a file."""
    save_file_content(req.path, req.content)
    
    # 2. Trigger Background Diagnostics (Linter-like behavior)
    try:
        diagnostics = pipeline.diagnostics.run_diagnostics(req.path, req.content)
        for artifact in diagnostics:
            # Feed syntax errors into the runtime sink so the UI updates immediately
            pipeline.runtime._current_artifacts.insert(0, artifact)
            # Cap the buffer
            pipeline.runtime._current_artifacts = pipeline.runtime._current_artifacts[:10]
    except Exception as e:
        print(f"[Diagnostics] Failed for {req.path}: {e}")

    return {"status": "success", "message": "File saved and diagnostics completed."}

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

