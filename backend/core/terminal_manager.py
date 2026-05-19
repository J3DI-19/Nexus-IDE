import asyncio
import hashlib
import json
import os
import shlex
import signal
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from core.runtime_registry import runtime_registry
from utils.security import get_project_root, is_safe_path

try:
    import winpty
except ImportError:  # pragma: no cover - Windows dependency
    winpty = None


def _default_shell() -> str:
    if os.name == "nt":
        pwsh = shutil.which("pwsh")
        if pwsh:
            return f'"{pwsh}" -NoLogo -NoProfile'
        powershell = shutil.which("powershell")
        if powershell:
            return f'"{powershell}" -NoLogo -NoProfile'
        return "cmd"
    return os.environ.get("SHELL") or shutil.which("bash") or "sh"


def _quote(path: Path) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([str(path)])
    return shlex.quote(str(path))


def _quote_project_path(path: Path) -> str:
    root = get_project_root()
    try:
        rel = path.resolve().relative_to(root.resolve())
        if os.name == "nt":
            rel_win = str(rel).replace("/", "\\")
            return subprocess.list2cmdline([f".\\{rel_win}"])
        return shlex.quote(f"./{rel.as_posix()}")
    except Exception:
        return _quote(path)


def _ps_single_quote(path: Path) -> str:
    # PowerShell-safe literal string, preserving backslashes and spaces.
    return "'" + str(path).replace("'", "''") + "'"


def _workspace_runtime_dir() -> Path:
    return get_project_root() / "backend" / "runtimes"


def _runtime_executable(*parts: str) -> Optional[Path]:
    candidate = _workspace_runtime_dir().joinpath(*parts)
    return candidate if candidate.exists() else None


def _shell_command(*parts: str) -> Optional[str]:
    runtime = _runtime_executable(*parts)
    return _quote(runtime) if runtime else None


def _require_runtime(*parts: str, detail: str) -> str:
    runtime = _shell_command(*parts)
    if runtime:
        return runtime
    raise HTTPException(status_code=400, detail=detail)


def _run_compiled_command(compiler: str, source: Path, exe: Path, extra_flags: str = "", runtime_bin_dir: Optional[Path] = None) -> str:
    quoted_source = _quote(source)
    quoted_exe = _quote(exe)
    compile_cmd = f"{compiler} {quoted_source}{extra_flags} -o {quoted_exe}"
    if os.name == "nt":
        if runtime_bin_dir:
            quoted_bin = _ps_single_quote(runtime_bin_dir)
            return f"$env:PATH={quoted_bin} + ';' + $env:PATH; {compile_cmd}; if ($LASTEXITCODE -eq 0) {{ & {quoted_exe} }}"
        return f"{compile_cmd}; if ($LASTEXITCODE -eq 0) {{ & {quoted_exe} }}"
    return f"{compile_cmd} && {quoted_exe}"


def _collect_cpp_sources(primary: Path) -> list[Path]:
    exts = {".cpp", ".cc", ".cxx"}
    files = sorted(
        p for p in primary.parent.iterdir()
        if p.is_file() and p.suffix.lower() in exts
    )
    if primary not in files:
        files.insert(0, primary)
    return files


def _find_nearest_csproj(start: Path, root: Path) -> Optional[Path]:
    current = start.parent
    while True:
        matches = sorted(current.glob("*.csproj"))
        if matches:
            return matches[0]
        if current == root or current.parent == current:
            break
        current = current.parent
    return None


def _find_nearest_java_project_root(start: Path, root: Path) -> Path:
    current = start.parent
    while True:
        if (current / "pom.xml").exists() or (current / "build.gradle").exists() or (current / "build.gradle.kts").exists():
            return current
        if current == root or current.parent == current:
            return start.parent
        current = current.parent


def _runtime_version(executable: Path) -> Optional[str]:
    probes = [["--version"], ["-version"], ["/?"]]
    for args in probes:
        try:
            result = subprocess.run(
                [str(executable), *args],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            output = (result.stdout or result.stderr or "").strip().splitlines()
            if output:
                return output[0][:200]
        except Exception:
            continue
    return None


def _sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(2 * 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


def build_run_command(path: str) -> dict:
    file_path = is_safe_path((get_project_root() / path).resolve())
    ext = file_path.suffix.lower()
    quoted = _quote_project_path(file_path)
    provenance: dict = {
        "runtime": None,
        "source": "missing",
        "path": None,
        "version": None,
        "hash": None,
        "determinism": "unresolved",
        "working_directory": str(get_project_root()),
        "command": None,
        "run_mode": "direct",
    }

    def _set_runtime(key: str, bundled_relpath: str, detail: str):
        resolution = runtime_registry.resolve_with_metadata(key, bundled_relpath)
        if not resolution.path:
            raise HTTPException(status_code=400, detail=detail)
        provenance["runtime"] = key
        provenance["source"] = resolution.source
        provenance["path"] = str(resolution.path)
        provenance["determinism"] = resolution.determinism
        provenance["version"] = _runtime_version(resolution.path)
        provenance["hash"] = _sha256_file(resolution.path)
        return _quote_project_path(resolution.path), resolution.path

    if ext == ".py":
        python, _ = _set_runtime("python", "python/python.exe", "Python runtime is not available.")
        command = f"{python} {quoted}"
        provenance["command"] = command
        return {"command": command, "provenance": provenance}
    if ext in {".js", ".mjs", ".cjs"}:
        node, _ = _set_runtime("node", "node/node.exe", "Node runtime is not available.")
        command = f"{node} {quoted}"
        provenance["command"] = command
        return {"command": command, "provenance": provenance}
    if ext == ".ts":
        _, node_root = _set_runtime("node", "node/node.exe", "Node runtime is not available.")
        node_root_dir = node_root.parent
        if not (node_root_dir / "node_modules").exists() and (node_root_dir / "node-install").exists():
            node_root_dir = node_root_dir / "node-install"
        tsx = None
        if node_root_dir:
            tsx = _quote(node_root_dir / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx"))
        if not tsx or not Path(tsx.strip('"')).exists():
            tsx = None
        if tsx:
            command = f"{tsx} {quoted}"
            provenance["command"] = command
            return {"command": command, "provenance": provenance}
        ts_node = None
        if node_root_dir:
            ts_node = _quote(node_root_dir / "node_modules" / ".bin" / ("ts-node.cmd" if os.name == "nt" else "ts-node"))
        if not ts_node or not Path(ts_node.strip('"')).exists():
            ts_node = None
        if ts_node:
            command = f"{ts_node} {quoted}"
            provenance["command"] = command
            return {"command": command, "provenance": provenance}
        command = f"{_quote_project_path(node_root)} {quoted}"
        provenance["command"] = command
        provenance["run_mode"] = "node-direct"
        return {"command": command, "provenance": provenance}
    if ext == ".java":
        java, java_path = _set_runtime("java", "java/bin/java.exe", "Java runtime is not available.")
        javac_path = java_path.parent / ("javac.exe" if os.name == "nt" else "javac")
        if not javac_path.exists():
            raise HTTPException(status_code=400, detail="Java compiler (javac) is not available.")
        javac = _quote_project_path(javac_path)
        project_root = get_project_root()
        build_root = project_root / "backend" / ".nexus-java-runner"
        root_hash = hashlib.sha1(str(file_path.parent).encode("utf-8")).hexdigest()
        out_dir = build_root / root_hash
        out_dir.mkdir(parents=True, exist_ok=True)
        class_name = file_path.stem
        java_project_root = _find_nearest_java_project_root(file_path, project_root)
        if os.name == "nt":
            source = _quote(file_path)
            classpath = _quote(out_dir)
            path_bin = _ps_single_quote(java_path.parent)
            command = (
                f"$env:PATH={path_bin} + ';' + $env:PATH; "
                f"& {javac} -d {_quote(out_dir)} {source}; "
                f"if ($LASTEXITCODE -eq 0) {{ & {java} -cp {classpath} {class_name} }}"
            )
        else:
            command = f"{javac} -d {_quote(out_dir)} {_quote(file_path)} && {java} -cp {_quote(out_dir)} {class_name}"
        provenance["run_mode"] = "compile-run"
        provenance["working_directory"] = str(java_project_root)
        provenance["command"] = command
        return {"command": command, "provenance": provenance}
    if ext == ".c":
        exe = file_path.with_suffix(".exe" if os.name == "nt" else "")
        gcc, _ = _set_runtime("gcc", "gcc/bin/gcc.exe", "C compiler is not available.")
        command = _run_compiled_command(gcc, file_path, exe, runtime_bin_dir=Path(gcc.strip('"')).parent)
        provenance["command"] = command
        return {"command": command, "provenance": provenance}
    if ext in {".cpp", ".cc", ".cxx"}:
        exe = file_path.with_suffix(".exe" if os.name == "nt" else "")
        gpp, _ = _set_runtime("gpp", "gcc/bin/g++.exe", "C++ compiler is not available.")
        cpp_sources = _collect_cpp_sources(file_path)
        quoted_sources = " ".join(_quote(src) for src in cpp_sources)
        quoted_exe = _quote(exe)
        compile_cmd = f"{gpp} {quoted_sources} -o {quoted_exe}"
        runtime_bin = Path(gpp.strip('"')).parent
        if os.name == "nt":
            command = f"$env:PATH={_ps_single_quote(runtime_bin)} + ';' + $env:PATH; {compile_cmd}; if ($LASTEXITCODE -eq 0) {{ & {quoted_exe} }}"
        else:
            command = f"{compile_cmd} && {quoted_exe}"
        provenance["command"] = command
        return {"command": command, "provenance": provenance}
    if ext == ".cs":
        dotnet, _ = _set_runtime("dotnet", "dotnet/dotnet.exe", ".NET runtime is not available.")
        project_root = get_project_root()
        csproj = _find_nearest_csproj(file_path, project_root)
        if csproj:
            if os.name == "nt":
                runner_home = project_root / "backend" / ".nexus-cs-runner" / ".dotnet-home"
                nuget_packages = project_root / "backend" / ".nexus-cs-runner" / ".nuget-packages"
                nuget_config = project_root / "backend" / ".nexus-cs-runner" / "NuGet.Config"
                runner_home.mkdir(parents=True, exist_ok=True)
                nuget_packages.mkdir(parents=True, exist_ok=True)
                if not nuget_config.exists():
                    nuget_config.write_text(
                        "<configuration>\n  <packageSources>\n    <clear />\n    <add key=\"nuget.org\" value=\"https://api.nuget.org/v3/index.json\" />\n  </packageSources>\n</configuration>\n",
                        encoding="utf-8",
                    )
                command = (
                    f"$env:DOTNET_CLI_HOME={_ps_single_quote(runner_home)}; "
                    f"$env:NUGET_PACKAGES={_ps_single_quote(nuget_packages)}; "
                    f"$env:NUGET_CONFIG_FILE={_ps_single_quote(nuget_config)}; "
                    f"& {dotnet} run --project {_quote(csproj)}"
                )
            else:
                command = f"{dotnet} run --project {_quote(csproj)}"
            provenance["command"] = command
            provenance["run_mode"] = "project"
            return {"command": command, "provenance": provenance}

        runner_root = project_root / "backend" / ".nexus-cs-runner" / hashlib.sha1(str(file_path.parent).encode("utf-8")).hexdigest()
        runner_root.mkdir(parents=True, exist_ok=True)
        program_path = runner_root / "Program.cs"
        csproj_path = runner_root / "NexusRunner.csproj"
        program_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
        if not csproj_path.exists():
            csproj_path.write_text(
                "\n".join(
                    [
                        "<Project Sdk=\"Microsoft.NET.Sdk\">",
                        "  <PropertyGroup>",
                        "    <OutputType>Exe</OutputType>",
                        "    <TargetFramework>net9.0</TargetFramework>",
                        "    <ImplicitUsings>enable</ImplicitUsings>",
                        "    <Nullable>enable</Nullable>",
                        "  </PropertyGroup>",
                        "</Project>",
                    ]
                ),
                encoding="utf-8",
            )
        if os.name == "nt":
            runner_home = project_root / "backend" / ".nexus-cs-runner" / ".dotnet-home"
            nuget_packages = project_root / "backend" / ".nexus-cs-runner" / ".nuget-packages"
            nuget_config = project_root / "backend" / ".nexus-cs-runner" / "NuGet.Config"
            runner_home.mkdir(parents=True, exist_ok=True)
            nuget_packages.mkdir(parents=True, exist_ok=True)
            if not nuget_config.exists():
                nuget_config.write_text(
                    "<configuration>\n  <packageSources>\n    <clear />\n    <add key=\"nuget.org\" value=\"https://api.nuget.org/v3/index.json\" />\n  </packageSources>\n</configuration>\n",
                    encoding="utf-8",
                )
            command = (
                f"$env:DOTNET_CLI_HOME={_ps_single_quote(runner_home)}; "
                f"$env:NUGET_PACKAGES={_ps_single_quote(nuget_packages)}; "
                f"$env:NUGET_CONFIG_FILE={_ps_single_quote(nuget_config)}; "
                f"& {dotnet} run --project {_quote(csproj_path)}"
            )
        else:
            command = f"{dotnet} run --project {_quote(csproj_path)}"
        provenance["command"] = command
        provenance["run_mode"] = "single-file-runner"
        return {"command": command, "provenance": provenance}
    if ext in {".sh", ".bash"}:
        bash, _ = _set_runtime("bash", "bash/usr/bin/bash.exe", "Bash runtime is not available.")
        command = f"{bash} {quoted}"
        provenance["command"] = command
        return {"command": command, "provenance": provenance}
    if ext == ".ps1":
        powershell, _ = _set_runtime("powershell", "powershell/7/pwsh.exe", "PowerShell runtime is not available.")
        command = f"{powershell} -NoProfile -ExecutionPolicy Bypass -File {quoted}"
        provenance["command"] = command
        return {"command": command, "provenance": provenance}

    raise HTTPException(status_code=400, detail=f"No run configuration for {ext or 'this file type'}.")


class TerminalSession:
    def __init__(self, session_id: str, cwd: Path, shell: Optional[str] = None):
        if os.name == "nt" and winpty is None:
            raise HTTPException(status_code=500, detail="pywinpty is required for Windows terminal sessions.")

        self.id = session_id
        self.cwd = cwd
        self.shell = shell or _default_shell()
        self.clients: set[asyncio.Queue[str]] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.closed = False
        self._lock = threading.Lock()

        if os.name == "nt":
            self.process = winpty.PTY(cols=100, rows=30)
            self.process.spawn(
                self.shell,
                cwd=str(cwd),
            )
        else:
            from ptyprocess import PtyProcessUnicode

            self.process = PtyProcessUnicode.spawn([self.shell], cwd=str(cwd), dimensions=(30, 100))

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def _read_loop(self):
        while not self.closed and self.process.isalive():
            try:
                if os.name == "nt":
                    data = self.process.read(blocking=False)
                    if not data:
                        time.sleep(0.01)
                        continue
                else:
                    data = self.process.read(1024)
            except Exception:
                break

            if not data:
                continue

            if self.loop:
                for queue in list(self.clients):
                    self.loop.call_soon_threadsafe(queue.put_nowait, data)

        self.closed = True

    def write(self, data: str):
        with self._lock:
            if self.closed or not self.process.isalive():
                raise HTTPException(status_code=410, detail="Terminal session is closed.")
            self.process.write(data)

    def run(self, command: str):
        # Force a clean new line before dispatching command to avoid prompt/output overlap.
        self.write("\r\n" + command.rstrip() + "\r\n")

    def interrupt(self):
        with self._lock:
            if not self.closed and self.process.isalive():
                if os.name == "nt":
                    self.process.write("\x03")
                else:
                    self.process.sendintr()

    def resize(self, cols: int, rows: int):
        with self._lock:
            if not self.closed and self.process.isalive():
                if os.name == "nt":
                    self.process.set_size(cols, rows)
                else:
                    self.process.setwinsize(rows, cols)

    def kill(self):
        self.closed = True
        with self._lock:
            if self.process.isalive():
                if os.name == "nt":
                    try:
                        os.kill(self.process.pid, signal.SIGTERM)
                    except Exception:
                        pass
                    try:
                        self.process.cancel_io()
                    except Exception:
                        pass
                else:
                    self.process.terminate(force=True)


class TerminalManager:
    def __init__(self):
        self.sessions: Dict[str, TerminalSession] = {}

    def create(self, shell: Optional[str] = None) -> TerminalSession:
        session_id = uuid.uuid4().hex
        session = TerminalSession(session_id, get_project_root(), shell)
        self.sessions[session_id] = session
        return session

    def get(self, session_id: str) -> TerminalSession:
        session = self.sessions.get(session_id)
        if not session or session.closed:
            raise HTTPException(status_code=404, detail="Terminal session not found.")
        return session

    def kill(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if not session:
            return
        session.kill()

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        session = self.get(session_id)
        session.attach_loop(asyncio.get_running_loop())
        queue: asyncio.Queue[str] = asyncio.Queue()
        session.clients.add(queue)

        async def sender():
            try:
                while True:
                    await websocket.send_text(await queue.get())
            except WebSocketDisconnect:
                pass

        async def receiver():
            try:
                while True:
                    message = await websocket.receive_json()
                    kind = message.get("type")
                    if kind == "input":
                        session.write(message.get("data", ""))
                    elif kind == "resize":
                        session.resize(int(message.get("cols", 100)), int(message.get("rows", 30)))
            except WebSocketDisconnect:
                pass

        sender_task = asyncio.create_task(sender())
        receiver_task = asyncio.create_task(receiver())
        try:
            done, pending = await asyncio.wait(
                {sender_task, receiver_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.gather(*done, return_exceptions=True)
        finally:
            session.clients.discard(queue)


terminal_manager = TerminalManager()
