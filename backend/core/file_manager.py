from fastapi import HTTPException
from utils.security import is_safe_path, PROJECT_ROOT

def get_file_content(path: str) -> str:
    """Returns the content of a file with robust reading and security checks."""
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")

    try:
        resolved_path = is_safe_path(PROJECT_ROOT / path)
        
        if not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="File not found or is a directory.")

        with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        return content
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read failed: {str(e)}")
