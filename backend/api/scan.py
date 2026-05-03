from fastapi import APIRouter, HTTPException
from core.scanner import fast_recursive_scan
from utils.security import PROJECT_ROOT

router = APIRouter()

@router.get("/scan")
async def scan_project():
    """Returns a list of all relevant files in the project."""
    try:
        files = fast_recursive_scan(str(PROJECT_ROOT))
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")
