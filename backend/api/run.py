import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.security import get_project_root, is_safe_path

router = APIRouter()


class RunRequest(BaseModel):
    path: str


class RunResponse(BaseModel):
    status: str
    path: str
    language: str
    command: List[str]
    cwd: str
    stdout: str
    stderr: str
    exit_code: int


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise HTTPException(status_code=400, detail=f"Required runtime not found: {name}")
    return executable


def _detect_command(file_path: Path) -> tuple[str, List[str], Path]:
    ext = file_path.suffix.lower()
    stem = file_path.stem
    parent = file_path.parent

    if ext == ".py":
        return "Python", [_tool("python"), str(file_path)], parent
    if ext in {".js", ".mjs", ".cjs"}:
        return "JavaScript", [_tool("node"), str(file_path)], parent
    if ext == ".ts":
        if shutil.which("tsx"):
            return "TypeScript", [_tool("tsx"), str(file_path)], parent
        if shutil.which("ts-node"):
            return "TypeScript", [_tool("ts-node"), str(file_path)], parent
        raise HTTPException(status_code=400, detail="TypeScript needs tsx or ts-node installed.")
    if ext == ".java":
        java = _tool("java")
        _tool("javac")
        return "Java", [java, str(file_path)], parent
    if ext in {".c", ".cpp", ".cc", ".cxx"}:
        compiler_name = "gcc" if ext == ".c" else "g++"
        compiler = _tool(compiler_name)
        temp_dir = Path(tempfile.mkdtemp(prefix="nexus-run-"))
        exe_path = temp_dir / (stem + (".exe" if os.name == "nt" else ""))
        return "C" if ext == ".c" else "C++", [compiler, str(file_path), "-o", str(exe_path), "&&", str(exe_path)], parent
    if ext == ".cs":
        compiler = shutil.which("csc")
        if not compiler:
            raise HTTPException(status_code=400, detail="C# execution needs csc installed.")
        temp_dir = Path(tempfile.mkdtemp(prefix="nexus-run-"))
        exe_path = temp_dir / (stem + (".exe" if os.name == "nt" else ""))
        return "C#", [compiler, f"/out:{exe_path}", str(file_path), "&&", str(exe_path)], parent
    if ext in {".sh", ".bash"}:
        return "Shell", [_tool("bash"), str(file_path)], parent
    if ext == ".ps1":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise HTTPException(status_code=400, detail="PowerShell runtime not found.")
        return "PowerShell", [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(file_path)], parent

    raise HTTPException(status_code=400, detail=f"No run configuration for {ext or 'this file type'}.")


def _run_compiled(command: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    split_at = command.index("&&")
    compile_command = command[:split_at]
    run_command = command[split_at + 1 :]
    temp_dir = Path(run_command[0]).parent

    try:
        compile_result = subprocess.run(
            compile_command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile_result.returncode != 0:
            return compile_result

        run_result = subprocess.run(
            run_command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return subprocess.CompletedProcess(
            command,
            run_result.returncode,
            compile_result.stdout + run_result.stdout,
            compile_result.stderr + run_result.stderr,
        )
    finally:
        if temp_dir.name.startswith("nexus-run-"):
            shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/run", response_model=RunResponse)
async def run_file(req: RunRequest):
    if not req.path or not req.path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")

    file_path = is_safe_path(get_project_root() / req.path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found or is a directory.")

    language, command, cwd = _detect_command(file_path)

    try:
        if "&&" in command:
            result = _run_compiled(command, cwd)
        else:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=30,
            )
    except subprocess.TimeoutExpired as exc:
        return RunResponse(
            status="timeout",
            path=req.path,
            language=language,
            command=command,
            cwd=str(cwd),
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + "\nProcess timed out after 30 seconds.",
            exit_code=-1,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Run failed: {exc}") from exc

    return RunResponse(
        status="success" if result.returncode == 0 else "error",
        path=req.path,
        language=language,
        command=command,
        cwd=str(cwd),
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )
