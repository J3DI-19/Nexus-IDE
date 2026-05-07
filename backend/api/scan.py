from fastapi import APIRouter, HTTPException
from context_engine.core.scanner import fast_recursive_scan
from utils.security import get_project_root

router = APIRouter()

@router.get("/scan")
async def scan_project():
    """Returns a list of all relevant files in the project."""
    try:
        files = fast_recursive_scan(str(get_project_root()))
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")
