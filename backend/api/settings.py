from pydantic import BaseModel
from fastapi import APIRouter

from core.runtime_registry import RuntimeConfig, runtime_registry

router = APIRouter()


class RuntimeSettingsRequest(BaseModel):
    python: str | None = None
    node: str | None = None
    java: str | None = None
    gcc: str | None = None
    gpp: str | None = None
    dotnet: str | None = None
    bash: str | None = None
    powershell: str | None = None


@router.get("/settings/runtimes")
async def get_runtime_settings():
    return runtime_registry.load().__dict__


@router.post("/settings/runtimes")
async def update_runtime_settings(request: RuntimeSettingsRequest):
    runtime_registry.save(RuntimeConfig(**request.dict()))
    return {"status": "success", "message": "Runtime settings updated."}
