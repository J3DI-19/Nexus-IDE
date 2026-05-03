from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from core.file_manager import get_file_content

router = APIRouter()

@router.get("/file")
async def read_file(path: str = Query(..., description="Relative path to file")):
    """Returns the content of a file."""
    content = get_file_content(path)
    return PlainTextResponse(content)
