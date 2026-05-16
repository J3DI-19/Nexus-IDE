from fastapi import HTTPException
from utils.security import is_safe_path, get_project_root
import shutil
import os

def get_file_content(path: str) -> str:
    """Returns the content of a file with robust reading and security checks."""
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")

    try:
        resolved_path = is_safe_path(get_project_root() / path)
        
        if not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="File not found or is a directory.")

        with open(resolved_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            content = f.read()
            
        return content
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read failed: {str(e)}")

def save_file_content(path: str, content: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")
    try:
        resolved_path = is_safe_path(get_project_root() / path)
        if not resolved_path.parent.exists():
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")

def create_new_file(path: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")
    try:
        resolved_path = is_safe_path(get_project_root() / path)
        if resolved_path.exists():
            raise HTTPException(status_code=400, detail="File already exists.")
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.touch(exist_ok=False)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create file failed: {str(e)}")

def create_new_folder(path: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")
    try:
        resolved_path = is_safe_path(get_project_root() / path)
        if resolved_path.exists():
            raise HTTPException(status_code=400, detail="Folder already exists.")
        resolved_path.mkdir(parents=True, exist_ok=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create folder failed: {str(e)}")

def rename_path(old_path: str, new_path: str) -> None:
    if not old_path or not old_path.strip() or not new_path or not new_path.strip():
        raise HTTPException(status_code=400, detail="Invalid paths provided.")
    try:
        resolved_old = is_safe_path(get_project_root() / old_path)
        resolved_new = is_safe_path(get_project_root() / new_path)
        
        if not resolved_old.exists():
            raise HTTPException(status_code=404, detail="Source path does not exist.")
        if resolved_new.exists():
            raise HTTPException(status_code=400, detail="Destination path already exists.")
            
        resolved_new.parent.mkdir(parents=True, exist_ok=True)
        resolved_old.rename(resolved_new)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rename failed: {str(e)}")

def move_path(source_path: str, dest_path: str) -> None:
    if not source_path or not source_path.strip() or not dest_path or not dest_path.strip():
        raise HTTPException(status_code=400, detail="Invalid paths provided.")
    try:
        root_path = get_project_root()
        resolved_src = is_safe_path(root_path / source_path)
        resolved_dest = is_safe_path(root_path / dest_path)

        if not resolved_src.exists():
            raise HTTPException(status_code=404, detail="Source path does not exist.")
        if resolved_dest.exists():
            raise HTTPException(status_code=400, detail="Destination path already exists.")

        # Prevent moving a directory into itself or its descendants
        # Convert to strings for robust prefix checking
        src_str = str(resolved_src.resolve())
        dest_str = str(resolved_dest.resolve())
        if dest_str.startswith(src_str + os.sep) or dest_str == src_str:
            raise HTTPException(status_code=400, detail="Cannot move a folder into itself.")

        resolved_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved_src), str(resolved_dest))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Move failed: {str(e)}")

def delete_path(path: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")
    try:
        resolved_path = is_safe_path(get_project_root() / path)
        if not resolved_path.exists():
            raise HTTPException(status_code=404, detail="Path does not exist.")
            
        if resolved_path.is_dir():
            shutil.rmtree(resolved_path)
        else:
            resolved_path.unlink()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
