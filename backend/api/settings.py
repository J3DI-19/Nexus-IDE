from __future__ import annotations

import json
from pathlib import Path
import os
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter

from core.runtime_registry import RuntimeConfig, runtime_registry
from core.runtime_installer import runtime_installer
from utils.security import get_project_root

router = APIRouter()


class RuntimeSettingsRequest(BaseModel):
    python: Optional[str] = None
    node: Optional[str] = None
    java: Optional[str] = None
    gcc: Optional[str] = None
    gpp: Optional[str] = None
    dotnet: Optional[str] = None
    bash: Optional[str] = None
    powershell: Optional[str] = None


class RuntimeInstallRequest(BaseModel):
    runtimes: list[str] = []
    reinstall: bool = False


class PromptPreset(BaseModel):
    id: str
    name: str
    description: str
    template: str = ""
    isDefault: bool = False


class PromptSettingsRequest(BaseModel):
    selected_preset_id: str
    presets: list[PromptPreset]
    manual_file_add_enabled: bool = False
    allow_preset_change_in_preview: bool = True
    executor_response_format: str = "nexus_edits_v2"


def _prompt_settings_path() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "NexusIDE" / "config" / "prompt_settings.json"
    return Path.home() / ".nexuside" / "config" / "prompt_settings.json"


def _legacy_prompt_settings_paths() -> list[Path]:
    root = get_project_root()
    return [
        root / "backend" / "config" / "prompt_settings.json",
        root / "backend" / "backend" / "config" / "prompt_settings.json",
    ]


def _read_json_if_exists(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _default_prompt_settings() -> dict:
    return {
        "selected_preset_id": "default",
        "manual_file_add_enabled": False,
        "allow_preset_change_in_preview": True,
        "executor_response_format": "nexus_edits_v2",
        "presets": [
            {
                "id": "default",
                "name": "Nexus Default",
                "description": "Locked system template that ships with Nexus.",
                "template": "You are Nexus.\nGoal: {{goal}}\nMode: {{mode}}\nActive file: {{active_file}}\nUse selected context and produce a precise implementation plan and patch.",
                "isDefault": True,
            },
            {
                "id": "system-safe",
                "name": "System Safe",
                "description": "Compact, structured prompt for routine work.",
                "template": "Task: {{goal}}\nMode: {{mode}}\nUse the selected files as context.\nReturn concise actionable steps.",
                "isDefault": False,
            },
            {
                "id": "deep-debug",
                "name": "Deep Debug",
                "description": "Biases toward runtime and failure analysis.",
                "template": "Task: {{goal}}\nMode: {{mode}}\nFocus on runtime behavior, error chains, and deterministic execution risks first.",
                "isDefault": False,
            },
        ],
    }


def _default_preset() -> dict:
    return _default_prompt_settings()["presets"][0]


@router.get("/settings/runtimes")
async def get_runtime_settings():
    current = runtime_registry.load()
    mapping = {
        "python": "python/python.exe",
        "node": "node/node.exe",
        "java": "java/bin/java.exe",
        "gcc": "gcc/bin/gcc.exe",
        "gpp": "gcc/bin/g++.exe",
        "dotnet": "dotnet/dotnet.exe",
        "bash": "bash/usr/bin/bash.exe",
        "powershell": "powershell/pwsh.exe",
    }
    payload = current.__dict__.copy()
    changed = False
    for key, relpath in mapping.items():
        if payload.get(key):
            continue
        bundled = runtime_registry.bundle_root / relpath
        if bundled.exists():
            payload[key] = str(bundled)
            changed = True
    if changed:
        runtime_registry.save(RuntimeConfig(**payload))
    return payload


@router.post("/settings/runtimes")
async def update_runtime_settings(request: RuntimeSettingsRequest):
    runtime_registry.save(RuntimeConfig(**request.dict()))
    return {"status": "success", "message": "Runtime settings updated."}


@router.get("/settings/runtimes/diagnostics")
async def get_runtime_diagnostics():
    return runtime_registry.runtime_status()


@router.get("/settings/runtimes/catalog")
async def get_runtime_catalog():
    return runtime_installer.get_catalog()


@router.get("/settings/runtimes/preflight")
async def get_runtime_preflight():
    return runtime_installer.get_preflight()


@router.post("/settings/runtimes/install")
async def install_runtimes(request: RuntimeInstallRequest):
    job_id = runtime_installer.create_install_job(request.runtimes, reinstall=request.reinstall)
    return {"status": "accepted", "job_id": job_id}


@router.get("/settings/runtimes/install/{job_id}")
async def get_runtime_install_job(job_id: str):
    return runtime_installer.get_job(job_id)


@router.post("/settings/runtimes/update")
async def update_runtimes(request: RuntimeInstallRequest):
    job_id = runtime_installer.create_install_job(request.runtimes, reinstall=True)
    return {"status": "accepted", "job_id": job_id}


@router.get("/settings/prompts")
async def get_prompt_settings():
    path = _prompt_settings_path()
    if not path.exists():
        # One-time fallback for legacy workspace-local settings.
        for legacy_path in _legacy_prompt_settings_paths():
            legacy_data = _read_json_if_exists(legacy_path)
            if legacy_data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")
                break
        if not path.exists():
            return _default_prompt_settings()
    try:
        data = _read_json_if_exists(path)
        if not data:
            return _default_prompt_settings()
        presets = data.get("presets")
        selected = data.get("selected_preset_id", "default")
        if not isinstance(presets, list) or not presets:
            return _default_prompt_settings()
        return {
            "selected_preset_id": selected,
            "manual_file_add_enabled": bool(data.get("manual_file_add_enabled", False)),
            "allow_preset_change_in_preview": bool(data.get("allow_preset_change_in_preview", True)),
            "executor_response_format": str(data.get("executor_response_format", "nexus_edits_v2")),
            "presets": presets,
        }
    except Exception:
        return _default_prompt_settings()


@router.post("/settings/prompts")
async def update_prompt_settings(request: PromptSettingsRequest):
    if request.executor_response_format not in {"unified_diff", "nexus_edits_v2"}:
        return {"status": "error", "message": "Unsupported executor response format."}

    default_presets = [p for p in request.presets if p.isDefault]
    if len(default_presets) != 1 or default_presets[0].id != "default":
        return {"status": "error", "message": "Default preset must exist and stay locked."}
    locked_default = _default_preset()
    incoming_default = default_presets[0]
    if (
        incoming_default.name != locked_default["name"]
        or incoming_default.description != locked_default["description"]
        or incoming_default.template != locked_default["template"]
    ):
        return {"status": "error", "message": "Default preset content cannot be changed."}

    preset_ids_list = [p.id for p in request.presets]
    if len(set(preset_ids_list)) != len(preset_ids_list):
        return {"status": "error", "message": "Preset ids must be unique."}

    for preset in request.presets:
        if preset.id != "default" and preset.isDefault:
            return {"status": "error", "message": "Only the default preset can be marked as default."}

    preset_ids = {p.id for p in request.presets}
    if request.selected_preset_id not in preset_ids:
        return {"status": "error", "message": "Selected preset id must exist in presets."}

    path = _prompt_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "selected_preset_id": request.selected_preset_id,
        "manual_file_add_enabled": request.manual_file_add_enabled,
        "allow_preset_change_in_preview": request.allow_preset_change_in_preview,
        "executor_response_format": request.executor_response_format,
        "presets": [p.dict() for p in request.presets],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "success", "message": "Prompt settings updated."}
