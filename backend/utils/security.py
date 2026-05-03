import os
from pathlib import Path
from fastapi import HTTPException

PROJECT_ROOT = Path.cwd().resolve()

def is_safe_path(path: Path) -> Path:
    """
    Resolves the path and verifies it is safely inside PROJECT_ROOT.
    Returns the resolved path if safe, otherwise raises an HTTPException.
    """
    try:
        resolved_path = path.resolve()
        if PROJECT_ROOT in resolved_path.parents or resolved_path == PROJECT_ROOT:
            return resolved_path
    except Exception:
        pass
    
    raise HTTPException(status_code=403, detail="Access denied: Path is outside project root.")
