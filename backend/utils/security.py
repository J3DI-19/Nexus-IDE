import os
from pathlib import Path
from fastapi import HTTPException

_PROJECT_ROOT = Path.cwd().resolve()

def get_project_root() -> Path:
    return _PROJECT_ROOT

def set_project_root(new_path: str):
    global _PROJECT_ROOT
    path = Path(new_path).resolve()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Invalid directory path")
    _PROJECT_ROOT = path

def is_safe_path(path: Path) -> Path:
    """
    Resolves the path and verifies it is safely inside PROJECT_ROOT.
    Returns the resolved path if safe, otherwise raises an HTTPException.
    """
    try:
        resolved_path = path.resolve()
        root = get_project_root()
        if root in resolved_path.parents or resolved_path == root:
            return resolved_path
    except Exception:
        pass
    
    raise HTTPException(status_code=403, detail="Access denied: Path is outside project root.")
